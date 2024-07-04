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

import collections

import os_resource_classes as orc
import os_traits
from oslo_utils.fixture import uuidsentinel as uuids
import sqlalchemy as sa

from placement import exception
from placement import lib as placement_lib
from placement.objects import allocation_candidate as ac_obj
from placement.objects import research_context as res_ctx
from placement.objects import resource_class as rc_obj
from placement.objects import resource_provider as rp_obj
from placement.objects import trait as trait_obj
from placement.tests.functional.db import test_base as tb


def _req_group_search_context(context, **kwargs):
    resources = {
        orc.VCPU: 2,
        orc.MEMORY_MB: 256,
        orc.SRIOV_NET_VF: 1,
    }
    request = placement_lib.RequestGroup(
        use_same_provider=False,
        resources=kwargs.get('resources', resources),
        required_traits=kwargs.get('required_traits', []),
        forbidden_traits=kwargs.get('forbidden_traits', set()),
        member_of=kwargs.get('member_of', []),
        forbidden_aggs=kwargs.get('forbidden_aggs', []),
        in_tree=kwargs.get('in_tree', None),
    )
    has_trees = res_ctx._has_provider_trees(context)
    sharing = res_ctx.get_sharing_providers(context)
    rg_ctx = res_ctx.RequestGroupSearchContext(
        context, request, has_trees, sharing)

    return rg_ctx


class ProviderDBHelperTestCase(tb.PlacementDbBaseTestCase):

    def test_get_provider_ids_matching(self):
        # These RPs are named based on whether we expect them to be 'incl'uded
        # or 'excl'uded in the result.

        # No inventory records.  This one should never show up in a result.
        self._create_provider('no_inventory')

        # Inventory of adequate CPU and memory, no allocations against it.
        excl_big_cm_noalloc = self._create_provider('big_cm_noalloc')
        tb.add_inventory(excl_big_cm_noalloc, orc.VCPU, 15)
        tb.add_inventory(excl_big_cm_noalloc, orc.MEMORY_MB,
                         4096, max_unit=2048)

        # Inventory of adequate memory and disk, no allocations against it.
        excl_big_md_noalloc = self._create_provider('big_md_noalloc')
        tb.add_inventory(excl_big_md_noalloc, orc.MEMORY_MB,
                         4096, max_unit=2048)
        tb.add_inventory(excl_big_md_noalloc, orc.DISK_GB, 2000)

        # Adequate inventory, no allocations against it.
        incl_biginv_noalloc = self._create_provider('biginv_noalloc')
        tb.add_inventory(incl_biginv_noalloc, orc.VCPU, 15)
        tb.add_inventory(incl_biginv_noalloc, orc.MEMORY_MB,
                         4096, max_unit=2048)
        tb.add_inventory(incl_biginv_noalloc, orc.DISK_GB, 2000)

        # No allocations, but inventory unusable.  Try to hit all the possible
        # reasons for exclusion.
        # VCPU min_unit too high
        excl_badinv_min_unit = self._create_provider('badinv_min_unit')
        tb.add_inventory(excl_badinv_min_unit, orc.VCPU, 12, min_unit=6)
        tb.add_inventory(excl_badinv_min_unit, orc.MEMORY_MB,
                         4096, max_unit=2048)
        tb.add_inventory(excl_badinv_min_unit, orc.DISK_GB, 2000)
        # MEMORY_MB max_unit too low
        excl_badinv_max_unit = self._create_provider('badinv_max_unit')
        tb.add_inventory(excl_badinv_max_unit, orc.VCPU, 15)
        tb.add_inventory(excl_badinv_max_unit, orc.MEMORY_MB,
                         4096, max_unit=512)
        tb.add_inventory(excl_badinv_max_unit, orc.DISK_GB, 2000)
        # DISK_GB unsuitable step_size
        excl_badinv_step_size = self._create_provider('badinv_step_size')
        tb.add_inventory(excl_badinv_step_size, orc.VCPU, 15)
        tb.add_inventory(excl_badinv_step_size, orc.MEMORY_MB,
                         4096, max_unit=2048)
        tb.add_inventory(excl_badinv_step_size, orc.DISK_GB, 2000, step_size=7)
        # Not enough total VCPU
        excl_badinv_total = self._create_provider('badinv_total')
        tb.add_inventory(excl_badinv_total, orc.VCPU, 4)
        tb.add_inventory(excl_badinv_total, orc.MEMORY_MB,
                         4096, max_unit=2048)
        tb.add_inventory(excl_badinv_total, orc.DISK_GB, 2000)
        # Too much reserved MEMORY_MB
        excl_badinv_reserved = self._create_provider('badinv_reserved')
        tb.add_inventory(excl_badinv_reserved, orc.VCPU, 15)
        tb.add_inventory(excl_badinv_reserved, orc.MEMORY_MB,
                         4096, max_unit=2048, reserved=3500)
        tb.add_inventory(excl_badinv_reserved, orc.DISK_GB, 2000)
        # DISK_GB allocation ratio blows it up
        excl_badinv_alloc_ratio = self._create_provider('badinv_alloc_ratio')
        tb.add_inventory(excl_badinv_alloc_ratio, orc.VCPU, 15)
        tb.add_inventory(excl_badinv_alloc_ratio,
                         orc.MEMORY_MB, 4096, max_unit=2048)
        tb.add_inventory(excl_badinv_alloc_ratio, orc.DISK_GB,
                         2000, allocation_ratio=0.5)

        # Inventory consumed in one RC, but available in the others
        excl_1invunavail = self._create_provider('1invunavail')
        tb.add_inventory(excl_1invunavail, orc.VCPU, 10)
        self.allocate_from_provider(excl_1invunavail, orc.VCPU, 7)
        tb.add_inventory(excl_1invunavail, orc.MEMORY_MB, 4096)
        self.allocate_from_provider(excl_1invunavail, orc.MEMORY_MB, 1024)
        tb.add_inventory(excl_1invunavail, orc.DISK_GB, 2000)
        self.allocate_from_provider(excl_1invunavail, orc.DISK_GB, 400)

        # Inventory all consumed
        excl_allused = self._create_provider('allused')
        tb.add_inventory(excl_allused, orc.VCPU, 10)
        self.allocate_from_provider(excl_allused, orc.VCPU, 7)
        tb.add_inventory(excl_allused, orc.MEMORY_MB, 4000)
        self.allocate_from_provider(excl_allused, orc.MEMORY_MB, 1500)
        self.allocate_from_provider(excl_allused, orc.MEMORY_MB, 2000)
        tb.add_inventory(excl_allused, orc.DISK_GB, 1500)
        self.allocate_from_provider(excl_allused, orc.DISK_GB, 1)

        # Inventory available in requested classes, but unavailable in others
        incl_extra_full = self._create_provider('extra_full')
        tb.add_inventory(incl_extra_full, orc.VCPU, 20)
        self.allocate_from_provider(incl_extra_full, orc.VCPU, 15)
        tb.add_inventory(incl_extra_full, orc.MEMORY_MB, 4096)
        self.allocate_from_provider(incl_extra_full, orc.MEMORY_MB, 1024)
        tb.add_inventory(incl_extra_full, orc.DISK_GB, 2000)
        self.allocate_from_provider(incl_extra_full, orc.DISK_GB, 400)
        tb.add_inventory(incl_extra_full, orc.PCI_DEVICE, 4)
        self.allocate_from_provider(incl_extra_full, orc.PCI_DEVICE, 1)
        self.allocate_from_provider(incl_extra_full, orc.PCI_DEVICE, 3)

        # Inventory available in a unrequested classes, not in requested ones
        excl_extra_avail = self._create_provider('extra_avail')
        # Incompatible step size
        tb.add_inventory(excl_extra_avail, orc.VCPU, 10, step_size=3)
        # Not enough left after reserved + used
        tb.add_inventory(excl_extra_avail, orc.MEMORY_MB, 4096,
                         max_unit=2048, reserved=2048)
        self.allocate_from_provider(excl_extra_avail, orc.MEMORY_MB, 1040)
        # Allocation ratio math
        tb.add_inventory(excl_extra_avail, orc.DISK_GB, 2000,
                         allocation_ratio=0.5)
        tb.add_inventory(excl_extra_avail, orc.IPV4_ADDRESS, 48)
        custom_special = rc_obj.ResourceClass(self.ctx, name='CUSTOM_SPECIAL')
        custom_special.create()
        tb.add_inventory(excl_extra_avail, 'CUSTOM_SPECIAL', 100)
        self.allocate_from_provider(excl_extra_avail, 'CUSTOM_SPECIAL', 99)

        resources = {
            orc.VCPU: 5,
            orc.MEMORY_MB: 1024,
            orc.DISK_GB: 1500
        }

        # Run it!
        rg_ctx = _req_group_search_context(self.ctx, resources=resources)
        res = res_ctx.get_provider_ids_matching(rg_ctx)

        # We should get all the incl_* RPs
        expected = [incl_biginv_noalloc, incl_extra_full]

        self.assertEqual(set((rp.id, rp.id) for rp in expected), set(res))

        # Now request that the providers must have a set of required traits and
        # that this results in no results returned, since we haven't yet
        # associated any traits with the providers
        avx2_t = trait_obj.Trait.get_by_name(
            self.ctx, os_traits.HW_CPU_X86_AVX2)
        req_traits = [{os_traits.HW_CPU_X86_AVX2}]
        rg_ctx = _req_group_search_context(
            self.ctx,
            resources=resources,
            required_traits=req_traits,
        )
        res = res_ctx.get_provider_ids_matching(rg_ctx)

        self.assertEqual([], res)

        # Next let's set the required trait to an excl_* RPs.
        # This should result in no results returned as well.
        excl_big_md_noalloc.set_traits([avx2_t])
        res = res_ctx.get_provider_ids_matching(rg_ctx)
        self.assertEqual([], res)

        # OK, now add the trait to one of the incl_* providers and verify that
        # provider now shows up in our results
        incl_biginv_noalloc.set_traits([avx2_t])
        res = res_ctx.get_provider_ids_matching(rg_ctx)

        rp_ids = [r[0] for r in res]
        self.assertEqual([incl_biginv_noalloc.id], rp_ids)

        # ask for a complex required trait query: (AVX2 and (SEE or SSE2))
        # first it should match no RPs as neither has SSE nor SSE2
        req_traits = [
            {os_traits.HW_CPU_X86_AVX2},
            {os_traits.HW_CPU_X86_SSE, os_traits.HW_CPU_X86_SSE2}
        ]
        rg_ctx = _req_group_search_context(
            self.ctx,
            resources=resources,
            required_traits=req_traits,
        )
        res = res_ctx.get_provider_ids_matching(rg_ctx)

        self.assertEqual([], res)

        # now add SSE to an RP that has no AVX2 so we still not have a match
        sse_t = trait_obj.Trait.get_by_name(
            self.ctx, os_traits.HW_CPU_X86_SSE)
        incl_extra_full.set_traits([sse_t])

        res = res_ctx.get_provider_ids_matching(rg_ctx)

        self.assertEqual([], res)

        # now add SSE2 to an RP which also has AVX2. We expect that RP is a
        # match
        sse2_t = trait_obj.Trait.get_by_name(
            self.ctx, os_traits.HW_CPU_X86_SSE2)
        incl_biginv_noalloc.set_traits([avx2_t, sse2_t])

        res = res_ctx.get_provider_ids_matching(rg_ctx)

        rp_ids = [r[0] for r in res]
        self.assertEqual([incl_biginv_noalloc.id], rp_ids)

        # Let's see if the in_tree filter works
        rg_ctx = _req_group_search_context(
            self.ctx,
            resources=resources,
            in_tree=uuids.biginv_noalloc,
        )
        res = res_ctx.get_provider_ids_matching(rg_ctx)
        rp_ids = [r[0] for r in res]
        self.assertEqual([incl_biginv_noalloc.id], rp_ids)

        # We don't get anything if the specified tree doesn't satisfy the
        # requirements in the first place
        self.assertRaises(exception.ResourceProviderNotFound,
                          _req_group_search_context,
                          self.ctx, resources=resources,
                          in_tree=uuids.allused)

    def test_get_provider_ids_matching_with_multiple_forbidden(self):
        rp1 = self._create_provider('rp1', uuids.agg1)
        tb.add_inventory(rp1, orc.VCPU, 64)

        rp2 = self._create_provider('rp2', uuids.agg1)
        trait_two, = tb.set_traits(rp2, 'CUSTOM_TWO')
        tb.add_inventory(rp2, orc.VCPU, 64)

        rp3 = self._create_provider('rp3')
        trait_three, = tb.set_traits(rp3, 'CUSTOM_THREE')
        tb.add_inventory(rp3, orc.VCPU, 64)

        resources = {orc.VCPU: 4}
        forbidden_traits = {trait_two.name, trait_three.name}
        member_of = [[uuids.agg1]]

        rg_ctx = _req_group_search_context(
            self.ctx,
            resources=resources,
            forbidden_traits=forbidden_traits,
            member_of=member_of)
        res = res_ctx.get_provider_ids_matching(rg_ctx)
        self.assertEqual({(rp1.id, rp1.id)}, set(res))

    def test_get_provider_ids_matching_with_aggregates(self):
        rp1 = self._create_provider('rp1', uuids.agg1, uuids.agg2)
        rp2 = self._create_provider('rp2', uuids.agg2, uuids.agg3)
        rp3 = self._create_provider('rp3', uuids.agg3, uuids.agg4)
        rp4 = self._create_provider('rp4', uuids.agg4, uuids.agg1)
        rp5 = self._create_provider('rp5')

        tb.add_inventory(rp1, orc.VCPU, 64)
        tb.add_inventory(rp2, orc.VCPU, 64)
        tb.add_inventory(rp3, orc.VCPU, 64)
        tb.add_inventory(rp4, orc.VCPU, 64)
        tb.add_inventory(rp5, orc.VCPU, 64)

        resources = {orc.VCPU: 4}
        rg_ctx = _req_group_search_context(
            self.ctx,
            resources=resources,
            member_of=[[uuids.agg1]],
        )
        expected_rp = [rp1, rp4]

        res = res_ctx.get_provider_ids_matching(rg_ctx)
        self.assertEqual(set((rp.id, rp.id) for rp in expected_rp), set(res))

        rg_ctx = _req_group_search_context(
            self.ctx,
            resources=resources,
            member_of=[[uuids.agg1, uuids.agg2]],
        )
        expected_rp = [rp1, rp2, rp4]

        res = res_ctx.get_provider_ids_matching(rg_ctx)
        self.assertEqual(set((rp.id, rp.id) for rp in expected_rp), set(res))

        rg_ctx = _req_group_search_context(
            self.ctx,
            resources=resources,
            member_of=[[uuids.agg1, uuids.agg2], [uuids.agg4]],
        )
        expected_rp = [rp4]

        res = res_ctx.get_provider_ids_matching(rg_ctx)
        self.assertEqual(set((rp.id, rp.id) for rp in expected_rp), set(res))

        rg_ctx = _req_group_search_context(
            self.ctx,
            resources=resources,
            forbidden_aggs=[uuids.agg1],
        )
        expected_rp = [rp2, rp3, rp5]

        res = res_ctx.get_provider_ids_matching(rg_ctx)
        self.assertEqual(set((rp.id, rp.id) for rp in expected_rp), set(res))

        rg_ctx = _req_group_search_context(
            self.ctx,
            resources=resources,
            forbidden_aggs=[uuids.agg1, uuids.agg2],
        )
        expected_rp = [rp3, rp5]

        res = res_ctx.get_provider_ids_matching(rg_ctx)
        self.assertEqual(set((rp.id, rp.id) for rp in expected_rp), set(res))

        rg_ctx = _req_group_search_context(
            self.ctx,
            resources=resources,
            member_of=[[uuids.agg1, uuids.agg2]],
            forbidden_aggs=[uuids.agg3, uuids.agg4],
        )
        expected_rp = [rp1]

        res = res_ctx.get_provider_ids_matching(rg_ctx)
        self.assertEqual(set((rp.id, rp.id) for rp in expected_rp), set(res))

        rg_ctx = _req_group_search_context(
            self.ctx,
            resources=resources,
            member_of=[[uuids.agg1]],
            forbidden_aggs=[uuids.agg1],
        )
        expected_rp = []

        res = res_ctx.get_provider_ids_matching(rg_ctx)
        self.assertEqual(set((rp.id, rp.id) for rp in expected_rp), set(res))

    def test_get_provider_ids_having_all_traits(self):
        def run(required_traits, expected_ids):

            # translate trait names to trait ids in the nested structure
            required_traits = [
                {
                    self.ctx.trait_cache.id_from_string(trait)
                    for trait in any_traits
                }
                for any_traits in required_traits
            ]

            obs = res_ctx.provider_ids_matching_required_traits(
                self.ctx, required_traits)
            self.assertEqual(sorted(expected_ids), sorted(obs))

        # No traits.  This will never be returned, because it's illegal to
        # invoke the method with no traits.
        self._create_provider('cn1')

        # One trait
        cn2 = self._create_provider('cn2')
        tb.set_traits(cn2, 'HW_CPU_X86_TBM')

        # One the same as cn2
        cn3 = self._create_provider('cn3')
        tb.set_traits(cn3, 'HW_CPU_X86_TBM', 'HW_CPU_X86_TSX',
                      'HW_CPU_X86_SGX')

        # Disjoint
        cn4 = self._create_provider('cn4')
        tb.set_traits(cn4, 'HW_CPU_X86_SSE2', 'HW_CPU_X86_SSE3', 'CUSTOM_FOO')

        # Request with no traits not allowed
        self.assertRaises(
            ValueError,
            res_ctx.provider_ids_matching_required_traits, self.ctx, None)
        self.assertRaises(
            ValueError,
            res_ctx.provider_ids_matching_required_traits, self.ctx, [])

        # Common trait returns both RPs having it
        run([{'HW_CPU_X86_TBM'}], [cn2.id, cn3.id])
        # Just the one
        run([{'HW_CPU_X86_TSX'}], [cn3.id])
        run([{'HW_CPU_X86_TSX'}, {'HW_CPU_X86_SGX'}], [cn3.id])
        run([{'CUSTOM_FOO'}], [cn4.id])
        # Including the common one still just gets me cn3
        run([{'HW_CPU_X86_TBM'}, {'HW_CPU_X86_SGX'}], [cn3.id])
        run(
            [{'HW_CPU_X86_TBM'}, {'HW_CPU_X86_TSX'}, {'HW_CPU_X86_SGX'}],
            [cn3.id])
        # Can't be satisfied
        run([{'HW_CPU_X86_TBM'}, {'HW_CPU_X86_TSX'}, {'CUSTOM_FOO'}], [])
        run([{'HW_CPU_X86_TBM'}, {'HW_CPU_X86_TSX'}, {'HW_CPU_X86_SGX'},
             {'CUSTOM_FOO'}], [])
        run([{'HW_CPU_X86_SGX'}, {'HW_CPU_X86_SSE3'}], [])
        run([{'HW_CPU_X86_TBM'}, {'CUSTOM_FOO'}], [])
        run([{'HW_CPU_X86_BMI'}], [])
        trait_obj.Trait(self.ctx, name='CUSTOM_BAR').create()
        run([{'CUSTOM_BAR'}], [])

        # now let's use traits with OR relationships as well
        run([{'HW_CPU_X86_TBM', 'HW_CPU_X86_TSX'}], [cn2.id, cn3.id])
        run([{'HW_CPU_X86_TBM', 'HW_CPU_X86_SSE2'}], [cn2.id, cn3.id, cn4.id])
        run([{'HW_CPU_X86_TSX', 'CUSTOM_FOO'}], [cn3.id, cn4.id])
        run(
            [{'HW_CPU_X86_TBM', 'HW_CPU_X86_TSX', 'CUSTOM_FOO'}],
            [cn2.id, cn3.id, cn4.id])

        trait_obj.Trait(self.ctx, name='CUSTOM_BAZ').create()

        run([{'CUSTOM_BAR', 'CUSTOM_BAZ'}], [])
        run([{'HW_CPU_X86_TBM', 'HW_CPU_X86_SSE2'}, {'CUSTOM_BAR'}], [])

        run([{'HW_CPU_X86_TBM'}, {'HW_CPU_X86_TSX', 'CUSTOM_FOO'}], [cn3.id])


