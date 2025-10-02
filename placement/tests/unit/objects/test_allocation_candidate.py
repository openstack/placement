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
from oslo_utils.fixture import uuidsentinel as uuids
from unittest import mock

from placement import lib as placement_lib
from placement.objects import allocation_candidate as ac_obj
from placement.objects import research_context as res_ctx
from placement.objects import resource_provider as rp_obj
from placement.tests.unit.objects import base


class TestAllocationCandidatesNoDB(base.TestCase):
    @mock.patch('placement.objects.research_context._has_provider_trees',
                new=mock.Mock(return_value=True))
    def test_limit_results(self):
        # Results are limited based on their root provider uuid, not uuid.
        # For a more "real" test of this functionality, one that exercises
        # nested providers, see the 'get allocation candidates nested limit'
        # test in the 'allocation-candidates.yaml' gabbit.
        aro_in = [
            mock.Mock(
                resource_requests=[
                    mock.Mock(resource_provider=mock.Mock(
                        root_provider_uuid=uuid))
                    for uuid in (1, 0, 4, 8)]),
            mock.Mock(
                resource_requests=[
                    mock.Mock(resource_provider=mock.Mock(
                        root_provider_uuid=uuid))
                    for uuid in (4, 8, 5)]),
            mock.Mock(
                resource_requests=[
                    mock.Mock(resource_provider=mock.Mock(
                        root_provider_uuid=uuid))
                    for uuid in (1, 7, 6, 4, 8, 5)]),
        ]
        sum1 = mock.Mock(resource_provider=mock.Mock(root_provider_uuid=1))
        sum0 = mock.Mock(resource_provider=mock.Mock(root_provider_uuid=0))
        sum4 = mock.Mock(resource_provider=mock.Mock(root_provider_uuid=4))
        sum8 = mock.Mock(resource_provider=mock.Mock(root_provider_uuid=8))
        sum5 = mock.Mock(resource_provider=mock.Mock(root_provider_uuid=5))
        sum7 = mock.Mock(resource_provider=mock.Mock(root_provider_uuid=7))
        sum6 = mock.Mock(resource_provider=mock.Mock(root_provider_uuid=6))
        sum_in = [sum1, sum0, sum4, sum8, sum5, sum7, sum6]
        rw_ctx = res_ctx.RequestWideSearchContext(
            self.context, placement_lib.RequestWideParams(limit=2), True)
        aro, sum = rw_ctx.limit_results(aro_in, sum_in)
        self.assertEqual(aro_in[:2], aro)
        self.assertEqual(set([sum1, sum0, sum4, sum8, sum5]), set(sum))

    def test_check_same_subtree(self):
        # Construct a tree that look like this
        #
        #  0 -+- 00 --- 000    1 -+- 10 --- 100
        #     |                   |
        #     +- 01 -+- 010       +- 11 -+- 110
        #     |      +- 011       |      +- 111
        #     +- 02 -+- 020       +- 12 -+- 120
        #            +- 021              +- 121
        #
        parent_by_rp = {"0": None, "00": "0", "000": "00",
                        "01": "0", "010": "01", "011": "01",
                        "02": "0", "020": "02", "021": "02",
                        "1": None, "10": "1", "100": "10",
                        "11": "1", "110": "11", "111": "11",
                        "12": "1", "120": "12", "121": "12"}
        same_subtree = [
            set(["0", "00", "01"]),
            set(["01", "010"]),
            set(["02", "020", "021"]),
            set(["02", "020", "021"]),
            set(["0", "02", "010"]),
            set(["000"])
        ]

        different_subtree = [
            set(["10", "11"]),
            set(["110", "111"]),
            set(["10", "11", "110"]),
            set(["12", "120", "100"]),
            set(["0", "1"]),
        ]

        for group in same_subtree:
            self.assertTrue(
                ac_obj._check_same_subtree(group, parent_by_rp))

        for group in different_subtree:
            self.assertFalse(
                ac_obj._check_same_subtree(group, parent_by_rp))

    @mock.patch('placement.objects.research_context._has_provider_trees',
                new=mock.Mock(return_value=True))
    def _test_generate_areq_list(self, strategy, expected_candidates):
        self.conf_fixture.conf.set_override(
            "allocation_candidates_generation_strategy", strategy,
            group="placement")

        rw_ctx = res_ctx.RequestWideSearchContext(
            self.context, placement_lib.RequestWideParams(), True)
        areq_lists_by_anchor = {
            "root1": {
                "": ["r1A", "r1B",],
                "group1": ["r1g1A", "r1g1B",],
            },
            "root2": {
                "": ["r2A"],
                "group1": ["r2g1A", "r2g1B"],
            },
            "root3": {
                "": ["r3A"],
            },
        }
        generator = ac_obj._generate_areq_lists(
            rw_ctx, areq_lists_by_anchor, {"", "group1"})

        self.assertEqual(expected_candidates, list(generator))

    def test_generate_areq_lists_depth_first(self):
        # Depth-first will generate all root1 candidates first then root2,
        # root3 is ignored as it has no candidate for group1.
        expected_candidates = [
            ('r1A', 'r1g1A'),
            ('r1A', 'r1g1B'),
            ('r1B', 'r1g1A'),
            ('r1B', 'r1g1B'),
            ('r2A', 'r2g1A'),
            ('r2A', 'r2g1B'),
        ]
        self._test_generate_areq_list("depth-first", expected_candidates)

    @mock.patch('placement.objects.research_context._has_provider_trees',
                new=mock.Mock(return_value=True))
    def test_generate_areq_lists_breadth_first(self):
        # Breadth-first will take one candidate from root1 then root2 then goes
        # back to root1 etc. Root2 runs out of candidates earlier than root1 so
        # the last two candidates are both from root1. The root3 is still
        # ignored as it has no candidates for group1.
        expected_candidates = [
            ('r1A', 'r1g1A'),
            ('r2A', 'r2g1A'),
            ('r1A', 'r1g1B'),
            ('r2A', 'r2g1B'),
            ('r1B', 'r1g1A'),
            ('r1B', 'r1g1B')
        ]
        self._test_generate_areq_list("breadth-first", expected_candidates)


