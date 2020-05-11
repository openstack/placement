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

from unittest import mock

from placement.objects import trait
from placement.tests.unit.objects import base


class TestTraits(base.TestCase):

    @mock.patch('placement.objects.trait._trait_sync')
    def test_sync_flag(self, mock_sync):
        synced = trait._TRAITS_SYNCED
        self.assertFalse(synced)
        # Sync the traits
        trait.ensure_sync(self.context)
        synced = trait._TRAITS_SYNCED
        self.assertTrue(synced)
