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
from oslo_utils.fixture import uuidsentinel as uuids
import sqlalchemy as sa

from placement import db_api
from placement import exception
from placement.objects import allocation as alloc_obj
from placement.objects import consumer as consumer_obj
from placement.objects import project as project_obj
from placement.objects import resource_provider as rp_obj
from placement.objects import user as user_obj
from placement.tests.functional import base
from placement.tests.functional.db import test_base as tb


CONSUMER_TBL = consumer_obj.CONSUMER_TBL
PROJECT_TBL = project_obj.PROJECT_TBL
USER_TBL = user_obj.USER_TBL
ALLOC_TBL = rp_obj._ALLOC_TBL


class ConsumerTestCase(tb.PlacementDbBaseTestCase):
    def test_non_existing_consumer(self):
        self.assertRaises(
            exception.ConsumerNotFound,
            consumer_obj.Consumer.get_by_uuid, self.ctx,
            uuids.non_existing_consumer)

    def test_create_and_get(self):
        u = user_obj.User(self.ctx, external_id='another-user')
        u.create()
        p = project_obj.Project(self.ctx, external_id='another-project')
        p.create()
        c = consumer_obj.Consumer(
            self.ctx, uuid=uuids.consumer, user=u, project=p)
        c.create()
        c = consumer_obj.Consumer.get_by_uuid(self.ctx, uuids.consumer)
        self.assertEqual(1, c.id)
        # Project ID == 1 is fake-project created in setup
        self.assertEqual(2, c.project.id)
        # User ID == 1 is fake-user created in setup
        self.assertEqual(2, c.user.id)
        self.assertRaises(exception.ConsumerExists, c.create)

    def test_update(self):
        """Tests the scenario where a user supplies a different project/user ID
        for an allocation's consumer and we call Consumer.update() to save that
        information to the consumers table.
        """
        # First, create the consumer with the "fake-user" and "fake-project"
        # user/project in the base test class's setUp
        c = consumer_obj.Consumer(
            self.ctx, uuid=uuids.consumer, user=self.user_obj,
            project=self.project_obj)
        c.create()
        c = consumer_obj.Consumer.get_by_uuid(self.ctx, uuids.consumer)
        self.assertEqual(self.project_obj.id, c.project.id)
        self.assertEqual(self.user_obj.id, c.user.id)

        # Now change the consumer's project and user to a different project
        another_user = user_obj.User(self.ctx, external_id='another-user')
        another_user.create()
        another_proj = project_obj.Project(
            self.ctx, external_id='another-project')
        another_proj.create()

        c.project = another_proj
        c.user = another_user
        c.update()
        c = consumer_obj.Consumer.get_by_uuid(self.ctx, uuids.consumer)
        self.assertEqual(another_proj.id, c.project.id)
        self.assertEqual(another_user.id, c.user.id)


@db_api.placement_context_manager.reader
def _get_allocs_with_no_consumer_relationship(ctx):
    alloc_to_consumer = sa.outerjoin(
        ALLOC_TBL, CONSUMER_TBL,
        ALLOC_TBL.c.consumer_id == CONSUMER_TBL.c.uuid)
    sel = sa.select(ALLOC_TBL.c.consumer_id)
    sel = sel.select_from(alloc_to_consumer)
    sel = sel.where(CONSUMER_TBL.c.id.is_(None))
    return ctx.session.execute(sel).fetchall()


class CreateIncompleteAllocationsMixin(object):
    """Mixin for test setup to create some allocations with missing consumers
    """

    @db_api.placement_context_manager.writer
    def _create_leftover_consumer(self, ctx):
        ins_stmt = CONSUMER_TBL.insert().values(
            uuid=uuids.unknown_consumer,
            project_id=999,
            user_id=999)
        ctx.session.execute(ins_stmt)

    @db_api.placement_context_manager.writer
    def _create_incomplete_allocations(self, ctx, num_of_consumer_allocs=1):
        # Create some allocations with consumers that don't exist in the
        # consumers table to represent old allocations that we expect to be
        # "cleaned up" with consumers table records that point to the sentinel
        # project/user records.
        self._create_leftover_consumer(ctx)
        c1_missing_uuid = uuids.c1_missing
        c2_missing_uuid = uuids.c2_missing
        c3_missing_uuid = uuids.c3_missing
        for c_uuid in (c1_missing_uuid, c2_missing_uuid, c3_missing_uuid):
            # Create $num_of_consumer_allocs allocations per consumer with
            # different resource classes.
            for resource_class_id in range(num_of_consumer_allocs):
                ins_stmt = ALLOC_TBL.insert().values(
                    resource_provider_id=1,
                    resource_class_id=resource_class_id,
                    consumer_id=c_uuid, used=1)
                ctx.session.execute(ins_stmt)
        # Verify there are no records in the projects/users table
        project_count = ctx.session.scalar(
            sa.select(sa.func.count('*')).select_from(PROJECT_TBL))
        self.assertEqual(0, project_count)
        user_count = ctx.session.scalar(
            sa.select(sa.func.count('*')).select_from(USER_TBL))
        self.assertEqual(0, user_count)
        # Verify there are no consumer records for the missing consumers
        sel = CONSUMER_TBL.select().where(
            CONSUMER_TBL.c.uuid.in_([c1_missing_uuid, c2_missing_uuid]))
        res = ctx.session.execute(sel).fetchall()
        self.assertEqual(0, len(res))


