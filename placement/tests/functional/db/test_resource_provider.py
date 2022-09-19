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
from oslo_db import exception as db_exc
from oslo_utils.fixture import uuidsentinel

from placement.db.sqlalchemy import models
from placement import exception
from placement import lib as placement_lib
from placement.objects import allocation as alloc_obj
from placement.objects import inventory as inv_obj
from placement.objects import research_context as res_ctx
from placement.objects import resource_provider as rp_obj
from placement.objects import trait as trait_obj
from placement.objects import usage as usage_obj
from placement.tests.functional.db import test_base as tb


class ResourceProviderTestCase(tb.PlacementDbBaseTestCase):
    """Test resource-provider objects' lifecycles."""

    def test_create_resource_provider_requires_uuid(self):
        resource_provider = rp_obj.ResourceProvider(context=self.ctx)
        self.assertRaises(exception.ObjectActionError,
                          resource_provider.create)

    def test_create_unknown_parent_provider(self):
        """Test that if we provide a parent_provider_uuid value that points to
        a resource provider that doesn't exist, that we get an
        ObjectActionError.
        """
        rp = rp_obj.ResourceProvider(
            context=self.ctx,
            name='rp1',
            uuid=uuidsentinel.rp1,
            parent_provider_uuid=uuidsentinel.noexists)
        exc = self.assertRaises(exception.ObjectActionError, rp.create)
        self.assertIn('parent provider UUID does not exist', str(exc))

    def test_create_with_parent_provider_uuid_same_as_uuid_fail(self):
        """Setting a parent provider UUID to one's own UUID makes no sense, so
        check we don't support it.
        """
        cn1 = rp_obj.ResourceProvider(
            context=self.ctx, uuid=uuidsentinel.cn1, name='cn1',
            parent_provider_uuid=uuidsentinel.cn1)

        exc = self.assertRaises(exception.ObjectActionError, cn1.create)
        self.assertIn('parent provider UUID cannot be same as UUID', str(exc))

    def test_create_resource_provider(self):
        created_resource_provider = self._create_provider(
            uuidsentinel.fake_resource_name,
            uuid=uuidsentinel.fake_resource_provider,
        )
        self.assertIsInstance(created_resource_provider.id, int)

        retrieved_resource_provider = rp_obj.ResourceProvider.get_by_uuid(
            self.ctx,
            uuidsentinel.fake_resource_provider
        )
        self.assertEqual(retrieved_resource_provider.id,
                         created_resource_provider.id)
        self.assertEqual(retrieved_resource_provider.uuid,
                         created_resource_provider.uuid)
        self.assertEqual(retrieved_resource_provider.name,
                         created_resource_provider.name)
        self.assertEqual(0, created_resource_provider.generation)
        self.assertEqual(0, retrieved_resource_provider.generation)
        self.assertIsNone(retrieved_resource_provider.parent_provider_uuid)

    def test_create_with_parent_provider_uuid(self):
        self._create_provider('p1', uuid=uuidsentinel.create_p)
        child = self._create_provider('c1', uuid=uuidsentinel.create_c,
                                      parent=uuidsentinel.create_p)
        self.assertEqual(uuidsentinel.create_c, child.uuid)
        self.assertEqual(uuidsentinel.create_p, child.parent_provider_uuid)
        self.assertEqual(uuidsentinel.create_p, child.root_provider_uuid)

    def test_inherit_root_from_parent(self):
        """Tests that if we update an existing provider's parent provider UUID,
        that the root provider UUID of the updated provider is automatically
        set to the parent provider's root provider UUID.
        """
        rp1 = self._create_provider('rp1')

        # Test the root was auto-set to the create provider's UUID
        self.assertEqual(uuidsentinel.rp1, rp1.root_provider_uuid)

        # Create a new provider that we will make the parent of rp1
        parent_rp = self._create_provider('parent')
        self.assertEqual(uuidsentinel.parent, parent_rp.root_provider_uuid)

        # Now change rp1 to be a child of parent and check rp1's root is
        # changed to that of the parent.
        rp1.parent_provider_uuid = parent_rp.uuid
        rp1.save()

        self.assertEqual(uuidsentinel.parent, rp1.root_provider_uuid)

    def test_save_unknown_parent_provider(self):
        """Test that if we provide a parent_provider_uuid value that points to
        a resource provider that doesn't exist, that we get an
        ObjectActionError if we save the object.
        """
        self.assertRaises(
            exception.ObjectActionError,
            self._create_provider, 'rp1', parent=uuidsentinel.noexists)

    def test_save_resource_provider(self):
        created_resource_provider = self._create_provider(
            uuidsentinel.fake_resource_name,
            uuid=uuidsentinel.fake_resource_provider,
        )
        created_resource_provider.name = 'new-name'
        created_resource_provider.save()
        retrieved_resource_provider = rp_obj.ResourceProvider.get_by_uuid(
            self.ctx,
            uuidsentinel.fake_resource_provider
        )
        self.assertEqual('new-name', retrieved_resource_provider.name)

    def test_get_subtree(self):
        root1 = self._create_provider('root1')
        child1 = self._create_provider('child1', parent=root1.uuid)
        child2 = self._create_provider('child2', parent=root1.uuid)
        grandchild1 = self._create_provider('grandchild1', parent=child1.uuid)
        grandchild2 = self._create_provider('grandchild2', parent=child1.uuid)
        grandchild3 = self._create_provider('grandchild3', parent=child2.uuid)
        grandchild4 = self._create_provider('grandchild4', parent=child2.uuid)

        self.assertEqual(
            {grandchild1.uuid},
            {rp.uuid for rp in grandchild1.get_subtree(self.context)})
        self.assertEqual(
            {child1.uuid, grandchild1.uuid, grandchild2.uuid},
            {rp.uuid for rp in child1.get_subtree(self.context)})
        self.assertEqual(
            {child2.uuid, grandchild3.uuid, grandchild4.uuid},
            {rp.uuid for rp in child2.get_subtree(self.context)})
        self.assertEqual(
            {root1.uuid, child1.uuid, child2.uuid,
             grandchild1.uuid, grandchild2.uuid, grandchild3.uuid,
             grandchild4.uuid},
            {rp.uuid for rp in root1.get_subtree(self.context)})

    def test_save_reparenting_not_allowed(self):
        """Tests that we prevent a resource provider's parent provider UUID
        from being changed from a non-NULL value to another non-NULL value if
        not explicitly requested.
        """
        cn1 = self._create_provider('cn1')
        self._create_provider('cn2')
        self._create_provider('cn3')

        # First, make sure we can set the parent for a provider that does not
        # have a parent currently
        cn1.parent_provider_uuid = uuidsentinel.cn2
        cn1.save()

        # Now make sure we can't change the parent provider
        cn1.parent_provider_uuid = uuidsentinel.cn3
        exc = self.assertRaises(exception.ObjectActionError, cn1.save)
        self.assertIn('re-parenting a provider is not currently', str(exc))

        # Also ensure that we can't "un-parent" a provider
        cn1.parent_provider_uuid = None
        exc = self.assertRaises(exception.ObjectActionError, cn1.save)
        self.assertIn('un-parenting a provider is not currently', str(exc))

    def test_save_reparent_same_tree(self):
        root1 = self._create_provider('root1')
        child1 = self._create_provider('child1', parent=root1.uuid)
        child2 = self._create_provider('child2', parent=root1.uuid)
        self._create_provider('grandchild1', parent=child1.uuid)
        self._create_provider('grandchild2', parent=child1.uuid)
        self._create_provider('grandchild3', parent=child2.uuid)
        self._create_provider('grandchild4', parent=child2.uuid)

        test_rp = self._create_provider('test_rp', parent=child1.uuid)
        test_rp_child = self._create_provider(
            'test_rp_child', parent=test_rp.uuid)

        # move test_rp RP upwards
        test_rp.parent_provider_uuid = root1.uuid
        test_rp.save(allow_reparenting=True)

        # to make sure that this re-parenting does not effect the child test RP
        # in the db we need to reload it before we assert any change
        test_rp_child = rp_obj.ResourceProvider.get_by_uuid(
            self.ctx, test_rp_child.uuid)

        self.assertEqual(root1.uuid, test_rp.parent_provider_uuid)
        self.assertEqual(root1.uuid, test_rp.root_provider_uuid)
        self.assertEqual(test_rp.uuid, test_rp_child.parent_provider_uuid)
        self.assertEqual(root1.uuid, test_rp_child.root_provider_uuid)

        # move downwards
        test_rp.parent_provider_uuid = child1.uuid
        test_rp.save(allow_reparenting=True)

        # to make sure that this re-parenting does not effect the child test RP
        # in the db we need to reload it before we assert any change
        test_rp_child = rp_obj.ResourceProvider.get_by_uuid(
            self.ctx, test_rp_child.uuid)

        self.assertEqual(child1.uuid, test_rp.parent_provider_uuid)
        self.assertEqual(root1.uuid, test_rp.root_provider_uuid)
        self.assertEqual(test_rp.uuid, test_rp_child.parent_provider_uuid)
        self.assertEqual(root1.uuid, test_rp_child.root_provider_uuid)

        # move sideways
        test_rp.parent_provider_uuid = child2.uuid
        test_rp.save(allow_reparenting=True)

        # to make sure that this re-parenting does not effect the child test RP
        # in the db we need to reload it before we assert any change
        test_rp_child = rp_obj.ResourceProvider.get_by_uuid(
            self.ctx, test_rp_child.uuid)

        self.assertEqual(child2.uuid, test_rp.parent_provider_uuid)
        self.assertEqual(root1.uuid, test_rp.root_provider_uuid)
        self.assertEqual(test_rp.uuid, test_rp_child.parent_provider_uuid)
        self.assertEqual(root1.uuid, test_rp_child.root_provider_uuid)

    def test_save_reparent_another_tree(self):
        root1 = self._create_provider('root1')
        child1 = self._create_provider('child1', parent=root1.uuid)
        self._create_provider('child2', parent=root1.uuid)

        root2 = self._create_provider('root2')
        self._create_provider('child3', parent=root2.uuid)
        child4 = self._create_provider('child4', parent=root2.uuid)

        test_rp = self._create_provider('test_rp', parent=child1.uuid)
        test_rp_child = self._create_provider(
            'test_rp_child', parent=test_rp.uuid)

        test_rp.parent_provider_uuid = child4.uuid
        test_rp.save(allow_reparenting=True)

        # the re-parenting affected the the child test RP in the db so we
        # have to reload it and assert the change
        test_rp_child = rp_obj.ResourceProvider.get_by_uuid(
            self.ctx, test_rp_child.uuid)

        self.assertEqual(child4.uuid, test_rp.parent_provider_uuid)
        self.assertEqual(root2.uuid, test_rp.root_provider_uuid)
        self.assertEqual(test_rp.uuid, test_rp_child.parent_provider_uuid)
        self.assertEqual(root2.uuid, test_rp_child.root_provider_uuid)

    def test_save_reparent_to_new_root(self):
        root1 = self._create_provider('root1')
        child1 = self._create_provider('child1', parent=root1.uuid)

        test_rp = self._create_provider('test_rp', parent=child1.uuid)
        test_rp_child = self._create_provider(
            'test_rp_child', parent=test_rp.uuid)

        # we are creating a new root from a subtree, a.k.a un-parenting
        test_rp.parent_provider_uuid = None
        test_rp.save(allow_reparenting=True)

        # the un-parenting affected the the child test RP in the db so we
        # have to reload it and assert the change
        test_rp_child = rp_obj.ResourceProvider.get_by_uuid(
            self.ctx, test_rp_child.uuid)

        self.assertIsNone(test_rp.parent_provider_uuid)
        self.assertEqual(test_rp.uuid, test_rp.root_provider_uuid)
        self.assertEqual(test_rp.uuid, test_rp_child.parent_provider_uuid)
        self.assertEqual(test_rp.uuid, test_rp_child.root_provider_uuid)

    def test_save_reparent_the_root(self):
        root1 = self._create_provider('root1')
        child1 = self._create_provider('child1', parent=root1.uuid)

        # now the test_rp is also a root RP
        test_rp = self._create_provider('test_rp')
        test_rp_child = self._create_provider(
            'test_rp_child', parent=test_rp.uuid)

        test_rp.parent_provider_uuid = child1.uuid
        test_rp.save(allow_reparenting=True)

        # the re-parenting affected the the child test RP in the db so we
        # have to reload it and assert the change
        test_rp_child = rp_obj.ResourceProvider.get_by_uuid(
            self.ctx, test_rp_child.uuid)

        self.assertEqual(child1.uuid, test_rp.parent_provider_uuid)
        self.assertEqual(root1.uuid, test_rp.root_provider_uuid)
        self.assertEqual(test_rp.uuid, test_rp_child.parent_provider_uuid)
        self.assertEqual(root1.uuid, test_rp_child.root_provider_uuid)

    def test_save_reparent_loop_fail(self):
        root1 = self._create_provider('root1')

        test_rp = self._create_provider('test_rp', parent=root1.uuid)
        test_rp_child = self._create_provider(
            'test_rp_child', parent=test_rp.uuid)
        test_rp_grandchild = self._create_provider(
            'test_rp_grandchild', parent=test_rp_child.uuid)

        # self loop, i.e. we are our parents
        test_rp.parent_provider_uuid = test_rp.uuid
        exc = self.assertRaises(
            exception.ObjectActionError, test_rp.save, allow_reparenting=True)
        self.assertIn(
            'creating loop in the provider tree is not allowed.', str(exc))

        # direct loop, i.e. our child is our parent
        test_rp.parent_provider_uuid = test_rp_child.uuid
        exc = self.assertRaises(
            exception.ObjectActionError, test_rp.save, allow_reparenting=True)
        self.assertIn(
            'creating loop in the provider tree is not allowed.', str(exc))

        # indirect loop, i.e. our grandchild is our parent
        test_rp.parent_provider_uuid = test_rp_grandchild.uuid
        exc = self.assertRaises(
            exception.ObjectActionError, test_rp.save, allow_reparenting=True)
        self.assertIn(
            'creating loop in the provider tree is not allowed.', str(exc))

    def test_nested_providers(self):
        """Create a hierarchy of resource providers and run through a series of
        tests that ensure one cannot delete a resource provider that has no
        direct allocations but its child providers do have allocations.
        """
        root_rp = self._create_provider('root_rp')
        child_rp = self._create_provider('child_rp',
                                         parent=uuidsentinel.root_rp)
        grandchild_rp = self._create_provider('grandchild_rp',
                                              parent=uuidsentinel.child_rp)

        # Verify that the root_provider_uuid of both the child and the
        # grandchild is the UUID of the grandparent
        self.assertEqual(root_rp.uuid, child_rp.root_provider_uuid)
        self.assertEqual(root_rp.uuid, grandchild_rp.root_provider_uuid)

        # Create some inventory in the grandchild, allocate some consumers to
        # the grandchild and then attempt to delete the root provider and child
        # provider, both of which should fail.
        tb.add_inventory(grandchild_rp, orc.VCPU, 1)

        # Check all providers returned when getting by root UUID
        rps = rp_obj.get_all_by_filters(
            self.ctx,
            filters={
                'in_tree': uuidsentinel.root_rp,
            }
        )
        self.assertEqual(3, len(rps))

        # Check all providers returned when getting by child UUID
        rps = rp_obj.get_all_by_filters(
            self.ctx,
            filters={
                'in_tree': uuidsentinel.child_rp,
            }
        )
        self.assertEqual(3, len(rps))

        # Check all providers returned when getting by grandchild UUID
        rps = rp_obj.get_all_by_filters(
            self.ctx,
            filters={
                'in_tree': uuidsentinel.grandchild_rp,
            }
        )
        self.assertEqual(3, len(rps))

        # Make sure that the member_of and uuid filters work with the in_tree
        # filter

        # No aggregate associations yet, so expect no records when adding a
        # member_of filter
        rps = rp_obj.get_all_by_filters(
            self.ctx,
            filters={
                'member_of': [[uuidsentinel.agg]],
                'in_tree': uuidsentinel.grandchild_rp,
            }
        )
        self.assertEqual(0, len(rps))

        # OK, associate the grandchild with an aggregate and verify that ONLY
        # the grandchild is returned when asking for the grandchild's tree
        # along with the aggregate as member_of
        grandchild_rp.set_aggregates([uuidsentinel.agg])
        rps = rp_obj.get_all_by_filters(
            self.ctx,
            filters={
                'member_of': [[uuidsentinel.agg]],
                'in_tree': uuidsentinel.grandchild_rp,
            }
        )
        self.assertEqual(1, len(rps))
        self.assertEqual(uuidsentinel.grandchild_rp, rps[0].uuid)

        # Try filtering on an unknown UUID and verify no results
        rps = rp_obj.get_all_by_filters(
            self.ctx,
            filters={
                'uuid': uuidsentinel.unknown_rp,
                'in_tree': uuidsentinel.grandchild_rp,
            }
        )
        self.assertEqual(0, len(rps))

        # And now check that filtering for just the child's UUID along with the
        # tree produces just a single provider (the child)
        rps = rp_obj.get_all_by_filters(
            self.ctx,
            filters={
                'uuid': uuidsentinel.child_rp,
                'in_tree': uuidsentinel.grandchild_rp,
            }
        )
        self.assertEqual(1, len(rps))
        self.assertEqual(uuidsentinel.child_rp, rps[0].uuid)

        # Ensure that the resources filter also continues to work properly with
        # the in_tree filter. Request resources that none of the providers
        # currently have and ensure no providers are returned
        rps = rp_obj.get_all_by_filters(
            self.ctx,
            filters={
                'in_tree': uuidsentinel.grandchild_rp,
                'resources': {
                    'VCPU': 200,
                }
            }
        )
        self.assertEqual(0, len(rps))

        # And now ask for one VCPU, which should only return us the grandchild
        rps = rp_obj.get_all_by_filters(
            self.ctx,
            filters={
                'in_tree': uuidsentinel.grandchild_rp,
                'resources': {
                    'VCPU': 1,
                }
            }
        )
        self.assertEqual(1, len(rps))
        self.assertEqual(uuidsentinel.grandchild_rp, rps[0].uuid)

        # Finally, verify we still get the grandchild if filtering on the
        # parent's UUID as in_tree
        rps = rp_obj.get_all_by_filters(
            self.ctx,
            filters={
                'in_tree': uuidsentinel.child_rp,
                'resources': {
                    'VCPU': 1,
                }
            }
        )
        self.assertEqual(1, len(rps))
        self.assertEqual(uuidsentinel.grandchild_rp, rps[0].uuid)

        alloc_list = self.allocate_from_provider(
            grandchild_rp, orc.VCPU, 1)

        self.assertRaises(exception.CannotDeleteParentResourceProvider,
                          root_rp.destroy)
        self.assertRaises(exception.CannotDeleteParentResourceProvider,
                          child_rp.destroy)

        # Cannot delete provider if it has allocations
        self.assertRaises(exception.ResourceProviderInUse,
                          grandchild_rp.destroy)

        # Now remove the allocations against the child and check that we can
        # now delete the child provider
        alloc_obj.delete_all(self.ctx, alloc_list)
        grandchild_rp.destroy()
        child_rp.destroy()
        root_rp.destroy()

    def test_has_provider_trees(self):
        """The _has_provider_trees() helper method should return False unless
        there is a resource provider that is a parent.
        """
        self.assertFalse(res_ctx._has_provider_trees(self.ctx))
        self._create_provider('cn')

        # No parents yet. Should still be False.
        self.assertFalse(res_ctx._has_provider_trees(self.ctx))

        self._create_provider('numa0', parent=uuidsentinel.cn)

        # OK, now we've got a parent, so should be True
        self.assertTrue(res_ctx._has_provider_trees(self.ctx))

    def test_destroy_resource_provider(self):
        created_resource_provider = self._create_provider(
            uuidsentinel.fake_resource_name,
            uuid=uuidsentinel.fake_resource_provider,
        )
        created_resource_provider.destroy()
        self.assertRaises(exception.NotFound,
                          rp_obj.ResourceProvider.get_by_uuid,
                          self.ctx,
                          uuidsentinel.fake_resource_provider)
        self.assertRaises(exception.NotFound,
                          created_resource_provider.destroy)

    def test_destroy_foreign_key(self):
        """This tests bug #1739571."""

        def emulate_rp_mysql_delete(func):
            def wrapped(context, _id):
                query = context.session.query(models.ResourceProvider)
                query = query.filter(models.ResourceProvider.id == _id)
                rp = query.first()
                self.assertIsNone(rp.root_provider_id)
                return func(context, _id)
            return wrapped

        emulated = emulate_rp_mysql_delete(rp_obj._delete_rp_record)

        rp = self._create_provider(uuidsentinel.fk)

        with mock.patch.object(rp_obj, '_delete_rp_record', emulated):
            rp.destroy()

    def test_destroy_allocated_resource_provider_fails(self):
        rp, allocation = self._make_allocation(tb.DISK_INVENTORY,
                                               tb.DISK_ALLOCATION)
        self.assertRaises(exception.ResourceProviderInUse,
                          rp.destroy)

    def test_destroy_resource_provider_destroy_inventory(self):
        resource_provider = self._create_provider(
            uuidsentinel.fake_resource_name,
            uuid=uuidsentinel.fake_resource_provider,
        )
        tb.add_inventory(resource_provider,
                         tb.DISK_INVENTORY['resource_class'],
                         tb.DISK_INVENTORY['total'])
        inventories = inv_obj.get_all_by_resource_provider(
            self.ctx, resource_provider)
        self.assertEqual(1, len(inventories))
        resource_provider.destroy()
        inventories = inv_obj.get_all_by_resource_provider(
            self.ctx, resource_provider)
        self.assertEqual(0, len(inventories))

    def test_destroy_with_traits(self):
        """Test deleting a resource provider that has a trait successfully.
        """
        rp = self._create_provider('fake_rp1', uuid=uuidsentinel.fake_rp1)
        custom_trait = 'CUSTOM_TRAIT_1'
        tb.set_traits(rp, custom_trait)

        trl = trait_obj.get_all_by_resource_provider(self.ctx, rp)
        self.assertEqual(1, len(trl))

        # Delete a resource provider that has a trait association.
        rp.destroy()

        # Assert the record has been deleted
        # in 'resource_provider_traits' table
        # after Resource Provider object has been destroyed.
        trl = trait_obj.get_all_by_resource_provider(self.ctx, rp)
        self.assertEqual(0, len(trl))
        # Assert that NotFound exception is raised.
        self.assertRaises(exception.NotFound,
                          rp_obj.ResourceProvider.get_by_uuid,
                          self.ctx, uuidsentinel.fake_rp1)

    def test_set_traits_for_resource_provider(self):
        rp = self._create_provider('fake_resource_provider')
        generation = rp.generation
        self.assertIsInstance(rp.id, int)

        trait_names = ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B', 'CUSTOM_TRAIT_C']
        tb.set_traits(rp, *trait_names)

        rp_traits = trait_obj.get_all_by_resource_provider(self.ctx, rp)
        self._assert_traits(trait_names, rp_traits)
        self.assertEqual(rp.generation, generation + 1)
        generation = rp.generation

        trait_names.remove('CUSTOM_TRAIT_A')
        updated_traits = trait_obj.get_all(
            self.ctx, filters={'name_in': trait_names})
        self._assert_traits(trait_names, updated_traits)
        tb.set_traits(rp, *trait_names)
        rp_traits = trait_obj.get_all_by_resource_provider(self.ctx, rp)
        self._assert_traits(trait_names, rp_traits)
        self.assertEqual(rp.generation, generation + 1)

    def test_set_traits_for_correct_resource_provider(self):
        """This test creates two ResourceProviders, and attaches same trait to
        both of them. Then detaching the trait from one of them, and ensure
        the trait still associated with another one.
        """
        # Create two ResourceProviders
        rp1 = self._create_provider('fake_resource_provider1')
        rp2 = self._create_provider('fake_resource_provider2')

        tname = 'CUSTOM_TRAIT_A'

        # Associate the trait with two ResourceProviders
        tb.set_traits(rp1, tname)
        tb.set_traits(rp2, tname)

        # Ensure the association
        rp1_traits = trait_obj.get_all_by_resource_provider(self.ctx, rp1)
        rp2_traits = trait_obj.get_all_by_resource_provider(self.ctx, rp2)
        self._assert_traits([tname], rp1_traits)
        self._assert_traits([tname], rp2_traits)

        # Detach the trait from one of ResourceProvider, and ensure the
        # trait association with another ResourceProvider still exists.
        tb.set_traits(rp1)
        rp1_traits = trait_obj.get_all_by_resource_provider(self.ctx, rp1)
        rp2_traits = trait_obj.get_all_by_resource_provider(self.ctx, rp2)
        self._assert_traits([], rp1_traits)
        self._assert_traits([tname], rp2_traits)

    def test_set_inventory_unknown_resource_class(self):
        """Test attempting to set inventory to an unknown resource class raises
        an exception.
        """
        rp = self._create_provider('compute-host')
        inv = inv_obj.Inventory(
            rp._context, resource_provider=rp,
            resource_class='UNKNOWN',
            total=1024,
            reserved=15,
            min_unit=10,
            max_unit=100,
            step_size=10,
            allocation_ratio=1.0)
        self.assertRaises(
            exception.ResourceClassNotFound, rp.add_inventory, inv)

    def test_set_inventory_fail_in_use(self):
        """Test attempting to set inventory which would result in removing an
        inventory record for a resource class that still has allocations
        against it.
        """
        rp = self._create_provider('compute-host')
        tb.add_inventory(rp, 'VCPU', 12)
        self.allocate_from_provider(rp, 'VCPU', 1)

        inv = inv_obj.Inventory(
            resource_provider=rp,
            resource_class='MEMORY_MB',
            total=1024,
            reserved=0,
            min_unit=256,
            max_unit=1024,
            step_size=256,
            allocation_ratio=1.0,
        )

        self.assertRaises(exception.InventoryInUse,
                          rp.set_inventory,
                          [inv])

    @mock.patch('placement.objects.resource_provider.LOG')
    def test_set_inventory_over_capacity(self, mock_log):
        rp = self._create_provider(uuidsentinel.rp_name)

        disk_inv = tb.add_inventory(rp, orc.DISK_GB, 2048,
                                    reserved=15,
                                    min_unit=10,
                                    max_unit=600,
                                    step_size=10)
        vcpu_inv = tb.add_inventory(rp, orc.VCPU, 12,
                                    allocation_ratio=16.0)

        self.assertFalse(mock_log.warning.called)

        # Allocate something reasonable for the above inventory
        self.allocate_from_provider(rp, 'DISK_GB', 500)

        # Update our inventory to over-subscribe us after the above allocation
        disk_inv.total = 400
        rp.set_inventory([disk_inv, vcpu_inv])

        # We should succeed, but have logged a warning for going over on disk
        mock_log.warning.assert_called_once_with(
            mock.ANY, {'uuid': rp.uuid, 'resource': 'DISK_GB'})

    def test_provider_modify_inventory(self):
        rp = self._create_provider(uuidsentinel.rp_name)
        saved_generation = rp.generation

        disk_inv = tb.add_inventory(rp, orc.DISK_GB, 1024,
                                    reserved=15,
                                    min_unit=10,
                                    max_unit=100,
                                    step_size=10)

        vcpu_inv = tb.add_inventory(rp, orc.VCPU, 12,
                                    allocation_ratio=16.0)

        # generation has bumped once for each add
        self.assertEqual(saved_generation + 2, rp.generation)
        saved_generation = rp.generation

        new_inv_list = inv_obj.get_all_by_resource_provider(self.ctx, rp)
        self.assertEqual(2, len(new_inv_list))
        resource_classes = [inv.resource_class for inv in new_inv_list]
        self.assertIn(orc.VCPU, resource_classes)
        self.assertIn(orc.DISK_GB, resource_classes)

        # reset inventory to just disk_inv
        rp.set_inventory([disk_inv])

        # generation has bumped
        self.assertEqual(saved_generation + 1, rp.generation)
        saved_generation = rp.generation

        new_inv_list = inv_obj.get_all_by_resource_provider(self.ctx, rp)
        self.assertEqual(1, len(new_inv_list))
        resource_classes = [inv.resource_class for inv in new_inv_list]
        self.assertNotIn(orc.VCPU, resource_classes)
        self.assertIn(orc.DISK_GB, resource_classes)
        self.assertEqual(1024, new_inv_list[0].total)

        # update existing disk inv to new settings
        disk_inv = inv_obj.Inventory(
            resource_provider=rp,
            resource_class=orc.DISK_GB,
            total=2048,
            reserved=15,
            min_unit=10,
            max_unit=100,
            step_size=10,
            allocation_ratio=1.0)
        rp.update_inventory(disk_inv)

        # generation has bumped
        self.assertEqual(saved_generation + 1, rp.generation)
        saved_generation = rp.generation

        new_inv_list = inv_obj.get_all_by_resource_provider(self.ctx, rp)
        self.assertEqual(1, len(new_inv_list))
        self.assertEqual(2048, new_inv_list[0].total)

        # delete inventory
        rp.delete_inventory(orc.DISK_GB)

        # generation has bumped
        self.assertEqual(saved_generation + 1, rp.generation)
        saved_generation = rp.generation

        new_inv_list = inv_obj.get_all_by_resource_provider(self.ctx, rp)
        result = inv_obj.find(new_inv_list, orc.DISK_GB)
        self.assertIsNone(result)
        self.assertRaises(exception.NotFound, rp.delete_inventory,
                          orc.DISK_GB)

        # check inventory list is empty
        inv_list = inv_obj.get_all_by_resource_provider(self.ctx, rp)
        self.assertEqual(0, len(inv_list))

        # add some inventory
        rp.add_inventory(vcpu_inv)
        inv_list = inv_obj.get_all_by_resource_provider(self.ctx, rp)
        self.assertEqual(1, len(inv_list))

        # generation has bumped
        self.assertEqual(saved_generation + 1, rp.generation)
        saved_generation = rp.generation

        # add same inventory again
        self.assertRaises(db_exc.DBDuplicateEntry,
                          rp.add_inventory, vcpu_inv)

        # generation has not bumped
        self.assertEqual(saved_generation, rp.generation)

        # fail when generation wrong
        rp.generation = rp.generation - 1
        self.assertRaises(exception.ConcurrentUpdateDetected,
                          rp.set_inventory, inv_list)

    def test_delete_inventory_not_found(self):
        rp = self._create_provider(uuidsentinel.rp_name)
        error = self.assertRaises(exception.NotFound, rp.delete_inventory,
                                  'DISK_GB')
        self.assertIn('No inventory of class DISK_GB found for delete',
                      str(error))

    def test_delete_inventory_with_allocation(self):
        rp, allocation = self._make_allocation(tb.DISK_INVENTORY,
                                               tb.DISK_ALLOCATION)
        error = self.assertRaises(exception.InventoryInUse,
                                  rp.delete_inventory,
                                  'DISK_GB')
        self.assertIn(
            "Inventory for 'DISK_GB' on resource provider '%s' in use"
            % rp.uuid, str(error))

    def test_update_inventory_not_found(self):
        rp = self._create_provider(uuidsentinel.rp_name)
        disk_inv = inv_obj.Inventory(resource_provider=rp,
                                     resource_class='DISK_GB',
                                     total=2048)
        error = self.assertRaises(exception.NotFound, rp.update_inventory,
                                  disk_inv)
        self.assertIn('No inventory of class DISK_GB found',
                      str(error))

    @mock.patch('placement.objects.resource_provider.LOG')
    def test_update_inventory_violates_allocation(self, mock_log):
        # Compute nodes that are reconfigured have to be able to set
        # their inventory to something that violates allocations so
        # we need to make that possible.
        rp, allocation = self._make_allocation(tb.DISK_INVENTORY,
                                               tb.DISK_ALLOCATION)
        # attempt to set inventory to less than currently allocated
        # amounts
        new_total = 1
        disk_inv = inv_obj.Inventory(
            resource_provider=rp,
            resource_class=orc.DISK_GB, total=new_total)
        rp.update_inventory(disk_inv)

        usages = usage_obj.get_all_by_resource_provider_uuid(
            self.ctx, rp.uuid)
        self.assertEqual(allocation.used, usages[0].usage)

        inv_list = inv_obj.get_all_by_resource_provider(self.ctx, rp)
        self.assertEqual(new_total, inv_list[0].total)
        mock_log.warning.assert_called_once_with(
            mock.ANY, {'uuid': rp.uuid, 'resource': 'DISK_GB'})

    def test_add_allocation_increments_generation(self):
        rp = self._create_provider(name='foo')
        tb.add_inventory(rp, tb.DISK_INVENTORY['resource_class'],
                         tb.DISK_INVENTORY['total'])
        expected_gen = rp.generation + 1
        self.allocate_from_provider(rp, tb.DISK_ALLOCATION['resource_class'],
                                    tb.DISK_ALLOCATION['used'])
        self.assertEqual(expected_gen, rp.generation)

    def test_get_all_by_resource_provider_multiple_providers(self):
        rp1 = self._create_provider('cn1')
        rp2 = self._create_provider(name='cn2')

        for rp in (rp1, rp2):
            tb.add_inventory(rp, tb.DISK_INVENTORY['resource_class'],
                             tb.DISK_INVENTORY['total'])
            tb.add_inventory(rp, orc.IPV4_ADDRESS, 10,
                             max_unit=2)

        # Get inventories for the first resource provider and validate
        # the inventory records have a matching resource provider
        got_inv = inv_obj.get_all_by_resource_provider(self.ctx, rp1)
        for inv in got_inv:
            self.assertEqual(rp1.id, inv.resource_provider.id)


