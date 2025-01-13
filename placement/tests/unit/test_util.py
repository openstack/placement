#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""Unit tests for the utility functions used by the placement API."""


import datetime
from unittest import mock

import fixtures
import microversion_parse
from oslo_middleware import request_id
from oslo_utils.fixture import uuidsentinel
from oslo_utils import timeutils
import testtools
import webob

import placement
from placement import context
from placement import lib as pl
from placement import microversion
from placement.objects import resource_class as rc_obj
from placement.objects import resource_provider as rp_obj
from placement.tests.unit import base
from placement import util
from placement.util import roundrobin


class TestCheckAccept(testtools.TestCase):
    """Confirm behavior of util.check_accept."""

    @staticmethod
    @util.check_accept('application/json', 'application/vnd.openstack')
    def handler(req):
        """Fake handler to test decorator."""
        return True

    def test_fail_no_match(self):
        req = webob.Request.blank('/')
        req.accept = 'text/plain'

        error = self.assertRaises(webob.exc.HTTPNotAcceptable,
                                  self.handler, req)
        self.assertEqual(
            'Only application/json, application/vnd.openstack is provided',
            str(error))

    def test_fail_complex_no_match(self):
        req = webob.Request.blank('/')
        req.accept = 'text/html;q=0.9,text/plain,application/vnd.aws;q=0.8'

        error = self.assertRaises(webob.exc.HTTPNotAcceptable,
                                  self.handler, req)
        self.assertEqual(
            'Only application/json, application/vnd.openstack is provided',
            str(error))

    def test_success_no_accept(self):
        req = webob.Request.blank('/')
        self.assertTrue(self.handler(req))

    def test_success_simple_match(self):
        req = webob.Request.blank('/')
        req.accept = 'application/json'
        self.assertTrue(self.handler(req))

    def test_success_complex_any_match(self):
        req = webob.Request.blank('/')
        req.accept = 'application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        self.assertTrue(self.handler(req))

    def test_success_complex_lower_quality_match(self):
        req = webob.Request.blank('/')
        req.accept = 'application/xml;q=0.9,application/vnd.openstack;q=0.8'
        self.assertTrue(self.handler(req))


class TestExtractJSON(testtools.TestCase):

    # Although the intent of this test class is not to test that
    # schemas work, we may as well use a real one to ensure that
    # behaviors are what we expect.
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "uuid": {"type": "string", "format": "uuid"}
        },
        "required": ["name"],
        "additionalProperties": False
    }

    def test_not_json(self):
        error = self.assertRaises(webob.exc.HTTPBadRequest,
                                  util.extract_json,
                                  'I am a string',
                                  self.schema)
        self.assertIn('Malformed JSON', str(error))

    def test_malformed_json(self):
        error = self.assertRaises(webob.exc.HTTPBadRequest,
                                  util.extract_json,
                                  '{"my bytes got left behind":}',
                                  self.schema)
        self.assertIn('Malformed JSON', str(error))

    def test_schema_mismatch(self):
        error = self.assertRaises(webob.exc.HTTPBadRequest,
                                  util.extract_json,
                                  '{"a": "b"}',
                                  self.schema)
        self.assertIn('JSON does not validate', str(error))

    def test_type_invalid(self):
        error = self.assertRaises(webob.exc.HTTPBadRequest,
                                  util.extract_json,
                                  '{"name": 1}',
                                  self.schema)
        self.assertIn('JSON does not validate', str(error))

    def test_format_checker(self):
        error = self.assertRaises(webob.exc.HTTPBadRequest,
                                  util.extract_json,
                                  '{"name": "hello", "uuid": "not a uuid"}',
                                  self.schema)
        self.assertIn('JSON does not validate', str(error))

    def test_no_additional_properties(self):
        error = self.assertRaises(webob.exc.HTTPBadRequest,
                                  util.extract_json,
                                  '{"name": "hello", "cow": "moo"}',
                                  self.schema)
        self.assertIn('JSON does not validate', str(error))

    def test_valid(self):
        data = util.extract_json(
            '{"name": "cow", '
            '"uuid": "%s"}' % uuidsentinel.rp_uuid,
            self.schema)
        self.assertEqual('cow', data['name'])
        self.assertEqual(uuidsentinel.rp_uuid, data['uuid'])


class QueryParamsSchemaTestCase(testtools.TestCase):

    def test_validate_request(self):
        schema = {
            'type': 'object',
            'properties': {
                'foo': {'type': 'string'}
            },
            'additionalProperties': False}
        req = webob.Request.blank('/test?foo=%88')
        error = self.assertRaises(webob.exc.HTTPBadRequest,
                                  util.validate_query_params,
                                  req, schema)
        self.assertIn('Invalid query string parameters', str(error))


class TestJSONErrorFormatter(testtools.TestCase):

    def setUp(self):
        super(TestJSONErrorFormatter, self).setUp()
        self.environ = {}
        # TODO(jaypipes): Remove this when we get more than a single version
        # in the placement API. The fact that we only had a single version was
        # masking a bug in the utils code.
        _versions = [
            '1.0',
            '1.1',
        ]
        self.useFixture(fixtures.MonkeyPatch('placement.microversion.VERSIONS',
                                             _versions))

    def test_status_to_int_code(self):
        body = ''
        status = '404 Not Found'
        title = ''

        result = util.json_error_formatter(
            body, status, title, self.environ)
        self.assertEqual(404, result['errors'][0]['status'])

    def test_strip_body_tags(self):
        body = '<h1>Big Error!</h1>'
        status = '400 Bad Request'
        title = ''

        result = util.json_error_formatter(
            body, status, title, self.environ)
        self.assertEqual('Big Error!', result['errors'][0]['detail'])

    def test_request_id_presence(self):
        body = ''
        status = '400 Bad Request'
        title = ''

        # no request id in environ, none in error
        result = util.json_error_formatter(
            body, status, title, self.environ)
        self.assertNotIn('request_id', result['errors'][0])

        # request id in environ, request id in error
        self.environ[request_id.ENV_REQUEST_ID] = 'stub-id'

        result = util.json_error_formatter(
            body, status, title, self.environ)
        self.assertEqual('stub-id', result['errors'][0]['request_id'])

    def test_microversion_406_handling(self):
        body = ''
        status = '400 Bad Request'
        title = ''

        # Not a 406, no version info required.
        result = util.json_error_formatter(
            body, status, title, self.environ)
        self.assertNotIn('max_version', result['errors'][0])
        self.assertNotIn('min_version', result['errors'][0])

        # A 406 but not because of microversions (microversion
        # parsing was successful), no version info
        # required.
        status = '406 Not Acceptable'
        version_obj = microversion_parse.parse_version_string('2.3')
        self.environ[microversion.MICROVERSION_ENVIRON] = version_obj

        result = util.json_error_formatter(
            body, status, title, self.environ)
        self.assertNotIn('max_version', result['errors'][0])
        self.assertNotIn('min_version', result['errors'][0])

        # Microversion parsing failed, status is 406, send version info.
        del self.environ[microversion.MICROVERSION_ENVIRON]

        result = util.json_error_formatter(
            body, status, title, self.environ)
        self.assertEqual(microversion.max_version_string(),
                         result['errors'][0]['max_version'])
        self.assertEqual(microversion.min_version_string(),
                         result['errors'][0]['min_version'])


