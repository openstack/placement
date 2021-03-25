# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
Unit tests for code in the resource provider handler that gabbi isn't covering.
"""

from unittest import mock

import microversion_parse
from oslo_db import exception as db_exc
import webob

from placement import context
from placement.handlers import resource_provider
from placement.tests.unit import base


class TestAggregateHandlerErrors(base.ContextTestCase):

    @mock.patch('placement.context.RequestContext.can', new=mock.Mock())
    def _test_duplicate_error_parsing_mysql(self, key):
        fake_context = context.RequestContext(
            user_id='fake', project_id='fake')

        req = webob.Request.blank(
            '/resource_providers',
            method='POST',
            content_type='application/json')
        req.body = b'{"name": "foobar"}'
        req.environ['placement.context'] = fake_context

        parse_version = microversion_parse.parse_version_string
        microversion = parse_version('1.15')
        microversion.max_version = parse_version('9.99')
        microversion.min_version = parse_version('1.0')
        req.environ['placement.microversion'] = microversion

        with mock.patch(
            'placement.objects.resource_provider.ResourceProvider.create',
            side_effect=db_exc.DBDuplicateEntry(columns=[key]),
        ):
            response = req.get_response(
                resource_provider.create_resource_provider)

        self.assertEqual('409 Conflict', response.status)
        self.assertIn(
            'Conflicting resource provider name: foobar already exists.',
            response.text)

    def test_duplicate_error_parsing_mysql_5x(self):
        """Ensure we parse the correct column on MySQL 5.x.

        On MySQL 5.x, DBDuplicateEntry.columns will contain the name of the
        column causing the integrity error.
        """
        self._test_duplicate_error_parsing_mysql('name')

    def test_duplicate_error_parsing_mysql_8x(self):
        """Ensure we parse the correct column on MySQL 5.x.

        On MySQL 5.x, DBDuplicateEntry.columns will contain the name of the
        constraint causing the integrity error.
        """
        self._test_duplicate_error_parsing_mysql(
            'uniq_resource_providers0name')