class ResourceProviderListTestCase(tb.PlacementDbBaseTestCase):
    def _run_get_all_by_filters(self, expected_rps, filters=None):
        '''Helper function to validate get_all_by_filters()'''
        resource_providers = rp_obj.get_all_by_filters(self.ctx,
                                                       filters=filters)
        self.assertEqual(len(expected_rps), len(resource_providers))
        rp_names = set([rp.name for rp in resource_providers])
        self.assertEqual(set(expected_rps), rp_names)
        return resource_providers

    def test_get_all_by_filters(self):
        for rp_i in ['1', '2']:
            self._create_provider('rp_' + rp_i)

        expected_rps = ['rp_1', 'rp_2']
        self._run_get_all_by_filters(expected_rps)

        filters = {'name': 'rp_1'}
        expected_rps = ['rp_1']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        filters = {'uuid': uuidsentinel.rp_2}
        expected_rps = ['rp_2']
        self._run_get_all_by_filters(expected_rps, filters=filters)

    def test_get_all_by_filters_with_resources(self):
        for rp_i in ['1', '2']:
            rp = self._create_provider('rp_' + rp_i)
            tb.add_inventory(rp, orc.VCPU, 2)
            tb.add_inventory(rp, orc.DISK_GB, 1024,
                             reserved=2)
            # Write a specific inventory for testing min/max units and steps
            tb.add_inventory(rp, orc.MEMORY_MB, 1024,
                             reserved=2, min_unit=2, max_unit=4, step_size=2)

            # Create the VCPU allocation only for the first RP
            if rp_i != '1':
                continue
            self.allocate_from_provider(rp, orc.VCPU, used=1)

        # Both RPs should accept that request given the only current allocation
        # for the first RP is leaving one VCPU
        filters = {'resources': {orc.VCPU: 1}}
        expected_rps = ['rp_1', 'rp_2']
        self._run_get_all_by_filters(expected_rps, filters=filters)
        # Now, when asking for 2 VCPUs, only the second RP should accept that
        # given the current allocation for the first RP
        filters = {'resources': {orc.VCPU: 2}}
        expected_rps = ['rp_2']
        self._run_get_all_by_filters(expected_rps, filters=filters)
        # Adding a second resource request should be okay for the 2nd RP
        # given it has enough disk but we also need to make sure that the
        # first RP is not acceptable because of the VCPU request
        filters = {'resources': {orc.VCPU: 2, orc.DISK_GB: 1022}}
        expected_rps = ['rp_2']
        self._run_get_all_by_filters(expected_rps, filters=filters)
        # Now, we are asking for both disk and VCPU resources that all the RPs
        # can't accept (as the 2nd RP is having a reserved size)
        filters = {'resources': {orc.VCPU: 2, orc.DISK_GB: 1024}}
        expected_rps = []
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # We also want to verify that asking for a specific RP can also be
        # checking the resource usage.
        filters = {'name': 'rp_1', 'resources': {orc.VCPU: 1}}
        expected_rps = ['rp_1']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Let's verify that the min and max units are checked too
        # Case 1: amount is in between min and max and modulo step_size
        filters = {'resources': {orc.MEMORY_MB: 2}}
        expected_rps = ['rp_1', 'rp_2']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Case 2: amount is less than min_unit
        filters = {'resources': {orc.MEMORY_MB: 1}}
        expected_rps = []
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Case 3: amount is more than min_unit
        filters = {'resources': {orc.MEMORY_MB: 5}}
        expected_rps = []
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Case 4: amount is not modulo step_size
        filters = {'resources': {orc.MEMORY_MB: 3}}
        expected_rps = []
        self._run_get_all_by_filters(expected_rps, filters=filters)

    def test_get_all_by_filters_with_resources_not_existing(self):
        self.assertRaises(
            exception.ResourceClassNotFound,
            rp_obj.get_all_by_filters,
            self.ctx, {'resources': {'FOOBAR': 3}})

    def test_get_all_by_filters_aggregate(self):
        for rp_i in [1, 2, 3, 4]:
            aggs = [uuidsentinel.agg_a, uuidsentinel.agg_b] if rp_i % 2 else []
            self._create_provider('rp_' + str(rp_i), *aggs)
        for rp_i in [5, 6]:
            aggs = [uuidsentinel.agg_b, uuidsentinel.agg_c]
            self._create_provider('rp_' + str(rp_i), *aggs)

        # Get rps in "agg_a"
        filters = {'member_of': [[uuidsentinel.agg_a]]}
        expected_rps = ['rp_1', 'rp_3']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Validate rps in "agg_a" or "agg_b"
        filters = {'member_of': [[uuidsentinel.agg_a, uuidsentinel.agg_b]]}
        expected_rps = ['rp_1', 'rp_3', 'rp_5', 'rp_6']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Validate rps in "agg_a" or "agg_b" and named "rp_1"
        filters = {'member_of': [[uuidsentinel.agg_a, uuidsentinel.agg_b]],
                   'name': 'rp_1'}
        expected_rps = ['rp_1']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Validate rps in "agg_a" or "agg_b" and named "barnabas"
        filters = {'member_of': [[uuidsentinel.agg_a, uuidsentinel.agg_b]],
                   'name': 'barnabas'}
        expected_rps = []
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Validate rps in "agg_1" or "agg_2"
        filters = {'member_of': [[uuidsentinel.agg_1, uuidsentinel.agg_2]]}
        expected_rps = []
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Validate rps NOT in "agg_a"
        filters = {'forbidden_aggs': [uuidsentinel.agg_a]}
        expected_rps = ['rp_2', 'rp_4', 'rp_5', 'rp_6']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Validate rps NOT in "agg_1"
        filters = {'forbidden_aggs': [uuidsentinel.agg_1]}
        expected_rps = ['rp_1', 'rp_2', 'rp_3', 'rp_4', 'rp_5', 'rp_6']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Validate rps in "agg_a" or "agg_b" that are not in "agg_1"
        filters = {'member_of': [[uuidsentinel.agg_a, uuidsentinel.agg_b]],
                   'forbidden_aggs': [uuidsentinel.agg_1]}
        expected_rps = ['rp_1', 'rp_3', 'rp_5', 'rp_6']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Validate rps in "agg_a" or "agg_b" that are not in "agg_a"
        # ...which means rps in "agg_b"
        filters = {'member_of': [[uuidsentinel.agg_a, uuidsentinel.agg_b]],
                   'forbidden_aggs': [uuidsentinel.agg_a]}
        expected_rps = ['rp_5', 'rp_6']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # Validate rps in both "agg_a" and "agg_b" that are not in "agg_a"
        # ...which means no rp
        filters = {'member_of': [[uuidsentinel.agg_a], [uuidsentinel.agg_b]],
                   'forbidden_aggs': [uuidsentinel.agg_a]}
        expected_rps = []
        self._run_get_all_by_filters(expected_rps, filters=filters)

    def test_get_all_by_required(self):
        # Create some resource providers and give them each 0 or more traits.
        # rp_name_0: no traits
        # rp_name_1: CUSTOM_TRAIT_A
        # rp_name_2: CUSTOM_TRAIT_A, CUSTOM_TRAIT_B
        # rp_name_3: CUSTOM_TRAIT_A, CUSTOM_TRAIT_B, CUSTOM_TRAIT_C
        trait_names = ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B',
                       'CUSTOM_TRAIT_C']
        for rp_i in [0, 1, 2, 3]:
            rp = self._create_provider('rp_' + str(rp_i))
            if rp_i:
                traits = trait_names[0:rp_i]
                tb.set_traits(rp, *traits)

        # Three rps (1, 2, 3) should have CUSTOM_TRAIT_A
        filters = {'required_traits': [{'CUSTOM_TRAIT_A'}]}
        expected_rps = ['rp_1', 'rp_2', 'rp_3']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # One rp (rp 1) if we forbid CUSTOM_TRAIT_B, with a single trait of
        # CUSTOM_TRAIT_A
        filters = {
            'required_traits': [{'CUSTOM_TRAIT_A'}],
            'forbidden_traits': {'CUSTOM_TRAIT_B'},
        }
        expected_rps = ['rp_1']
        custom_a_rps = self._run_get_all_by_filters(expected_rps,
                                                    filters=filters)

        self.assertEqual(uuidsentinel.rp_1, custom_a_rps[0].uuid)
        traits = trait_obj.get_all_by_resource_provider(
            self.ctx, custom_a_rps[0])
        self.assertEqual(1, len(traits))
        self.assertEqual('CUSTOM_TRAIT_A', traits[0].name)

        # (A or B) and not C
        filters = {
            'required_traits': [{'CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B'}],
            'forbidden_traits': {'CUSTOM_TRAIT_C'},
        }
        expected_rps = ['rp_1', 'rp_2']
        self._run_get_all_by_filters(expected_rps, filters=filters)

        # A and (B or C)
        filters = {
            'required_traits': [
                {'CUSTOM_TRAIT_A'}, {'CUSTOM_TRAIT_B', 'CUSTOM_TRAIT_C'}],
        }
        expected_rps = ['rp_2', 'rp_3']
        self._run_get_all_by_filters(expected_rps, filters=filters)