class TestRequireContent(testtools.TestCase):
    """Confirm behavior of util.require_accept."""

    @staticmethod
    @util.require_content('application/json')
    def handler(req):
        """Fake handler to test decorator."""
        return True

    def test_fail_no_content_type(self):
        req = webob.Request.blank('/')

        error = self.assertRaises(webob.exc.HTTPUnsupportedMediaType,
                                  self.handler, req)
        self.assertEqual(
            'The media type None is not supported, use application/json',
            str(error))

    def test_fail_wrong_content_type(self):
        req = webob.Request.blank('/')
        req.content_type = 'text/plain'

        error = self.assertRaises(webob.exc.HTTPUnsupportedMediaType,
                                  self.handler, req)
        self.assertEqual(
            'The media type text/plain is not supported, use application/json',
            str(error))

    def test_success_content_type(self):
        req = webob.Request.blank('/')
        req.content_type = 'application/json'
        self.assertTrue(self.handler(req))


class TestPlacementURLs(base.ContextTestCase):

    def setUp(self):
        super(TestPlacementURLs, self).setUp()
        fake_context = context.RequestContext(
            user_id='fake', project_id='fake')
        self.resource_provider = rp_obj.ResourceProvider(
            fake_context,
            name=uuidsentinel.rp_name,
            uuid=uuidsentinel.rp_uuid)
        self.resource_class = rc_obj.ResourceClass(
            fake_context,
            name='CUSTOM_BAREMETAL_GOLD',
            id=1000)

    def test_resource_provider_url(self):
        environ = {}
        expected_url = '/resource_providers/%s' % uuidsentinel.rp_uuid
        self.assertEqual(expected_url, util.resource_provider_url(
            environ, self.resource_provider))

    def test_resource_provider_url_prefix(self):
        # SCRIPT_NAME represents the mount point of a WSGI
        # application when it is hosted at a path/prefix.
        environ = {'SCRIPT_NAME': '/placement'}
        expected_url = ('/placement/resource_providers/%s'
                        % uuidsentinel.rp_uuid)
        self.assertEqual(expected_url, util.resource_provider_url(
            environ, self.resource_provider))

    def test_inventories_url(self):
        environ = {}
        expected_url = ('/resource_providers/%s/inventories'
                        % uuidsentinel.rp_uuid)
        self.assertEqual(expected_url, util.inventory_url(
            environ, self.resource_provider))

    def test_inventory_url(self):
        resource_class = 'DISK_GB'
        environ = {}
        expected_url = ('/resource_providers/%s/inventories/%s'
                        % (uuidsentinel.rp_uuid, resource_class))
        self.assertEqual(expected_url, util.inventory_url(
            environ, self.resource_provider, resource_class))

    def test_resource_class_url(self):
        environ = {}
        expected_url = '/resource_classes/CUSTOM_BAREMETAL_GOLD'
        self.assertEqual(expected_url, util.resource_class_url(
            environ, self.resource_class))

    def test_resource_class_url_prefix(self):
        # SCRIPT_NAME represents the mount point of a WSGI
        # application when it is hosted at a path/prefix.
        environ = {'SCRIPT_NAME': '/placement'}
        expected_url = '/placement/resource_classes/CUSTOM_BAREMETAL_GOLD'
        self.assertEqual(expected_url, util.resource_class_url(
            environ, self.resource_class))


class TestNormalizeResourceQsParam(testtools.TestCase):

    def test_success(self):
        qs = "VCPU:1"
        resources = util.normalize_resources_qs_param(qs)
        expected = {
            'VCPU': 1,
        }
        self.assertEqual(expected, resources)

        qs = "VCPU:1,MEMORY_MB:1024,DISK_GB:100"
        resources = util.normalize_resources_qs_param(qs)
        expected = {
            'VCPU': 1,
            'MEMORY_MB': 1024,
            'DISK_GB': 100,
        }
        self.assertEqual(expected, resources)

    def test_400_empty_string(self):
        qs = ""
        self.assertRaises(
            webob.exc.HTTPBadRequest,
            util.normalize_resources_qs_param,
            qs,
        )

    def test_400_bad_int(self):
        qs = "VCPU:foo"
        self.assertRaises(
            webob.exc.HTTPBadRequest,
            util.normalize_resources_qs_param,
            qs,
        )

    def test_400_no_amount(self):
        qs = "VCPU"
        self.assertRaises(
            webob.exc.HTTPBadRequest,
            util.normalize_resources_qs_param,
            qs,
        )

    def test_400_zero_amount(self):
        qs = "VCPU:0"
        self.assertRaises(
            webob.exc.HTTPBadRequest,
            util.normalize_resources_qs_param,
            qs,
        )


class TestNormalizeTraitsQsParamLegacy(testtools.TestCase):

    def test_one(self):
        trait = 'HW_CPU_X86_VMX'
        # Various whitespace permutations
        for fmt in ('%s', ' %s', '%s ', ' %s ', '  %s  '):
            self.assertEqual(
                set([trait]),
                util.normalize_traits_qs_param_to_legacy_value(fmt % trait)
            )

    def test_multiple(self):
        traits = (
            'HW_CPU_X86_VMX',
            'HW_GPU_API_DIRECT3D_V12_0',
            'HW_NIC_OFFLOAD_RX',
            'CUSTOM_GOLD',
            'STORAGE_DISK_SSD',
        )
        self.assertEqual(
            set(traits),
            util.normalize_traits_qs_param_to_legacy_value(
                '%s, %s,%s , %s ,  %s  ' % traits)
        )

    def test_400_all_empty(self):
        for qs in ('', ' ', '   ', ',', ' , , '):
            self.assertRaises(
                webob.exc.HTTPBadRequest,
                util.normalize_traits_qs_param_to_legacy_value, qs)

    def test_400_some_empty(self):
        traits = (
            'HW_NIC_OFFLOAD_RX',
            'CUSTOM_GOLD',
            'STORAGE_DISK_SSD',
        )
        for fmt in ('%s,,%s,%s', ',%s,%s,%s', '%s,%s,%s,', ' %s , %s ,  , %s'):
            self.assertRaises(
                webob.exc.HTTPBadRequest,
                util.normalize_traits_qs_param_to_legacy_value, fmt % traits)


