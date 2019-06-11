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

import mock

from placement.objects import allocation_candidate
from placement.tests.unit.objects import base


class TestAllocationCandidatesNoDB(base.TestCase):
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
        aro, sum = allocation_candidate.AllocationCandidates._limit_results(
            self.context, aro_in, sum_in, 2)
        self.assertEqual(aro_in[:2], aro)
        self.assertEqual(set([sum1, sum0, sum4, sum8, sum5]), set(sum))
