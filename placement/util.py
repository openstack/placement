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
"""Utility methods for placement API."""

import functools

import jsonschema
from oslo_log import log as logging
from oslo_middleware import request_id
from oslo_serialization import jsonutils
from oslo_utils import timeutils
from oslo_utils import uuidutils
import webob

from placement import errors
# NOTE(cdent): avoid cyclical import conflict between util and
# microversion
import placement.microversion

LOG = logging.getLogger(__name__)

# Error code handling constants
ENV_ERROR_CODE = 'placement.error_code'
ERROR_CODE_MICROVERSION = (1, 23)


# NOTE(cdent): This registers a FormatChecker on the jsonschema
# module. Do not delete this code! Although it appears that nothing
# is using the decorated method it is being used in JSON schema
# validations to check uuid formatted strings.
@jsonschema.FormatChecker.cls_checks('uuid')
def _validate_uuid_format(instance):
    return uuidutils.is_uuid_like(instance)


def check_accept(*types):
    """If accept is set explicitly, try to follow it.

    If there is no match for the incoming accept header
    send a 406 response code.

    If accept is not set send our usual content-type in
    response.
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(req):
            if req.accept:
                best_matches = req.accept.acceptable_offers(types)
                if not best_matches:
                    type_string = ', '.join(types)
                    raise webob.exc.HTTPNotAcceptable(
                        'Only %(type)s is provided' % {'type': type_string},
                        json_formatter=json_error_formatter)
            return f(req)
        return decorated_function
    return decorator


def extract_json(body, schema):
    """Extract JSON from a body and validate with the provided schema."""
    try:
        data = jsonutils.loads(body)
    except ValueError as exc:
        raise webob.exc.HTTPBadRequest(
            'Malformed JSON: %(error)s' % {'error': exc},
            json_formatter=json_error_formatter)
    try:
        jsonschema.validate(data, schema,
                            format_checker=jsonschema.FormatChecker())
    except jsonschema.ValidationError as exc:
        raise webob.exc.HTTPBadRequest(
            'JSON does not validate: %(error)s' % {'error': exc},
            json_formatter=json_error_formatter)
    return data


def inventory_url(environ, resource_provider, resource_class=None):
    url = '%s/inventories' % resource_provider_url(environ, resource_provider)
    if resource_class:
        url = '%s/%s' % (url, resource_class)
    return url


def json_error_formatter(body, status, title, environ):
    """A json_formatter for webob exceptions.

    Follows API-WG guidelines at
    http://specs.openstack.org/openstack/api-wg/guidelines/errors.html
    """
    # Shortcut to microversion module, to avoid wraps below.
    microversion = placement.microversion

    # Clear out the html that webob sneaks in.
    body = webob.exc.strip_tags(body)
    # Get status code out of status message. webob's error formatter
    # only passes entire status string.
    status_code = int(status.split(None, 1)[0])
    error_dict = {
        'status': status_code,
        'title': title,
        'detail': body
    }

    # Version may not be set if we have experienced an error before it
    # is set.
    want_version = environ.get(microversion.MICROVERSION_ENVIRON)
    if want_version and want_version.matches(ERROR_CODE_MICROVERSION):
        error_dict['code'] = environ.get(ENV_ERROR_CODE, errors.DEFAULT)

    # If the request id middleware has had a chance to add an id,
    # put it in the error response.
    if request_id.ENV_REQUEST_ID in environ:
        error_dict['request_id'] = environ[request_id.ENV_REQUEST_ID]

    # When there is a no microversion in the environment and a 406,
    # microversion parsing failed so we need to include microversion
    # min and max information in the error response.
    if status_code == 406 and microversion.MICROVERSION_ENVIRON not in environ:
        error_dict['max_version'] = microversion.max_version_string()
        error_dict['min_version'] = microversion.min_version_string()

    return {'errors': [error_dict]}


def pick_last_modified(last_modified, obj):
    """Choose max of last_modified and obj.updated_at or obj.created_at.

    If updated_at is not implemented in `obj` use the current time in UTC.
    """
    current_modified = (obj.updated_at or obj.created_at)
    if current_modified is None:
        # The object was not loaded from the DB, it was created in
        # the current context.
        current_modified = timeutils.utcnow(with_timezone=True)
    if last_modified:
        last_modified = max(last_modified, current_modified)
    else:
        last_modified = current_modified
    return last_modified


def require_content(content_type):
    """Decorator to require a content type in a handler."""
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(req):
            if req.content_type != content_type:
                # webob's unset content_type is the empty string so
                # set it the error message content to 'None' to make
                # a useful message in that case. This also avoids a
                # KeyError raised when webob.exc eagerly fills in a
                # Template for output we will never use.
                if not req.content_type:
                    req.content_type = 'None'
                raise webob.exc.HTTPUnsupportedMediaType(
                    'The media type %(bad_type)s is not supported, '
                    'use %(good_type)s' %
                    {'bad_type': req.content_type,
                     'good_type': content_type},
                    json_formatter=json_error_formatter)
            else:
                return f(req)
        return decorated_function
    return decorator


def resource_class_url(environ, resource_class):
    """Produce the URL for a resource class.

    If SCRIPT_NAME is present, it is the mount point of the placement
    WSGI app.
    """
    prefix = environ.get('SCRIPT_NAME', '')
    return '%s/resource_classes/%s' % (prefix, resource_class.name)


def resource_provider_url(environ, resource_provider):
    """Produce the URL for a resource provider.

    If SCRIPT_NAME is present, it is the mount point of the placement
    WSGI app.
    """
    prefix = environ.get('SCRIPT_NAME', '')
    return '%s/resource_providers/%s' % (prefix, resource_provider.uuid)


def trait_url(environ, trait):
    """Produce the URL for a trait.

    If SCRIPT_NAME is present, it is the mount point of the placement
    WSGI app.
    """
    prefix = environ.get('SCRIPT_NAME', '')
    return '%s/traits/%s' % (prefix, trait.name)


def validate_query_params(req, schema):
    try:
        # NOTE(Kevin_Zheng): The webob package throws UnicodeError when
        # param cannot be decoded. Catch this and raise HTTP 400.
        jsonschema.validate(dict(req.GET), schema,
                            format_checker=jsonschema.FormatChecker())
    except (jsonschema.ValidationError, UnicodeDecodeError) as exc:
        raise webob.exc.HTTPBadRequest(
            'Invalid query string parameters: %(exc)s' %
            {'exc': exc})


def wsgi_path_item(environ, name):
    """Extract the value of a named field in a URL.

    Return None if the name is not present or there are no path items.
    """
    # NOTE(cdent): For the time being we don't need to urldecode
    # the value as the entire placement API has paths that accept no
    # encoded values.
    try:
        return environ['wsgiorg.routing_args'][1][name]
    except (KeyError, IndexError):
        return None


def normalize_resources_qs_param(qs):
    """Given a query string parameter for resources, validate it meets the
    expected format and return a dict of amounts, keyed by resource class name.

    The expected format of the resources parameter looks like so:

        $RESOURCE_CLASS_NAME:$AMOUNT,$RESOURCE_CLASS_NAME:$AMOUNT

    So, if the user was looking for resource providers that had room for an
    instance that will consume 2 vCPUs, 1024 MB of RAM and 50GB of disk space,
    they would use the following query string:

        ?resources=VCPU:2,MEMORY_MB:1024,DISK_GB:50

    The returned value would be:

        {
            "VCPU": 2,
            "MEMORY_MB": 1024,
            "DISK_GB": 50,
        }

    :param qs: The value of the 'resources' query string parameter
    :raises `webob.exc.HTTPBadRequest` if the parameter's value isn't in the
            expected format.
    """
    if qs.strip() == "":
        msg = ('Badly formed resources parameter. Expected resources '
               'query string parameter in form: '
               '?resources=VCPU:2,MEMORY_MB:1024. Got: empty string.')
        raise webob.exc.HTTPBadRequest(msg)

    result = {}
    resource_tuples = qs.split(',')
    for rt in resource_tuples:
        try:
            rc_name, amount = rt.split(':')
        except ValueError:
            msg = ('Badly formed resources parameter. Expected resources '
                   'query string parameter in form: '
                   '?resources=VCPU:2,MEMORY_MB:1024. Got: %s.')
            msg = msg % rt
            raise webob.exc.HTTPBadRequest(msg)
        try:
            amount = int(amount)
        except ValueError:
            msg = ('Requested resource %(resource_name)s expected positive '
                   'integer amount. Got: %(amount)s.')
            msg = msg % {
                'resource_name': rc_name,
                'amount': amount,
            }
            raise webob.exc.HTTPBadRequest(msg)
        if amount < 1:
            msg = ('Requested resource %(resource_name)s requires '
                   'amount >= 1. Got: %(amount)d.')
            msg = msg % {
                'resource_name': rc_name,
                'amount': amount,
            }
            raise webob.exc.HTTPBadRequest(msg)
        result[rc_name] = amount
    return result


def valid_trait(trait, allow_forbidden):
    """Return True if the provided trait is the expected form.

    When allow_forbidden is True, then a leading '!' is acceptable.
    """
    if trait.startswith('!') and not allow_forbidden:
        return False
    return True


def normalize_traits_qs_param(val, allow_forbidden=False):
    """Parse a traits query string parameter value.

    Note that this method doesn't know or care about the query parameter key,
    which may currently be of the form `required`, `required123`, etc., but
    which may someday also include `preferred`, etc.

    This method currently does no format validation of trait strings, other
    than to ensure they're not zero-length.

    :param val: A traits query parameter value: a comma-separated string of
                trait names.
    :param allow_forbidden: If True, accept forbidden traits (that is, traits
                            prefixed by '!') as a valid form when notifying
                            the caller that the provided value is not properly
                            formed.
    :return: A set of trait names.
    :raises `webob.exc.HTTPBadRequest` if the val parameter is not in the
            expected format.
    """
    ret = set(substr.strip() for substr in val.split(','))
    expected_form = 'HW_CPU_X86_VMX,CUSTOM_MAGIC'
    if allow_forbidden:
        expected_form = 'HW_CPU_X86_VMX,!CUSTOM_MAGIC'
    if not all(trait and valid_trait(trait, allow_forbidden) for trait in ret):
        msg = ("Invalid query string parameters: Expected 'required' "
               "parameter value of the form: %(form)s. "
               "Got: %(val)s") % {'form': expected_form, 'val': val}
        raise webob.exc.HTTPBadRequest(msg)
    return ret


def normalize_member_of_qs_params(req, suffix=''):
    """Given a webob.Request object, validate that the member_of querystring
    parameters are correct. We begin supporting multiple member_of params in
    microversion 1.24 and forbidden aggregates in microversion 1.32.

    :param req: webob.Request object
    :return: A tuple of
        required_aggs: A list containing sets of UUIDs of required
                       aggregates to filter on
        forbidden_aggs: A set of UUIDs of forbidden aggregates to filter on
    :raises `webob.exc.HTTPBadRequest` if the microversion requested is <1.24
            and the request contains multiple member_of querystring params
    :raises `webob.exc.HTTPBadRequest` if the microversion requested is <1.32
            and the request contains forbidden format of member_of querystring
            params with '!' prefix
    :raises `webob.exc.HTTPBadRequest` if the val parameter is not in the
            expected format.
    """
    want_version = req.environ[placement.microversion.MICROVERSION_ENVIRON]
    multi_member_of = want_version.matches((1, 24))
    allow_forbidden = want_version.matches((1, 32))
    if not multi_member_of and len(req.GET.getall('member_of' + suffix)) > 1:
        raise webob.exc.HTTPBadRequest(
            'Multiple member_of%s parameters are not supported' % suffix)
    required_aggs = []
    forbidden_aggs = set()
    for value in req.GET.getall('member_of' + suffix):
        required, forbidden = normalize_member_of_qs_param(value)
        if required:
            required_aggs.append(required)
        if forbidden:
            if not allow_forbidden:
                raise webob.exc.HTTPBadRequest(
                    'Forbidden member_of%s parameters are not supported '
                    'in the specified microversion' % suffix)
            forbidden_aggs |= forbidden
    return required_aggs, forbidden_aggs


def normalize_member_of_qs_param(value):
    """Parse a member_of query string parameter value.

    Valid values are one of either
        - a single UUID
        - the prefix '!' followed by a single UUID
        - the prefix 'in:' or '!in:' followed by two or more
          comma-separated UUIDs.

    :param value: A member_of query parameter
    :return: A tuple of:
        required: A set of aggregate UUIDs at least one of which is required
        forbidden: A set of aggregate UUIDs all of which are forbidden
    :raises `webob.exc.HTTPBadRequest` if the value parameter is not in the
            expected format.
    """
    if "," in value and not (
            value.startswith("in:") or value.startswith("!in:")):
        msg = ("Multiple values for 'member_of' must be prefixed with the "
               "'in:' or '!in:' keyword using the valid microversion. "
               "Got: %s") % value
        raise webob.exc.HTTPBadRequest(msg)

    required = forbidden = set()
    if value.startswith('!in:'):
        forbidden = set(value[4:].split(','))
    elif value.startswith('!'):
        forbidden = set([value[1:]])
    elif value.startswith('in:'):
        required = set(value[3:].split(','))
    else:
        required = set([value])

    # Make sure the values are actually UUIDs.
    for aggr_uuid in (required | forbidden):
        if not uuidutils.is_uuid_like(aggr_uuid):
            msg = ("Invalid query string parameters: Expected 'member_of' "
                   "parameter to contain valid UUID(s). Got: %s") % aggr_uuid
            raise webob.exc.HTTPBadRequest(msg)
    return required, forbidden


def normalize_in_tree_qs_params(value):
    """Parse a in_tree query string parameter value.

    :param value: in_tree query parameter: A UUID of a resource provider.
    :return: A UUID of a resource provider.
    :raises `webob.exc.HTTPBadRequest` if the val parameter is not in the
            expected format.
    """
    ret = value.strip()
    if not uuidutils.is_uuid_like(ret):
        msg = ("Invalid query string parameters: Expected 'in_tree' "
               "parameter to be a format of uuid. "
               "Got: %(val)s") % {'val': value}
        raise webob.exc.HTTPBadRequest(msg)
    return ret


def run_once(message, logger, cleanup=None):
    """This is a utility function decorator to ensure a function
    is run once and only once in an interpreter instance.
    The decorated function object can be reset by calling its
    reset function. All exceptions raised by the wrapped function,
    logger and cleanup function will be propagated to the caller.
    """
    def outer_wrapper(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not wrapper.called:
                # Note(sean-k-mooney): the called state is always
                # updated even if the wrapped function completes
                # by raising an exception. If the caller catches
                # the exception it is their responsibility to call
                # reset if they want to re-execute the wrapped function.
                try:
                    return func(*args, **kwargs)
                finally:
                    wrapper.called = True
            else:
                logger(message)

        wrapper.called = False

        def reset(wrapper, *args, **kwargs):
            # Note(sean-k-mooney): we conditionally call the
            # cleanup function if one is provided only when the
            # wrapped function has been called previously. We catch
            # and reraise any exception that may be raised and update
            # the called state in a finally block to ensure its
            # always updated if reset is called.
            try:
                if cleanup and wrapper.called:
                    return cleanup(*args, **kwargs)
            finally:
                wrapper.called = False

        wrapper.reset = functools.partial(reset, wrapper)
        return wrapper
    return outer_wrapper