# NOTE(jaypipes): The tb.PlacementDbBaseTestCase creates a project and user
# which is why we don't base off that. We want a completely bare DB for this
# test.
class CreateIncompleteConsumersTestCase(
        base.TestCase, CreateIncompleteAllocationsMixin):

    def setUp(self):
        super(CreateIncompleteConsumersTestCase, self).setUp()
        self.ctx = self.context

    def test_create_incomplete_consumers(self):
        """Test the online data migration that creates incomplete consumer
        records along with the incomplete consumer project/user records.
        """
        self._create_incomplete_allocations(self.ctx)
        # We do a "really online" online data migration for incomplete
        # consumers when calling alloc_obj.get_all_by_consumer_id() and
        # alloc_obj.get_all_by_resource_provider() and there are still
        # incomplete consumer records. So, to simulate a situation where the
        # operator has yet to run the nova-manage online_data_migration CLI
        # tool completely, we first call
        # consumer_obj.create_incomplete_consumers() with a batch size of 1.
        # This should mean there will be two allocation records still remaining
        # with a missing consumer record (since we create 3 total to begin
        # with).
        res = consumer_obj.create_incomplete_consumers(self.ctx, 1)
        self.assertEqual((1, 1), res)

        # Confirm there are still 2 incomplete allocations after one
        # iteration of the migration.
        res = _get_allocs_with_no_consumer_relationship(self.ctx)
        self.assertEqual(2, len(res))


class DeleteConsumerIfNoAllocsTestCase(tb.PlacementDbBaseTestCase):
    def test_delete_consumer_if_no_allocs(self):
        """alloc_obj.replace_all() should attempt to delete consumers that
        no longer have any allocations. Due to the REST API not having any way
        to query for consumers directly (only via the GET
        /allocations/{consumer_uuid} endpoint which returns an empty dict even
        when no consumer record exists for the {consumer_uuid}) we need to do
        this functional test using only the object layer.
        """
        # We will use two consumers in this test, only one of which will get
        # all of its allocations deleted in a transaction (and we expect that
        # consumer record to be deleted)
        c1 = consumer_obj.Consumer(
            self.ctx, uuid=uuids.consumer1, user=self.user_obj,
            project=self.project_obj)
        c1.create()
        c2 = consumer_obj.Consumer(
            self.ctx, uuid=uuids.consumer2, user=self.user_obj,
            project=self.project_obj)
        c2.create()

        # Create some inventory that we will allocate
        cn1 = self._create_provider('cn1')
        tb.add_inventory(cn1, orc.VCPU, 8)
        tb.add_inventory(cn1, orc.MEMORY_MB, 2048)
        tb.add_inventory(cn1, orc.DISK_GB, 2000)

        # Now allocate some of that inventory to two different consumers
        allocs = [
            alloc_obj.Allocation(
                consumer=c1, resource_provider=cn1,
                resource_class=orc.VCPU, used=1),
            alloc_obj.Allocation(
                consumer=c1, resource_provider=cn1,
                resource_class=orc.MEMORY_MB, used=512),
            alloc_obj.Allocation(
                consumer=c2, resource_provider=cn1,
                resource_class=orc.VCPU, used=1),
            alloc_obj.Allocation(
                consumer=c2, resource_provider=cn1,
                resource_class=orc.MEMORY_MB, used=512),
        ]
        alloc_obj.replace_all(self.ctx, allocs)

        # Validate that we have consumer records for both consumers
        for c_uuid in (uuids.consumer1, uuids.consumer2):
            c_obj = consumer_obj.Consumer.get_by_uuid(self.ctx, c_uuid)
            self.assertIsNotNone(c_obj)

        # OK, now "remove" the allocation for consumer2 by setting the used
        # value for both allocated resources to 0 and re-running the
        # alloc_obj.replace_all(). This should end up deleting the
        # consumer record for consumer2
        allocs = [
            alloc_obj.Allocation(
                consumer=c2, resource_provider=cn1,
                resource_class=orc.VCPU, used=0),
            alloc_obj.Allocation(
                consumer=c2, resource_provider=cn1,
                resource_class=orc.MEMORY_MB, used=0),
        ]
        alloc_obj.replace_all(self.ctx, allocs)

        # consumer1 should still exist...
        c_obj = consumer_obj.Consumer.get_by_uuid(self.ctx, uuids.consumer1)
        self.assertIsNotNone(c_obj)

        # but not consumer2...
        self.assertRaises(
            exception.NotFound, consumer_obj.Consumer.get_by_uuid,
            self.ctx, uuids.consumer2)

        # DELETE /allocations/{consumer_uuid} is the other place where we
        # delete all allocations for a consumer. Let's delete all for consumer1
        # and check that the consumer record is deleted
        alloc_list = alloc_obj.get_all_by_consumer_id(
            self.ctx, uuids.consumer1)
        alloc_obj.delete_all(self.ctx, alloc_list)

        # consumer1 should no longer exist in the DB since we just deleted all
        # of its allocations
        self.assertRaises(
            exception.NotFound, consumer_obj.Consumer.get_by_uuid,
            self.ctx, uuids.consumer1)