class TestNormalizeTraitsQsParam(testtools.TestCase):

    def test_one(self):
        trait = 'HW_CPU_X86_VMX'
        # Various whitespace permutations
        for fmt in ('%s', ' %s', '%s ', ' %s ', '  %s  '):
            self.assertEqual(
                ([{trait}], set()),
                util.normalize_traits_qs_param(fmt % trait)
            )

    def test_multiple(self):
        traits = (
            'HW_CPU_X86_VMX',
            'HW_GPU_API_DIRECT3D_V12_0',
            'HW_NIC_OFFLOAD_RX',
            'CUSTOM_GOLD',
            'STORAGE_DISK_SSD',
        )
        self.assertEqual(
            ([{trait} for trait in traits], set()),
            util.normalize_traits_qs_param(
                '%s, %s,%s , %s ,  %s  ' % traits)
        )

    def test_400_all_empty(self):
        for qs in ('', ' ', '   ', ',', ' , , '):
            self.assertRaises(
                webob.exc.HTTPBadRequest,
                util.normalize_traits_qs_param, qs)

    def test_400_some_empty(self):
        traits = (
            'HW_NIC_OFFLOAD_RX',
            'CUSTOM_GOLD',
            'STORAGE_DISK_SSD',
        )
        for fmt in (
            '%s,,%s,%s',
            ',%s,%s,%s',
            '%s,%s,%s,',
            ' %s , %s ,  , %s',
            '!,%s,%s,%s',
        ):
            self.assertRaises(
                webob.exc.HTTPBadRequest,
                util.normalize_traits_qs_param,
                fmt % traits,
                allow_forbidden=True,
            )

    def test_multiple_with_forbidden(self):
        traits = (
            '!HW_CPU_X86_VMX',
            'HW_GPU_API_DIRECT3D_V12_0',
            '!HW_NIC_OFFLOAD_RX',
            'CUSTOM_GOLD',
            '!STORAGE_DISK_SSD',
        )

        self.assertRaises(
            webob.exc.HTTPBadRequest,
            util.normalize_traits_qs_param,
            '%s, %s,%s , %s ,  %s  ' % traits,
            allow_forbidden=False)

        self.assertEqual(
            (
                [{'HW_GPU_API_DIRECT3D_V12_0'}, {'CUSTOM_GOLD'}],
                {'HW_CPU_X86_VMX', 'HW_NIC_OFFLOAD_RX', 'STORAGE_DISK_SSD'}),
            util.normalize_traits_qs_param(
                '%s, %s,%s , %s ,  %s  ' % traits, allow_forbidden=True)
        )

    def test_any_traits(self):
        param = 'in:T1 ,T2 , T3'
        self.assertRaises(
            webob.exc.HTTPBadRequest,
            util.normalize_traits_qs_param,
            param,
            allow_any_traits=False
        )
        self.assertEqual(
            ([{'T1', 'T2', 'T3'}], set()),
            util.normalize_traits_qs_param(param, allow_any_traits=True)
        )

    def test_any_traits_not_mix_with_forbidden(self):
        param = 'in:T1 ,!T2 , T3'
        self.assertRaises(
            webob.exc.HTTPBadRequest,
            util.normalize_traits_qs_param,
            param,
            allow_forbidden=True,
            allow_any_traits=True,
        )


class TestNormalizeTraitsQsParams(testtools.TestCase):
    @staticmethod
    def _get_req(qstring, version):
        req = webob.Request.blank(
            '?' + qstring,
        )
        mv_parsed = microversion_parse.Version(*version)
        mv_parsed.max_version = microversion_parse.parse_version_string(
            microversion.max_version_string()
        )
        mv_parsed.min_version = microversion_parse.parse_version_string(
            microversion.min_version_string()
        )
        req.environ[placement.microversion.MICROVERSION_ENVIRON] = mv_parsed
        return req

    def test_suffix(self):
        req = self._get_req('required=!BAZ&requiredX=FOO,BAR', (1, 38))

        required, forbidden = util.normalize_traits_qs_params(req, suffix='')

        self.assertEqual([], required)
        self.assertEqual({'BAZ'}, forbidden)

        required, forbidden = util.normalize_traits_qs_params(req, suffix='X')

        self.assertEqual([{'FOO'}, {'BAR'}], required)
        self.assertEqual(set(), forbidden)

    def test_allow_forbidden_1_21(self):
        req = self._get_req('required=!BAZ', (1, 21))

        ex = self.assertRaises(
            webob.exc.HTTPBadRequest,
            util.normalize_traits_qs_params,
            req,
            suffix='',
        )

        self.assertIn(
            "Invalid query string parameters: Expected 'required' parameter "
            "value of the form: HW_CPU_X86_VMX,CUSTOM_MAGIC. Got: !BAZ",
            str(ex),
        )

    def test_allow_forbidden_1_22(self):
        req = self._get_req('required=!BAZ', (1, 22))

        required, forbidden = util.normalize_traits_qs_params(req, suffix='')

        self.assertEqual([], required)
        self.assertEqual({'BAZ'}, forbidden)

    def test_repeated_param_1_38(self):
        req = self._get_req('required=FOO,!BAR&required=BAZ', (1, 38))

        required, forbidden = util.normalize_traits_qs_params(req, suffix='')

        self.assertEqual([{'BAZ'}], required)
        self.assertEqual(set(), forbidden)

    def test_allow_any_traits_1_38(self):
        req = self._get_req('required=in:FOO,BAZ', (1, 38))

        ex = self.assertRaises(
            webob.exc.HTTPBadRequest,
            util.normalize_traits_qs_params,
            req,
            suffix='',
        )

        self.assertIn(
            "Invalid query string parameters: "
            "The format 'in:HW_CPU_X86_VMX,CUSTOM_MAGIC' only supported "
            "since microversion 1.39. Got: in:FOO,BAZ",
            str(ex),
        )

    def test_allow_any_traits_1_39(self):
        req = self._get_req('required=in:FOO,BAZ', (1, 39))

        required, forbidden = util.normalize_traits_qs_params(req, suffix='')

        self.assertEqual([{'FOO', 'BAZ'}], required)
        self.assertEqual(set(), forbidden)

    def test_repeated_param_1_39(self):
        req = self._get_req(
            'required=in:T1,T2'
            '&required=T3,!T4'
            '&required=in:T5,T6'
            '&required=!T7,T8',
            (1, 39)
        )

        required, forbidden = util.normalize_traits_qs_params(req, suffix='')

        self.assertEqual(
            [{'T1', 'T2'}, {'T3'}, {'T5', 'T6'}, {'T8'}],
            required)
        self.assertEqual({'T4', 'T7'}, forbidden)


