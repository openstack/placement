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

from oslo_upgradecheck import upgradecheck

from placement.cmd import status
from placement.objects import consumer
from placement.tests.functional import base
from placement.tests.functional.db import test_consumer


class UpgradeCheckIncompleteConsumersTestCase(
        base.TestCase, test_consumer.CreateIncompleteAllocationsMixin):
    """Tests the "Incomplete Consumers" check for the
    "placement-status upgrade check" command.
    """
    def setUp(self):
        super(UpgradeCheckIncompleteConsumersTestCase, self).setUp()
        self.checks = status.Checks()

    def test_check_incomplete_consumers(self):
        # Create some allocations with 3 missing consumers.
        self._create_incomplete_allocations(
            self.context, num_of_consumer_allocs=2)
        result = self.checks._check_incomplete_consumers()
        # Since there are incomplete consumers, there should be a warning.
        self.assertEqual(upgradecheck.Code.WARNING, result.code)
        # Check the details for the consumer count.
        self.assertIn('There are 3 incomplete consumers table records for '
                      'existing allocations', result.details)
        # Run the online data migration (as recommended from the check output).
        consumer.create_incomplete_consumers(self.context, batch_size=50)
        # Run the check again and it should be successful.
        result = self.checks._check_incomplete_consumers()
        self.assertEqual(upgradecheck.Code.SUCCESS, result.code)