class TestResourceProviderAggregates(tb.PlacementDbBaseTestCase):
    def test_set_and_get_new_aggregates(self):
        aggregate_uuids = [uuidsentinel.agg_a, uuidsentinel.agg_b]
        rp = self._create_provider(
            uuidsentinel.rp_name,
            *aggregate_uuids,
            uuid=uuidsentinel.rp_uuid
        )

        read_aggregate_uuids = rp.get_aggregates()
        self.assertCountEqual(aggregate_uuids, read_aggregate_uuids)

        # Since get_aggregates always does a new query this is
        # mostly nonsense but is here for completeness.
        read_rp = rp_obj.ResourceProvider.get_by_uuid(
            self.ctx, uuidsentinel.rp_uuid)
        re_read_aggregate_uuids = read_rp.get_aggregates()
        self.assertCountEqual(aggregate_uuids, re_read_aggregate_uuids)

    def test_set_aggregates_is_replace(self):
        start_aggregate_uuids = [uuidsentinel.agg_a, uuidsentinel.agg_b]
        rp = self._create_provider(
            uuidsentinel.rp_name,
            *start_aggregate_uuids,
            uuid=uuidsentinel.rp_uuid
        )

        read_aggregate_uuids = rp.get_aggregates()
        self.assertCountEqual(start_aggregate_uuids, read_aggregate_uuids)

        rp.set_aggregates([uuidsentinel.agg_a])
        read_aggregate_uuids = rp.get_aggregates()
        self.assertNotIn(uuidsentinel.agg_b, read_aggregate_uuids)
        self.assertIn(uuidsentinel.agg_a, read_aggregate_uuids)

        # Empty list means delete.
        rp.set_aggregates([])
        read_aggregate_uuids = rp.get_aggregates()
        self.assertEqual([], read_aggregate_uuids)

    def test_delete_rp_clears_aggs(self):
        start_aggregate_uuids = [uuidsentinel.agg_a, uuidsentinel.agg_b]
        rp = self._create_provider(
            uuidsentinel.rp_name,
            *start_aggregate_uuids,
            uuid=uuidsentinel.rp_uuid
        )
        aggs = rp.get_aggregates()
        self.assertEqual(2, len(aggs))
        rp.destroy()
        aggs = rp.get_aggregates()
        self.assertEqual(0, len(aggs))

    def test_anchors_for_sharing_providers(self):
        """Test anchors_for_sharing_providers with the following setup.

      .............agg2.....
     :                      :
     :  +====+               : +====+                ..agg5..
     :  | r1 |                .| r2 |               : +----+ :
     :  +=+==+                 +=+==+     +----+    : | s3 | :
     :    |                      |        | s2 |    : +----+ :
     :  +=+==+ agg1            +=+==+     +----+     ........
     :  | c1 |.....            | c2 |       :
     :  +====+ :   :           +====+     agg4        +----+
     :        :     :            :          :         | s4 |
     :    +----+   +----+        :        +====+      +----+
     :....| s5 |   | s1 |.......agg3......| r3 |
     :    +----+   +----+                 +====+
     :.........agg2...:
        """
        agg1 = uuidsentinel.agg1
        agg2 = uuidsentinel.agg2
        agg3 = uuidsentinel.agg3
        agg4 = uuidsentinel.agg4
        agg5 = uuidsentinel.agg5
        shr_trait = trait_obj.Trait.get_by_name(
            self.ctx, "MISC_SHARES_VIA_AGGREGATE")

        def mkrp(name, sharing, aggs, **kwargs):
            rp = self._create_provider(name, *aggs, **kwargs)
            if sharing:
                rp.set_traits([shr_trait])
            rp.set_aggregates(aggs)
            return rp

        def _anchor(shr, anc):
            return res_ctx.AnchorIds(
                rp_id=shr.id, rp_uuid=shr.uuid,
                anchor_id=anc.id, anchor_uuid=anc.uuid)

        # r1 and c1 constitute a tree.  The child is in agg1.  We use this to
        # show that, when we ask for anchors for s1 (a member of agg1), we get
        # the *root* of the tree, not the aggregate member itself (c1).
        r1 = mkrp('r1', False, [])
        mkrp('c1', False, [agg1], parent=r1.uuid)
        # r2 and c2 constitute a tree.  The root is in agg2; the child is in
        # agg3.  We use this to show that, when we ask for anchors for a
        # provider that's in both of those aggregates (s1), we only get r2 once
        r2 = mkrp('r2', False, [agg2])
        mkrp('c2', False, [agg3], parent=r2.uuid)
        # r3 stands alone, but is a member of two aggregates.  We use this to
        # show that we don't "jump aggregates" - when we ask for anchors for s2
        # we only get r3 (and s2 itself).
        r3 = mkrp('r3', False, [agg3, agg4])
        # s* are sharing providers
        s1 = mkrp('s1', True, [agg1, agg2, agg3])
        s2 = mkrp('s2', True, [agg4])
        # s3 is the only member of agg5.  We use this to show that the provider
        # is still considered its own root, even if the aggregate is only
        # associated with itself.
        s3 = mkrp('s3', True, [agg5])
        # s4 is a broken semi-sharing provider - has MISC_SHARES_VIA_AGGREGATE,
        # but is not a member of an aggregate.  It has no "anchor".
        s4 = mkrp('s4', True, [])
        # s5 is a sharing provider whose aggregates overlap with those of s1.
        # s5 and s1 will show up as "anchors" for each other.
        s5 = mkrp('s5', True, [agg1, agg2])

        # s1 gets s1 (self),
        # r1 via agg1 through c1,
        # r2 via agg2 AND via agg3 through c2
        # r3 via agg3
        # s5 via agg1 and agg2
        expected = set(_anchor(s1, rp) for rp in (s1, r1, r2, r3, s5))
        self.assertCountEqual(
            expected, res_ctx.anchors_for_sharing_providers(self.ctx, [s1.id]))

        # s2 gets s2 (self) and r3 via agg4
        expected = set(_anchor(s2, rp) for rp in (s2, r3))
        self.assertCountEqual(
            expected, res_ctx.anchors_for_sharing_providers(self.ctx, [s2.id]))

        # s3 gets self
        self.assertEqual(
            set([_anchor(s3, s3)]),
            res_ctx.anchors_for_sharing_providers(self.ctx, [s3.id]))

        # s4 isn't really a sharing provider - gets nothing
        self.assertEqual(
            set([]), res_ctx.anchors_for_sharing_providers(self.ctx, [s4.id]))

        # s5 gets s5 (self),
        # r1 via agg1 through c1,
        # r2 via agg2
        # s1 via agg1 and agg2
        expected = set(_anchor(s5, rp) for rp in (s5, r1, r2, s1))
        self.assertCountEqual(
            expected, res_ctx.anchors_for_sharing_providers(self.ctx, [s5.id]))

        # validate that we can get them all at once
        expected = set(
            [_anchor(s1, rp) for rp in (r1, r2, r3, s1, s5)] +
            [_anchor(s2, rp) for rp in (r3, s2)] +
            [_anchor(s3, rp) for rp in (s3,)] +
            [_anchor(s5, rp) for rp in (r1, r2, s1, s5)]
        )
        self.assertCountEqual(
            expected,
            res_ctx.anchors_for_sharing_providers(
                self.ctx, [s1.id, s2.id, s3.id, s4.id, s5.id]))


