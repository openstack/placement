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

import copy

import os_resource_classes as orc
from oslo_utils.fixture import uuidsentinel
from oslo_utils import uuidutils

from placement.objects import consumer as c_obj
from placement.objects import consumer_type as ct_obj
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

    def test_get_by_unspecified_consumer_type(self):
        # This will add a consumer with a NULL consumer type and the default
        # project and user external_ids
        self._make_allocation(tb.DISK_INVENTORY, tb.DISK_ALLOCATION)

        # Verify we filter the project external_id correctly. Note: this will
        # also work if filtering is broken (if it's not filtering at all)
        usages = usage_obj.get_by_consumer_type(
            self.ctx, self.project_obj.external_id)
        self.assertEqual(1, len(usages))
        usage = usages[0]
        self.assertEqual('unknown', usage.consumer_type)
        self.assertEqual(1, usage.consumer_count)
        self.assertEqual(orc.DISK_GB, usage.resource_class)
        self.assertEqual(2, usage.usage)
        # Verify we get nothing back if we filter on a different project
        # external_id that does not exist (will not work if filtering is
        # broken)
        usages = usage_obj.get_by_consumer_type(self.ctx, 'BOGUS')
        self.assertEqual(0, len(usages))

    def test_get_by_specified_consumer_type(self):
        ct = ct_obj.ConsumerType(self.ctx, name='INSTANCE')
        ct.create()
        consumer_id = uuidutils.generate_uuid()
        c = c_obj.Consumer(self.ctx, uuid=consumer_id,
                           project=self.project_obj, user=self.user_obj,
                           consumer_type_id=ct.id)
        c.create()
        # This will add a consumer with the consumer type INSTANCE
        # and the default project and user external_ids
        da = copy.deepcopy(tb.DISK_ALLOCATION)
        da['consumer_id'] = c.uuid
        self._make_allocation(tb.DISK_INVENTORY, da)

        # Verify we filter the INSTANCE type correctly. Note: this will also
        # work if filtering is broken (if it's not filtering at all)
        usages = usage_obj.get_by_consumer_type(
            self.ctx, self.project_obj.external_id,
            consumer_type=ct.name)
        self.assertEqual(1, len(usages))
        usage = usages[0]
        self.assertEqual(ct.name, usage.consumer_type)
        self.assertEqual(1, usage.consumer_count)
        self.assertEqual(orc.DISK_GB, usage.resource_class)
        self.assertEqual(2, usage.usage)
        # Verify we get nothing back if we filter on a different consumer
        # type that does not exist (will not work if filtering is broken)
        usages = usage_obj.get_by_consumer_type(
            self.ctx, self.project_obj.external_id,
            consumer_type='BOGUS')
        self.assertEqual(0, len(usages))

    def test_get_by_specified_consumer_type_with_user(self):
        ct = ct_obj.ConsumerType(self.ctx, name='INSTANCE')
        ct.create()
        consumer_id = uuidutils.generate_uuid()
        c = c_obj.Consumer(self.ctx, uuid=consumer_id,
                           project=self.project_obj, user=self.user_obj,
                           consumer_type_id=ct.id)
        c.create()
        # This will add a consumer with the consumer type INSTANCE
        # and the default project and user external_ids
        da = copy.deepcopy(tb.DISK_ALLOCATION)
        da['consumer_id'] = c.uuid
        db_rp, _ = self._make_allocation(tb.DISK_INVENTORY, da)

        # Verify we filter the user external_id correctly. Note: this will also
        # work if filtering is broken (if it's not filtering at all)
        usages = usage_obj.get_by_consumer_type(
            self.ctx, self.project_obj.external_id,
            user_id=self.user_obj.external_id,
            consumer_type=ct.name)
        self.assertEqual(1, len(usages))
        usage = usages[0]
        self.assertEqual(ct.name, usage.consumer_type)
        self.assertEqual(1, usage.consumer_count)
        self.assertEqual(orc.DISK_GB, usage.resource_class)
        self.assertEqual(2, usage.usage)
        # Verify we get nothing back if we filter on a different user
        # external_id that does not exist (will not work if filtering is
        # broken)
        usages = usage_obj.get_by_consumer_type(
            self.ctx, self.project_obj.external_id,
            user_id='BOGUS',
            consumer_type=ct.name)
        self.assertEqual(0, len(usages))

    def test_get_by_all_consumer_type(self):
        # This will add a consumer with the default consumer type UNKNOWN
        db_rp, _ = self._make_allocation(tb.DISK_INVENTORY,
                                         tb.DISK_ALLOCATION)
        # Make another allocation with a different consumer type
        ct = ct_obj.ConsumerType(self.ctx, name='FOO')
        ct.create()
        consumer_id = uuidutils.generate_uuid()
        c = c_obj.Consumer(self.ctx, uuid=consumer_id,
                           project=self.project_obj, user=self.user_obj,
                           consumer_type_id=ct.id)
        c.create()
        self.allocate_from_provider(db_rp, orc.DISK_GB, 2, consumer=c)

        # Verify we get usages back for both consumer types with 'all'
        usages = usage_obj.get_by_consumer_type(
            self.ctx, self.project_obj.external_id, consumer_type='all')
        self.assertEqual(1, len(usages))
        usage = usages[0]
        self.assertEqual('all', usage.consumer_type)
        self.assertEqual(2, usage.consumer_count)
        self.assertEqual(orc.DISK_GB, usage.resource_class)
        self.assertEqual(4, usage.usage)

    def test_get_by_unused_consumer_type(self):
        # This will add a consumer with the default consumer type UNKNOWN
        self._make_allocation(tb.DISK_INVENTORY, tb.DISK_ALLOCATION)

        usages = usage_obj.get_by_consumer_type(
            self.ctx, self.project_obj.external_id, consumer_type='EMPTY')
        self.assertEqual(0, len(usages))
