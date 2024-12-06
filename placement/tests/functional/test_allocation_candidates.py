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

from placement import direct
from placement.tests.functional import base
from placement.tests.functional.db import test_base as tb


class TestWideTreeAllocationCandidateExplosion(base.TestCase):
    """Test candidate generation ordering and limiting in wide symmetric trees,
     i.e. with trees of many similar child RPs.
    """

    def setUp(self):
        super().setUp()
        self.headers = {
            'x-auth-token': 'admin',
            'content-type': 'application/json',
            'OpenStack-API-Version': 'placement 1.38',
            'X_ROLES': 'admin,service'
        }

        self.conf_fixture.conf.set_override(
            "max_allocation_candidates", 100000, group="placement")
        self.conf_fixture.conf.set_override(
            "allocation_candidates_generation_strategy", "breadth-first",
            group="placement")

    def create_tree(self, num_roots, num_child, num_res_per_child):
        self.roots = {}

        for i in range(num_roots):
            compute = tb.create_provider(
                self.context, f'compute{i}')
            self.roots[compute.uuid] = compute.name
            tb.add_inventory(compute, 'VCPU', 8)
            tb.add_inventory(compute, 'MEMORY_MB', 4096)
            tb.add_inventory(compute, 'DISK_GB', 500)

            for j in range(num_child):
                child = tb.create_provider(
                    self.context, f'compute{i}:PF{j}', parent=compute.uuid)
                tb.add_inventory(child, 'CUSTOM_VF', num_res_per_child)

    @staticmethod
    def get_candidate_query(num_groups, num_res, limit):
        query = ("/allocation_candidates?"
                 "resources=DISK_GB%3A20%2CMEMORY_MB%3A2048%2CVCPU%3A2")

        for g in range(num_groups):
            query += f"&resources{g}=CUSTOM_VF%3A{num_res}"

        query += "&group_policy=none"
        query += f"&limit={limit}"

        return query

    def _test_num_candidates_and_computes(
        self, computes, pfs, vfs_per_pf, req_groups, req_res_per_group,
        req_limit, expected_candidates, expected_computes_with_candidates
    ):
        self.create_tree(
            num_roots=computes, num_child=pfs, num_res_per_child=vfs_per_pf)

        conf = self.conf_fixture.conf
        with direct.PlacementDirect(conf) as client:
            resp = client.get(
                self.get_candidate_query(
                    num_groups=req_groups, num_res=req_res_per_group,
                    limit=req_limit),
                headers=self.headers)
            self.assertEqual(200, resp.status_code)

        body = resp.json()
        self.assertEqual(expected_candidates, len(body["allocation_requests"]))

        root_rps = set(self.roots.keys())
        roots_with_candidates = set()
        nr_of_candidates_per_compute = collections.Counter()
        for ar in body["allocation_requests"]:
            allocated_rps = set(ar["allocations"].keys())
            root_allocated_rps = allocated_rps.intersection(root_rps)
            roots_with_candidates |= root_allocated_rps
            nr_of_candidates_per_compute.update(root_allocated_rps)

        self.assertEqual(
            expected_computes_with_candidates, len(roots_with_candidates))

    def test_all_candidates_generated_and_returned(self):
        self._test_num_candidates_and_computes(
            computes=2, pfs=8, vfs_per_pf=8, req_groups=2, req_res_per_group=1,
            req_limit=1000,
            expected_candidates=2 * 64, expected_computes_with_candidates=2,)

    def test_requested_limit_is_hit_result_balanced(self):
        # 8192 possible candidates, all generated, returned 1000,
        # result is balanced due to python sets usage
        self._test_num_candidates_and_computes(
            computes=2, pfs=8, vfs_per_pf=8, req_groups=4, req_res_per_group=1,
            req_limit=1000,
            expected_candidates=1000, expected_computes_with_candidates=2)

    def test_too_many_candidates_global_limit_is_hit_result_unbalanced(self):
        self.conf_fixture.conf.set_override(
            "allocation_candidates_generation_strategy", "depth-first",
            group="placement")
        # With max_allocation_candidates set to 100k limit this test now
        # runs in reasonable time (10 sec on my machine), without that it would
        # time out.
        # However, with depth-first strategy and with the global limit in place
        # only the first compute gets candidates.
        # 524288 valid candidates, the generation stops at 100k candidates,
        # only 1000 is returned, result is unbalanced as the first 100k
        # candidate is always from the first compute.
        self._test_num_candidates_and_computes(
            computes=2, pfs=8, vfs_per_pf=8, req_groups=6, req_res_per_group=1,
            req_limit=1000,
            expected_candidates=1000, expected_computes_with_candidates=1)

    def test_too_many_candidates_global_limit_is_hit_breadth_first_balanced(
        self
    ):
        # With max_allocation_candidates set to 100k limit this test now
        # runs in reasonable time (10 sec on my machine), without that it would
        # time out.
        # With the round-robin candidate generator in place the 100k generated
        # candidates spread across both computes now.
        # 524288 valid candidates, the generation stops at 100k candidates,
        # only 1000 is returned, result is balanced between the computes
        self._test_num_candidates_and_computes(
            computes=2, pfs=8, vfs_per_pf=8, req_groups=6, req_res_per_group=1,
            req_limit=1000,
            expected_candidates=1000, expected_computes_with_candidates=2)

    def test_global_limit_hit(self):
        # 8192 possible candidates, global limit is set to 8000, higher request
        # limit so number of candidates are limited by the global limit
        self.conf_fixture.conf.set_override(
            "max_allocation_candidates", 8000, group="placement")
        self._test_num_candidates_and_computes(
            computes=2, pfs=8, vfs_per_pf=8, req_groups=4, req_res_per_group=1,
            req_limit=9000,
            expected_candidates=8000, expected_computes_with_candidates=2)

    def test_no_global_limit(self):
        # 8192 possible candidates, there is no global limit, high request
        # limit so all candidates returned
        self.conf_fixture.conf.set_override(
            "max_allocation_candidates", -1, group="placement")
        self._test_num_candidates_and_computes(
            computes=2, pfs=8, vfs_per_pf=8, req_groups=4, req_res_per_group=1,
            req_limit=9000,
            expected_candidates=8192, expected_computes_with_candidates=2)

    def test_breadth_first_strategy_generates_stable_ordering(self):
        """Run the same query twice against the same two tree and assert that
        response text is exactly the same proving that even with breadth-first
        strategy the candidate ordering is stable.
        """

        self.create_tree(num_roots=2, num_child=8, num_res_per_child=8)

        def query():
            return client.get(
                self.get_candidate_query(
                    num_groups=2, num_res=1,
                    limit=1000),
                headers=self.headers)

        conf = self.conf_fixture.conf
        with direct.PlacementDirect(conf) as client:
            resp = query()
            self.assertEqual(200, resp.status_code)
            body1 = resp.text

            resp = query()
            self.assertEqual(200, resp.status_code)
            body2 = resp.text

            self.assertEqual(body1, body2)
