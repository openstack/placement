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
"""Unit tests for code in the aggregate handler that gabbi isn't covering."""

from unittest import mock

import webob

from placement import context
from placement import exception
from placement.handlers import aggregate
from placement.objects import resource_provider
from placement.tests.unit import base


class TestAggregateHandlerErrors(base.ContextTestCase):
    """Tests that make sure errors hard to trigger by gabbi result in expected
    exceptions.
    """

    def test_concurrent_exception_causes_409(self):
        fake_context = context.RequestContext(
            user_id='fake', project_id='fake')
        rp = resource_provider.ResourceProvider(fake_context)
        expected_message = ('Update conflict: Another thread concurrently '
                            'updated the data')
        with mock.patch("placement.objects.resource_provider._set_aggregates",
                        side_effect=exception.ConcurrentUpdateDetected):
            exc = self.assertRaises(webob.exc.HTTPConflict,
                                    aggregate._set_aggregates, rp, [])
        self.assertIn(expected_message, str(exc))