class TestParseQsRequestGroups(testtools.TestCase):

    @staticmethod
    def do_parse(qstring, version=(1, 18)):
        """Converts a querystring to a MultiDict, mimicking request.GET, and
        runs dict_from_request on it.
        """
        req = webob.Request.blank('?' + qstring)
        mv_parsed = microversion_parse.Version(*version)
        mv_parsed.max_version = microversion_parse.parse_version_string(
            microversion.max_version_string())
        mv_parsed.min_version = microversion_parse.parse_version_string(
            microversion.min_version_string())
        req.environ['placement.microversion'] = mv_parsed
        rqparam = pl.RequestWideParams.from_request(req)
        d = pl.RequestGroup.dict_from_request(req, rqparam)
        # Sort for easier testing
        return [d[suff] for suff in sorted(d)]

    def assertRequestGroupsEqual(self, expected, observed):
        self.assertEqual(len(expected), len(observed))
        for exp, obs in zip(expected, observed):
            self.assertEqual(vars(exp), vars(obs))

    def test_empty_raises(self):
        # TODO(efried): Check the specific error code
        self.assertRaises(webob.exc.HTTPBadRequest, self.do_parse, '')

    def test_unnumbered_only(self):
        """Unnumbered resources & traits - no numbered groupings."""
        qs = ('resources=VCPU:2,MEMORY_MB:2048'
              '&required=HW_CPU_X86_VMX,CUSTOM_GOLD')
        expected = [
            pl.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'MEMORY_MB': 2048,
                },
                required_traits=[
                    {'HW_CPU_X86_VMX'}, {'CUSTOM_GOLD'}
                ],
            ),
        ]
        self.assertRequestGroupsEqual(expected, self.do_parse(qs))

    def test_member_of_single_agg(self):
        """Unnumbered resources with one member_of query param."""
        agg1_uuid = uuidsentinel.agg1
        qs = ('resources=VCPU:2,MEMORY_MB:2048'
              '&member_of=%s' % agg1_uuid)
        expected = [
            pl.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'MEMORY_MB': 2048,
                },
                member_of=[
                    set([agg1_uuid])
                ]
            ),
        ]
        self.assertRequestGroupsEqual(expected, self.do_parse(qs))

    def test_member_of_multiple_aggs_prior_microversion(self):
        """Unnumbered resources with multiple member_of query params before the
        supported microversion should raise a 400.
        """
        agg1_uuid = uuidsentinel.agg1
        agg2_uuid = uuidsentinel.agg2
        qs = ('resources=VCPU:2,MEMORY_MB:2048'
              '&member_of=%s'
              '&member_of=%s' % (agg1_uuid, agg2_uuid))
        self.assertRaises(webob.exc.HTTPBadRequest, self.do_parse, qs)

    def test_member_of_multiple_aggs(self):
        """Unnumbered resources with multiple member_of query params."""
        agg1_uuid = uuidsentinel.agg1
        agg2_uuid = uuidsentinel.agg2
        qs = ('resources=VCPU:2,MEMORY_MB:2048'
              '&member_of=%s'
              '&member_of=%s' % (agg1_uuid, agg2_uuid))
        expected = [
            pl.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'MEMORY_MB': 2048,
                },
                member_of=[
                    set([agg1_uuid]),
                    set([agg2_uuid])
                ]
            ),
        ]
        self.assertRequestGroupsEqual(
            expected, self.do_parse(qs, version=(1, 24)))

    def test_unnumbered_resources_only(self):
        """Validate the bit that can be used for 1.10 and earlier."""
        qs = 'resources=VCPU:2,MEMORY_MB:2048,DISK_GB:5,CUSTOM_MAGIC:123'
        expected = [
            pl.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'MEMORY_MB': 2048,
                    'DISK_GB': 5,
                    'CUSTOM_MAGIC': 123,
                },
            ),
        ]
        self.assertRequestGroupsEqual(expected, self.do_parse(qs))

    def test_numbered_only(self):
        # Crazy ordering and nonsequential numbers don't matter.
        # It's okay to have a 'resources' without a 'required'.
        # A trait that's repeated shows up in both spots.
        qs = ('resources1=VCPU:2,MEMORY_MB:2048'
              '&required42=CUSTOM_GOLD'
              '&resources99=DISK_GB:5'
              '&resources42=CUSTOM_MAGIC:123'
              '&required1=HW_CPU_X86_VMX,CUSTOM_GOLD')
        expected = [
            pl.RequestGroup(
                resources={
                    'VCPU': 2,
                    'MEMORY_MB': 2048,
                },
                required_traits=[
                    {'HW_CPU_X86_VMX'}, {'CUSTOM_GOLD'}
                ],
            ),
            pl.RequestGroup(
                resources={
                    'CUSTOM_MAGIC': 123,
                },
                required_traits=[
                    {'CUSTOM_GOLD'}
                ],
            ),
            pl.RequestGroup(
                resources={
                    'DISK_GB': 5,
                },
            ),
        ]
        self.assertRequestGroupsEqual(expected, self.do_parse(qs))

    def test_numbered_and_unnumbered(self):
        qs = ('resources=VCPU:3,MEMORY_MB:4096,DISK_GB:10'
              '&required=HW_CPU_X86_VMX,CUSTOM_MEM_FLASH,STORAGE_DISK_SSD'
              '&resources1=SRIOV_NET_VF:2'
              '&required1=CUSTOM_PHYSNET_PRIVATE'
              '&resources2=SRIOV_NET_VF:1,NET_INGRESS_BYTES_SEC:20000'
              ',NET_EGRESS_BYTES_SEC:10000'
              '&required2=CUSTOM_SWITCH_BIG,CUSTOM_PHYSNET_PROD'
              '&resources3=CUSTOM_MAGIC:123')
        expected = [
            pl.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 3,
                    'MEMORY_MB': 4096,
                    'DISK_GB': 10,
                },
                required_traits=[
                    {'HW_CPU_X86_VMX'},
                    {'CUSTOM_MEM_FLASH'},
                    {'STORAGE_DISK_SSD'}
                ],
            ),
            pl.RequestGroup(
                resources={
                    'SRIOV_NET_VF': 2,
                },
                required_traits=[
                    {'CUSTOM_PHYSNET_PRIVATE'},
                ],
            ),
            pl.RequestGroup(
                resources={
                    'SRIOV_NET_VF': 1,
                    'NET_INGRESS_BYTES_SEC': 20000,
                    'NET_EGRESS_BYTES_SEC': 10000,
                },
                required_traits=[
                    {'CUSTOM_SWITCH_BIG'},
                    {'CUSTOM_PHYSNET_PROD'},
                ],
            ),
            pl.RequestGroup(
                resources={
                    'CUSTOM_MAGIC': 123,
                },
            ),
        ]
        self.assertRequestGroupsEqual(expected, self.do_parse(qs))

    def test_member_of_multiple_aggs_numbered(self):
        """Numbered resources with multiple member_of query params."""
        agg1_uuid = uuidsentinel.agg1
        agg2_uuid = uuidsentinel.agg2
        agg3_uuid = uuidsentinel.agg3
        agg4_uuid = uuidsentinel.agg4
        qs = ('resources1=VCPU:2'
              '&member_of1=%s'
              '&member_of1=%s'
              '&resources2=VCPU:2'
              '&member_of2=in:%s,%s' % (
                  agg1_uuid, agg2_uuid, agg3_uuid, agg4_uuid))
        expected = [
            pl.RequestGroup(
                resources={
                    'VCPU': 2,
                },
                member_of=[
                    set([agg1_uuid]),
                    set([agg2_uuid])
                ]
            ),
            pl.RequestGroup(
                resources={
                    'VCPU': 2,
                },
                member_of=[
                    set([agg3_uuid, agg4_uuid]),
                ]
            ),
        ]
        self.assertRequestGroupsEqual(
            expected, self.do_parse(qs, version=(1, 24)))

    def test_member_of_forbidden_aggs(self):
        agg1_uuid = uuidsentinel.agg1
        agg2_uuid = uuidsentinel.agg2
        agg3_uuid = uuidsentinel.agg3
        agg4_uuid = uuidsentinel.agg4
        qs = ('resources=VCPU:2'
              '&member_of=%s'
              '&member_of=%s'
              '&member_of=!%s'
              '&member_of=!%s' % (
                  agg1_uuid, agg2_uuid, agg3_uuid, agg4_uuid))
        expected = [
            pl.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                },
                member_of=[
                    set([agg1_uuid]),
                    set([agg2_uuid]),
                ],
                forbidden_aggs=set(
                    [agg3_uuid, agg4_uuid]
                ),
            ),
        ]
        self.assertRequestGroupsEqual(
            expected, self.do_parse(qs, version=(1, 32)))

    def test_member_of_multiple_forbidden_aggs(self):
        agg1_uuid = uuidsentinel.agg1
        agg2_uuid = uuidsentinel.agg2
        agg3_uuid = uuidsentinel.agg3
        qs = ('resources=VCPU:2'
              '&member_of=!in:%s,%s,%s' % (
                  agg1_uuid, agg2_uuid, agg3_uuid))
        expected = [
            pl.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                },
                forbidden_aggs=set(
                    [agg1_uuid, agg2_uuid, agg3_uuid]
                ),
            ),
        ]
        self.assertRequestGroupsEqual(
            expected, self.do_parse(qs, version=(1, 32)))

    def test_member_of_forbidden_aggs_prior_microversion(self):
        agg1_uuid = uuidsentinel.agg1
        agg2_uuid = uuidsentinel.agg2
        qs = ('resources=VCPU:2'
              '&member_of=!%s'
              '&member_of=!%s' % (agg1_uuid, agg2_uuid))
        self.assertRaises(
            webob.exc.HTTPBadRequest, self.do_parse, qs, version=(1, 31))

        qs = ('resources=VCPU:2'
              '&member_of=!in:%s,%s' % (agg1_uuid, agg2_uuid))
        self.assertRaises(
            webob.exc.HTTPBadRequest, self.do_parse, qs, version=(1, 31))

    def test_member_of_forbidden_aggs_invalid_usage(self):
        agg1_uuid = uuidsentinel.agg1
        agg2_uuid = uuidsentinel.agg2
        qs = ('resources=VCPU:2'
              '&member_of=in:%s,!%s' % (agg1_uuid, agg2_uuid))
        self.assertRaises(
            webob.exc.HTTPBadRequest, self.do_parse, qs, version=(1, 32))

        agg1_uuid = uuidsentinel.agg1
        agg2_uuid = uuidsentinel.agg2
        qs = ('resources=VCPU:2'
              '&member_of=!%s,!%s' % (agg1_uuid, agg2_uuid))
        self.assertRaises(
            webob.exc.HTTPBadRequest, self.do_parse, qs, version=(1, 32))

    def test_400_malformed_resources(self):
        # Somewhat duplicates TestNormalizeResourceQsParam.test_400*.
        qs = ('resources=VCPU:0,MEMORY_MB:4096,DISK_GB:10'
              # Bad ----------^
              '&required=HW_CPU_X86_VMX,CUSTOM_MEM_FLASH,STORAGE_DISK_SSD'
              '&resources1=SRIOV_NET_VF:2'
              '&required1=CUSTOM_PHYSNET_PRIVATE'
              '&resources2=SRIOV_NET_VF:1,NET_INGRESS_BYTES_SEC:20000'
              ',NET_EGRESS_BYTES_SEC:10000'
              '&required2=CUSTOM_SWITCH_BIG,CUSTOM_PHYSNET_PROD'
              '&resources3=CUSTOM_MAGIC:123')
        self.assertRaises(webob.exc.HTTPBadRequest, self.do_parse, qs)

    def test_400_malformed_traits(self):
        # Somewhat duplicates TestNormalizeResourceQsParam.test_400*.
        qs = ('resources=VCPU:7,MEMORY_MB:4096,DISK_GB:10'
              '&required=HW_CPU_X86_VMX,CUSTOM_MEM_FLASH,STORAGE_DISK_SSD'
              '&resources1=SRIOV_NET_VF:2'
              '&required1=CUSTOM_PHYSNET_PRIVATE'
              '&resources2=SRIOV_NET_VF:1,NET_INGRESS_BYTES_SEC:20000'
              ',NET_EGRESS_BYTES_SEC:10000'
              '&required2=CUSTOM_SWITCH_BIG,CUSTOM_PHYSNET_PROD,'
              # Bad -------------------------------------------^
              '&resources3=CUSTOM_MAGIC:123')
        self.assertRaises(webob.exc.HTTPBadRequest, self.do_parse, qs)

    def test_400_traits_no_resources_unnumbered(self):
        qs = ('resources9=VCPU:7,MEMORY_MB:4096,DISK_GB:10'
              # Oops ---^
              '&required=HW_CPU_X86_VMX,CUSTOM_MEM_FLASH,STORAGE_DISK_SSD'
              '&resources1=SRIOV_NET_VF:2'
              '&required1=CUSTOM_PHYSNET_PRIVATE'
              '&resources2=SRIOV_NET_VF:1,NET_INGRESS_BYTES_SEC:20000'
              ',NET_EGRESS_BYTES_SEC:10000'
              '&required2=CUSTOM_SWITCH_BIG,CUSTOM_PHYSNET_PROD'
              '&resources3=CUSTOM_MAGIC:123')
        self.assertRaises(webob.exc.HTTPBadRequest, self.do_parse, qs)

    def test_400_traits_no_resources_numbered(self):
        qs = ('resources=VCPU:7,MEMORY_MB:4096,DISK_GB:10'
              '&required=HW_CPU_X86_VMX,CUSTOM_MEM_FLASH,STORAGE_DISK_SSD'
              '&resources11=SRIOV_NET_VF:2'
              # Oops ----^^
              '&required1=CUSTOM_PHYSNET_PRIVATE'
              '&resources20=SRIOV_NET_VF:1,NET_INGRESS_BYTES_SEC:20000'
              # Oops ----^^
              ',NET_EGRESS_BYTES_SEC:10000'
              '&required2=CUSTOM_SWITCH_BIG,CUSTOM_PHYSNET_PROD'
              '&resources3=CUSTOM_MAGIC:123')
        self.assertRaises(webob.exc.HTTPBadRequest, self.do_parse, qs)

    def test_400_member_of_no_resources_numbered(self):
        agg1_uuid = uuidsentinel.agg1
        qs = ('resources=VCPU:7,MEMORY_MB:4096,DISK_GB:10'
              '&required=HW_CPU_X86_VMX,CUSTOM_MEM_FLASH,STORAGE_DISK_SSD'
              '&member_of2=%s' % agg1_uuid)
        self.assertRaises(webob.exc.HTTPBadRequest, self.do_parse, qs)

    def test_forbidden_one_group(self):
        """When forbidden are allowed this will parse, but otherwise will
        indicate an invalid trait.
        """
        qs = ('resources=VCPU:2,MEMORY_MB:2048'
              '&required=CUSTOM_PHYSNET1,!CUSTOM_SWITCH_BIG')
        expected_forbidden = [
            pl.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'MEMORY_MB': 2048,
                },
                required_traits=[
                    {'CUSTOM_PHYSNET1'},
                ],
                forbidden_traits={
                    'CUSTOM_SWITCH_BIG',
                }
            ),
        ]
        expected_message = (
            "Invalid query string parameters: Expected 'required' parameter "
            "value of the form: HW_CPU_X86_VMX,CUSTOM_MAGIC. Got: "
            "CUSTOM_PHYSNET1,!CUSTOM_SWITCH_BIG")
        exc = self.assertRaises(webob.exc.HTTPBadRequest, self.do_parse, qs)
        self.assertEqual(expected_message, str(exc))
        self.assertRequestGroupsEqual(
            expected_forbidden, self.do_parse(qs, version=(1, 22)))

    def test_forbidden_conflict(self):
        qs = ('resources=VCPU:2,MEMORY_MB:2048'
              '&required=CUSTOM_PHYSNET1,!CUSTOM_PHYSNET1')

        expected_message = (
            'Conflicting required and forbidden traits found '
            'in the following traits keys: required: (CUSTOM_PHYSNET1)')

        exc = self.assertRaises(
            webob.exc.HTTPBadRequest, self.do_parse, qs, version=(1, 22))
        self.assertEqual(expected_message, str(exc))

    def test_forbidden_two_groups(self):
        qs = ('resources=VCPU:2,MEMORY_MB:2048&resources1=CUSTOM_MAGIC:1'
              '&required1=CUSTOM_PHYSNET1,!CUSTOM_PHYSNET2')
        expected = [
            pl.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'MEMORY_MB': 2048,
                },
            ),
            pl.RequestGroup(
                resources={
                    'CUSTOM_MAGIC': 1,
                },
                required_traits=[
                    {'CUSTOM_PHYSNET1'},
                ],
                forbidden_traits={
                    'CUSTOM_PHYSNET2',
                }
            ),
        ]

        self.assertRequestGroupsEqual(
            expected, self.do_parse(qs, version=(1, 22)))

    def test_forbidden_separate_groups_no_conflict(self):
        qs = ('resources1=CUSTOM_MAGIC:1&required1=CUSTOM_PHYSNET1'
              '&resources2=CUSTOM_MAGIC:1&required2=!CUSTOM_PHYSNET1')
        expected = [
            pl.RequestGroup(
                use_same_provider=True,
                resources={
                    'CUSTOM_MAGIC': 1,
                },
                required_traits=[
                    {'CUSTOM_PHYSNET1'},
                ],
            ),
            pl.RequestGroup(
                use_same_provider=True,
                resources={
                    'CUSTOM_MAGIC': 1,
                },
                forbidden_traits={
                    'CUSTOM_PHYSNET1',
                }
            ),
        ]

        self.assertRequestGroupsEqual(
            expected, self.do_parse(qs, version=(1, 22)))

    def test_group_suffix_length_1_33(self):
        longstring = '01234567' * 8
        qs = 'resources_%s=CUSTOM_MAGIC:1' % longstring
        exc = self.assertRaises(
            webob.exc.HTTPBadRequest, self.do_parse, qs, version=(1, 33))
        # NOTE(cdent): This error message is not what an API user would see.
        # They would get an error during JSON schema processing.
        self.assertIn('least one request group', str(exc))

    def test_group_suffix_character_limits_1_33(self):
        qs = 'resources!#%=CUSTOM_MAGIC:1'
        exc = self.assertRaises(
            webob.exc.HTTPBadRequest, self.do_parse, qs, version=(1, 33))
        # NOTE(cdent): This error message is not what an API user would see.
        # They would get an error during JSON schema processing.
        self.assertIn('least one request group', str(exc))

    def test_group_suffix_character_limits_1_22(self):
        qs = 'resources!#%=CUSTOM_MAGIC:1'
        exc = self.assertRaises(
            webob.exc.HTTPBadRequest, self.do_parse, qs, version=(1, 22))
        # NOTE(cdent): This error message is not what an API user would see.
        # They would get an error during JSON schema processing.
        self.assertIn('least one request group', str(exc))

    def test_good_suffix_1_33(self):
        qs = ('resources_car_HOUSE_10=CUSTOM_MAGIC:1'
              '&required_car_HOUSE_10=CUSTOM_PHYSNET1')
        expected = [
            pl.RequestGroup(
                use_same_provider=True,
                resources={
                    'CUSTOM_MAGIC': 1,
                },
                required_traits=[
                    {'CUSTOM_PHYSNET1'},
                ],
            ),
        ]
        self.assertRequestGroupsEqual(
            expected, self.do_parse(qs, version=(1, 33)))
        self.assertRaises(
            webob.exc.HTTPBadRequest, self.do_parse, qs, version=(1, 22))

    def test_any_traits_1_38(self):
        qs = 'resources1=RABBIT:1&required1=in:WHITE,BLACK'

        exc = self.assertRaises(
            webob.exc.HTTPBadRequest, self.do_parse, qs, version=(1, 38))
        self.assertIn(
            "The format 'in:HW_CPU_X86_VMX,CUSTOM_MAGIC' only supported since "
            "microversion 1.39.",
            str(exc))

    def test_any_traits_1_39(self):
        qs = 'resources1=RABBIT:1&required1=in:WHITE,BLACK'
        expected = [
            pl.RequestGroup(
                use_same_provider=True,
                resources={
                    'RABBIT': 1,
                },
                required_traits=[
                    {'WHITE', 'BLACK'},
                ],
            ),
        ]

        self.assertRequestGroupsEqual(
            expected, self.do_parse(qs, version=(1, 39)))

    def test_any_traits_repeated(self):
        qs = 'resources1=CUSTOM_MAGIC:1&required1=in:T1,T2&required1=T3,!T4'
        expected = [
            pl.RequestGroup(
                use_same_provider=True,
                resources={
                    'CUSTOM_MAGIC': 1,
                },
                required_traits=[
                    {'T1', 'T2'},
                    {'T3'},
                ],
                forbidden_traits={
                    'T4'
                },
            ),
        ]

        self.assertRequestGroupsEqual(
            expected, self.do_parse(qs, version=(1, 39)))

    def test_any_traits_multiple_groups(self):
        qs = ('resources=RABBIT:1&required=in:WHITE,BLACK&'
              'resources2=CAT:2&required2=in:SILVER,RED&required2=!SPOTTED')
        expected = [
            pl.RequestGroup(
                use_same_provider=False,
                resources={
                    'RABBIT': 1,
                },
                required_traits=[
                    {'WHITE', 'BLACK'},
                ],
                forbidden_traits={
                },
            ),
            pl.RequestGroup(
                use_same_provider=True,
                resources={
                    'CAT': 2,
                },
                required_traits=[
                    {'SILVER', 'RED'},
                ],
                forbidden_traits={
                    'SPOTTED'
                },
            ),
        ]

        self.assertRequestGroupsEqual(
            expected, self.do_parse(qs, version=(1, 39)))

    def test_any_traits_forbidden_conflict(self):
        # going against one part of an OR expression is not a conflict as the
        # other parts still can match and fulfill the query
        qs = ('resources=VCPU:2'
              '&required=in:CUSTOM_PHYSNET1,CUSTOM_PHYSNET2'
              '&required=!CUSTOM_PHYSNET1')

        rgs = self.do_parse(qs, version=(1, 39))
        self.assertEqual(1, len(rgs))

        # but going against all parts of an OR expression is a conflict
        qs = ('resources=VCPU:2'
              '&required=in:CUSTOM_PHYSNET1,CUSTOM_PHYSNET2'
              '&required=!CUSTOM_PHYSNET1,!CUSTOM_PHYSNET2')

        expected_message = (
            'Conflicting required and forbidden traits found '
            'in the following traits keys: required: '
            '(CUSTOM_PHYSNET1, CUSTOM_PHYSNET2)')

        exc = self.assertRaises(
            webob.exc.HTTPBadRequest, self.do_parse, qs, version=(1, 39))
        self.assertEqual(expected_message, str(exc))

    def test_stringification(self):
        agg1 = uuidsentinel.agg1
        agg2 = uuidsentinel.agg2
        qs = (f'resources1=CAT:2&required1=in:SILVER,RED&'
              f'required1=TABBY,!SPOTTED&member_of1=in:{agg1},{agg2}')

        rgs = self.do_parse(qs, version=(1, 39))
        self.assertEqual(1, len(rgs))
        self.assertEqual(
            'RequestGroup('
            'use_same_provider=True, '
            'resources={CAT:2}, '
            'traits=((RED or SILVER) and TABBY and !SPOTTED), '
            f'aggregates=[[{", ".join(sorted([agg1, agg2]))}]])',
            str(rgs[0])
        )


