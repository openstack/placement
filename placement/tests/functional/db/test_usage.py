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

import os_resource_classes as orc
from oslo_utils.fixture import uuidsentinel

from placement.objects import inventory as inv_obj
from placement.objects import usage as usage_obj
from placement.tests.functional.db import test_base as tb


class UsageListTestCase(tb.PlacementDbBaseTestCase):

    def test_get_all_null(self):
        for uuid in [uuidsentinel.rp_uuid_1, uuidsentinel.rp_uuid_2]:
            self._create_provider(uuid, uuid=uuid)

        usages = usage_obj.get_all_by_resource_provider_uuid(
            self.ctx, uuidsentinel.rp_uuid_1)
        self.assertEqual(0, len(usages))

    def test_get_all_one_allocation(self):
        db_rp, _ = self._make_allocation(tb.DISK_INVENTORY,
                                         tb.DISK_ALLOCATION)
        inv = inv_obj.Inventory(resource_provider=db_rp,
                                resource_class=orc.DISK_GB,
                                total=1024)
        db_rp.set_inventory([inv])

        usages = usage_obj.get_all_by_resource_provider_uuid(
            self.ctx, db_rp.uuid)
        self.assertEqual(1, len(usages))
        self.assertEqual(2, usages[0].usage)
        self.assertEqual(orc.DISK_GB,
                         usages[0].resource_class)

    def test_get_inventory_no_allocation(self):
        db_rp = self._create_provider('rp_no_inv')
        tb.add_inventory(db_rp, orc.DISK_GB, 1024)

        usages = usage_obj.get_all_by_resource_provider_uuid(
            self.ctx, db_rp.uuid)
        self.assertEqual(1, len(usages))
        self.assertEqual(0, usages[0].usage)
        self.assertEqual(orc.DISK_GB,
                         usages[0].resource_class)

    def test_get_all_multiple_inv(self):
        db_rp = self._create_provider('rp_no_inv')
        tb.add_inventory(db_rp, orc.DISK_GB, 1024)
        tb.add_inventory(db_rp, orc.VCPU, 24)

        usages = usage_obj.get_all_by_resource_provider_uuid(
            self.ctx, db_rp.uuid)
        self.assertEqual(2, len(usages))