def _rp(rp_id, capacity=1, max_unit=None):
    return {(rp_id, "SRIOV_VF"):
            ac_obj.ProviderSummaryResource(
                resource_class="SRIOV_VF", capacity=capacity,
                used=0, max_unit=max_unit or capacity)}


def _alloc_req(group, rp_id, amount):
    return ac_obj.AllocationRequest(
        anchor_root_provider_uuid=uuids.root,
        use_same_provider=True,
        resource_requests=[
            ac_obj.AllocationRequestResource(
                resource_provider=rp_obj.ResourceProvider(
                    context=None, id=rp_id, uuid=rp_id),
                resource_class="SRIOV_VF",
                amount=amount)
        ],
        mappings={group: [rp_id]})


class TestOptimizedAllocationCandidatesNoDB(base.TestCase):
    def setUp(self):
        super().setUp()
        self.conf_fixture.conf.set_override(
            "optimize_for_wide_provider_trees", True, group="workarounds")

    @mock.patch('placement.objects.research_context._has_provider_trees',
                new=mock.Mock(return_value=True))
    def test_multiple_groups_usage_overlap_3_3(self):
        rw_ctx = res_ctx.RequestWideSearchContext(
            self.context, placement_lib.RequestWideParams(), True)

        # We have 3 child RPs each having a capacity of one resource
        rw_ctx.psum_res_by_rp_rc.update(_rp("RP1", capacity=1))
        rw_ctx.psum_res_by_rp_rc.update(_rp("RP2", capacity=1))
        rw_ctx.psum_res_by_rp_rc.update(_rp("RP3", capacity=1))

        G1_RP1 = _alloc_req("G1", rp_id="RP1", amount=1)
        G1_RP2 = _alloc_req("G1", rp_id="RP2", amount=1)
        G1_RP3 = _alloc_req("G1", rp_id="RP3", amount=1)

        G2_RP1 = _alloc_req("G2", rp_id="RP1", amount=1)
        G2_RP2 = _alloc_req("G2", rp_id="RP2", amount=1)
        G2_RP3 = _alloc_req("G2", rp_id="RP3", amount=1)

        G3_RP1 = _alloc_req("G3", rp_id="RP1", amount=1)
        G3_RP2 = _alloc_req("G3", rp_id="RP2", amount=1)
        G3_RP3 = _alloc_req("G3", rp_id="RP3", amount=1)

        # This algorithm starts with the possible solutions for each group
        # independent of the other groups in the same request. So here G1
        # can be fulfilled from RP1, RP2, or RP3. As well as G2, and G3.
        areq_lists_by_anchor = {
            "root": {
                "G1": [G1_RP1, G1_RP2, G1_RP3],
                "G2": [G2_RP1, G2_RP2, G2_RP3],
                "G3": [G3_RP1, G3_RP2, G3_RP3],
            },
        }

        orig_consolidate = ac_obj._consolidate_allocation_requests
        consolidate_calls = []

        def wrap_consolidate_allocation_requests(areq_list, rw_ctx):
            # we need to deep copy the call args as they are mutated during
            # the test run
            consolidate_calls.append(copy.deepcopy(areq_list))
            return orig_consolidate(areq_list, rw_ctx)

        orig_exceeds_capacity = ac_obj._exceeds_capacity
        # pairs of areq_list from the call arg and the return value of the
        # wrapped call
        exceeds_capacity_calls = []

        def warp_exceeds_capacity(rw_ctx, areq_list):
            result = orig_exceeds_capacity(rw_ctx, areq_list)
            exceeds_capacity_calls.append((areq_list, result))
            return result

        with (
            # Consolidate is not called during product generation as we
            # re-implemented exceeds_capacity to work on non consolidated
            # areq_lists
            mock.patch.object(
                ac_obj, "_consolidate_allocation_requests",
                new=mock.NonCallableMock
            ),
            # the rw_ctx exceeds_capacity working on consolidated areqs
            # are not called at all, the local _exceeds_capacity called instead
            # on all partial products, mocked below.
            mock.patch.object(
                rw_ctx, "exceeds_capacity", new=mock.NonCallableMock()
            ),
            mock.patch.object(
                ac_obj, "_exceeds_capacity",
                side_effect=warp_exceeds_capacity
            ) as mock_exceeds_capacity,
        ):
            generator = ac_obj._generate_areq_lists(
                rw_ctx, areq_lists_by_anchor, {"G1", "G2", "G3"})

            areq_lists = list(generator)

            # We don't have 27 (3^3) valid solutions just 6 (3!) as if one of
            # the Group is fulfilled from an RP then the other Groups cannot be
            # fulfilled from the same RP as each RP has 1 resource only.
            # Without the optimize_for_wide_provider_trees = true the
            # _generate_areq_lists call would generate all the 27 possible
            # product and then later processing would filter out the invalid,
            # overlapping ones.
            self.assertEqual(6, len(areq_lists))
            self.assertEqual([
                (G1_RP1, G2_RP2, G3_RP3),
                (G1_RP1, G2_RP3, G3_RP2),
                (G1_RP2, G2_RP1, G3_RP3),
                (G1_RP2, G2_RP3, G3_RP1),
                (G1_RP3, G2_RP1, G3_RP2),
                (G1_RP3, G2_RP2, G3_RP1),],
                areq_lists)

        # areq_list, result pairs where areq_list is a partial product
        # and the result is the expected return value of _exceeds_capacity
        expected_exceeds_capacity_calls = [
            ((G1_RP1,), False),
            ((G1_RP1, G2_RP1), True),
            # This is the pruning. The algo did not try to generate
            # G1_RP1, G2_RP1, G3_RPx for all three possible x RPs as it knows
            # that if the prefix is invalid then all the product with that
            # prefix is also invalid.
            ((G1_RP1, G2_RP2), False),
            ((G1_RP1, G2_RP2, G3_RP1), True),
            # This is another optimization (compared to an index odometer
            # based product algo) that the recursive call reuses the already
            # calculated and checked valid prefix of G1_RP1, G2_RP2 and don't
            # need to re-create it to try G3_RP2 with it.
            ((G1_RP1, G2_RP2, G3_RP2), True),
            ((G1_RP1, G2_RP2, G3_RP3), False),  # this is a valid product
            # simple backtrack as we run out of possibilities on level 3
            ((G1_RP1, G2_RP3), False),
            ((G1_RP1, G2_RP3, G3_RP1), True),
            ((G1_RP1, G2_RP3, G3_RP2), False),  # this is a valid product
            ((G1_RP1, G2_RP3, G3_RP3), True),
            # double backtrack as we run out the possibilities on level 2 and
            # level 3
            ((G1_RP2,), False),
            ((G1_RP2, G2_RP1), False),
            ((G1_RP2, G2_RP1, G3_RP1), True),
            ((G1_RP2, G2_RP1, G3_RP2), True),
            ((G1_RP2, G2_RP1, G3_RP3), False),  # this is a valid product
            ((G1_RP2, G2_RP2), True),  # suffixes are pruned
            ((G1_RP2, G2_RP3), False),
            ((G1_RP2, G2_RP3, G3_RP1), False),  # this is a valid product
            ((G1_RP2, G2_RP3, G3_RP2), True),
            ((G1_RP2, G2_RP3, G3_RP3), True),  # double backtrack
            ((G1_RP3,), False),
            ((G1_RP3, G2_RP1), False),
            ((G1_RP3, G2_RP1, G3_RP1), True),
            ((G1_RP3, G2_RP1, G3_RP2), False),  # this is a valid product
            ((G1_RP3, G2_RP1, G3_RP3), True),   # backtrack
            ((G1_RP3, G2_RP2), False),
            ((G1_RP3, G2_RP2, G3_RP1), False),  # this is a valid product
            ((G1_RP3, G2_RP2, G3_RP2), True),
            ((G1_RP3, G2_RP2, G3_RP3), True),  # backtrack
            ((G1_RP3, G2_RP3), True),  # suffixes are pruned
            # backtrack all the way as we finished with the level 1
            # possibilities as well
        ]

        for i, p in enumerate(
            zip(expected_exceeds_capacity_calls, exceeds_capacity_calls)
        ):
            expected, actual = p
            self.assertEqual(
                expected, actual, "Call index %d does not match" % i)

        # Why 30 is the correct answer?
        # I don't have an easy way to prove that mathematically. It was
        # easier to list them all out above so they can be reviewed
        #
        # With this 3 by 3 example the number of checks are higher when
        # optimization is enabled than without it. But if you increase the
        # size of the product then the number of pruned space grows fast
        # as well as the size of the product space. On an 8 by 8 example
        # this is already a must-have optimization to run the checks in
        # less than a minute. See the included functional tests for the
        # scale results.
        self.assertEqual(30, len(mock_exceeds_capacity.mock_calls))
        self.assertEqual(30, len(expected_exceeds_capacity_calls))