class TestPickLastModified(base.ContextTestCase):

    def setUp(self):
        super(TestPickLastModified, self).setUp()
        fake_context = context.RequestContext(
            user_id='fake', project_id='fake')
        self.resource_provider = rp_obj.ResourceProvider(
            fake_context, name=uuidsentinel.rp_name, uuid=uuidsentinel.rp_uuid)

    def test_updated_versus_none(self):
        now = timeutils.utcnow(with_timezone=True)
        self.resource_provider.updated_at = now
        self.resource_provider.created_at = now
        chosen_time = util.pick_last_modified(None, self.resource_provider)
        self.assertEqual(now, chosen_time)

    def test_created_versus_none(self):
        now = timeutils.utcnow(with_timezone=True)
        self.resource_provider.created_at = now
        self.resource_provider.updated_at = None
        chosen_time = util.pick_last_modified(None, self.resource_provider)
        self.assertEqual(now, chosen_time)

    def test_last_modified_less(self):
        now = timeutils.utcnow(with_timezone=True)
        less = now - datetime.timedelta(seconds=300)
        self.resource_provider.updated_at = now
        self.resource_provider.created_at = now
        chosen_time = util.pick_last_modified(less, self.resource_provider)
        self.assertEqual(now, chosen_time)

    def test_last_modified_more(self):
        now = timeutils.utcnow(with_timezone=True)
        more = now + datetime.timedelta(seconds=300)
        self.resource_provider.updated_at = now
        self.resource_provider.created_at = now
        chosen_time = util.pick_last_modified(more, self.resource_provider)
        self.assertEqual(more, chosen_time)

    def test_last_modified_same(self):
        now = timeutils.utcnow(with_timezone=True)
        self.resource_provider.updated_at = now
        self.resource_provider.created_at = now
        chosen_time = util.pick_last_modified(now, self.resource_provider)
        self.assertEqual(now, chosen_time)

    def test_no_object_time_fields_less(self):
        # An unsaved ovo will not have the created_at or updated_at fields
        # present on the object at all.
        now = timeutils.utcnow(with_timezone=True)
        less = now - datetime.timedelta(seconds=300)
        with mock.patch('oslo_utils.timeutils.utcnow') as mock_utc:
            mock_utc.return_value = now
            chosen_time = util.pick_last_modified(
                less, self.resource_provider)
            self.assertEqual(now, chosen_time)
            mock_utc.assert_called_once_with(with_timezone=True)

    def test_no_object_time_fields_more(self):
        # An unsaved ovo will not have the created_at or updated_at fields
        # present on the object at all.
        now = timeutils.utcnow(with_timezone=True)
        more = now + datetime.timedelta(seconds=300)
        with mock.patch('oslo_utils.timeutils.utcnow') as mock_utc:
            mock_utc.return_value = now
            chosen_time = util.pick_last_modified(
                more, self.resource_provider)
            self.assertEqual(more, chosen_time)
            mock_utc.assert_called_once_with(with_timezone=True)

    def test_no_object_time_fields_none(self):
        # An unsaved ovo will not have the created_at or updated_at fields
        # present on the object at all.
        now = timeutils.utcnow(with_timezone=True)
        with mock.patch('oslo_utils.timeutils.utcnow') as mock_utc:
            mock_utc.return_value = now
            chosen_time = util.pick_last_modified(
                None, self.resource_provider)
            self.assertEqual(now, chosen_time)
            mock_utc.assert_called_once_with(with_timezone=True)