class ProviderTreeDBHelperTestCase(tb.PlacementDbBaseTestCase):

    def _get_rp_ids_matching_names(self, names):
        """Utility function to look up resource provider IDs from a set of
        supplied provider names directly from the API DB.
        """
        names = map(str, names)
        sel = sa.select(rp_obj._RP_TBL.c.id)
        sel = sel.where(rp_obj._RP_TBL.c.name.in_(names))
        with self.placement_db.get_engine().connect() as conn:
            rp_ids = set([r[0] for r in conn.execute(sel)])
        return rp_ids

    def test_get_trees_matching_all(self):
        """Creates a few provider trees having different inventories and
        allocations and tests the get_trees_matching_all_resources() utility
        function to ensure that matching trees and resource providers are
        returned.
        """
        def _run_test(expected_trees, expected_rps, **kwargs):
            """Helper function to validate the test result"""
            # NOTE(jaypipes): get_trees_matching_all() expects a dict of
            # resource class internal identifiers, not string names
            if not expected_trees:
                try:
                    self.assertRaises(exception.ResourceProviderNotFound,
                                      _req_group_search_context,
                                      self.ctx, **kwargs)
                    return
                except Exception:
                    pass
            rg_ctx = _req_group_search_context(self.ctx, **kwargs)
            rw_ctx = res_ctx.RequestWideSearchContext(
                self.ctx, placement_lib.RequestWideParams(), True)
            results = res_ctx.get_trees_matching_all(rg_ctx, rw_ctx)

            tree_ids = self._get_rp_ids_matching_names(expected_trees)
            rp_ids = self._get_rp_ids_matching_names(expected_rps)
            self.assertEqual(tree_ids, results.trees)
            self.assertEqual(rp_ids, results.rps)

        # Before we even set up any providers, verify that the short-circuits
        # work to return empty lists
        _run_test([], [])

        # We are setting up 3 trees of providers that look like this:
        #
        #                  compute node (cn)
        #                 /                 \
        #                /                   \
        #           numa cell 0         numa cell 1
        #               |                    |
        #               |                    |
        #              pf 0                 pf 1
        #
        for x in ('1', '2', '3'):
            name = 'cn' + x
            cn = self._create_provider(name)

            tb.add_inventory(cn, orc.VCPU, 16)
            tb.add_inventory(cn, orc.MEMORY_MB, 32768)

            name = 'cn' + x + '_numa0'
            numa_cell0 = self._create_provider(name, parent=cn.uuid)
            name = 'cn' + x + '_numa1'
            numa_cell1 = self._create_provider(name, parent=cn.uuid)

            name = 'cn' + x + '_numa0_pf0'
            pf0 = self._create_provider(name, parent=numa_cell0.uuid)
            tb.add_inventory(pf0, orc.SRIOV_NET_VF, 8)
            name = 'cn' + x + '_numa1_pf1'
            pf1 = self._create_provider(name, parent=numa_cell1.uuid)
            tb.add_inventory(pf1, orc.SRIOV_NET_VF, 8)
            if x == '1':
                # Associate the first compute node with agg1 and agg2
                cn.set_aggregates([uuids.agg1, uuids.agg2])
            if x == '2':
                # Associate the second PF on the second compute node with agg2
                pf1.set_aggregates([uuids.agg2])
            if x == '3':
                # Associate the first compute node with agg2 and agg3
                cn.set_aggregates([uuids.agg2, uuids.agg3])
                # Associate the second PF on the second compute node with agg4
                pf1.set_aggregates([uuids.agg4])
                # Mark the second PF on the third compute node as having
                # GENEVE offload enabled
                tb.set_traits(pf1, os_traits.HW_NIC_OFFLOAD_GENEVE)
                # Doesn't really make a whole lot of logical sense, but allows
                # us to test situations where the same trait is associated with
                # multiple providers in the same tree and one of the providers
                # has inventory we will use...
                tb.set_traits(cn, os_traits.HW_NIC_OFFLOAD_GENEVE)

        # First, we test that all the candidates are returned
        expected_trees = ['cn1', 'cn2', 'cn3']
        expected_rps = ['cn1', 'cn1_numa0_pf0', 'cn1_numa1_pf1',
                        'cn2', 'cn2_numa0_pf0', 'cn2_numa1_pf1',
                        'cn3', 'cn3_numa0_pf0', 'cn3_numa1_pf1']
        _run_test(expected_trees, expected_rps)

        # Let's see if the tree_root_id filter works
        expected_trees = ['cn1']
        expected_rps = ['cn1', 'cn1_numa0_pf0', 'cn1_numa1_pf1']
        _run_test(expected_trees, expected_rps, in_tree=uuids.cn1)

        # Let's see if the aggregate filter works

        # 1. rps in agg1
        # All rps under cn1 should be included because aggregate on a root
        # spans the whole tree
        member_of = [[uuids.agg1]]
        expected_trees = ['cn1']
        expected_rps = ['cn1', 'cn1_numa0_pf0', 'cn1_numa1_pf1']
        _run_test(expected_trees, expected_rps, member_of=member_of)

        # 2. rps in agg2
        # cn2 doesn't come up because while cn2_numa1_pf1 is in agg2, aggs on
        # non-root does NOT span the whole tree. Thus cn2 can't provide VCPU
        # or MEMORY_MB resource
        member_of = [[uuids.agg2]]
        expected_trees = ['cn1', 'cn3']
        expected_rps = ['cn1', 'cn1_numa0_pf0', 'cn1_numa1_pf1',
                        'cn3', 'cn3_numa0_pf0', 'cn3_numa1_pf1']
        _run_test(expected_trees, expected_rps, member_of=member_of)

        # 3. rps in agg1 or agg3
        # cn1 in agg1 and cn3 in agg3 comes up
        member_of = [[uuids.agg1, uuids.agg3]]
        expected_trees = ['cn1', 'cn3']
        expected_rps = ['cn1', 'cn1_numa0_pf0', 'cn1_numa1_pf1',
                        'cn3', 'cn3_numa0_pf0', 'cn3_numa1_pf1']
        _run_test(expected_trees, expected_rps, member_of=member_of)

        # 4. rps in (agg1 or agg2) and (agg3)
        # cn1 is not in agg3
        member_of = [[uuids.agg1, uuids.agg2], [uuids.agg3]]
        expected_trees = ['cn3']
        expected_rps = ['cn3', 'cn3_numa0_pf0', 'cn3_numa1_pf1']
        _run_test(expected_trees, expected_rps, member_of=member_of)

        # 5. rps not in agg1
        # All rps under cn1 are excluded
        forbidden_aggs = [uuids.agg1]
        expected_trees = ['cn2', 'cn3']
        expected_rps = ['cn2', 'cn2_numa0_pf0', 'cn2_numa1_pf1',
                        'cn3', 'cn3_numa0_pf0', 'cn3_numa1_pf1']
        _run_test(expected_trees, expected_rps, forbidden_aggs=forbidden_aggs)

        # 6. rps not in agg2
        # All rps under cn1, under cn3 and pf1 on cn2 are excluded
        forbidden_aggs = [uuids.agg2]
        expected_trees = ['cn2']
        expected_rps = ['cn2', 'cn2_numa0_pf0']
        _run_test(expected_trees, expected_rps, forbidden_aggs=forbidden_aggs)

        # 7. rps neither in agg1 nor in agg4
        # All rps under cn1 and pf1 on cn3 are excluded
        forbidden_aggs = [uuids.agg1, uuids.agg4]
        expected_trees = ['cn2', 'cn3']
        expected_rps = ['cn2', 'cn2_numa0_pf0', 'cn2_numa1_pf1',
                        'cn3', 'cn3_numa0_pf0']
        _run_test(expected_trees, expected_rps, forbidden_aggs=forbidden_aggs)

        # 8. rps in agg3 and neither in agg1 nor in agg4
        # cn2 is not in agg3 so excluded
        member_of = [[uuids.agg3]]
        forbidden_aggs = [uuids.agg1, uuids.agg4]
        expected_trees = ['cn3']
        expected_rps = ['cn3', 'cn3_numa0_pf0']
        _run_test(expected_trees, expected_rps, member_of=member_of,
                  forbidden_aggs=forbidden_aggs)

        # 9. rps in agg1 or agg3 and not in agg3
        # ...which means rps in agg1 but not in agg3
        member_of = [[uuids.agg1, uuids.agg3]]
        forbidden_aggs = [uuids.agg3]
        expected_trees = ['cn1']
        expected_rps = ['cn1', 'cn1_numa0_pf0', 'cn1_numa1_pf1']
        _run_test(expected_trees, expected_rps, member_of=member_of,
                  forbidden_aggs=forbidden_aggs)

        # 10. rps in agg1 and not in agg1
        # ...which results in no rp
        member_of = [[uuids.agg1]]
        forbidden_aggs = [uuids.agg1]
        expected_trees = []
        expected_rps = []
        _run_test(expected_trees, expected_rps, member_of=member_of,
                  forbidden_aggs=forbidden_aggs)

        # OK, now consume all the VFs in the second compute node and verify
        # only the first and third computes are returned as root providers from
        # get_trees_matching_all()
        cn2_pf0 = rp_obj.ResourceProvider.get_by_uuid(self.ctx,
                                                      uuids.cn2_numa0_pf0)
        self.allocate_from_provider(cn2_pf0, orc.SRIOV_NET_VF, 8)

        cn2_pf1 = rp_obj.ResourceProvider.get_by_uuid(self.ctx,
                                                      uuids.cn2_numa1_pf1)
        self.allocate_from_provider(cn2_pf1, orc.SRIOV_NET_VF, 8)

        # cn2 had all its VFs consumed, so we should only get cn1 and cn3's IDs
        # as the root provider IDs.
        expected_trees = ['cn1', 'cn3']
        expected_rps = ['cn1', 'cn1_numa0_pf0', 'cn1_numa1_pf1',
                        'cn3', 'cn3_numa0_pf0', 'cn3_numa1_pf1']
        _run_test(expected_trees, expected_rps)

        # OK, now we're going to add a required trait to the mix. The only
        # provider that is decorated with the HW_NIC_OFFLOAD_GENEVE trait is
        # the second physical function on the third compute host. So we should
        # only get the third compute node back if we require that trait

        geneve_t = trait_obj.Trait.get_by_name(
            self.ctx, os_traits.HW_NIC_OFFLOAD_GENEVE)
        req_traits = [{geneve_t.name}]
        expected_trees = ['cn3']
        # NOTE(tetsuro): Actually we also get providers without traits here.
        # This is reported as bug#1771707 and from users' view the bug is now
        # fixed out of this get_trees_matching_all() function by checking
        # traits later again in _check_traits_for_alloc_request().
        # But ideally, we'd like to have only pf1 from cn3 here using SQL
        # query in get_trees_matching_all() function for optimization.
        # provider_names = ['cn3', 'cn3_numa1_pf1']
        expected_rps = ['cn3', 'cn3_numa0_pf0', 'cn3_numa1_pf1']
        _run_test(expected_trees, expected_rps, required_traits=req_traits)

        # Add in a required trait that no provider has associated with it and
        # verify that there are no returned allocation candidates
        avx2_t = trait_obj.Trait.get_by_name(
            self.ctx, os_traits.HW_CPU_X86_AVX2)
        req_traits = [{geneve_t.name}, {avx2_t.name}]
        _run_test([], [], required_traits=req_traits)

        # If we add the AVX2 trait as forbidden, not required, then we
        # should get back the original cn3
        req_traits = [{geneve_t.name}]
        forbidden_traits = {
            avx2_t.name: avx2_t.id,
        }
        expected_trees = ['cn3']
        # NOTE(tetsuro): Actually we also get providers without traits here.
        # This is reported as bug#1771707 and from users' view the bug is now
        # fixed out of this get_trees_matching_all() function by checking
        # traits later again in _check_traits_for_alloc_request().
        # But ideally, we'd like to have only pf1 from cn3 here using SQL
        # query in get_trees_matching_all() function for optimization.
        # provider_names = ['cn3', 'cn3_numa1_pf1']
        expected_rps = ['cn3', 'cn3_numa0_pf0', 'cn3_numa1_pf1']
        _run_test(expected_trees, expected_rps,
                  required_traits=req_traits,
                  forbidden_traits=forbidden_traits)

        # Consume all the VFs in first and third compute nodes and verify
        # no more providers are returned
        cn1_pf0 = rp_obj.ResourceProvider.get_by_uuid(self.ctx,
                                                      uuids.cn1_numa0_pf0)
        self.allocate_from_provider(cn1_pf0, orc.SRIOV_NET_VF, 8)

        cn1_pf1 = rp_obj.ResourceProvider.get_by_uuid(self.ctx,
                                                      uuids.cn1_numa1_pf1)
        self.allocate_from_provider(cn1_pf1, orc.SRIOV_NET_VF, 8)
        cn3_pf0 = rp_obj.ResourceProvider.get_by_uuid(self.ctx,
                                                      uuids.cn3_numa0_pf0)
        self.allocate_from_provider(cn3_pf0, orc.SRIOV_NET_VF, 8)

        cn3_pf1 = rp_obj.ResourceProvider.get_by_uuid(self.ctx,
                                                      uuids.cn3_numa1_pf1)
        self.allocate_from_provider(cn3_pf1, orc.SRIOV_NET_VF, 8)

        _run_test([], [], required_traits=req_traits,
                  forbidden_traits=forbidden_traits)

    def _make_trees_with_traits(self):
        # We are setting up 6 trees of providers with following traits:
        #
        #                  compute node (cn)
        #                 /                 \
        #               pf 0               pf 1
        #
        # +-----+----------------+---------------------+---------------------+
        # |     |       cn       |         pf0         |         pf1         |
        # +-----+----------------+---------------------+---------------------+
        # |tree1|HW_CPU_X86_AVX2 |                     |HW_NIC_OFFLOAD_GENEVE|
        # +-----+----------------+---------------------+---------------------+
        # |tree2|STORAGE_DISK_SSD|                     |                     |
        # +-----+----------------+---------------------+---------------------+
        # |tree3|HW_CPU_X86_AVX2 |                     |                     |
        # |     |STORAGE_DISK_SSD|                     |                     |
        # +-----+----------------+---------------------+---------------------+
        # |tree4|                |HW_NIC_ACCEL_SSL     |                     |
        # |     |                |HW_NIC_OFFLOAD_GENEVE|                     |
        # +-----+----------------+---------------------+---------------------+
        # |tree5|                |HW_NIC_ACCEL_SSL     |HW_NIC_OFFLOAD_GENEVE|
        # +-----+----------------+---------------------+---------------------+
        # |tree6|                |HW_NIC_ACCEL_SSL     |HW_NIC_ACCEL_SSL     |
        # +-----+----------------+---------------------+---------------------+
        # |tree7|                |                     |                     |
        # +-----+----------------+---------------------+---------------------+
        #

        rp_ids = set()
        for x in ('1', '2', '3', '4', '5', '6', '7'):
            name = 'cn' + x
            cn = self._create_provider(name)
            name = 'cn' + x + '_pf0'
            pf0 = self._create_provider(name, parent=cn.uuid)
            name = 'cn' + x + '_pf1'
            pf1 = self._create_provider(name, parent=cn.uuid)

            rp_ids |= set([cn.id, pf0.id, pf1.id])

            if x == '1':
                tb.set_traits(cn, os_traits.HW_CPU_X86_AVX2)
                tb.set_traits(pf1, os_traits.HW_NIC_OFFLOAD_GENEVE)
            if x == '2':
                tb.set_traits(cn, os_traits.STORAGE_DISK_SSD)
            if x == '3':
                tb.set_traits(cn, os_traits.HW_CPU_X86_AVX2,
                              os_traits.STORAGE_DISK_SSD)
            if x == '4':
                tb.set_traits(pf0, os_traits.HW_NIC_ACCEL_SSL,
                              os_traits.HW_NIC_OFFLOAD_GENEVE)
            if x == '5':
                tb.set_traits(pf0, os_traits.HW_NIC_ACCEL_SSL)
                tb.set_traits(pf1, os_traits.HW_NIC_OFFLOAD_GENEVE)
            if x == '6':
                tb.set_traits(pf0, os_traits.HW_NIC_ACCEL_SSL)
                tb.set_traits(pf1, os_traits.HW_NIC_ACCEL_SSL)

        avx2_t = trait_obj.Trait.get_by_name(
            self.ctx, os_traits.HW_CPU_X86_AVX2)
        ssd_t = trait_obj.Trait.get_by_name(
            self.ctx, os_traits.STORAGE_DISK_SSD)
        geneve_t = trait_obj.Trait.get_by_name(
            self.ctx, os_traits.HW_NIC_OFFLOAD_GENEVE)
        ssl_t = trait_obj.Trait.get_by_name(
            self.ctx, os_traits.HW_NIC_ACCEL_SSL)

        return rp_ids, avx2_t, ssd_t, geneve_t, ssl_t

    def test_get_trees_with_traits(self):
        """Creates a few provider trees having different traits and tests the
        _get_trees_with_traits() utility function to ensure that only the
        root provider IDs of matching traits are returned.
        """
        rp_ids, avx2_t, ssd_t, geneve_t, ssl_t = self._make_trees_with_traits()

        # Case1: required on root
        required_traits = [{avx2_t.id}]
        forbidden_traits = {}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)

        tree_root_ids = set([p[1] for p in rp_tuples_with_trait])

        provider_names = ['cn1', 'cn3']
        expect_root_ids = self._get_rp_ids_matching_names(provider_names)
        self.assertEqual(expect_root_ids, tree_root_ids)

        # Case1': required on root with forbidden traits
        # Let's validate that cn3 disappears
        required_traits = [{avx2_t.id}]
        forbidden_traits = {ssd_t.id}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)

        tree_root_ids = set([p[1] for p in rp_tuples_with_trait])

        provider_names = ['cn1']
        expect_root_ids = self._get_rp_ids_matching_names(provider_names)
        self.assertEqual(expect_root_ids, tree_root_ids)

        # Case2: multiple required on root
        required_traits = [{avx2_t.id}, {ssd_t.id}]
        forbidden_traits = {}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)

        tree_root_ids = set([p[1] for p in rp_tuples_with_trait])

        provider_names = ['cn3']
        expect_root_ids = self._get_rp_ids_matching_names(provider_names)
        self.assertEqual(expect_root_ids, tree_root_ids)

        # Case3: required on child
        required_traits = [{geneve_t.id}]
        forbidden_traits = {}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)

        tree_root_ids = set([p[1] for p in rp_tuples_with_trait])

        provider_names = ['cn1', 'cn4', 'cn5']
        expect_root_ids = self._get_rp_ids_matching_names(provider_names)
        self.assertEqual(expect_root_ids, tree_root_ids)

        # Case3': required on child with forbidden traits
        # Let's validate that cn4 disappears
        required_traits = [{geneve_t.id}]
        forbidden_traits = {ssl_t.id}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)

        tree_root_ids = set([p[1] for p in rp_tuples_with_trait])

        provider_names = ['cn1', 'cn5']
        expect_root_ids = self._get_rp_ids_matching_names(provider_names)
        self.assertEqual(expect_root_ids, tree_root_ids)

        # Case4: multiple required on child
        required_traits = [{geneve_t.id}, {ssl_t.id}]
        forbidden_traits = {}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)

        tree_root_ids = set([p[1] for p in rp_tuples_with_trait])

        provider_names = ['cn4', 'cn5']
        expect_root_ids = self._get_rp_ids_matching_names(provider_names)
        self.assertEqual(expect_root_ids, tree_root_ids)

        # Case5: required on root and child
        required_traits = [{avx2_t.id}, {geneve_t.id}]
        forbidden_traits = {}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)

        tree_root_ids = set([p[1] for p in rp_tuples_with_trait])

        provider_names = ['cn1']
        expect_root_ids = self._get_rp_ids_matching_names(provider_names)
        self.assertEqual(expect_root_ids, tree_root_ids)

    def test_get_trees_with_traits_forbidden_1(self):
        """Using the following tree
               cn1 CUSTOM_FOO
                |
               cn1_c1
        """

        cn1 = self._create_provider('cn1')
        cn1_c1 = self._create_provider('cn1_c1', parent=cn1.uuid)
        tb.set_traits(cn1, 'CUSTOM_FOO')
        custom_foo = trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_FOO')

        required_traits = []
        forbidden_traits = {custom_foo.id}
        rp_ids = {cn1.id, cn1_c1.id}  # both RP from the tree

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)
        # tree is returned as the forbidden trait did not filter out all the
        # rps from the tree. The tree might still be a match to the request
        # via cn1_c1
        self.assertEqual(
            {(cn1.id, cn1.id), (cn1_c1.id, cn1.id)},
            rp_tuples_with_trait
        )

        # simulate that cn1_c1 already filtered out by other filters
        rp_ids = {cn1.id}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)
        # the tree is not returned any more as the only considered rp is cn1
        # but that has a forbidden trait
        self.assertEqual(set(), rp_tuples_with_trait)

    def test_get_trees_with_traits_forbidden_2(self):
        """Using the following tree
               cn1 CUSTOM_FOO
                |
               cn1_c1 CUSTOM_FOO
        """
        cn1 = self._create_provider('cn1')
        cn1_c1 = self._create_provider('cn1_c1', parent=cn1.uuid)
        tb.set_traits(cn1, 'CUSTOM_FOO')
        custom_foo = trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_FOO')
        tb.set_traits(cn1_c1, 'CUSTOM_FOO')

        required_traits = []
        forbidden_traits = {custom_foo.id}
        rp_ids = {cn1.id, cn1_c1.id}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)
        # now both rp from the tree is filtered out by the forbidden trait
        # so the tree is filtered out
        self.assertEqual(set(), rp_tuples_with_trait)

    def test_get_trees_with_traits_forbidden_3(self):
        """Using the following tree
               cn1 CUSTOM_FOO, CUSTOM_BAR
                |
               cn1_c1
        """
        cn1 = self._create_provider('cn1')
        cn1_c1 = self._create_provider('cn1_c1', parent=cn1.uuid)
        tb.set_traits(cn1, 'CUSTOM_FOO', 'CUSTOM_BAR')
        custom_foo = trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_FOO')
        custom_bar = trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_BAR')

        required_traits = [{custom_bar.id}]
        forbidden_traits = {custom_foo.id}
        rp_ids = {cn1.id, cn1_c1.id}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)
        # only cn1 could provide the required trait but cn1 also has the
        # forbidden trait. The rest of the tree does not provide the required
        # trait so this tree cannot be a match for the request
        self.assertEqual(set(), rp_tuples_with_trait)

        # simulate that cn1_c1 already filtered out by other filters
        rp_ids = {cn1.id}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)
        # only cn1 could provide the required trait but cn1 also has the
        # forbidden trait. There is no other rps in the tree to be considered.
        self.assertEqual(set(), rp_tuples_with_trait)

    def make_tree_for_any_traits(self, tree_index, trait_list):
        """Create an RP tree with traits
                     CNx
                    /   \
              CNx_C1    CNx_C2
                |
              CNx_C1_GC1
        """
        cn_name = f'cn{tree_index}'
        cn = self._create_provider(cn_name)
        cn_c1 = self._create_provider(cn_name + 'c1', parent=cn.uuid)
        cn_c1_gc1 = self._create_provider(
            cn_name + 'c1_gc1', parent=cn_c1.uuid)
        cn_c2 = self._create_provider(cn_name + 'c2', parent=cn.uuid)

        rps = [cn, cn_c1, cn_c2, cn_c1_gc1]

        for rp, traits in zip(rps, trait_list):
            tb.set_traits(rp, *traits)

        return [(rp.id, cn.id) for rp in rps]

    def make_trees_with_traits_for_any_traits(self, rp_trait_list):
        rp_ids = []

        for index, rp_traits in rp_trait_list:
            rp_ids += self.make_tree_for_any_traits(index, rp_traits)

        return rp_ids

    def test_get_trees_with_traits_any_traits(self):
        """We are setting up multiple RP trees with the same structure but
        with different traits. The structure is
                     CNx
                    /   \
              CNx_C1    CNx_C2
                |
              CNx_C1_GC1

        The required trait query is ((A or B) and C). Then we assert that
        only the matching trees are returned.

        """
        a = 'CUSTOM_A'
        b = 'CUSTOM_B'
        c = 'CUSTOM_C'

        # autopep8: off
        matching_trees = [
            #     CN         C1      C2      C1_GC1
            (1,  [[a, b, c], [],     [],     [], ], ), # noqa
            (2,  [[a, c],    [b],    [],     [], ], ), # noqa
            (3,  [[a],       [b, c], [],     [], ], ), # noqa
            (4,  [[a],       [b],    [c],    [], ], ), # noqa
            (5,  [[c],       [b],    [a],    [], ], ), # noqa
            (6,  [[],        [a],    [b],    [c], ], ), # noqa
            (7,  [[c],       [],     [a, b], [], ], ), # noqa
            (8,  [[c],       [],     [],     [a, b], ], ), # noqa
            (9,  [[a, b],    [b],    [a],    [c], ], ), # noqa
            (10, [[b, c],    [],     [],     [], ], ), # noqa
            (11, [[c],       [a],    [],     [], ], ), # noqa
            (12, [[a],       [],     [c],    [], ], ), # noqa
            (13, [[b],       [],     [],     [c], ], ), # noqa
            (14, [[],        [b],    [],     [c], ], ), # noqa
        ]

        non_matching_trees = [
            #     CN         C1      C2      C1_GC1
            (15, [[a, b],    [],     [],     [], ], ), # noqa
            (16, [[],        [a],    [],     [b], ], ), # noqa
            (17, [[c],       [],     [],     [], ], ), # noqa
            (18, [[],        [c],    [],     [], ], ), # noqa
            (19, [[],        [],     [a],    [], ], ), # noqa
        ]
        # autopep8: on

        matching_rp_ids = self.make_trees_with_traits_for_any_traits(
            matching_trees)

        non_matching_rp_ids = self.make_trees_with_traits_for_any_traits(
            non_matching_trees)

        trait_a = trait_obj.Trait.get_by_name(self.ctx, a).id
        trait_b = trait_obj.Trait.get_by_name(self.ctx, b).id
        trait_c = trait_obj.Trait.get_by_name(self.ctx, c).id

        # (A or B) and C
        required_traits = [{trait_a, trait_b}, {trait_c}]

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx,
            {rp_id for rp_id, _ in matching_rp_ids + non_matching_rp_ids},
            required_traits,
            {}
        )
        # we check that every RP from every tree we expected to match is
        # returned and none of the RPs from the other trees are returned
        self.assertEqual(set(matching_rp_ids), rp_tuples_with_trait)

    def test_get_trees_with_traits_any_traits_forbidden(self):
        """Query RP trees with complex trait query involving both AND and OR
        and forbidden traits

        We use the following tree structure for these test with specific
        traits.
                     CN1 CUSTOM_A
                    /   \
              CN1_C1    CN1_C2 CUSTOM_B,
                |
              CN1_C1_GC1 CUSTOM_C

        And each node has one extra custom trait with its own name so the test
        can easily forbid one or more RPs directly from the tree.

        We use the formula (CUSTOM_A or CUSTOM_B) and CUSTOM_C) in this test.
        Then we do the following cases where forbidden traits remove RPs:

            1) with an unnecessary trait -> OK
            2) with one side of an OR -> OK
            3) with both side of an OR -> NOK
            4) with one side of an AND -> NOK
        """
        cn1 = self._create_provider('cn1')
        tb.set_traits(cn1, 'CUSTOM_A', 'CUSTOM_CN1')
        cn1_c1 = self._create_provider('cn1_c1', parent=cn1.uuid)
        tb.set_traits(cn1_c1, 'CUSTOM_CN1_C1')
        cn1_c1_gc1 = self._create_provider('cn1_c1_gc1', parent=cn1_c1.uuid)
        tb.set_traits(cn1_c1_gc1, 'CUSTOM_C', 'CUSTOM_CN1_C1_GC1')
        cn1_c2 = self._create_provider('cn1_c2', parent=cn1.uuid)
        tb.set_traits(cn1_c2, 'CUSTOM_B', 'CUSTOM_CN1_C2')

        trait_a = trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_A').id
        trait_b = trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_B').id
        trait_c = trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_C').id

        trait_cn1 = trait_obj.Trait.get_by_name(self.ctx, 'CUSTOM_CN1').id
        trait_cn1_c1 = trait_obj.Trait.get_by_name(
            self.ctx, 'CUSTOM_CN1_C1').id
        trait_cn1_c1_gc1 = trait_obj.Trait.get_by_name(
            self.ctx, 'CUSTOM_CN1_C1_GC1').id
        trait_cn1_c2 = trait_obj.Trait.get_by_name(
            self.ctx, 'CUSTOM_CN1_C2').id

        rp_ids = {cn1.id, cn1_c1.id, cn1_c1_gc1.id, cn1_c2.id}
        expected_whole_tree = {(rp_id, cn1.id) for rp_id in rp_ids}

        # (A or B) and C
        required_traits = [{trait_a, trait_b}, {trait_c}]

        # 1) forbid CN1_C1 but that is not needed
        forbidden_traits = {trait_cn1_c1}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)
        self.assertEqual(expected_whole_tree, rp_tuples_with_trait)

        # 2) forbid CN1_C2 which has trait B. But trait A is also enough, and
        # we have that on CN1 so this should still match
        forbidden_traits = {trait_cn1_c2}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)
        self.assertEqual(expected_whole_tree, rp_tuples_with_trait)

        # 3) forbid CN1 and CN1_C2. This means neither trait A nor B is
        # available so this is expected to not produce a match
        forbidden_traits = {trait_cn1_c2, trait_cn1}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)
        self.assertEqual(set(), rp_tuples_with_trait)

        # 4) forbid CN1_C1_GC1. This means neither trait C is not available.
        # So (A or B) and C cannot be fulfilled.
        forbidden_traits = {trait_cn1_c1_gc1}

        rp_tuples_with_trait = res_ctx._get_trees_with_traits(
            self.ctx, rp_ids, required_traits, forbidden_traits)
        self.assertEqual(set(), rp_tuples_with_trait)

    def test_get_roots_with_traits(self):
        _, avx2_t, ssd_t, geneve_t, ssl_t = self._make_trees_with_traits()

        def do_test(required=None, forbidden=None, expected=None):
            actual = res_ctx._get_roots_with_traits(
                self.ctx,
                set(trait.id for trait in required or []),
                set(trait.id for trait in forbidden or []))
            if expected:
                expected = self._get_rp_ids_matching_names(
                    'cn%d' % d for d in expected)
            self.assertEqual(expected or set(), actual)

        # One of required/forbidden must be specified
        self.assertRaises(ValueError, do_test)

        # AVX2 is on cn1 and cn3
        do_test(required=[avx2_t], expected=(1, 3))
        # Multiple required
        do_test(required=[avx2_t, ssd_t], expected=(3,))
        # No match on roots for a trait on children
        do_test(required=[geneve_t])
        # ...even if including a trait also on roots
        do_test(required=[geneve_t, ssd_t])

        # Forbid traits not on any roots. These are on non-root providers...
        do_test(forbidden=[geneve_t, ssl_t], expected=(1, 2, 3, 4, 5, 6, 7))
        # ...and this one is nowhere in the environment.
        hdd_t = trait_obj.Trait.get_by_name(
            self.ctx, os_traits.STORAGE_DISK_HDD)
        do_test(forbidden=[hdd_t], expected=(1, 2, 3, 4, 5, 6, 7))
        # Forbid traits just on roots
        do_test(forbidden=[avx2_t, ssd_t], expected=(4, 5, 6, 7))
        # Forbid traits on roots and children
        do_test(forbidden=[ssd_t, ssl_t, geneve_t], expected=(1, 4, 5, 6, 7))

        # Required & forbidden both on roots
        do_test(required=[avx2_t], forbidden=[ssd_t], expected=(1,))
        # Same, but adding forbidden not on roots has no effect
        do_test(required=[avx2_t], forbidden=[ssd_t, ssl_t], expected=(1,))
        # Required on roots, forbidden only on children
        do_test(
            required=[avx2_t, ssd_t], forbidden=[ssl_t, geneve_t],
            expected=(3,))

        # Required & forbidden overlap. No results because it is impossible for
        # one provider to both have and not have a trait. (Unreachable in real
        # life due to conflict check in the handler.)
        do_test(required=[avx2_t, ssd_t], forbidden=[ssd_t, geneve_t])


