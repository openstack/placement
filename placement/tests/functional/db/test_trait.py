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

import os_traits

from placement import exception
from placement.objects import trait as trait_obj
from placement.tests.functional.db import test_base as tb


class TraitTestCase(tb.PlacementDbBaseTestCase):

    def test_provider_traits_empty_param(self):
        self.assertRaises(ValueError, trait_obj.get_traits_by_provider_tree,
                          self.ctx, [])

    def test_trait_ids_from_names_empty_param(self):
        self.assertRaises(ValueError, trait_obj.ids_from_names,
                          self.ctx, [])

    def test_trait_create(self):
        t = trait_obj.Trait(self.ctx)
        t.name = 'CUSTOM_TRAIT_A'
        t.create()
        self.assertIsNotNone(t.id)
        self.assertEqual(t.name, 'CUSTOM_TRAIT_A')

    def test_trait_create_with_id_set(self):
        t = trait_obj.Trait(self.ctx)
        t.name = 'CUSTOM_TRAIT_A'
        t.id = 1
        self.assertRaises(exception.ObjectActionError, t.create)

    def test_trait_create_without_name_set(self):
        t = trait_obj.Trait(self.ctx)
        self.assertRaises(exception.ObjectActionError, t.create)

    def test_trait_create_duplicated_trait(self):
        trait = trait_obj.Trait(self.ctx)
        trait.name = 'CUSTOM_TRAIT_A'
        trait.create()
        tmp_trait = trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_TRAIT_A')
        self.assertEqual('CUSTOM_TRAIT_A', tmp_trait.name)
        duplicated_trait = trait_obj.Trait(self.ctx)
        duplicated_trait.name = 'CUSTOM_TRAIT_A'
        self.assertRaises(exception.TraitExists, duplicated_trait.create)

    def test_trait_get(self):
        t = trait_obj.Trait(self.ctx)
        t.name = 'CUSTOM_TRAIT_A'
        t.create()
        t = trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_TRAIT_A')
        self.assertEqual(t.name, 'CUSTOM_TRAIT_A')

    def test_trait_get_non_existed_trait(self):
        self.assertRaises(
            exception.TraitNotFound,
            trait_obj.Trait.get_by_name, self.ctx, 'CUSTOM_TRAIT_A')

    def test_bug_1760322(self):
        # Under bug # #1760322, if the first hit to the traits table resulted
        # in an exception, the sync transaction rolled back and the table
        # stayed empty; but _TRAITS_SYNCED got set to True, so it didn't resync
        # next time.
        # NOTE(cdent): With change Ic87518948ed5bf4ab79f9819cd94714e350ce265
        # syncing is no longer done in the same way, so the bug fix that this
        # test was testing is gone, but this test has been left in place to
        # make sure we still get behavior we expect.
        try:
            trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_GOLD')
        except exception.TraitNotFound:
            pass
        # Under bug #1760322, this raised TraitNotFound.
        trait_obj.Trait.get_by_name(self.ctx, os_traits.HW_CPU_X86_AVX2)

    def test_trait_destroy(self):
        t = trait_obj.Trait(self.ctx)
        t.name = 'CUSTOM_TRAIT_A'
        t.create()
        t = trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_TRAIT_A')
        self.assertEqual(t.name, 'CUSTOM_TRAIT_A')
        t.destroy()
        self.assertRaises(exception.TraitNotFound, trait_obj.Trait.get_by_name,
                          self.ctx, 'CUSTOM_TRAIT_A')

    def test_trait_destroy_with_standard_trait(self):
        t = trait_obj.Trait(self.ctx)
        t.id = 1
        t.name = 'HW_CPU_X86_AVX'
        self.assertRaises(exception.TraitCannotDeleteStandard, t.destroy)

    def test_traits_get_all(self):
        trait_names = ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B', 'CUSTOM_TRAIT_C']
        for name in trait_names:
            t = trait_obj.Trait(self.ctx)
            t.name = name
            t.create()

        self._assert_traits_in(trait_names,
                               trait_obj.get_all(self.ctx))

    def test_traits_get_all_with_name_in_filter(self):
        trait_names = ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B', 'CUSTOM_TRAIT_C']
        for name in trait_names:
            t = trait_obj.Trait(self.ctx)
            t.name = name
            t.create()

        traits = trait_obj.get_all(
            self.ctx,
            filters={'name_in': ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B']})
        self._assert_traits(['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B'], traits)

    def test_traits_get_all_with_non_existed_name(self):
        traits = trait_obj.get_all(
            self.ctx,
            filters={'name_in': ['CUSTOM_TRAIT_X', 'CUSTOM_TRAIT_Y']})
        self.assertEqual(0, len(traits))

    def test_traits_get_all_with_prefix_filter(self):
        trait_names = ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B', 'CUSTOM_TRAIT_C']
        for name in trait_names:
            t = trait_obj.Trait(self.ctx)
            t.name = name
            t.create()

        traits = trait_obj.get_all(self.ctx, filters={'prefix': 'CUSTOM'})
        self._assert_traits(
            ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B', 'CUSTOM_TRAIT_C'],
            traits)

    def test_traits_get_all_with_non_existed_prefix(self):
        traits = trait_obj.get_all(self.ctx, filters={"prefix": "NOT_EXISTED"})
        self.assertEqual(0, len(traits))

    def test_trait_delete_in_use(self):
        rp = self._create_provider('fake_resource_provider')
        t, = tb.set_traits(rp, 'CUSTOM_TRAIT_A')
        self.assertRaises(exception.TraitInUse, t.destroy)

    def test_traits_get_all_with_associated_true(self):
        rp1 = self._create_provider('fake_resource_provider1')
        rp2 = self._create_provider('fake_resource_provider2')
        trait_names = ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B', 'CUSTOM_TRAIT_C']
        for name in trait_names:
            t = trait_obj.Trait(self.ctx)
            t.name = name
            t.create()

        associated_traits = trait_obj.get_all(
            self.ctx,
            filters={'name_in': ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B']})
        rp1.set_traits(associated_traits)
        rp2.set_traits(associated_traits)
        self._assert_traits(
            ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B'],
            trait_obj.get_all(self.ctx, filters={'associated': True}))

    def test_traits_get_all_with_associated_false(self):
        rp1 = self._create_provider('fake_resource_provider1')
        rp2 = self._create_provider('fake_resource_provider2')
        trait_names = ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B', 'CUSTOM_TRAIT_C']
        for name in trait_names:
            t = trait_obj.Trait(self.ctx)
            t.name = name
            t.create()

        associated_traits = trait_obj.get_all(
            self.ctx,
            filters={'name_in': ['CUSTOM_TRAIT_A', 'CUSTOM_TRAIT_B']})
        rp1.set_traits(associated_traits)
        rp2.set_traits(associated_traits)
        self._assert_traits_in(
            ['CUSTOM_TRAIT_C'],
            trait_obj.get_all(self.ctx, filters={'associated': False}))