class SharedProviderTestCase(tb.PlacementDbBaseTestCase):
    """Tests that the queries used to determine placement in deployments with
    shared resource providers such as a shared disk pool result in accurate
    reporting of inventory and usage.
    """

    def _requested_resources(self):
        STANDARDS = orc.STANDARDS
        VCPU_ID = STANDARDS.index(orc.VCPU)
        MEMORY_MB_ID = STANDARDS.index(orc.MEMORY_MB)
        DISK_GB_ID = STANDARDS.index(orc.DISK_GB)
        # The resources we will request
        resources = {
            VCPU_ID: 1,
            MEMORY_MB_ID: 64,
            DISK_GB_ID: 100,
        }
        return resources

    def test_shared_provider_capacity(self):
        """Sets up a resource provider that shares DISK_GB inventory via an
        aggregate, a couple resource providers representing "local disk"
        compute nodes and ensures the _get_providers_sharing_capacity()
        function finds that provider and not providers of "local disk".
        """
        # Create the two "local disk" compute node providers
        cn1 = self._create_provider('cn1')
        cn2 = self._create_provider('cn2')

        # Populate the two compute node providers with inventory.  One has
        # DISK_GB.  Both should be excluded from the result (one doesn't have
        # the requested resource; but neither is a sharing provider).
        for cn in (cn1, cn2):
            tb.add_inventory(cn, orc.VCPU, 24,
                             allocation_ratio=16.0)
            tb.add_inventory(cn, orc.MEMORY_MB, 32768,
                             min_unit=64,
                             max_unit=32768,
                             step_size=64,
                             allocation_ratio=1.5)
            if cn is cn1:
                tb.add_inventory(cn, orc.DISK_GB, 2000,
                                 min_unit=100,
                                 max_unit=2000,
                                 step_size=10)

        # Create the shared storage pool
        ss1 = self._create_provider('shared storage 1')
        ss2 = self._create_provider('shared storage 2')

        # Give the shared storage pool some inventory of DISK_GB
        for ss, disk_amount in ((ss1, 2000), (ss2, 1000)):
            tb.add_inventory(ss, orc.DISK_GB, disk_amount,
                             min_unit=100,
                             max_unit=2000,
                             step_size=10)
            # Mark the shared storage pool as having inventory shared among
            # any provider associated via aggregate
            tb.set_traits(ss, "MISC_SHARES_VIA_AGGREGATE")

        # OK, now that has all been set up, let's verify that we get the ID of
        # the shared storage pool
        got_ids = res_ctx.get_sharing_providers(self.ctx)
        self.assertEqual(set([ss1.id, ss2.id]), got_ids)

        request = placement_lib.RequestGroup(
            use_same_provider=False,
            resources={orc.VCPU: 2,
                       orc.MEMORY_MB: 256,
                       orc.DISK_GB: 1500})
        has_trees = res_ctx._has_provider_trees(self.ctx)
        sharing = res_ctx.get_sharing_providers(self.ctx)
        rg_ctx = res_ctx.RequestGroupSearchContext(
            self.ctx, request, has_trees, sharing)

        VCPU_ID = orc.STANDARDS.index(orc.VCPU)
        DISK_GB_ID = orc.STANDARDS.index(orc.DISK_GB)

        rps_sharing_vcpu = rg_ctx.get_rps_with_shared_capacity(VCPU_ID)
        self.assertEqual(set(), rps_sharing_vcpu)

        rps_sharing_dist = rg_ctx.get_rps_with_shared_capacity(DISK_GB_ID)
        self.assertEqual(set([ss1.id]), rps_sharing_dist)


