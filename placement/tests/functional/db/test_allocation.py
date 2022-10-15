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

import os_resource_classes as orc
from oslo_utils.fixture import uuidsentinel

from placement import exception
from placement.objects import allocation as alloc_obj
from placement.objects import consumer as consumer_obj
from placement.objects import consumer_type as ct_obj
from placement.objects import inventory as inv_obj
from placement.objects import usage as usage_obj
from placement.tests.functional.db import test_base as tb


class TestAllocation(tb.PlacementDbBaseTestCase):

    def test_create_list_and_delete_allocation(self):
        rp, _ = self._make_allocation(tb.DISK_INVENTORY, tb.DISK_ALLOCATION)

        allocations = alloc_obj.get_all_by_resource_provider(self.ctx, rp)

        self.assertEqual(1, len(allocations))

        self.assertEqual(tb.DISK_ALLOCATION['used'],
                         allocations[0].used)

        alloc_obj.delete_all(self.ctx, allocations)

        allocations = alloc_obj.get_all_by_resource_provider(self.ctx, rp)

        self.assertEqual(0, len(allocations))

    def test_delete_all_with_multiple_consumers(self):
        """Tests fix for LP #1781430 where alloc_obj.delete_all() when
        issued for a list of allocations returned by
        alloc_obj.get_by_resource_provider() where the resource provider
        had multiple consumers allocated against it, left the DB in an
        inconsistent state.
        """
        # Create a single resource provider and allocate resources for two
        # instances from it. Then grab all the provider's allocations with
        # alloc_obj.get_all_by_resource_provider() and attempt to delete
        # them all with alloc_obj.delete_all(). After which, another call
        # to alloc_obj.get_all_by_resource_provider() should return an
        # empty list.
        cn1 = self._create_provider('cn1')
        tb.add_inventory(cn1, 'VCPU', 8)

        c1_uuid = uuidsentinel.consumer1
        c2_uuid = uuidsentinel.consumer2

        for c_uuid in (c1_uuid, c2_uuid):
            self.allocate_from_provider(cn1, 'VCPU', 1, consumer_id=c_uuid)

        allocs = alloc_obj.get_all_by_resource_provider(self.ctx, cn1)
        self.assertEqual(2, len(allocs))

        alloc_obj.delete_all(self.ctx, allocs)

        allocs = alloc_obj.get_all_by_resource_provider(self.ctx, cn1)
        self.assertEqual(0, len(allocs))

    def test_multi_provider_allocation(self):
        """Tests that an allocation that includes more than one resource
        provider can be created, listed and deleted properly.

        Bug #1707669 highlighted a situation that arose when attempting to
        remove part of an allocation for a source host during a resize
        operation where the exiting allocation was not being properly
        deleted.
        """
        cn_source = self._create_provider('cn_source')
        cn_dest = self._create_provider('cn_dest')

        # Add same inventory to both source and destination host
        for cn in (cn_source, cn_dest):
            tb.add_inventory(cn, orc.VCPU, 24,
                             allocation_ratio=16.0)
            tb.add_inventory(cn, orc.MEMORY_MB, 1024,
                             min_unit=64,
                             max_unit=1024,
                             step_size=64,
                             allocation_ratio=1.5)

        # Create an INSTANCE consumer type
        ct = ct_obj.ConsumerType(self.ctx, name='INSTANCE')
        ct.create()
        # Save consumer type id for later confirmation.
        ct_id = ct.id

        # Create a consumer representing the instance
        inst_consumer = consumer_obj.Consumer(
            self.ctx, uuid=uuidsentinel.instance, user=self.user_obj,
            project=self.project_obj, consumer_type_id=ct_id)
        inst_consumer.create()

        # Now create an allocation that represents a move operation where the
        # scheduler has selected cn_dest as the target host and created a
        # "doubled-up" allocation for the duration of the move operation
        alloc_list = [
            alloc_obj.Allocation(
                consumer=inst_consumer,
                resource_provider=cn_source,
                resource_class=orc.VCPU,
                used=1),
            alloc_obj.Allocation(
                consumer=inst_consumer,
                resource_provider=cn_source,
                resource_class=orc.MEMORY_MB,
                used=256),
            alloc_obj.Allocation(
                consumer=inst_consumer,
                resource_provider=cn_dest,
                resource_class=orc.VCPU,
                used=1),
            alloc_obj.Allocation(
                consumer=inst_consumer,
                resource_provider=cn_dest,
                resource_class=orc.MEMORY_MB,
                used=256),
        ]
        alloc_obj.replace_all(self.ctx, alloc_list)

        src_allocs = alloc_obj.get_all_by_resource_provider(
            self.ctx, cn_source)

        self.assertEqual(2, len(src_allocs))

        dest_allocs = alloc_obj.get_all_by_resource_provider(self.ctx, cn_dest)

        self.assertEqual(2, len(dest_allocs))

        consumer_allocs = alloc_obj.get_all_by_consumer_id(
            self.ctx, uuidsentinel.instance)

        self.assertEqual(4, len(consumer_allocs))

        # Validate that when we create an allocation for a consumer that we
        # delete any existing allocation and replace it with what the new.
        # Here, we're emulating the step that occurs on confirm_resize() where
        # the source host pulls the existing allocation for the instance and
        # removes any resources that refer to itself and saves the allocation
        # back to placement
        new_alloc_list = [
            alloc_obj.Allocation(
                consumer=inst_consumer,
                resource_provider=cn_dest,
                resource_class=orc.VCPU,
                used=1),
            alloc_obj.Allocation(
                consumer=inst_consumer,
                resource_provider=cn_dest,
                resource_class=orc.MEMORY_MB,
                used=256),
        ]
        alloc_obj.replace_all(self.ctx, new_alloc_list)

        src_allocs = alloc_obj.get_all_by_resource_provider(
            self.ctx, cn_source)

        self.assertEqual(0, len(src_allocs))

        dest_allocs = alloc_obj.get_all_by_resource_provider(
            self.ctx, cn_dest)

        self.assertEqual(2, len(dest_allocs))

        consumer_allocs = alloc_obj.get_all_by_consumer_id(
            self.ctx, uuidsentinel.instance)

        self.assertEqual(2, len(consumer_allocs))

        # check the allocations have the expected INSTANCE consumer type
        self.assertEqual(ct_id, consumer_allocs[0].consumer.consumer_type_id)
        self.assertEqual(ct_id, consumer_allocs[1].consumer.consumer_type_id)

    def test_get_all_by_resource_provider(self):
        rp, allocation = self._make_allocation(tb.DISK_INVENTORY,
                                               tb.DISK_ALLOCATION)
        allocations = alloc_obj.get_all_by_resource_provider(self.ctx, rp)
        self.assertEqual(1, len(allocations))
        self.assertEqual(rp.id, allocations[0].resource_provider.id)
        self.assertEqual(allocation.resource_provider.id,
                         allocations[0].resource_provider.id)


