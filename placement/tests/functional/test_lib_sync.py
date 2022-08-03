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
import os_resource_classes
import os_traits

from placement import direct
from placement.tests.functional import base


class TestLibSync(base.TestCase):
    """Test that traits and resource classes are synced from os-traits and
    os-resource-classes libs to the DB at service startup.
    """

    def setUp(self):
        super().setUp()
        self.headers = {
            'x-auth-token': 'admin',
            'content-type': 'application/json',
            'OpenStack-API-Version': 'placement latest',
        }

    def test_traits_sync(self):
        with direct.PlacementDirect(self.conf_fixture.conf) as client:
            resp = client.get('/traits', headers=self.headers)
            self.assertItemsEqual(
                os_traits.get_traits(),
                resp.json()['traits'],
            )

    def test_resource_classes_sync(self):
        with direct.PlacementDirect(self.conf_fixture.conf) as client:
            resp = client.get('/resource_classes', headers=self.headers)
            self.assertItemsEqual(
                os_resource_classes.STANDARDS,
                [rc['name'] for rc in resp.json()['resource_classes']],
                resp.json(),
            )
