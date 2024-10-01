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

import io

import fixtures
from oslo_config import cfg
from oslo_upgradecheck import upgradecheck
from oslo_utils.fixture import uuidsentinel

from placement.cmd import status
from placement import conf
from placement import db_api
from placement.objects import consumer
from placement.objects import resource_provider
from placement.tests.functional import base
from placement.tests.functional.db import test_consumer


class UpgradeCheckIncompleteConsumersTestCase(
    base.TestCase, test_consumer.CreateIncompleteAllocationsMixin,
):
    """Tests the "Incomplete Consumers" check for the
    "placement-status upgrade check" command.
    """

    def setUp(self):
        super(UpgradeCheckIncompleteConsumersTestCase, self).setUp()
        self.output = io.StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))
        config = cfg.ConfigOpts()
        conf.register_opts(config)
        config(args=[], project='placement')
        self.checks = status.Checks(config)

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

    def test_check_root_provider_ids(self):

        @db_api.placement_context_manager.writer
        def _create_old_rp(ctx):
            rp_tbl = resource_provider._RP_TBL
            ins_stmt1 = rp_tbl.insert().values(
                id=1,
                uuid=uuidsentinel.rp1,
                name='rp-1',
                root_provider_id=None,
                parent_provider_id=None,
                generation=42,
            )
            ctx.session.execute(ins_stmt1)

        # Create a resource provider with no root provider id.
        _create_old_rp(self.context)
        result = self.checks._check_root_provider_ids()
        # Since there is a missing root id, there should be a failure.
        self.assertEqual(upgradecheck.Code.FAILURE, result.code)
        # Check the details for the consumer count.
        self.assertIn('There is at least one resource provider table record '
                      'which misses its root provider id. ', result.details)
        # Run the online data migration as recommended from the check output.
        resource_provider.set_root_provider_ids(self.context, batch_size=50)
        # Run the check again and it should be successful.
        result = self.checks._check_root_provider_ids()
        self.assertEqual(upgradecheck.Code.SUCCESS, result.code)

    def test_all_registered_check_is_runnable(self):
        self.assertEqual(upgradecheck.Code.SUCCESS, self.checks.check())