class AllocationCandidatesTestCase(tb.PlacementDbBaseTestCase):
    """Tests a variety of scenarios with both shared and non-shared resource
    providers that the AllocationCandidates.get_by_requests() method returns a
    set of alternative allocation requests and provider summaries that may be
    used by the scheduler to sort/weigh the options it has for claiming
    resources against providers.
    """

    def setUp(self):
        super(AllocationCandidatesTestCase, self).setUp()
        self.requested_resources = {
            orc.VCPU: 1,
            orc.MEMORY_MB: 64,
            orc.DISK_GB: 1500,
        }
        # For debugging purposes, populated by _create_provider and used by
        # _validate_allocation_requests to make failure results more readable.
        self.rp_uuid_to_name = {}

    def _get_allocation_candidates(self, groups=None, rqparams=None):
        if groups is None:
            groups = {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources)}
        if rqparams is None:
            rqparams = placement_lib.RequestWideParams()
        return ac_obj.AllocationCandidates.get_by_requests(
            self.ctx, groups, rqparams)

    def _mappings_to_suffix(self, mappings):
        """Turn a dict of AllocationRequest mappings keyed on suffix to
        a dict, keyed by uuid, of lists of suffixes.
        """
        suffixes_by_uuid = collections.defaultdict(set)
        for suffix, rps in mappings.items():
            for rp_uuid in rps:
                suffixes_by_uuid[rp_uuid].add(suffix)
        listed_sorted_suffixes = {}
        for rp_uuid, suffixes in suffixes_by_uuid.items():
            listed_sorted_suffixes[rp_uuid] = sorted(list(suffixes))
        return listed_sorted_suffixes

    def _validate_allocation_requests(self, expected, candidates,
                                      expect_suffixes=False):
        """Assert correctness of allocation requests in allocation candidates.

        This is set up to make it easy for the caller to specify the expected
        result, to make that expected structure readable for someone looking at
        the test case, and to make test failures readable for debugging.

        :param expected: A list of lists of tuples representing the expected
                         allocation requests, of the form:
             [
                [(resource_provider_name, resource_class_name, resource_count),
                 ...,
                ],
                ...
             ]
        :param candidates: The result from AllocationCandidates.get_by_requests
        :param expect_suffixes: If True, validate the AllocationRequest
                                mappings in the results, found as a list of
                                suffixes in 4th member of the tuple described
                                above.
        """
        # Extract/convert allocation requests from candidates
        observed = []
        for ar in candidates.allocation_requests:
            suffixes_by_uuid = self._mappings_to_suffix(ar.mappings)
            rrs = []
            for rr in ar.resource_requests:
                req_tuple = (self.rp_uuid_to_name[rr.resource_provider.uuid],
                             rr.resource_class, rr.amount)
                if expect_suffixes:
                    req_tuple = (
                        req_tuple +
                        (suffixes_by_uuid[rr.resource_provider.uuid], ))
                rrs.append(req_tuple)
            rrs.sort()
            observed.append(rrs)
        observed.sort()

        # Sort the guts of the expected structure
        for rr in expected:
            rr.sort()
        expected.sort()

        # Now we ought to be able to compare them
        self.assertEqual(expected, observed)

    def _validate_provider_summary_resources(self, expected, candidates):
        """Assert correctness of the resources in provider summaries in
        allocation candidates.

        This is set up to make it easy for the caller to specify the expected
        result, to make that expected structure readable for someone looking at
        the test case, and to make test failures readable for debugging.

        :param expected: A dict, keyed by resource provider name, of sets of
                         3-tuples containing resource class, capacity, and
                         amount used:
                            { resource_provider_name: set([
                                  (resource_class, capacity, used),
                                  ...,
                              ]),
                              ...,
                            }
        :param candidates: The result from AllocationCandidates.get_by_requests
        """
        observed = {}
        for psum in candidates.provider_summaries:
            rpname = self.rp_uuid_to_name[psum.resource_provider.uuid]
            reslist = set()
            for res in psum.resources:
                reslist.add((res.resource_class, res.capacity, res.used))
            if rpname in observed:
                self.fail("Found resource provider %s more than once in "
                          "provider_summaries!" % rpname)
            observed[rpname] = reslist

        # Now we ought to be able to compare them
        self.assertEqual(expected, observed)

    def _validate_provider_summary_traits(self, expected, candidates):
        """Assert correctness of the traits in provider summaries in allocation
        candidates.

        This is set up to make it easy for the caller to specify the expected
        result, to make that expected structure readable for someone looking at
        the test case, and to make test failures readable for debugging.

        :param expected: A dict, keyed by resource provider name, of sets of
                         string trait names:
                            { resource_provider_name: set([
                                  trait_name, ...
                              ]),
                              ...,
                            }
        :param candidates: The result from AllocationCandidates.get_by_requests
        """
        observed = {}
        for psum in candidates.provider_summaries:
            rpname = self.rp_uuid_to_name[psum.resource_provider.uuid]
            observed[rpname] = set(psum.traits)

        self.assertEqual(expected, observed)

    def test_unknown_traits(self):
        missing = [{'UNKNOWN_TRAIT'}]
        requests = {'': placement_lib.RequestGroup(
            use_same_provider=False, resources=self.requested_resources,
            required_traits=missing)}
        self.assertRaises(
            exception.TraitNotFound,
            ac_obj.AllocationCandidates.get_by_requests,
            self.ctx, requests, placement_lib.RequestWideParams())

    def test_allc_req_and_prov_summary(self):
        """Simply test with one resource provider that the allocation
        requests returned by AllocationCandidates have valid
        allocation_requests and provider_summaries.
        """
        cn1 = self._create_provider('cn1')
        tb.add_inventory(cn1, orc.VCPU, 8)
        tb.add_inventory(cn1, orc.MEMORY_MB, 2048)
        tb.add_inventory(cn1, orc.DISK_GB, 2000)

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.VCPU: 1
                }
            )}
        )

        expected = [
            [('cn1', orc.VCPU, 1, [''])]
        ]
        self._validate_allocation_requests(
            expected, alloc_cands, expect_suffixes=True)

        expected = {
            'cn1': set([
                (orc.VCPU, 8, 0),
                (orc.MEMORY_MB, 2048, 0),
                (orc.DISK_GB, 2000, 0)
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_all_local(self):
        """Create some resource providers that can satisfy the request for
        resources with local (non-shared) resources and verify that the
        allocation requests returned by AllocationCandidates correspond with
        each of these resource providers.
        """
        # Create three compute node providers with VCPU, RAM and local disk
        cn1, cn2, cn3 = (self._create_provider(name)
                         for name in ('cn1', 'cn2', 'cn3'))
        for cn in (cn1, cn2, cn3):
            tb.add_inventory(cn, orc.VCPU, 24,
                             allocation_ratio=16.0)
            tb.add_inventory(cn, orc.MEMORY_MB, 32768,
                             min_unit=64, step_size=64, allocation_ratio=1.5)
            total_gb = 1000 if cn.name == 'cn3' else 2000
            tb.add_inventory(cn, orc.DISK_GB, total_gb,
                             reserved=100, min_unit=10, step_size=10,
                             allocation_ratio=1.0)

        # Ask for the alternative placement possibilities and verify each
        # provider is returned
        alloc_cands = self._get_allocation_candidates()

        # Verify the provider summary information indicates 0 usage and
        # capacity calculated from above inventory numbers for the first two
        # compute nodes.  The third doesn't show up because it lacks sufficient
        # disk capacity.
        expected = {
            'cn1': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 32768 * 1.5, 0),
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 32768 * 1.5, 0),
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # Verify the allocation requests that are returned. There should be 2
        # allocation requests, one for each compute node, containing 3
        # resources in each allocation request, one each for VCPU, RAM, and
        # disk. The amounts of the requests should correspond to the requested
        # resource amounts in the filter:resources dict passed to
        # AllocationCandidates.get_by_requests().
        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('cn1', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 1),
             ('cn2', orc.MEMORY_MB, 64),
             ('cn2', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        # Now let's add traits into the mix. Currently, none of the compute
        # nodes has the AVX2 trait associated with it, so we should get 0
        # results if we required AVX2
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=[{os_traits.HW_CPU_X86_AVX2}]
            )},
        )
        self._validate_allocation_requests([], alloc_cands)

        # If we then associate the AVX2 trait to just compute node 2, we should
        # get back just that compute node in the provider summaries
        tb.set_traits(cn2, 'HW_CPU_X86_AVX2')

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=[{os_traits.HW_CPU_X86_AVX2}]
            )},
        )
        # Only cn2 should be in our allocation requests now since that's the
        # only one with the required trait
        expected = [
            [('cn2', orc.VCPU, 1),
             ('cn2', orc.MEMORY_MB, 64),
             ('cn2', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)
        p_sums = alloc_cands.provider_summaries
        self.assertEqual(1, len(p_sums))

        expected = {
            'cn2': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 32768 * 1.5, 0),
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        expected = {
            'cn2': set(['HW_CPU_X86_AVX2'])
        }
        self._validate_provider_summary_traits(expected, alloc_cands)

        # Confirm that forbidden traits changes the results to get cn1.
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                forbidden_traits=set([os_traits.HW_CPU_X86_AVX2])
            )},
        )
        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('cn1', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        # Now create a more complex trait query: (AVX2 and (SSE or SSE2))
        # First no result is expected as none of the RPs has SSE or SSE2 traits
        required_traits = [
            {os_traits.HW_CPU_X86_AVX2},
            {os_traits.HW_CPU_X86_SSE, os_traits.HW_CPU_X86_SSE2}
        ]

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=required_traits,
            )},
        )

        self._validate_allocation_requests([], alloc_cands)

        # Next we add SSE to one of the RPs that has no AVX2, so we still
        # expect empty result
        tb.set_traits(cn1, 'HW_CPU_X86_SSE')

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=required_traits,
            )},
        )

        self._validate_allocation_requests([], alloc_cands)

        # Next we add SSE2 to the cn2 where there are AVX2 too, and we expect
        # that cn2 is a match now
        tb.set_traits(cn2, 'HW_CPU_X86_AVX2', 'HW_CPU_X86_SSE2')

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=required_traits,
            )},
        )
        expected = [
            [('cn2', orc.VCPU, 1),
             ('cn2', orc.MEMORY_MB, 64),
             ('cn2', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)
        p_sums = alloc_cands.provider_summaries
        self.assertEqual(1, len(p_sums))

        expected = {
            'cn2': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 32768 * 1.5, 0),
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # Next forbid SSE2 in the request so the trait query becomes
        # (AVX2 and (SSE or SSE2) and !SSE2) this should lead to no candidate
        # as cn2 has SSE2
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=required_traits,
                forbidden_traits={'HW_CPU_X86_SSE2'},
            )},
        )

        self._validate_allocation_requests([], alloc_cands)

        # But if we forbid SSE instead of SSE2 then we get back cn2
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=required_traits,
                forbidden_traits={'HW_CPU_X86_SSE'}
            )},
        )
        expected = [
            [('cn2', orc.VCPU, 1),
             ('cn2', orc.MEMORY_MB, 64),
             ('cn2', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)
        p_sums = alloc_cands.provider_summaries
        self.assertEqual(1, len(p_sums))

        expected = {
            'cn2': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 32768 * 1.5, 0),
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_all_local_limit(self):
        """Create some resource providers that can satisfy the request for
        resources with local (non-shared) resources, limit them, and verify
        that the allocation requests returned by AllocationCandidates
        correspond with each of these resource providers.
        """
        # Create three compute node providers with VCPU, RAM and local disk
        for name in ('cn1', 'cn2', 'cn3'):
            cn = self._create_provider(name)
            tb.add_inventory(cn, orc.VCPU, 24, allocation_ratio=16.0)
            tb.add_inventory(cn, orc.MEMORY_MB, 32768,
                             min_unit=64, step_size=64, allocation_ratio=1.5)
            total_gb = 1000 if name == 'cn3' else 2000
            tb.add_inventory(cn, orc.DISK_GB, total_gb,
                             reserved=100, min_unit=10, step_size=10,
                             allocation_ratio=1.0)

        # Ask for just one candidate.
        limit = 1
        alloc_cands = self._get_allocation_candidates(
            rqparams=placement_lib.RequestWideParams(limit=limit))
        allocation_requests = alloc_cands.allocation_requests
        self.assertEqual(limit, len(allocation_requests))

        # provider summaries should have only one rp
        self.assertEqual(limit, len(alloc_cands.provider_summaries))

        # Do it again, with conf set to randomize. We can't confirm the
        # random-ness but we can be sure the code path doesn't explode.
        self.conf_fixture.config(randomize_allocation_candidates=True,
                                 group='placement')

        # Ask for two candidates.
        limit = 2
        alloc_cands = self._get_allocation_candidates(
            rqparams=placement_lib.RequestWideParams(limit=limit))
        allocation_requests = alloc_cands.allocation_requests
        self.assertEqual(limit, len(allocation_requests))

        # provider summaries should have two rps
        self.assertEqual(limit, len(alloc_cands.provider_summaries))

        # Do it again, asking for more than are available.
        limit = 5
        # We still only expect 2 because cn3 does not match default requests.
        expected_length = 2
        alloc_cands = self._get_allocation_candidates(
            rqparams=placement_lib.RequestWideParams(limit=limit))
        allocation_requests = alloc_cands.allocation_requests
        self.assertEqual(expected_length, len(allocation_requests))

        # provider summaries should have two rps
        self.assertEqual(expected_length, len(alloc_cands.provider_summaries))

    def test_local_with_shared_disk(self):
        """Create some resource providers that can satisfy the request for
        resources with local VCPU and MEMORY_MB but rely on a shared storage
        pool to satisfy DISK_GB and verify that the allocation requests
        returned by AllocationCandidates have DISK_GB served up by the shared
        storage pool resource provider and VCPU/MEMORY_MB by the compute node
        providers
        """
        # Create two compute node providers with VCPU, RAM and NO local disk,
        # associated with the aggregate.
        cn1, cn2 = (self._create_provider(name, uuids.agg)
                    for name in ('cn1', 'cn2'))
        for cn in (cn1, cn2):
            tb.add_inventory(cn, orc.VCPU, 24, allocation_ratio=16.0)
            tb.add_inventory(cn, orc.MEMORY_MB, 1024,
                             min_unit=64, allocation_ratio=1.5)

        # Create the shared storage pool, associated with the same aggregate
        ss = self._create_provider('shared storage', uuids.agg)

        # Give the shared storage pool some inventory of DISK_GB
        tb.add_inventory(ss, orc.DISK_GB, 2000, reserved=100, min_unit=10)

        # Mark the shared storage pool as having inventory shared among any
        # provider associated via aggregate
        tb.set_traits(ss, "MISC_SHARES_VIA_AGGREGATE")

        # Ask for the alternative placement possibilities and verify each
        # compute node provider is listed in the allocation requests as well as
        # the shared storage pool provider
        alloc_cands = self._get_allocation_candidates()

        # Verify the provider summary information indicates 0 usage and
        # capacity calculated from above inventory numbers for both compute
        # nodes and the shared provider.
        expected = {
            'cn1': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
            ]),
            'shared storage': set([
                (orc.DISK_GB, 2000 - 100, 0)
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # Verify the allocation requests that are returned. There should be 2
        # allocation requests, one for each compute node, containing 3
        # resources in each allocation request, one each for VCPU, RAM, and
        # disk. The amounts of the requests should correspond to the requested
        # resource amounts in the filter:resources dict passed to
        # AllocationCandidates.get_by_requests(). The providers for VCPU and
        # MEMORY_MB should be the compute nodes while the provider for the
        # DISK_GB should be the shared storage pool
        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('shared storage', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 1),
             ('cn2', orc.MEMORY_MB, 64),
             ('shared storage', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        # Test for bug #1705071. We query for allocation candidates with a
        # request for ONLY the DISK_GB (the resource that is shared with
        # compute nodes) and no VCPU/MEMORY_MB. Before the fix for bug
        # #1705071, this resulted in a KeyError

        alloc_cands = self._get_allocation_candidates(
            groups={'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'DISK_GB': 10,
                }
            )}
        )

        # We should only have provider summary information for the sharing
        # storage provider, since that's the only provider that can be
        # allocated against for this request.  In the future, we may look into
        # returning the shared-with providers in the provider summaries, but
        # that's a distant possibility.
        expected = {
            'shared storage': set([
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # The allocation_requests will only include the shared storage
        # provider because the only thing we're requesting to allocate is
        # against the provider of DISK_GB, which happens to be the shared
        # storage provider.
        expected = [[('shared storage', orc.DISK_GB, 10)]]
        self._validate_allocation_requests(expected, alloc_cands)

        # Now we're going to add a set of required traits into the request mix.
        # To start off, let's request a required trait that we know has not
        # been associated yet with any provider, and ensure we get no results
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=[{os_traits.HW_CPU_X86_AVX2}],
            )}
        )

        # We have not yet associated the AVX2 trait to any provider, so we
        # should get zero allocation candidates
        p_sums = alloc_cands.provider_summaries
        self.assertEqual(0, len(p_sums))

        # Now, if we then associate the required trait with both of our compute
        # nodes, we should get back both compute nodes since they both now
        # satisfy the required traits as well as the resource request
        avx2_t = trait_obj.Trait.get_by_name(
            self.ctx, os_traits.HW_CPU_X86_AVX2)
        cn1.set_traits([avx2_t])
        cn2.set_traits([avx2_t])

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=[{os_traits.HW_CPU_X86_AVX2}],
            )}
        )

        # There should be 2 compute node providers and 1 shared storage
        # provider in the summaries.
        expected = {
            'cn1': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
            ]),
            'shared storage': set([
                (orc.DISK_GB, 2000 - 100, 0)
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # Let's check that the traits listed for the compute nodes include the
        # AVX2 trait, and the shared storage provider in the provider summaries
        # does NOT have the AVX2 trait.
        expected = {
            'cn1': set(['HW_CPU_X86_AVX2']),
            'cn2': set(['HW_CPU_X86_AVX2']),
            'shared storage': set(['MISC_SHARES_VIA_AGGREGATE']),
        }
        self._validate_provider_summary_traits(expected, alloc_cands)

        # Forbid the AVX2 trait
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                forbidden_traits=set([os_traits.HW_CPU_X86_AVX2]),
            )}
        )
        # Should be no results as both cn1 and cn2 have the trait.
        expected = []
        self._validate_allocation_requests(expected, alloc_cands)

        # Require the AVX2 trait but forbid CUSTOM_EXTRA_FASTER, which is
        # added to cn2
        tb.set_traits(cn2, 'HW_CPU_X86_AVX2', 'CUSTOM_EXTRA_FASTER')
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=[{os_traits.HW_CPU_X86_AVX2}],
                forbidden_traits=set(['CUSTOM_EXTRA_FASTER']),
            )}
        )
        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('shared storage', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        # Add disk to cn1, forbid sharing, and require the AVX2 trait.
        # This should result in getting only cn1.
        tb.add_inventory(cn1, orc.DISK_GB, 2048, allocation_ratio=1.5)
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=[{os_traits.HW_CPU_X86_AVX2}],
                forbidden_traits=set(['MISC_SHARES_VIA_AGGREGATE']),
            )}
        )
        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('cn1', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        # Now create a more complex trait query. (AVX2 and (SSE or SSE2)
        # Right now none of the RPs has SEE nor SSE2 so we expect no candidates
        required_traits = [
            {os_traits.HW_CPU_X86_AVX2},
            {os_traits.HW_CPU_X86_SSE, os_traits.HW_CPU_X86_SSE2}
        ]
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=required_traits,
            )}
        )

        # We have not yet associated the SSE or SSE2 traits to any provider,
        # so we should get zero allocation candidates
        p_sums = alloc_cands.provider_summaries
        self.assertEqual([], alloc_cands.allocation_requests)
        self.assertEqual(0, len(p_sums))

        # Next associate SSE to the sharing provider that is enough to get
        # matches. cn1 with shared storage is a match as ss provides SSE but
        # cn1 with local disk is not a match as then ss is not used and
        # therefore no SSE is provided. cn2 is a match with ss.
        tb.set_traits(ss, "MISC_SHARES_VIA_AGGREGATE", "HW_CPU_X86_SSE")

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=required_traits,
            )}
        )

        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('shared storage', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 1),
             ('cn2', orc.MEMORY_MB, 64),
             ('shared storage', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        # Now add SSE2 to cn1 so cn1 + local disk will also be a match
        tb.set_traits(cn1, "HW_CPU_X86_AVX2", "HW_CPU_X86_SSE2")

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=required_traits,
            )}
        )

        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('shared storage', orc.DISK_GB, 1500)],
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('cn1', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 1),
             ('cn2', orc.MEMORY_MB, 64),
             ('shared storage', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        # Now change the trait query to
        # (AVX2 and (SSE or SSE2) and not CUSTOM_EXTRA_FASTER)
        # cn2 has the CUSTOM_EXTRA_FASTER trait so that is expected to be
        # filtered out
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=required_traits,
                forbidden_traits={'CUSTOM_EXTRA_FASTER'},
            )}
        )

        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('shared storage', orc.DISK_GB, 1500)],
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('cn1', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

    def test_local_with_shared_custom_resource(self):
        """Create some resource providers that can satisfy the request for
        resources with local VCPU and MEMORY_MB but rely on a shared resource
        provider to satisfy a custom resource requirement and verify that the
        allocation requests returned by AllocationCandidates have the custom
        resource served up by the shared custom resource provider and
        VCPU/MEMORY_MB by the compute node providers
        """
        # The aggregate that will be associated to everything...
        agg_uuid = uuids.agg

        # Create two compute node providers with VCPU, RAM and NO local
        # CUSTOM_MAGIC resources, associated with the aggregate.
        for name in ('cn1', 'cn2'):
            cn = self._create_provider(name, agg_uuid)
            tb.add_inventory(cn, orc.VCPU, 24, allocation_ratio=16.0)
            tb.add_inventory(cn, orc.MEMORY_MB, 1024,
                             min_unit=64, allocation_ratio=1.5)

        # Create a custom resource called MAGIC
        magic_rc = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_MAGIC',
        )
        magic_rc.create()

        # Create the shared provider that serves CUSTOM_MAGIC, associated with
        # the same aggregate
        magic_p = self._create_provider('shared custom resource provider',
                                        agg_uuid)
        tb.add_inventory(magic_p, magic_rc.name, 2048, reserved=1024,
                         min_unit=10)

        # Mark the magic provider as having inventory shared among any provider
        # associated via aggregate
        tb.set_traits(magic_p, "MISC_SHARES_VIA_AGGREGATE")

        # The resources we will request
        requested_resources = {
            orc.VCPU: 1,
            orc.MEMORY_MB: 64,
            magic_rc.name: 512,
        }

        alloc_cands = self._get_allocation_candidates(
            groups={'': placement_lib.RequestGroup(
                use_same_provider=False, resources=requested_resources)})

        # Verify the allocation requests that are returned. There should be 2
        # allocation requests, one for each compute node, containing 3
        # resources in each allocation request, one each for VCPU, RAM, and
        # MAGIC. The amounts of the requests should correspond to the requested
        # resource amounts in the filter:resources dict passed to
        # AllocationCandidates.get_by_requests(). The providers for VCPU and
        # MEMORY_MB should be the compute nodes while the provider for the
        # MAGIC should be the shared custom resource provider.
        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('shared custom resource provider', magic_rc.name, 512)],
            [('cn2', orc.VCPU, 1),
             ('cn2', orc.MEMORY_MB, 64),
             ('shared custom resource provider', magic_rc.name, 512)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
            ]),
            'shared custom resource provider': set([
                (magic_rc.name, 1024, 0)
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_mix_local_and_shared(self):
        # Create three compute node providers with VCPU and RAM, but only
        # the third compute node has DISK. The first two computes will
        # share the storage from the shared storage pool.
        cn1, cn2 = (self._create_provider(name, uuids.agg)
                    for name in ('cn1', 'cn2'))
        # cn3 is not associated with the aggregate
        cn3 = self._create_provider('cn3')
        for cn in (cn1, cn2, cn3):
            tb.add_inventory(cn, orc.VCPU, 24, allocation_ratio=16.0)
            tb.add_inventory(cn, orc.MEMORY_MB, 1024,
                             min_unit=64, allocation_ratio=1.5)
        # Only cn3 has disk
        tb.add_inventory(cn3, orc.DISK_GB, 2000, reserved=100, min_unit=10)

        # Create the shared storage pool in the same aggregate as the first two
        # compute nodes
        ss = self._create_provider('shared storage', uuids.agg)

        # Give the shared storage pool some inventory of DISK_GB
        tb.add_inventory(ss, orc.DISK_GB, 2000, reserved=100, min_unit=10)

        tb.set_traits(ss, "MISC_SHARES_VIA_AGGREGATE")

        alloc_cands = self._get_allocation_candidates()

        # Expect cn1, cn2, cn3 and ss in the summaries
        expected = {
            'cn1': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
            ]),
            'cn3': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
            'shared storage': set([
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # Expect three allocation requests: (cn1, ss), (cn2, ss), (cn3)
        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('shared storage', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 1),
             ('cn2', orc.MEMORY_MB, 64),
             ('shared storage', orc.DISK_GB, 1500)],
            [('cn3', orc.VCPU, 1),
             ('cn3', orc.MEMORY_MB, 64),
             ('cn3', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        # Now we're going to add a set of required traits into the request mix.
        # To start off, let's request a required trait that we know has not
        # been associated yet with any provider, and ensure we get no results
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=[{os_traits.HW_CPU_X86_AVX2}],
            )}
        )

        # We have not yet associated the AVX2 trait to any provider, so we
        # should get zero allocation candidates
        p_sums = alloc_cands.provider_summaries
        self.assertEqual(0, len(p_sums))
        a_reqs = alloc_cands.allocation_requests
        self.assertEqual(0, len(a_reqs))

        # Now, if we then associate the required trait with all of our compute
        # nodes, we should get back all compute nodes since they all now
        # satisfy the required traits as well as the resource request
        for cn in (cn1, cn2, cn3):
            tb.set_traits(cn, os_traits.HW_CPU_X86_AVX2)

        alloc_cands = self._get_allocation_candidates(
            groups={'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=[{os_traits.HW_CPU_X86_AVX2}],
            )}
        )

        # There should be 3 compute node providers and 1 shared storage
        # provider in the summaries.
        expected = {
            'cn1': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
            ]),
            'cn3': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
            'shared storage': set([
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # Let's check that the traits listed for the compute nodes include the
        # AVX2 trait, and the shared storage provider in the provider summaries
        # does NOT have the AVX2 trait
        expected = {
            'cn1': set(['HW_CPU_X86_AVX2']),
            'cn2': set(['HW_CPU_X86_AVX2']),
            'cn3': set(['HW_CPU_X86_AVX2']),
            'shared storage': set(['MISC_SHARES_VIA_AGGREGATE']),
        }
        self._validate_provider_summary_traits(expected, alloc_cands)

        # Now, let's add a new wrinkle to the equation and add a required trait
        # that will ONLY be satisfied by a compute node with local disk that
        # has SSD drives. Set this trait only on the compute node with local
        # disk (cn3)
        tb.set_traits(cn3, os_traits.HW_CPU_X86_AVX2,
                      os_traits.STORAGE_DISK_SSD)

        alloc_cands = self._get_allocation_candidates({
            '': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=[
                    {os_traits.HW_CPU_X86_AVX2}, {os_traits.STORAGE_DISK_SSD}
                ],
            )
        })

        # There should be only cn3 in the returned allocation candidates
        expected = [
            [('cn3', orc.VCPU, 1),
             ('cn3', orc.MEMORY_MB, 64),
             ('cn3', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn3': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        expected = {
            'cn3': set(['HW_CPU_X86_AVX2', 'STORAGE_DISK_SSD'])
        }
        self._validate_provider_summary_traits(expected, alloc_cands)

        # Let's have an even more complex trait query
        # (AVX2 and (SSD or SSE) and not SSE2). As no SEE or SSE2 is in the
        # current trees we still get back cn3 that has AVX and SSD
        required_traits = [
            {os_traits.HW_CPU_X86_AVX2},
            {os_traits.STORAGE_DISK_SSD, os_traits.HW_CPU_X86_SSE}
        ]

        alloc_cands = self._get_allocation_candidates({
            '': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=required_traits,
                forbidden_traits={os_traits.HW_CPU_X86_SSE2}
            )
        })

        # There should be only cn3 in the returned allocation candidates
        expected = [
            [('cn3', orc.VCPU, 1),
             ('cn3', orc.MEMORY_MB, 64),
             ('cn3', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn3': set([
                (orc.VCPU, 24 * 16.0, 0),
                (orc.MEMORY_MB, 1024 * 1.5, 0),
                (orc.DISK_GB, 2000 - 100, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        expected = {
            'cn3': set(['HW_CPU_X86_AVX2', 'STORAGE_DISK_SSD'])
        }
        self._validate_provider_summary_traits(expected, alloc_cands)

        # Next we add SSE to cn1 and both SSE and SSE2 to cn2. This will make
        # cn1 a match while cn2 still be ignored due to SSE2. cn3 is good as
        # before
        tb.set_traits(
            cn1, os_traits.HW_CPU_X86_AVX2, os_traits.HW_CPU_X86_SSE)
        tb.set_traits(
            cn2,
            os_traits.HW_CPU_X86_AVX2,
            os_traits.HW_CPU_X86_SSE,
            os_traits.HW_CPU_X86_SSE2
        )

        alloc_cands = self._get_allocation_candidates({
            '': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=required_traits,
                forbidden_traits={os_traits.HW_CPU_X86_SSE2}
            )
        })

        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('shared storage', orc.DISK_GB, 1500)],
            [('cn3', orc.VCPU, 1),
             ('cn3', orc.MEMORY_MB, 64),
             ('cn3', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

    def test_common_rc(self):
        """Candidates when cn and shared have inventory in the same class."""
        cn = self._create_provider('cn', uuids.agg1)
        tb.add_inventory(cn, orc.VCPU, 24)
        tb.add_inventory(cn, orc.MEMORY_MB, 2048)
        tb.add_inventory(cn, orc.DISK_GB, 1600)

        ss = self._create_provider('ss', uuids.agg1)
        tb.set_traits(ss, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss, orc.DISK_GB, 2000)

        alloc_cands = self._get_allocation_candidates()

        # One allocation_request should have cn + ss; the other should have
        # just the cn.
        expected = [
            [('cn', orc.VCPU, 1),
             ('cn', orc.MEMORY_MB, 64),
             ('cn', orc.DISK_GB, 1500)],
            [('cn', orc.VCPU, 1),
             ('cn', orc.MEMORY_MB, 64),
             ('ss', orc.DISK_GB, 1500)],
        ]

        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn': set([
                (orc.VCPU, 24, 0),
                (orc.MEMORY_MB, 2048, 0),
                (orc.DISK_GB, 1600, 0),
            ]),
            'ss': set([
                (orc.DISK_GB, 2000, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # Next let's increase the requested DISK_GB
        requested_resources = {
            orc.VCPU: 1,
            orc.MEMORY_MB: 64,
            orc.DISK_GB: 1800,
        }
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=requested_resources,
            )}
        )

        expected = [
            [('cn', orc.VCPU, 1),
             ('cn', orc.MEMORY_MB, 64),
             ('ss', orc.DISK_GB, 1800)],
        ]

        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn': set([
                (orc.VCPU, 24, 0),
                (orc.MEMORY_MB, 2048, 0),
                (orc.DISK_GB, 1600, 0),
            ]),
            'ss': set([
                (orc.DISK_GB, 2000, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_common_rc_traits_split(self):
        """Validate filters when traits are split across cn and shared RPs."""
        # NOTE(efried): This test case only applies to the scenario where we're
        # requesting resources via the RequestGroup where
        # use_same_provider=False

        cn = self._create_provider('cn', uuids.agg1)
        tb.add_inventory(cn, orc.VCPU, 24)
        tb.add_inventory(cn, orc.MEMORY_MB, 2048)
        tb.add_inventory(cn, orc.DISK_GB, 1600)
        # The compute node's disk is SSD
        tb.set_traits(cn, 'HW_CPU_X86_SSE', 'STORAGE_DISK_SSD')

        ss = self._create_provider('ss', uuids.agg1)
        tb.add_inventory(ss, orc.DISK_GB, 1600)
        # The shared storage's disk is RAID
        tb.set_traits(ss, 'MISC_SHARES_VIA_AGGREGATE', 'CUSTOM_RAID')

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources=self.requested_resources,
                required_traits=[
                    {'HW_CPU_X86_SSE'}, {'STORAGE_DISK_SSD'}, {'CUSTOM_RAID'}]
            )}
        )

        # TODO(efried): Bug #1724633: we'd *like* to get no candidates, because
        # there's no single DISK_GB resource with both STORAGE_DISK_SSD and
        # CUSTOM_RAID traits.
        # expected = []
        expected = [
            [('cn', orc.VCPU, 1),
             ('cn', orc.MEMORY_MB, 64),
             ('ss', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        # expected = {}
        expected = {
            'cn': set([
                (orc.VCPU, 24, 0),
                (orc.MEMORY_MB, 2048, 0),
                (orc.DISK_GB, 1600, 0),
            ]),
            'ss': set([
                (orc.DISK_GB, 1600, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_only_one_sharing_provider(self):
        ss1 = self._create_provider('ss1', uuids.agg1)
        tb.set_traits(ss1, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss1, orc.IPV4_ADDRESS, 24)
        tb.add_inventory(ss1, orc.SRIOV_NET_VF, 16)
        tb.add_inventory(ss1, orc.DISK_GB, 1600)

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'IPV4_ADDRESS': 2,
                    'SRIOV_NET_VF': 1,
                    'DISK_GB': 1500,
                }
            )}
        )

        expected = [
            [('ss1', orc.IPV4_ADDRESS, 2),
             ('ss1', orc.SRIOV_NET_VF, 1),
             ('ss1', orc.DISK_GB, 1500)]
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'ss1': set([
                (orc.IPV4_ADDRESS, 24, 0),
                (orc.SRIOV_NET_VF, 16, 0),
                (orc.DISK_GB, 1600, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_all_sharing_providers_no_rc_overlap(self):
        ss1 = self._create_provider('ss1', uuids.agg1)
        tb.set_traits(ss1, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss1, orc.IPV4_ADDRESS, 24)

        ss2 = self._create_provider('ss2', uuids.agg1)
        tb.set_traits(ss2, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss2, orc.DISK_GB, 1600)

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'IPV4_ADDRESS': 2,
                    'DISK_GB': 1500,
                }
            )}
        )

        expected = [
            [('ss1', orc.IPV4_ADDRESS, 2),
             ('ss2', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'ss1': set([
                (orc.IPV4_ADDRESS, 24, 0),
            ]),
            'ss2': set([
                (orc.DISK_GB, 1600, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_all_sharing_providers_no_rc_overlap_more_classes(self):
        ss1 = self._create_provider('ss1', uuids.agg1)
        tb.set_traits(ss1, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss1, orc.IPV4_ADDRESS, 24)
        tb.add_inventory(ss1, orc.SRIOV_NET_VF, 16)

        ss2 = self._create_provider('ss2', uuids.agg1)
        tb.set_traits(ss2, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss2, orc.DISK_GB, 1600)

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'IPV4_ADDRESS': 2,
                    'SRIOV_NET_VF': 1,
                    'DISK_GB': 1500,
                }
            )}
        )

        expected = [
            [('ss1', orc.IPV4_ADDRESS, 2),
             ('ss1', orc.SRIOV_NET_VF, 1),
             ('ss2', orc.DISK_GB, 1500)]
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'ss1': set([
                (orc.IPV4_ADDRESS, 24, 0),
                (orc.SRIOV_NET_VF, 16, 0)
            ]),
            'ss2': set([
                (orc.DISK_GB, 1600, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_all_sharing_providers(self):
        ss1 = self._create_provider('ss1', uuids.agg1)
        tb.set_traits(ss1, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss1, orc.IPV4_ADDRESS, 24)
        tb.add_inventory(ss1, orc.SRIOV_NET_VF, 16)
        tb.add_inventory(ss1, orc.DISK_GB, 1600)

        ss2 = self._create_provider('ss2', uuids.agg1)
        tb.set_traits(ss2, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss2, orc.SRIOV_NET_VF, 16)
        tb.add_inventory(ss2, orc.DISK_GB, 1600)

        alloc_cands = self._get_allocation_candidates(groups={
            '': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'IPV4_ADDRESS': 2,
                    'SRIOV_NET_VF': 1,
                    'DISK_GB': 1500,
                }
            )}
        )

        # We expect four candidates:
        #   - gets all the resources from ss1,
        #   - gets the SRIOV_NET_VF from ss2 and the rest from ss1,
        #   - gets the DISK_GB from ss2 and the rest from ss1,
        #   - gets SRIOV_NET_VF and DISK_GB from ss2 and rest from ss1
        expected = [
            [('ss1', orc.IPV4_ADDRESS, 2),
             ('ss1', orc.SRIOV_NET_VF, 1),
             ('ss1', orc.DISK_GB, 1500)],
            [('ss1', orc.IPV4_ADDRESS, 2),
             ('ss1', orc.SRIOV_NET_VF, 1),
             ('ss2', orc.DISK_GB, 1500)],
            [('ss1', orc.IPV4_ADDRESS, 2),
             ('ss2', orc.SRIOV_NET_VF, 1),
             ('ss1', orc.DISK_GB, 1500)],
            [('ss1', orc.IPV4_ADDRESS, 2),
             ('ss2', orc.SRIOV_NET_VF, 1),
             ('ss2', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'ss1': set([
                (orc.IPV4_ADDRESS, 24, 0),
                (orc.SRIOV_NET_VF, 16, 0),
                (orc.DISK_GB, 1600, 0)
            ]),
            'ss2': set([
                (orc.SRIOV_NET_VF, 16, 0),
                (orc.DISK_GB, 1600, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_two_non_sharing_connect_to_one_sharing_different_aggregate(self):
        # Covering the following setup:
        #
        #    CN1 (VCPU)        CN2 (VCPU)
        #        \ agg1        / agg2
        #         SS1 (DISK_GB)
        #
        # It is different from test_mix_local_and_shared as it uses two
        # different aggregates to connect the two CNs to the share RP
        cn1 = self._create_provider('cn1', uuids.agg1)
        tb.add_inventory(cn1, orc.VCPU, 24)
        tb.add_inventory(cn1, orc.MEMORY_MB, 2048)

        cn2 = self._create_provider('cn2', uuids.agg2)
        tb.add_inventory(cn2, orc.VCPU, 24)
        tb.add_inventory(cn2, orc.MEMORY_MB, 2048)

        ss1 = self._create_provider('ss1', uuids.agg1, uuids.agg2)
        tb.set_traits(ss1, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss1, orc.DISK_GB, 1600)

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'DISK_GB': 1500,
                }
            )}
        )
        expected = [
            [('cn1', orc.VCPU, 2),
             ('ss1', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 2),
             ('ss1', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 24, 0),
                (orc.MEMORY_MB, 2048, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24, 0),
                (orc.MEMORY_MB, 2048, 0),
            ]),
            'ss1': set([
                (orc.DISK_GB, 1600, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_two_non_sharing_one_common_and_two_unique_sharing(self):
        # Covering the following setup:
        #
        #    CN1 (VCPU)          CN2 (VCPU)
        #   / agg3   \ agg1     / agg1   \ agg2
        #  SS3 (IPV4)   SS1 (DISK_GB)      SS2 (IPV4)
        cn1 = self._create_provider('cn1', uuids.agg1, uuids.agg3)
        tb.add_inventory(cn1, orc.VCPU, 24)
        tb.add_inventory(cn1, orc.MEMORY_MB, 2048)

        cn2 = self._create_provider('cn2', uuids.agg1, uuids.agg2)
        tb.add_inventory(cn2, orc.VCPU, 24)
        tb.add_inventory(cn2, orc.MEMORY_MB, 2048)

        # ss1 is connected to both cn1 and cn2
        ss1 = self._create_provider('ss1', uuids.agg1)
        tb.set_traits(ss1, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss1, orc.DISK_GB, 1600)

        # ss2 only connected to cn2
        ss2 = self._create_provider('ss2', uuids.agg2)
        tb.set_traits(ss2, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss2, orc.IPV4_ADDRESS, 24)

        # ss3 only connected to cn1
        ss3 = self._create_provider('ss3', uuids.agg3)
        tb.set_traits(ss3, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss3, orc.IPV4_ADDRESS, 24)

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'DISK_GB': 1500,
                    'IPV4_ADDRESS': 2,
                }
            )}
        )

        expected = [
            [('cn1', orc.VCPU, 2),
             ('ss1', orc.DISK_GB, 1500),
             ('ss3', orc.IPV4_ADDRESS, 2)],
            [('cn2', orc.VCPU, 2),
             ('ss1', orc.DISK_GB, 1500),
             ('ss2', orc.IPV4_ADDRESS, 2)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 24, 0),
                (orc.MEMORY_MB, 2048, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24, 0),
                (orc.MEMORY_MB, 2048, 0),
            ]),
            'ss1': set([
                (orc.DISK_GB, 1600, 0),
            ]),
            'ss2': set([
                (orc.IPV4_ADDRESS, 24, 0),
            ]),
            'ss3': set([
                (orc.IPV4_ADDRESS, 24, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_rc_not_split_between_sharing_and_non_sharing(self):
        # cn1(VCPU,MEM)   Non-sharing RP with some of the resources
        #       | agg1    aggregated with
        #   ss1(DISK)     sharing RP that has the rest of the resources
        #
        #         cn2(VCPU)         Non-sharing with one of the resources;
        #         / agg2 \          aggregated with multiple sharing providers
        # ss2_1(MEM)  ss2_2(DISK)   with different resources.

        cn1 = self._create_provider('cn1', uuids.agg1)
        tb.add_inventory(cn1, orc.VCPU, 24)
        tb.add_inventory(cn1, orc.MEMORY_MB, 2048)
        ss1 = self._create_provider('ss1', uuids.agg1)
        tb.add_inventory(ss1, orc.DISK_GB, 2000)
        tb.set_traits(ss1, 'MISC_SHARES_VIA_AGGREGATE')

        cn2 = self._create_provider('cn2', uuids.agg2)
        tb.add_inventory(cn2, orc.VCPU, 24)
        ss2_1 = self._create_provider('ss2_1', uuids.agg2)
        tb.add_inventory(ss2_1, orc.MEMORY_MB, 2048)
        tb.set_traits(ss2_1, 'MISC_SHARES_VIA_AGGREGATE')
        ss2_2 = self._create_provider('ss2_2', uuids.agg2)
        tb.add_inventory(ss2_2, orc.DISK_GB, 2000)
        tb.set_traits(ss2_2, 'MISC_SHARES_VIA_AGGREGATE')

        alloc_cands = self._get_allocation_candidates()
        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('ss1', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 1),
             ('ss2_1', orc.MEMORY_MB, 64),
             ('ss2_2', orc.DISK_GB, 1500)],
        ]

        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 24, 0),
                (orc.MEMORY_MB, 2048, 0),
            ]),
            'ss1': set([
                (orc.DISK_GB, 2000, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24, 0),
            ]),
            'ss2_1': set([
                (orc.MEMORY_MB, 2048, 0),
            ]),
            'ss2_2': set([
                (orc.DISK_GB, 2000, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_multiple_sharing_providers_with_same_rc(self):
        #       cn1(VCPU,MEM)       Non-sharing with some of the resources;
        #         / agg1 \          aggregated with multiple sharing providers
        # ss1_1(DISK)  ss1_2(DISK)  with the same resource.
        #
        #         cn2(VCPU)         Non-sharing with one of the resources;
        #         / agg2 \          aggregated with multiple sharing providers
        # ss2_1(MEM)  ss2_2(DISK)   with different resources.

        cn1 = self._create_provider('cn1', uuids.agg1)
        tb.add_inventory(cn1, orc.VCPU, 24)
        tb.add_inventory(cn1, orc.MEMORY_MB, 2048)
        ss1_1 = self._create_provider('ss1_1', uuids.agg1)
        tb.add_inventory(ss1_1, orc.DISK_GB, 2000)
        tb.set_traits(ss1_1, 'MISC_SHARES_VIA_AGGREGATE')
        ss1_2 = self._create_provider('ss1_2', uuids.agg1)
        tb.add_inventory(ss1_2, orc.DISK_GB, 2000)
        tb.set_traits(ss1_2, 'MISC_SHARES_VIA_AGGREGATE')

        cn2 = self._create_provider('cn2', uuids.agg2)
        tb.add_inventory(cn2, orc.VCPU, 24)
        ss2_1 = self._create_provider('ss2_1', uuids.agg2)
        tb.add_inventory(ss2_1, orc.MEMORY_MB, 2048)
        tb.set_traits(ss2_1, 'MISC_SHARES_VIA_AGGREGATE')
        ss2_2 = self._create_provider('ss2_2', uuids.agg2)
        tb.add_inventory(ss2_2, orc.DISK_GB, 2000)
        tb.set_traits(ss2_2, 'MISC_SHARES_VIA_AGGREGATE')

        alloc_cands = self._get_allocation_candidates()
        expected = [
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('ss1_1', orc.DISK_GB, 1500)],
            [('cn1', orc.VCPU, 1),
             ('cn1', orc.MEMORY_MB, 64),
             ('ss1_2', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 1),
             ('ss2_1', orc.MEMORY_MB, 64),
             ('ss2_2', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 24, 0),
                (orc.MEMORY_MB, 2048, 0),
            ]),
            'ss1_1': set([
                (orc.DISK_GB, 2000, 0),
            ]),
            'ss1_2': set([
                (orc.DISK_GB, 2000, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24, 0),
            ]),
            'ss2_1': set([
                (orc.MEMORY_MB, 2048, 0),
            ]),
            'ss2_2': set([
                (orc.DISK_GB, 2000, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_sharing_providers_member_of(self):
        # Covering the following setup:
        #
        #       CN1 (VCPU, DISK_GB)     CN2 (VCPU, DISK_GB)
        #      / agg1     \ agg2       / agg2     \ agg3
        #  SS1 (DISK_GB)   SS2 (DISK_GB)       SS3 (DISK_GB)
        cn1 = self._create_provider('cn1', uuids.agg1, uuids.agg2)
        tb.add_inventory(cn1, orc.VCPU, 24)
        tb.add_inventory(cn1, orc.DISK_GB, 1600)

        cn2 = self._create_provider('cn2', uuids.agg2, uuids.agg3)
        tb.add_inventory(cn2, orc.VCPU, 24)
        tb.add_inventory(cn2, orc.DISK_GB, 1600)

        # ss1 is connected to cn1
        ss1 = self._create_provider('ss1', uuids.agg1)
        tb.set_traits(ss1, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss1, orc.DISK_GB, 1600)

        # ss2 is connected to both cn1 and cn2
        ss2 = self._create_provider('ss2', uuids.agg2)
        tb.set_traits(ss2, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss2, orc.DISK_GB, 1600)

        # ss3 is connected to cn2
        ss3 = self._create_provider('ss3', uuids.agg3)
        tb.set_traits(ss3, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss3, orc.DISK_GB, 1600)

        # Let's get allocation candidates from agg1
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'DISK_GB': 1500,
                },
                member_of=[[uuids.agg1]]
            )}
        )

        expected = [
            [('cn1', orc.VCPU, 2),
             ('cn1', orc.DISK_GB, 1500)],
            [('cn1', orc.VCPU, 2),
             ('ss1', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 24, 0),
                (orc.DISK_GB, 1600, 0),
            ]),
            'ss1': set([
                (orc.DISK_GB, 1600, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # Let's get allocation candidates from agg2
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'DISK_GB': 1500,
                },
                member_of=[[uuids.agg2]]
            )}
        )

        expected = [
            [('cn1', orc.VCPU, 2),
             ('cn1', orc.DISK_GB, 1500)],
            [('cn1', orc.VCPU, 2),
             ('ss2', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 2),
             ('cn2', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 2),
             ('ss2', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 24, 0),
                (orc.DISK_GB, 1600, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24, 0),
                (orc.DISK_GB, 1600, 0),
            ]),
            'ss2': set([
                (orc.DISK_GB, 1600, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # Let's move to validate multiple member_of scenario
        # The request from agg1 *AND* agg2 would provide only
        # resources from cn1 with its local DISK
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'DISK_GB': 1500,
                },
                member_of=[[uuids.agg1], [uuids.agg2]]
            )}
        )

        expected = [
            [('cn1', orc.VCPU, 2),
             ('cn1', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 24, 0),
                (orc.DISK_GB, 1600, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # The request from agg1 *OR* agg2 would provide five candidates
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'DISK_GB': 1500,
                },
                member_of=[[uuids.agg1, uuids.agg2]]
            )}
        )

        expected = [
            [('cn1', orc.VCPU, 2),
             ('cn1', orc.DISK_GB, 1500)],
            [('cn1', orc.VCPU, 2),
             ('ss1', orc.DISK_GB, 1500)],
            [('cn1', orc.VCPU, 2),
             ('ss2', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 2),
             ('cn2', orc.DISK_GB, 1500)],
            [('cn2', orc.VCPU, 2),
             ('ss2', orc.DISK_GB, 1500)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 24, 0),
                (orc.DISK_GB, 1600, 0),
            ]),
            'cn2': set([
                (orc.VCPU, 24, 0),
                (orc.DISK_GB, 1600, 0),
            ]),
            'ss1': set([
                (orc.DISK_GB, 1600, 0),
            ]),
            'ss2': set([
                (orc.DISK_GB, 1600, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_two_sharing_indirectly_connected_connecting_not_give_resource(
            self):
        # This covers the following setup
        #        CN1 (VCPU, MEMORY_MB)
        #        /      \
        #       /agg1    \agg2
        #      /          \
        #     SS1 (      SS2 (
        #      DISK_GB)   IPV4_ADDRESS
        #                 SRIOV_NET_VF)
        # The request then made for resources from the sharing RPs only

        ss1 = self._create_provider('ss1', uuids.agg1)
        tb.set_traits(ss1, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss1, orc.DISK_GB, 1600)

        cn1 = self._create_provider('cn1', uuids.agg1, uuids.agg2)
        tb.add_inventory(cn1, orc.VCPU, 24)
        tb.add_inventory(cn1, orc.MEMORY_MB, 2048)

        ss2 = self._create_provider('ss2', uuids.agg2)
        tb.set_traits(ss2, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss2, orc.IPV4_ADDRESS, 24)
        tb.add_inventory(ss2, orc.SRIOV_NET_VF, 16)

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'IPV4_ADDRESS': 2,
                    'SRIOV_NET_VF': 1,
                    'DISK_GB': 1500,
                }
            )}
        )

        expected = [
            [('ss1', orc.DISK_GB, 1500),
             ('ss2', orc.IPV4_ADDRESS, 2),
             ('ss2', orc.SRIOV_NET_VF, 1)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'ss1': set([
                (orc.DISK_GB, 1600, 0),
            ]),
            'ss2': set([
                (orc.IPV4_ADDRESS, 24, 0),
                (orc.SRIOV_NET_VF, 16, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_two_sharing_indirectly_connected_connecting_gives_resource(self):
        # This covers the following setup
        #        CN1 (VCPU, MEMORY_MB)
        #        /      \
        #       /agg1    \agg2
        #      /          \
        #     SS1 (      SS2 (
        #      DISK_GB)   IPV4_ADDRESS
        #                 SRIOV_NET_VF)
        # The request then made for resources from all three RPs

        ss1 = self._create_provider('ss1', uuids.agg1)
        tb.set_traits(ss1, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss1, orc.DISK_GB, 1600)

        cn1 = self._create_provider('cn1', uuids.agg1, uuids.agg2)
        tb.add_inventory(cn1, orc.VCPU, 24)
        tb.add_inventory(cn1, orc.MEMORY_MB, 2048)

        ss2 = self._create_provider('ss2', uuids.agg2)
        tb.set_traits(ss2, "MISC_SHARES_VIA_AGGREGATE")
        tb.add_inventory(ss2, orc.IPV4_ADDRESS, 24)
        tb.add_inventory(ss2, orc.SRIOV_NET_VF, 16)

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    'VCPU': 2,
                    'IPV4_ADDRESS': 2,
                    'SRIOV_NET_VF': 1,
                    'DISK_GB': 1500,
                }
            )}
        )

        expected = [
            [('cn1', orc.VCPU, 2),
             ('ss1', orc.DISK_GB, 1500),
             ('ss2', orc.IPV4_ADDRESS, 2),
             ('ss2', orc.SRIOV_NET_VF, 1)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 24, 0),
                (orc.MEMORY_MB, 2048, 0),
            ]),
            'ss1': set([
                (orc.DISK_GB, 1600, 0),
            ]),
            'ss2': set([
                (orc.IPV4_ADDRESS, 24, 0),
                (orc.SRIOV_NET_VF, 16, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def test_simple_tree_of_providers(self):
        """Tests that we properly winnow allocation requests when including
        traits in the request group and that the traits appear in the provider
        summaries of the returned allocation candidates
        """
        # We are setting up a single tree that looks like this:
        #
        #                  compute node (cn)
        #                 /                 \
        #                /                   \
        #           numa cell 0         numa cell 1
        #               |                    |
        #               |                    |
        #              pf 0                 pf 1
        #
        # The second physical function will be associated with the
        # HW_NIC_OFFLOAD_GENEVE trait, but not the first physical function.
        #
        # We will issue a request to _get_allocation_candidates() for VCPU,
        # MEMORY_MB and SRIOV_NET_VF **without** required traits, then include
        # a request that includes HW_NIC_OFFLOAD_GENEVE. In the latter case,
        # the compute node tree should be returned but the allocation requests
        # should only include the second physical function since the required
        # trait is only associated with that PF.
        #
        # Subsequently, we will consume all the SRIOV_NET_VF resources from the
        # second PF's inventory and attempt the same request of resources and
        # HW_NIC_OFFLOAD_GENEVE. We should get 0 returned results because now
        # the only PF that has the required trait has no inventory left.
        cn = self._create_provider('cn')

        tb.add_inventory(cn, orc.VCPU, 16)
        tb.add_inventory(cn, orc.MEMORY_MB, 32768)

        numa_cell0 = self._create_provider('cn_numa0', parent=cn.uuid)
        numa_cell1 = self._create_provider('cn_numa1', parent=cn.uuid)

        pf0 = self._create_provider('cn_numa0_pf0', parent=numa_cell0.uuid)
        tb.add_inventory(pf0, orc.SRIOV_NET_VF, 8)
        pf1 = self._create_provider('cn_numa1_pf1', parent=numa_cell1.uuid)
        tb.add_inventory(pf1, orc.SRIOV_NET_VF, 8)
        tb.set_traits(pf1, os_traits.HW_NIC_OFFLOAD_GENEVE)

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.VCPU: 2,
                    orc.MEMORY_MB: 256,
                    orc.SRIOV_NET_VF: 1,
                }
            )}
        )

        expected = [
            [('cn', orc.VCPU, 2),
             ('cn', orc.MEMORY_MB, 256),
             ('cn_numa0_pf0', orc.SRIOV_NET_VF, 1)],
            [('cn', orc.VCPU, 2),
             ('cn', orc.MEMORY_MB, 256),
             ('cn_numa1_pf1', orc.SRIOV_NET_VF, 1)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn': set([
                (orc.VCPU, 16, 0),
                (orc.MEMORY_MB, 32768, 0),
            ]),
            'cn_numa0': set([]),
            'cn_numa1': set([]),
            'cn_numa0_pf0': set([
                (orc.SRIOV_NET_VF, 8, 0),
            ]),
            'cn_numa1_pf1': set([
                (orc.SRIOV_NET_VF, 8, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        expected = {
            'cn': set([]),
            'cn_numa0': set([]),
            'cn_numa1': set([]),
            'cn_numa0_pf0': set([]),
            'cn_numa1_pf1': set([os_traits.HW_NIC_OFFLOAD_GENEVE]),
        }
        self._validate_provider_summary_traits(expected, alloc_cands)

        # Now add required traits to the mix and verify we still get the same
        # result (since we haven't yet consumed the second physical function's
        # inventory of SRIOV_NET_VF.
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.VCPU: 2,
                    orc.MEMORY_MB: 256,
                    orc.SRIOV_NET_VF: 1,
                },
                required_traits=[{os_traits.HW_NIC_OFFLOAD_GENEVE}],
            )}
        )

        expected = [
            [('cn', orc.VCPU, 2),
             ('cn', orc.MEMORY_MB, 256),
             ('cn_numa1_pf1', orc.SRIOV_NET_VF, 1)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn': set([
                (orc.VCPU, 16, 0),
                (orc.MEMORY_MB, 32768, 0),
            ]),
            'cn_numa0': set([]),
            'cn_numa1': set([]),
            'cn_numa0_pf0': set([
                (orc.SRIOV_NET_VF, 8, 0),
            ]),
            'cn_numa1_pf1': set([
                (orc.SRIOV_NET_VF, 8, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        expected = {
            'cn': set([]),
            'cn_numa0': set([]),
            'cn_numa1': set([]),
            'cn_numa0_pf0': set([]),
            'cn_numa1_pf1': set([os_traits.HW_NIC_OFFLOAD_GENEVE]),
        }
        self._validate_provider_summary_traits(expected, alloc_cands)

        # Next we test that we get resources only on non-root providers
        # without root providers involved
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.SRIOV_NET_VF: 1,
                },
            )}
        )

        expected = [
            [('cn_numa0_pf0', orc.SRIOV_NET_VF, 1)],
            [('cn_numa1_pf1', orc.SRIOV_NET_VF, 1)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn': set([
                (orc.VCPU, 16, 0),
                (orc.MEMORY_MB, 32768, 0),
            ]),
            'cn_numa0': set([]),
            'cn_numa1': set([]),
            'cn_numa0_pf0': set([
                (orc.SRIOV_NET_VF, 8, 0),
            ]),
            'cn_numa1_pf1': set([
                (orc.SRIOV_NET_VF, 8, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        expected = {
            'cn': set([]),
            'cn_numa0': set([]),
            'cn_numa1': set([]),
            'cn_numa0_pf0': set([]),
            'cn_numa1_pf1': set([os_traits.HW_NIC_OFFLOAD_GENEVE]),
        }
        self._validate_provider_summary_traits(expected, alloc_cands)

        # Same, but with the request in a granular group, which hits a
        # different code path.
        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=True,
                resources={
                    orc.SRIOV_NET_VF: 1,
                },
            )}
        )

        expected = [
            [('cn_numa0_pf0', orc.SRIOV_NET_VF, 1)],
            [('cn_numa1_pf1', orc.SRIOV_NET_VF, 1)],
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn': set([
                (orc.VCPU, 16, 0),
                (orc.MEMORY_MB, 32768, 0),
            ]),
            'cn_numa0': set([]),
            'cn_numa1': set([]),
            'cn_numa0_pf0': set([
                (orc.SRIOV_NET_VF, 8, 0),
            ]),
            'cn_numa1_pf1': set([
                (orc.SRIOV_NET_VF, 8, 0),
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        expected = {
            'cn': set([]),
            'cn_numa0': set([]),
            'cn_numa1': set([]),
            'cn_numa0_pf0': set([]),
            'cn_numa1_pf1': set([os_traits.HW_NIC_OFFLOAD_GENEVE]),
        }
        self._validate_provider_summary_traits(expected, alloc_cands)

        # Now consume all the inventory of SRIOV_NET_VF on the second physical
        # function (the one with HW_NIC_OFFLOAD_GENEVE associated with it) and
        # verify that the same request still results in 0 results since the
        # function with the required trait no longer has any inventory.
        self.allocate_from_provider(pf1, orc.SRIOV_NET_VF, 8)

        alloc_cands = self._get_allocation_candidates({
            '':
                placement_lib.RequestGroup(
                    use_same_provider=False,
                    resources={
                        orc.VCPU: 2,
                        orc.MEMORY_MB: 256,
                        orc.SRIOV_NET_VF: 1,
                    },
                    required_traits=[{os_traits.HW_NIC_OFFLOAD_GENEVE}],
                )
        })

        self._validate_allocation_requests([], alloc_cands)
        self._validate_provider_summary_resources({}, alloc_cands)
        self._validate_provider_summary_traits({}, alloc_cands)

    def test_forbidden_trait_in_unnamed_group_with_split_rcs_on_nested_tree(
        self
    ):
        """Using the following trees:

            cn1 VCPU=2
            |
            cn1_c1 SRIOV_NET_VF=2, CUSTOM_FOO

            cn2 VCPU=2
            |
            cn2_c1 SRIOV_NET_VF=2
        """
        cn1 = self._create_provider('cn1')

        tb.add_inventory(cn1, orc.VCPU, 2)
        cn1_c1 = self._create_provider('cn1_c1', parent=cn1.uuid)
        tb.add_inventory(cn1_c1, orc.SRIOV_NET_VF, 2)
        tb.set_traits(cn1_c1, 'CUSTOM_FOO')

        cn2 = self._create_provider('cn2')
        tb.add_inventory(cn2, orc.VCPU, 2)
        cn2_c1 = self._create_provider('cn2_c1', parent=cn2.uuid)
        tb.add_inventory(cn2_c1, orc.SRIOV_NET_VF, 2)

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.VCPU: 1,
                    orc.SRIOV_NET_VF: 1,
                },
                forbidden_traits={
                    'CUSTOM_FOO',
                },
            )}
        )

        # the tree rooted at CN1 is expected to be filtered out due to
        # forbidden trait on CN1_C1
        # CN2 tree is the same as CN1 but without the forbidden trait so that
        # is a match
        expected = [
            [('cn2', 'VCPU', 1), ('cn2_c1', 'SRIOV_NET_VF', 1)]
        ]
        self._validate_allocation_requests(expected, alloc_cands)

    def test_forbidden_trait_in_unnamed_group_in_nested_tree(self):
        """Using the following trees:

            cn1 VCPU=2
            |
            cn1_c1 SRIOV_NET_VF=2, CUSTOM_FOO

            cn2 VCPU=2
            |
            cn2_c1 SRIOV_NET_VF=2
        """
        cn1 = self._create_provider('cn1')

        tb.add_inventory(cn1, orc.VCPU, 2)
        cn1_c1 = self._create_provider('cn1_c1', parent=cn1.uuid)
        tb.add_inventory(cn1_c1, orc.SRIOV_NET_VF, 2)
        tb.set_traits(cn1_c1, 'CUSTOM_FOO')

        cn2 = self._create_provider('cn2')
        tb.add_inventory(cn2, orc.VCPU, 2)
        cn2_c1 = self._create_provider('cn2_c1', parent=cn2.uuid)
        tb.add_inventory(cn2_c1, orc.SRIOV_NET_VF, 2)

        alloc_cands = self._get_allocation_candidates(
            {'': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.VCPU: 1,
                },
                forbidden_traits={
                    'CUSTOM_FOO',
                },
            )}
        )

        # both CN1 and CN2 are returned. CN1 has the forbidden trait
        # in its tree but there is no RC requested from that RP providing the
        # forbidden trait. The general rule is
        # "traits on resource providers never span other resource providers."
        # See
        # https://docs.openstack.org/placement/latest/user/provider-tree.html#filtering-by-traits
        expected = [
            [('cn1', 'VCPU', 1)], [('cn2', 'VCPU', 1)]
        ]
        self._validate_allocation_requests(expected, alloc_cands)

    def test_simple_tree_with_shared_provider(self):
        """Tests that we properly winnow allocation requests when including
        shared and nested providers
        """
        # We are setting up 2 cn trees with 2 shared storages
        # that look like this:
        #
        #              compute node (cn1)      ----- shared storage (ss1)
        #             /                 \       agg1       with 2000 DISK_GB
        #            /                   \
        #       numa cell 1_0        numa cell 1_1
        #           |                    |
        #           |                    |
        #         pf 1_0               pf 1_1(HW_NIC_OFFLOAD_GENEVE)
        #
        #              compute node (cn2)      ----- shared storage (ss2)
        #             /                 \       agg2       with 1000 DISK_GB
        #            /                   \
        #       numa cell 2_0        numa cell 2_1
        #           |                    |
        #           |                    |
        #         pf 2_0               pf 2_1(HW_NIC_OFFLOAD_GENEVE)
        #
        # The second physical function in both trees (pf1_1, pf 2_1) will be
        # associated with the HW_NIC_OFFLOAD_GENEVE trait, but not the first
        # physical function.
        #
        # We will issue a request to _get_allocation_candidates() for VCPU,
        # SRIOV_NET_VF and DISK_GB **without** required traits, then include
        # a request that includes HW_NIC_OFFLOAD_GENEVE. In the latter case,
        # the compute node tree should be returned but the allocation requests
        # should only include the second physical function since the required
        # trait is only associated with that PF.

        cn1 = self._create_provider('cn1', uuids.agg1)
        cn2 = self._create_provider('cn2', uuids.agg2)
        tb.add_inventory(cn1, orc.VCPU, 16)
        tb.add_inventory(cn2, orc.VCPU, 16)

        numa1_0 = self._create_provider('cn1_numa0', parent=cn1.uuid)
        numa1_1 = self._create_provider('cn1_numa1', parent=cn1.uuid)
        numa2_0 = self._create_provider('cn2_numa0', parent=cn2.uuid)
        numa2_1 = self._create_provider('cn2_numa1', parent=cn2.uuid)

        pf1_0 = self._create_provider('cn1_numa0_pf0', parent=numa1_0.uuid)
        pf1_1 = self._create_provider('cn1_numa1_pf1', parent=numa1_1.uuid)
        pf2_0 = self._create_provider('cn2_numa0_pf0', parent=numa2_0.uuid)
        pf2_1 = self._create_provider('cn2_numa1_pf1', parent=numa2_1.uuid)

        tb.add_inventory(pf1_0, orc.SRIOV_NET_VF, 8)
        tb.add_inventory(pf1_1, orc.SRIOV_NET_VF, 8)
        tb.add_inventory(pf2_0, orc.SRIOV_NET_VF, 8)
        tb.add_inventory(pf2_1, orc.SRIOV_NET_VF, 8)
        tb.set_traits(pf2_1, os_traits.HW_NIC_OFFLOAD_GENEVE)
        tb.set_traits(pf1_1, os_traits.HW_NIC_OFFLOAD_GENEVE)

        ss1 = self._create_provider('ss1', uuids.agg1)
        ss2 = self._create_provider('ss2', uuids.agg2)
        tb.add_inventory(ss1, orc.DISK_GB, 2000)
        tb.add_inventory(ss2, orc.DISK_GB, 1000)
        tb.set_traits(ss1, 'MISC_SHARES_VIA_AGGREGATE')
        tb.set_traits(ss2, 'MISC_SHARES_VIA_AGGREGATE')

        alloc_cands = self._get_allocation_candidates({
            '': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.VCPU: 2,
                    orc.SRIOV_NET_VF: 1,
                    orc.DISK_GB: 1500,
                })
        })

        # cn2 is not in the allocation candidates because it doesn't have
        # enough DISK_GB resource with shared providers.
        expected = [
            [('cn1', orc.VCPU, 2),
             ('cn1_numa0_pf0', orc.SRIOV_NET_VF, 1),
             ('ss1', orc.DISK_GB, 1500)],
            [('cn1', orc.VCPU, 2),
             ('cn1_numa1_pf1', orc.SRIOV_NET_VF, 1),
             ('ss1', orc.DISK_GB, 1500)]
        ]

        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 16, 0)
            ]),
            'cn1_numa0': set([]),
            'cn1_numa1': set([]),
            'cn1_numa0_pf0': set([
                (orc.SRIOV_NET_VF, 8, 0)
            ]),
            'cn1_numa1_pf1': set([
                (orc.SRIOV_NET_VF, 8, 0)
            ]),
            'ss1': set([
                (orc.DISK_GB, 2000, 0)
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

        # Now add required traits to the mix and verify we still get the
        # inventory of SRIOV_NET_VF.
        alloc_cands = self._get_allocation_candidates({
            '': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.VCPU: 2,
                    orc.SRIOV_NET_VF: 1,
                    orc.DISK_GB: 1500,
                },
                required_traits=[{os_traits.HW_NIC_OFFLOAD_GENEVE}])
        })

        # cn1_numa0_pf0 is not in the allocation candidates because it
        # doesn't have the required trait.
        expected = [
            [('cn1', orc.VCPU, 2),
             ('cn1_numa1_pf1', orc.SRIOV_NET_VF, 1),
             ('ss1', orc.DISK_GB, 1500)]
        ]
        self._validate_allocation_requests(expected, alloc_cands)

        expected = {
            'cn1': set([
                (orc.VCPU, 16, 0)
            ]),
            'cn1_numa0': set([]),
            'cn1_numa1': set([]),
            'cn1_numa0_pf0': set([
                (orc.SRIOV_NET_VF, 8, 0)
            ]),
            'cn1_numa1_pf1': set([
                (orc.SRIOV_NET_VF, 8, 0)
            ]),
            'ss1': set([
                (orc.DISK_GB, 2000, 0)
            ]),
        }
        self._validate_provider_summary_resources(expected, alloc_cands)

    def _create_nested_trees(self):
        # We are setting up 2 identical compute trees with no storage
        # that look like this:
        #
        #              compute node (cn1)
        #             /                 \
        #            /                   \
        #       numa cell 1_0        numa cell 1_1
        #           |                    |
        #           |                    |
        #         pf 1_0               pf 1_1
        #
        #              compute node (cn2)
        #             /                 \
        #            /                   \
        #       numa cell 2_0        numa cell 2_1
        #           |                    |
        #           |                    |
        #         pf 2_0               pf 2_1
        #
        cn1 = self._create_provider('cn1', uuids.agg1)
        cn2 = self._create_provider('cn2', uuids.agg2)
        tb.add_inventory(cn1, orc.VCPU, 16)
        tb.add_inventory(cn2, orc.VCPU, 16)

        numa1_0 = self._create_provider('cn1_numa0', parent=cn1.uuid)
        numa1_1 = self._create_provider('cn1_numa1', parent=cn1.uuid)
        numa2_0 = self._create_provider('cn2_numa0', parent=cn2.uuid)
        numa2_1 = self._create_provider('cn2_numa1', parent=cn2.uuid)

        pf1_0 = self._create_provider('cn1_numa0_pf0', parent=numa1_0.uuid)
        pf1_1 = self._create_provider('cn1_numa1_pf1', parent=numa1_1.uuid)
        pf2_0 = self._create_provider('cn2_numa0_pf0', parent=numa2_0.uuid)
        pf2_1 = self._create_provider('cn2_numa1_pf1', parent=numa2_1.uuid)

        tb.add_inventory(pf1_0, orc.SRIOV_NET_VF, 8)
        tb.add_inventory(pf1_1, orc.SRIOV_NET_VF, 8)
        tb.add_inventory(pf2_0, orc.SRIOV_NET_VF, 8)
        tb.add_inventory(pf2_1, orc.SRIOV_NET_VF, 8)

    def test_nested_result_count_none(self):
        """Tests that we properly winnow allocation requests when including
        nested providers from different request groups with group policy none.
        """
        self._create_nested_trees()
        # Make a granular request to check count of results.
        alloc_cands = self._get_allocation_candidates({
            '': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.VCPU: 2,
                }),
            '_NET1': placement_lib.RequestGroup(
                use_same_provider=True,
                resources={
                    orc.SRIOV_NET_VF: 1,
                }),
            '_NET2': placement_lib.RequestGroup(
                use_same_provider=True,
                resources={
                    orc.SRIOV_NET_VF: 1,
                }),
        }, rqparams=placement_lib.RequestWideParams(group_policy='none'))
        # 4 VF providers each providing 2, 1, or 0 inventory makes 6
        # different combinations, plus two more that are effectively
        # the same but satisfying different suffix mappings.
        self.assertEqual(8, len(alloc_cands.allocation_requests))

    def test_nested_result_count_different_amounts_isolate(self):
        """Tests that we properly winnow allocation requests when including
        nested providers from different request groups, with different
        requested amounts.
        """
        self._create_nested_trees()
        # Make a granular request to check count of results.
        alloc_cands = self._get_allocation_candidates({
            '': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.VCPU: 2,
                }),
            '_NET1': placement_lib.RequestGroup(
                use_same_provider=True,
                resources={
                    orc.SRIOV_NET_VF: 1,
                }),
            '_NET2': placement_lib.RequestGroup(
                use_same_provider=True,
                resources={
                    orc.SRIOV_NET_VF: 2,
                }),
        }, rqparams=placement_lib.RequestWideParams(group_policy='isolate'))
        self.assertEqual(4, len(alloc_cands.allocation_requests))

    def test_nested_result_suffix_mappings(self):
        """Confirm that paying attention to suffix mappings expands
        the quantity of results and confirm those results.
        """
        self._create_nested_trees()
        # Make a granular request to check count and suffixes of results.
        alloc_cands = self._get_allocation_candidates({
            '': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.VCPU: 2,
                }),
            '_NET1': placement_lib.RequestGroup(
                use_same_provider=True,
                resources={
                    orc.SRIOV_NET_VF: 1,
                }),
            '_NET2': placement_lib.RequestGroup(
                use_same_provider=True,
                resources={
                    orc.SRIOV_NET_VF: 1,
                }),
        }, rqparams=placement_lib.RequestWideParams(group_policy='isolate'))

        expected = [
            [('cn1', orc.VCPU, 2, ['']),
             ('cn1_numa0_pf0', orc.SRIOV_NET_VF, 1, ['_NET1']),
             ('cn1_numa1_pf1', orc.SRIOV_NET_VF, 1, ['_NET2'])],
            [('cn1', orc.VCPU, 2, ['']),
             ('cn1_numa0_pf0', orc.SRIOV_NET_VF, 1, ['_NET2']),
             ('cn1_numa1_pf1', orc.SRIOV_NET_VF, 1, ['_NET1'])],
            [('cn2', orc.VCPU, 2, ['']),
             ('cn2_numa0_pf0', orc.SRIOV_NET_VF, 1, ['_NET1']),
             ('cn2_numa1_pf1', orc.SRIOV_NET_VF, 1, ['_NET2'])],
            [('cn2', orc.VCPU, 2, ['']),
             ('cn2_numa0_pf0', orc.SRIOV_NET_VF, 1, ['_NET2']),
             ('cn2_numa1_pf1', orc.SRIOV_NET_VF, 1, ['_NET1'])],
        ]

        # Near the end of _merge candidates we expect 4 different collections
        # of AllocationRequest to attempt to be added to a set. Admittance is
        # controlled by the __hash__ and __eq__ of the AllocationRequest which,
        # in this case, should keep the results at 4 since they are defined to
        # be different when they have different suffixes even if they have the
        # same resource provider, the same resource class and the same desired
        # amount.
        self.assertEqual(4, len(alloc_cands.allocation_requests))
        self._validate_allocation_requests(
            expected, alloc_cands, expect_suffixes=True)

    def test_nested_result_suffix_mappings_non_isolated(self):
        """Confirm that paying attention to suffix mappings expands
        the quantity of results and confirm those results.
        """
        self._create_nested_trees()
        # Make a granular request to check count and suffixes of results.
        alloc_cands = self._get_allocation_candidates({
            '': placement_lib.RequestGroup(
                use_same_provider=False,
                resources={
                    orc.VCPU: 2,
                }),
            '_NET1': placement_lib.RequestGroup(
                use_same_provider=True,
                resources={
                    orc.SRIOV_NET_VF: 1,
                }),
            '_NET2': placement_lib.RequestGroup(
                use_same_provider=True,
                resources={
                    orc.SRIOV_NET_VF: 1,
                }),
        }, rqparams=placement_lib.RequestWideParams(group_policy='none'))

        # We get four candidates from each compute node:
        # [A] Two where one VF comes from each PF+RequestGroup combination.
        # [B] Two where both VFs come from the same PF (which satisfies both
        # RequestGroupZ).
        expected = [
            # [A] (cn1)
            [('cn1', orc.VCPU, 2, ['']),
             ('cn1_numa0_pf0', orc.SRIOV_NET_VF, 1, ['_NET1']),
             ('cn1_numa1_pf1', orc.SRIOV_NET_VF, 1, ['_NET2'])],
            [('cn1', orc.VCPU, 2, ['']),
             ('cn1_numa0_pf0', orc.SRIOV_NET_VF, 1, ['_NET2']),
             ('cn1_numa1_pf1', orc.SRIOV_NET_VF, 1, ['_NET1'])],
            # [B] (cn1)
            [('cn1', orc.VCPU, 2, ['']),
             ('cn1_numa0_pf0', orc.SRIOV_NET_VF, 2, ['_NET1', '_NET2'])],
            [('cn1', orc.VCPU, 2, ['']),
             ('cn1_numa1_pf1', orc.SRIOV_NET_VF, 2, ['_NET1', '_NET2'])],
            # [A] (cn2)
            [('cn2', orc.VCPU, 2, ['']),
             ('cn2_numa0_pf0', orc.SRIOV_NET_VF, 1, ['_NET1']),
             ('cn2_numa1_pf1', orc.SRIOV_NET_VF, 1, ['_NET2'])],
            [('cn2', orc.VCPU, 2, ['']),
             ('cn2_numa0_pf0', orc.SRIOV_NET_VF, 1, ['_NET2']),
             ('cn2_numa1_pf1', orc.SRIOV_NET_VF, 1, ['_NET1'])],
            # [B] (cn2)
            [('cn2', orc.VCPU, 2, ['']),
             ('cn2_numa0_pf0', orc.SRIOV_NET_VF, 2, ['_NET1', '_NET2'])],
            [('cn2', orc.VCPU, 2, ['']),
             ('cn2_numa1_pf1', orc.SRIOV_NET_VF, 2, ['_NET1', '_NET2'])],
        ]

        self.assertEqual(8, len(alloc_cands.allocation_requests))
        self._validate_allocation_requests(
            expected, alloc_cands, expect_suffixes=True)