class TestAllocationListCreateDelete(tb.PlacementDbBaseTestCase):

    def test_allocation_checking(self):
        """Test that allocation check logic works with 2 resource classes on
        one provider.

        If this fails, we get a KeyError at replace_all()
        """

        max_unit = 10
        consumer_uuid = uuidsentinel.consumer
        consumer_uuid2 = uuidsentinel.consumer2

        # Create a consumer representing the two instances
        consumer = consumer_obj.Consumer(
            self.ctx, uuid=consumer_uuid, user=self.user_obj,
            project=self.project_obj)
        consumer.create()
        consumer2 = consumer_obj.Consumer(
            self.ctx, uuid=consumer_uuid2, user=self.user_obj,
            project=self.project_obj)
        consumer2.create()

        # Create one resource provider with 2 classes
        rp1_name = uuidsentinel.rp1_name
        rp1_uuid = uuidsentinel.rp1_uuid
        rp1_class = orc.DISK_GB
        rp1_used = 6

        rp2_class = orc.IPV4_ADDRESS
        rp2_used = 2

        rp1 = self._create_provider(rp1_name, uuid=rp1_uuid)
        tb.add_inventory(rp1, rp1_class, 1024, max_unit=max_unit)
        tb.add_inventory(rp1, rp2_class, 255, reserved=2, max_unit=max_unit)

        # create the allocations for a first consumer
        allocation_1 = alloc_obj.Allocation(
            resource_provider=rp1, consumer=consumer, resource_class=rp1_class,
            used=rp1_used)
        allocation_2 = alloc_obj.Allocation(
            resource_provider=rp1, consumer=consumer, resource_class=rp2_class,
            used=rp2_used)
        allocation_list = [allocation_1, allocation_2]
        alloc_obj.replace_all(self.ctx, allocation_list)

        # create the allocations for a second consumer, until we have
        # allocations for more than one consumer in the db, then we
        # won't actually be doing real allocation math, which triggers
        # the sql monster.
        allocation_1 = alloc_obj.Allocation(
            resource_provider=rp1, consumer=consumer2,
            resource_class=rp1_class, used=rp1_used)
        allocation_2 = alloc_obj.Allocation(
            resource_provider=rp1, consumer=consumer2,
            resource_class=rp2_class, used=rp2_used)
        allocation_list = [allocation_1, allocation_2]
        # If we are joining wrong, this will be a KeyError
        alloc_obj.replace_all(self.ctx, allocation_list)

    def test_allocation_list_create(self):
        max_unit = 10
        consumer_uuid = uuidsentinel.consumer

        # Create a consumer representing the instance
        inst_consumer = consumer_obj.Consumer(
            self.ctx, uuid=consumer_uuid, user=self.user_obj,
            project=self.project_obj)
        inst_consumer.create()

        # Create two resource providers
        rp1_name = uuidsentinel.rp1_name
        rp1_uuid = uuidsentinel.rp1_uuid
        rp1_class = orc.DISK_GB
        rp1_used = 6

        rp2_name = uuidsentinel.rp2_name
        rp2_uuid = uuidsentinel.rp2_uuid
        rp2_class = orc.IPV4_ADDRESS
        rp2_used = 2

        rp1 = self._create_provider(rp1_name, uuid=rp1_uuid)
        rp2 = self._create_provider(rp2_name, uuid=rp2_uuid)

        # Two allocations, one for each resource provider.
        allocation_1 = alloc_obj.Allocation(
            resource_provider=rp1, consumer=inst_consumer,
            resource_class=rp1_class, used=rp1_used)
        allocation_2 = alloc_obj.Allocation(
            resource_provider=rp2, consumer=inst_consumer,
            resource_class=rp2_class, used=rp2_used)
        allocation_list = [allocation_1, allocation_2]

        # There's no inventory, we have a failure.
        error = self.assertRaises(exception.InvalidInventory,
                                  alloc_obj.replace_all, self.ctx,
                                  allocation_list)
        # Confirm that the resource class string, not index, is in
        # the exception and resource providers are listed by uuid.
        self.assertIn(rp1_class, str(error))
        self.assertIn(rp2_class, str(error))
        self.assertIn(rp1.uuid, str(error))
        self.assertIn(rp2.uuid, str(error))

        # Add inventory for one of the two resource providers. This should also
        # fail, since rp2 has no inventory.
        tb.add_inventory(rp1, rp1_class, 1024, max_unit=1)
        self.assertRaises(exception.InvalidInventory,
                          alloc_obj.replace_all, self.ctx, allocation_list)

        # Add inventory for the second resource provider
        tb.add_inventory(rp2, rp2_class, 255, reserved=2, max_unit=1)

        # Now the allocations will still fail because max_unit 1
        self.assertRaises(exception.InvalidAllocationConstraintsViolated,
                          alloc_obj.replace_all, self.ctx, allocation_list)
        inv1 = inv_obj.Inventory(resource_provider=rp1,
                                 resource_class=rp1_class,
                                 total=1024, max_unit=max_unit)
        rp1.set_inventory([inv1])
        inv2 = inv_obj.Inventory(resource_provider=rp2,
                                 resource_class=rp2_class,
                                 total=255, reserved=2, max_unit=max_unit)
        rp2.set_inventory([inv2])

        # Now we can finally allocate.
        alloc_obj.replace_all(self.ctx, allocation_list)

        # Check that those allocations changed usage on each
        # resource provider.
        rp1_usage = usage_obj.get_all_by_resource_provider_uuid(
            self.ctx, rp1_uuid)
        rp2_usage = usage_obj.get_all_by_resource_provider_uuid(
            self.ctx, rp2_uuid)
        self.assertEqual(rp1_used, rp1_usage[0].usage)
        self.assertEqual(rp2_used, rp2_usage[0].usage)

        # redo one allocation
        # TODO(cdent): This does not currently behave as expected
        # because a new allocation is created, adding to the total
        # used, not replacing.
        rp1_used += 1
        self.allocate_from_provider(
            rp1, rp1_class, rp1_used, consumer=inst_consumer)

        rp1_usage = usage_obj.get_all_by_resource_provider_uuid(
            self.ctx, rp1_uuid)
        self.assertEqual(rp1_used, rp1_usage[0].usage)

        # delete the allocations for the consumer
        # NOTE(cdent): The database uses 'consumer_id' for the
        # column, presumably because some ids might not be uuids, at
        # some point in the future.
        consumer_allocations = alloc_obj.get_all_by_consumer_id(
            self.ctx, consumer_uuid)
        alloc_obj.delete_all(self.ctx, consumer_allocations)

        rp1_usage = usage_obj.get_all_by_resource_provider_uuid(
            self.ctx, rp1_uuid)
        rp2_usage = usage_obj.get_all_by_resource_provider_uuid(
            self.ctx, rp2_uuid)
        self.assertEqual(0, rp1_usage[0].usage)
        self.assertEqual(0, rp2_usage[0].usage)

    def _make_rp_and_inventory(self, **kwargs):
        # Create one resource provider and set some inventory
        rp_name = kwargs.get('rp_name') or uuidsentinel.rp_name
        rp_uuid = kwargs.get('rp_uuid') or uuidsentinel.rp_uuid
        rp = self._create_provider(rp_name, uuid=rp_uuid)
        rc = kwargs.pop('resource_class')
        tb.add_inventory(rp, rc, 1024, **kwargs)
        return rp

    def _validate_usage(self, rp, usage):
        rp_usage = usage_obj.get_all_by_resource_provider_uuid(
            self.ctx, rp.uuid)
        self.assertEqual(usage, rp_usage[0].usage)

    def _check_create_allocations(self, inventory_kwargs,
                                  bad_used, good_used):
        rp_class = orc.DISK_GB
        rp = self._make_rp_and_inventory(resource_class=rp_class,
                                         **inventory_kwargs)

        # allocation, bad step_size
        self.assertRaises(exception.InvalidAllocationConstraintsViolated,
                          self.allocate_from_provider, rp, rp_class, bad_used)

        # correct for step size
        self.allocate_from_provider(rp, rp_class, good_used)

        # check usage
        self._validate_usage(rp, good_used)

    def test_create_all_step_size(self):
        bad_used = 4
        good_used = 5
        inventory_kwargs = {'max_unit': 9999, 'step_size': 5}

        self._check_create_allocations(inventory_kwargs,
                                       bad_used, good_used)

    def test_create_all_min_unit(self):
        bad_used = 4
        good_used = 5
        inventory_kwargs = {'max_unit': 9999, 'min_unit': 5}

        self._check_create_allocations(inventory_kwargs,
                                       bad_used, good_used)

    def test_create_all_max_unit(self):
        bad_used = 5
        good_used = 3
        inventory_kwargs = {'max_unit': 3}

        self._check_create_allocations(inventory_kwargs,
                                       bad_used, good_used)

    def test_create_and_clear(self):
        """Test that a used of 0 in an allocation wipes allocations."""
        consumer_uuid = uuidsentinel.consumer

        # Create a consumer representing the instance
        inst_consumer = consumer_obj.Consumer(
            self.ctx, uuid=consumer_uuid, user=self.user_obj,
            project=self.project_obj)
        inst_consumer.create()

        rp_class = orc.DISK_GB
        target_rp = self._make_rp_and_inventory(resource_class=rp_class,
                                                max_unit=500)

        # Create two allocations with values and confirm the resulting
        # usage is as expected.
        allocation1 = alloc_obj.Allocation(
            resource_provider=target_rp, consumer=inst_consumer,
            resource_class=rp_class, used=100)
        allocation2 = alloc_obj.Allocation(
            resource_provider=target_rp, consumer=inst_consumer,
            resource_class=rp_class, used=200)
        allocation_list = [allocation1, allocation2]
        alloc_obj.replace_all(self.ctx, allocation_list)

        allocations = alloc_obj.get_all_by_consumer_id(self.ctx, consumer_uuid)
        self.assertEqual(2, len(allocations))
        usage = sum(alloc.used for alloc in allocations)
        self.assertEqual(300, usage)

        # Create two allocations, one with 0 used, to confirm the
        # resulting usage is only of one.
        allocation1 = alloc_obj.Allocation(
            resource_provider=target_rp, consumer=inst_consumer,
            resource_class=rp_class, used=0)
        allocation2 = alloc_obj.Allocation(
            resource_provider=target_rp, consumer=inst_consumer,
            resource_class=rp_class, used=200)
        allocation_list = [allocation1, allocation2]
        alloc_obj.replace_all(self.ctx, allocation_list)

        allocations = alloc_obj.get_all_by_consumer_id(self.ctx, consumer_uuid)
        self.assertEqual(1, len(allocations))
        usage = allocations[0].used
        self.assertEqual(200, usage)

        # add a source rp and a migration consumer
        migration_uuid = uuidsentinel.migration

        # Create a consumer representing the migration
        mig_consumer = consumer_obj.Consumer(
            self.ctx, uuid=migration_uuid, user=self.user_obj,
            project=self.project_obj)
        mig_consumer.create()

        source_rp = self._make_rp_and_inventory(
            rp_name=uuidsentinel.source_name, rp_uuid=uuidsentinel.source_uuid,
            resource_class=rp_class, max_unit=500)

        # Create two allocations, one as the consumer, one as the
        # migration.
        allocation1 = alloc_obj.Allocation(
            resource_provider=target_rp, consumer=inst_consumer,
            resource_class=rp_class, used=200)
        allocation2 = alloc_obj.Allocation(
            resource_provider=source_rp, consumer=mig_consumer,
            resource_class=rp_class, used=200)
        allocation_list = [allocation1, allocation2]
        alloc_obj.replace_all(self.ctx, allocation_list)

        # Check primary consumer allocations.
        allocations = alloc_obj.get_all_by_consumer_id(self.ctx, consumer_uuid)
        self.assertEqual(1, len(allocations))
        usage = allocations[0].used
        self.assertEqual(200, usage)

        # Check migration allocations.
        allocations = alloc_obj.get_all_by_consumer_id(
            self.ctx, migration_uuid)
        self.assertEqual(1, len(allocations))
        usage = allocations[0].used
        self.assertEqual(200, usage)

        # Clear the migration and confirm the target.
        allocation1 = alloc_obj.Allocation(
            resource_provider=target_rp, consumer=inst_consumer,
            resource_class=rp_class, used=200)
        allocation2 = alloc_obj.Allocation(
            resource_provider=source_rp, consumer=mig_consumer,
            resource_class=rp_class, used=0)
        allocation_list = [allocation1, allocation2]
        alloc_obj.replace_all(self.ctx, allocation_list)

        allocations = alloc_obj.get_all_by_consumer_id(self.ctx, consumer_uuid)
        self.assertEqual(1, len(allocations))
        usage = allocations[0].used
        self.assertEqual(200, usage)

        allocations = alloc_obj.get_all_by_consumer_id(
            self.ctx, migration_uuid)
        self.assertEqual(0, len(allocations))

    def test_create_exceeding_capacity_allocation(self):
        """Tests on a list of allocations which contains an invalid allocation
        exceeds resource provider's capacity.

        Expect InvalidAllocationCapacityExceeded to be raised and all
        allocations in the list should not be applied.

        """
        empty_rp = self._create_provider('empty_rp')
        full_rp = self._create_provider('full_rp')

        for rp in (empty_rp, full_rp):
            tb.add_inventory(rp, orc.VCPU, 24,
                             allocation_ratio=16.0)
            tb.add_inventory(rp, orc.MEMORY_MB, 1024,
                             min_unit=64,
                             max_unit=1024,
                             step_size=64)

        # Create a consumer representing the instance
        inst_consumer = consumer_obj.Consumer(
            self.ctx, uuid=uuidsentinel.instance, user=self.user_obj,
            project=self.project_obj)
        inst_consumer.create()

        # First create a allocation to consume full_rp's resource.
        alloc_list = [
            alloc_obj.Allocation(
                consumer=inst_consumer,
                resource_provider=full_rp,
                resource_class=orc.VCPU,
                used=12),
            alloc_obj.Allocation(
                consumer=inst_consumer,
                resource_provider=full_rp,
                resource_class=orc.MEMORY_MB,
                used=1024)
        ]
        alloc_obj.replace_all(self.ctx, alloc_list)

        # Create a consumer representing the second instance
        inst2_consumer = consumer_obj.Consumer(
            self.ctx, uuid=uuidsentinel.instance2, user=self.user_obj,
            project=self.project_obj)
        inst2_consumer.create()

        # Create an allocation list consisting of valid requests and an invalid
        # request exceeding the memory full_rp can provide.
        alloc_list = [
            alloc_obj.Allocation(
                consumer=inst2_consumer,
                resource_provider=empty_rp,
                resource_class=orc.VCPU,
                used=12),
            alloc_obj.Allocation(
                consumer=inst2_consumer,
                resource_provider=empty_rp,
                resource_class=orc.MEMORY_MB,
                used=512),
            alloc_obj.Allocation(
                consumer=inst2_consumer,
                resource_provider=full_rp,
                resource_class=orc.VCPU,
                used=12),
            alloc_obj.Allocation(
                consumer=inst2_consumer,
                resource_provider=full_rp,
                resource_class=orc.MEMORY_MB,
                used=512),
        ]

        self.assertRaises(exception.InvalidAllocationCapacityExceeded,
                          alloc_obj.replace_all, self.ctx, alloc_list)

        # Make sure that allocations of both empty_rp and full_rp remain
        # unchanged.
        allocations = alloc_obj.get_all_by_resource_provider(self.ctx, full_rp)
        self.assertEqual(2, len(allocations))

        allocations = alloc_obj.get_all_by_resource_provider(
            self.ctx, empty_rp)
        self.assertEqual(0, len(allocations))

    @mock.patch('placement.objects.allocation.LOG')
    def test_set_allocations_retry(self, mock_log):
        """Test server side allocation write retry handling."""

        # Create a single resource provider and give it some inventory.
        rp1 = self._create_provider('rp1')
        tb.add_inventory(rp1, orc.VCPU, 24,
                         allocation_ratio=16.0)
        tb.add_inventory(rp1, orc.MEMORY_MB, 1024,
                         min_unit=64,
                         max_unit=1024,
                         step_size=64)
        original_generation = rp1.generation
        # Verify the generation is what we expect (we'll be checking again
        # later).
        self.assertEqual(2, original_generation)

        # Create a consumer and have it make an allocation.
        inst_consumer = consumer_obj.Consumer(
            self.ctx, uuid=uuidsentinel.instance, user=self.user_obj,
            project=self.project_obj)
        inst_consumer.create()

        alloc_list = [
            alloc_obj.Allocation(
                consumer=inst_consumer,
                resource_provider=rp1,
                resource_class=orc.VCPU,
                used=12),
            alloc_obj.Allocation(
                consumer=inst_consumer,
                resource_provider=rp1,
                resource_class=orc.MEMORY_MB,
                used=1024)
        ]

        # Make sure the right exception happens when the retry loop expires.
        self.conf_fixture.config(allocation_conflict_retry_count=0,
                                 group='placement')
        self.assertRaises(
            exception.ResourceProviderConcurrentUpdateDetected,
            alloc_obj.replace_all, self.ctx, alloc_list)
        mock_log.warning.assert_called_with(
            'Exceeded retry limit of %d on allocations write', 0)

        # Make sure the right thing happens after a small number of failures.
        # There's a bit of mock magic going on here to ensure that we can
        # both do some side effects on _set_allocations as well as have the
        # real behavior. Two generation conflicts and then a success.
        mock_log.reset_mock()
        self.conf_fixture.config(allocation_conflict_retry_count=3,
                                 group='placement')
        unmocked_set = alloc_obj._set_allocations
        with mock.patch('placement.objects.allocation.'
                        '_set_allocations') as mock_set:
            exceptions = iter([
                exception.ResourceProviderConcurrentUpdateDetected(),
                exception.ResourceProviderConcurrentUpdateDetected(),
            ])

            def side_effect(*args, **kwargs):
                try:
                    raise next(exceptions)
                except StopIteration:
                    return unmocked_set(*args, **kwargs)

            mock_set.side_effect = side_effect
            alloc_obj.replace_all(self.ctx, alloc_list)
            self.assertEqual(2, mock_log.debug.call_count)
            mock_log.debug.assert_has_calls(
                [mock.call('Retrying allocations write on resource provider '
                           'generation conflict')] * 2)
            self.assertEqual(3, mock_set.call_count)

        # Confirm we're using a different rp object after the change
        # and that it has a higher generation.
        new_rp = alloc_list[0].resource_provider
        self.assertEqual(original_generation, rp1.generation)
        self.assertEqual(original_generation + 1, new_rp.generation)