class RunOnceTests(testtools.TestCase):

    fake_logger = mock.MagicMock()

    @util.run_once("already ran once", fake_logger)
    def dummy_test_func(self, fail=False):
        if fail:
            raise ValueError()
        return True

    def setUp(self):
        super(RunOnceTests, self).setUp()
        self.dummy_test_func.reset()
        RunOnceTests.fake_logger.reset_mock()

    def test_wrapped_funtions_called_once(self):
        self.assertFalse(self.dummy_test_func.called)
        result = self.dummy_test_func()
        self.assertTrue(result)
        self.assertTrue(self.dummy_test_func.called)

        # assert that on second invocation no result
        # is returned and that the logger is invoked.
        result = self.dummy_test_func()
        RunOnceTests.fake_logger.assert_called_once()
        self.assertIsNone(result)

    def test_wrapped_funtions_called_once_raises(self):
        self.assertFalse(self.dummy_test_func.called)
        self.assertRaises(ValueError, self.dummy_test_func, fail=True)
        self.assertTrue(self.dummy_test_func.called)

        # assert that on second invocation no result
        # is returned and that the logger is invoked.
        result = self.dummy_test_func()
        RunOnceTests.fake_logger.assert_called_once()
        self.assertIsNone(result)

    def test_wrapped_funtions_can_be_reset(self):
        # assert we start with a clean state
        self.assertFalse(self.dummy_test_func.called)
        result = self.dummy_test_func()
        self.assertTrue(result)

        self.dummy_test_func.reset()
        # assert we restored a clean state
        self.assertFalse(self.dummy_test_func.called)
        result = self.dummy_test_func()
        self.assertTrue(result)

        # assert that we never called the logger
        RunOnceTests.fake_logger.assert_not_called()

    def test_reset_calls_cleanup(self):
        mock_clean = mock.Mock()

        @util.run_once("already ran once", self.fake_logger,
                       cleanup=mock_clean)
        def f():
            pass

        f()
        self.assertTrue(f.called)

        f.reset()
        self.assertFalse(f.called)
        mock_clean.assert_called_once_with()

    def test_clean_is_not_called_at_reset_if_wrapped_not_called(self):
        mock_clean = mock.Mock()

        @util.run_once("already ran once", self.fake_logger,
                       cleanup=mock_clean)
        def f():
            pass

        self.assertFalse(f.called)

        f.reset()
        self.assertFalse(f.called)
        self.assertFalse(mock_clean.called)

    def test_reset_works_even_if_cleanup_raises(self):
        mock_clean = mock.Mock(side_effect=ValueError())

        @util.run_once("already ran once", self.fake_logger,
                       cleanup=mock_clean)
        def f():
            pass

        f()
        self.assertTrue(f.called)

        self.assertRaises(ValueError, f.reset)
        self.assertFalse(f.called)
        mock_clean.assert_called_once_with()


class RoundRobinTests(testtools.TestCase):
    def test_no_input(self):
        self.assertEqual([], list(roundrobin()))

    def test_single_input(self):
        self.assertEqual([1, 2], list(roundrobin(iter([1, 2]))))

    def test_balanced_inputs(self):
        self.assertEqual(
            [1, "x", 2, "y"],
            list(roundrobin(
                iter([1, 2]),
                iter(["x", "y"]))
            )
        )

    def test_unbalanced_inputs(self):
        self.assertEqual(
            ["A", "D", "E", "B", "F", "C"],
            list(roundrobin(
                iter("ABC"),
                iter("D"),
                iter("EF"))
            )
        )
