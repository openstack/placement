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
import os_resource_classes as orc

from placement.objects import allocation_candidate
from placement.tests.unit.objects import base


class TestAllocationCandidatesNoDB(base.TestCase):
    def test_limit_results(self):
        # UUIDs don't have to be real UUIDs to test the logic
        aro_in = [
            mock.Mock(
                resource_requests=[
                    mock.Mock(resource_provider=mock.Mock(uuid=uuid))
                    for uuid in (1, 0, 4, 8)]),
            mock.Mock(
                resource_requests=[
                    mock.Mock(resource_provider=mock.Mock(uuid=uuid))
                    for uuid in (4, 8, 5)]),
            mock.Mock(
                resource_requests=[
                    mock.Mock(resource_provider=mock.Mock(uuid=uuid))
                    for uuid in (1, 7, 6, 4, 8, 5)]),
        ]
        sum1 = mock.Mock(resource_provider=mock.Mock(uuid=1))
        sum0 = mock.Mock(resource_provider=mock.Mock(uuid=0))
        sum4 = mock.Mock(resource_provider=mock.Mock(uuid=4))
        sum8 = mock.Mock(resource_provider=mock.Mock(uuid=8))
        sum5 = mock.Mock(resource_provider=mock.Mock(uuid=5))
        sum7 = mock.Mock(resource_provider=mock.Mock(uuid=7))
        sum6 = mock.Mock(resource_provider=mock.Mock(uuid=6))
        sum_in = [sum1, sum0, sum4, sum8, sum5, sum7, sum6]
        aro, sum = allocation_candidate.AllocationCandidates._limit_results(
            self.context, aro_in, sum_in, 2)
        self.assertEqual(aro_in[:2], aro)
        self.assertEqual(set([sum1, sum0, sum4, sum8, sum5]), set(sum))


class TestProviderSummaryNoDB(base.TestCase):

    def test_resource_class_names(self):
        psum = allocation_candidate.ProviderSummary(mock.sentinel.ctx)
        disk_psr = allocation_candidate.ProviderSummaryResource(
            resource_class=orc.DISK_GB, capacity=100, used=0)
        ram_psr = allocation_candidate.ProviderSummaryResource(
            resource_class=orc.MEMORY_MB, capacity=1024, used=0)
        psum.resources = [disk_psr, ram_psr]
        expected = set(['DISK_GB', 'MEMORY_MB'])
        self.assertEqual(expected, psum.resource_class_names)