# We don't want to waste time sleeping in these tests. It would add
# tens of seconds.
@mock.patch('time.sleep', return_value=None)
class TestEnsureAggregateRetry(tb.PlacementDbBaseTestCase):

    @mock.patch('placement.objects.resource_provider._ensure_aggregate')
    def test_retry_happens(self, mock_ens_agg, mock_time):
        """Confirm that retrying on DBDuplicateEntry happens when ensuring
        aggregates.
        """
        rp = self._create_provider('rp1')
        agg_id = self.create_aggregate(uuidsentinel.agg)

        mock_ens_agg.side_effect = [db_exc.DBDuplicateEntry(), agg_id]
        rp.set_aggregates([uuidsentinel.agg])
        self.assertEqual([uuidsentinel.agg], rp.get_aggregates())
        self.assertEqual(2, mock_ens_agg.call_count)

    @mock.patch('placement.objects.resource_provider._ensure_aggregate')
    def test_retry_failsover(self, mock_ens_agg, mock_time):
        """Confirm that the retry loop used when ensuring aggregates only
        retries 10 times. After that it lets DBDuplicateEntry raise.
        """
        rp = self._create_provider('rp1')
        mock_ens_agg.side_effect = db_exc.DBDuplicateEntry()
        self.assertRaises(
            db_exc.DBDuplicateEntry, rp.set_aggregates, [uuidsentinel.agg])
        self.assertEqual(11, mock_ens_agg.call_count)
