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

import testtools

from placement.objects import rp_candidates


class TestRPCandidateList(testtools.TestCase):
    def setUp(self):
        super(TestRPCandidateList, self).setUp()
        self.rp_candidates = rp_candidates.RPCandidateList()
        self.rps_rc1 = set([
            ('rp1', 'root1'), ('rp2', 'root1'), ('ss1', 'root1'),
            ('rp3', 'root'), ('ss1', 'root')])
        self.rp_candidates.add_rps(self.rps_rc1, 'rc_1')

    def test_property(self):
        expected_rpsinfo = set([('rp1', 'root1', 'rc_1'),
                                ('rp2', 'root1', 'rc_1'),
                                ('ss1', 'root1', 'rc_1'),
                                ('rp3', 'root', 'rc_1'),
                                ('ss1', 'root', 'rc_1')])
        self.assertEqual(expected_rpsinfo, self.rp_candidates.rps_info)

        expected_rps = set(['rp1', 'rp2', 'rp3', 'ss1'])
        expected_trees = set(['root1', 'root'])
        expected_allrps = expected_rps | expected_trees

        self.assertEqual(expected_rps, self.rp_candidates.rps)
        self.assertEqual(expected_trees, self.rp_candidates.trees)
        self.assertEqual(expected_allrps, self.rp_candidates.all_rps)

    def test_filter_by_tree(self):
        self.rp_candidates.filter_by_tree(set(['root1']))
        expected_rpsinfo = set([('rp1', 'root1', 'rc_1'),
                                ('rp2', 'root1', 'rc_1'),
                                ('ss1', 'root1', 'rc_1')])
        self.assertEqual(expected_rpsinfo, self.rp_candidates.rps_info)

    def test_filter_by_rp(self):
        self.rp_candidates.filter_by_rp(set([('ss1', 'root1')]))
        expected_rpsinfo = set([('ss1', 'root1', 'rc_1')])
        self.assertEqual(expected_rpsinfo, self.rp_candidates.rps_info)

    def test_filter_by_rp_or_tree(self):
        self.rp_candidates.filter_by_rp_or_tree(set(['ss1', 'root1']))
        # we get 'ss1' and rps under 'root1'
        expected_rpsinfo = set([('ss1', 'root', 'rc_1'),
                                ('ss1', 'root1', 'rc_1'),
                                ('rp1', 'root1', 'rc_1'),
                                ('rp2', 'root1', 'rc_1')])
        self.assertEqual(expected_rpsinfo, self.rp_candidates.rps_info)

    def test_merge_common_trees(self):
        merge_candidates = rp_candidates.RPCandidateList()
        rps_rc2 = set([('rp1', 'root2'), ('rp4', 'root2'), ('ss1', 'root2'),
                       ('rp5', 'root'), ('ss1', 'root')])
        merge_candidates.add_rps(rps_rc2, 'rc_2')

        self.rp_candidates.merge_common_trees(merge_candidates)
        # we get only rps under 'root' since it's only the common tree
        expected_rpsinfo = set([('rp3', 'root', 'rc_1'),
                                ('rp5', 'root', 'rc_2'),
                                ('ss1', 'root', 'rc_1'),
                                ('ss1', 'root', 'rc_2')])
        self.assertEqual(expected_rpsinfo, self.rp_candidates.rps_info)

        # make sure merging empty candidates doesn't change anything
        empty_candidates = rp_candidates.RPCandidateList()
        self.rp_candidates.merge_common_trees(empty_candidates)
        self.assertEqual(expected_rpsinfo, self.rp_candidates.rps_info)
