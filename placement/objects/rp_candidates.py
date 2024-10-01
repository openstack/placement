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
"""Utility methods for getting allocation candidates."""

import collections


RPCandidate = collections.namedtuple('RPCandidates', 'id root_id rc_id')


class RPCandidateList(object):
    """Helper class to manage allocation candidate resource providers list,
    RPCandidates, which consists of three-tuples with the first element being
    the resource provider ID, the second element being the root provider ID
    and the third being resource class ID.
    """

    def __init__(self, rp_candidates=None):
        self.rp_candidates = rp_candidates or set()

    def __len__(self):
        return len(self.rp_candidates)

    def __bool__(self):
        return bool(len(self))

    def __nonzero__(self):
        return self.__bool__()

    def merge_common_trees(self, other):
        """Merge two RPCandidateLists by OR'ing the two list of candidates
        and if the tree is not in both RPCandidateLists, we exclude resource
        providers in that tree. This is used to get trees that can satisfy
        all requested resource.
        """
        if not self:
            self.rp_candidates = other.rp_candidates
        elif not other:
            pass
        else:
            trees_in_both = self.trees & other.trees
            self.rp_candidates |= other.rp_candidates
            self.filter_by_tree(trees_in_both)

    def add_rps(self, rps, rc_id):
        """Add given resource providers to the candidate list.

        :param rps: tuples of (resource provider ID, anchor root provider ID)
        :param rc_id: ID of the class of resource provided by these resource
                      providers
        """
        self.rp_candidates |= set(
            RPCandidate(id=rp[0], root_id=rp[1], rc_id=rc_id) for rp in rps)

    def filter_by_tree(self, tree_root_ids):
        """Filter the candidates by given trees"""
        self.rp_candidates = set(
            p for p in self.rp_candidates if p.root_id in tree_root_ids)

    def filter_by_rp(self, rptuples):
        """Filter the candidates by given resource provider"""
        self.rp_candidates = set(
            p for p in self.rp_candidates if (p.id, p.root_id) in rptuples)

    def filter_by_rp_or_tree(self, rp_ids):
        """Filter the candidates out if neither itself nor its root is in
        given resource providers
        """
        self.rp_candidates = set(
            p for p in self.rp_candidates if set([p.id, p.root_id]) & rp_ids)

    def filter_by_rp_nor_tree(self, rp_ids):
        """Filter the candidates out if either itself or its root is in
        given resource providers
        """
        self.rp_candidates = set(
            p for p in self.rp_candidates if not (
                set([p.id, p.root_id]) & rp_ids))

    @property
    def rps(self):
        """Returns a set of IDs of nominated resource providers"""
        return set(p.id for p in self.rp_candidates)

    @property
    def trees(self):
        """Returns a set of nominated trees each of which are expressed by
        the root provider ID
        """
        return set(p.root_id for p in self.rp_candidates)

    @property
    def all_rps(self):
        """Returns a set of IDs of all involved resource providers"""
        return (self.rps | self.trees)

    @property
    def rps_info(self):
        return self.rp_candidates