class TestExceedsCapacityNoDB(base.TestCase):

    def setUp(self):
        super().setUp()

        patcher = mock.patch(
            'placement.objects.research_context._has_provider_trees',
            new=mock.Mock(return_value=True))
        self.addCleanup(patcher.stop)
        patcher.start()

        self.rw_ctx = res_ctx.RequestWideSearchContext(
            self.context, placement_lib.RequestWideParams(), True)

        self.rw_ctx.psum_res_by_rp_rc.update(
            _rp("RP1", capacity=3, max_unit=1))
        self.rw_ctx.psum_res_by_rp_rc.update(
            _rp("RP2", capacity=2, max_unit=2))
        self.rw_ctx.psum_res_by_rp_rc.update(
            _rp("RP3", capacity=1, max_unit=1))

    def test_not_exceeds(self):
        self.assertFalse(
            ac_obj._exceeds_capacity(
                self.rw_ctx, (_alloc_req("G1", rp_id="RP1", amount=1),)))

        self.assertFalse(
            ac_obj._exceeds_capacity(
                self.rw_ctx, (
                    _alloc_req("G1", rp_id="RP2", amount=1),
                    _alloc_req("G2", rp_id="RP2", amount=1),
                )))

        self.assertFalse(
            ac_obj._exceeds_capacity(
                self.rw_ctx, (
                    _alloc_req("G1", rp_id="RP3", amount=1),
                    _alloc_req("G2", rp_id="RP1", amount=1),
                )))

    def test_exceeds_capacity(self):
        self.assertTrue(
            ac_obj._exceeds_capacity(
                self.rw_ctx, (
                    _alloc_req("G1", rp_id="RP3", amount=1),
                    _alloc_req("G2", rp_id="RP3", amount=1),
                )))

    def test_exceeds_max_unit(self):
        self.assertTrue(
            ac_obj._exceeds_capacity(self.rw_ctx, (
                _alloc_req("G1", rp_id="RP1", amount=1),
                _alloc_req("G2", rp_id="RP1", amount=1)
            )))
