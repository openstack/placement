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

from oslo_config import cfg
from oslo_config import fixture as config_fixture
from oslo_log.fixture import logging_error
from oslotest import output
import testtools

from placement import context
from placement import deploy
from placement.objects import resource_provider
from placement.tests import fixtures
from placement.tests.functional.fixtures import capture
from placement.tests.unit import policy_fixture


CONF = cfg.CONF


class TestCase(testtools.TestCase):
    """A base test case for placement functional tests.

    Sets up minimum configuration for database and policy handling
    and establishes the placement database.
    """

    def setUp(self):
        super(TestCase, self).setUp()

        # Manage required configuration
        conf_fixture = self.useFixture(config_fixture.Config(CONF))
        conf_fixture.config(
            group='placement_database',
            connection='sqlite://',
            sqlite_synchronous=False)
        CONF([], default_config_files=[])

        self.useFixture(policy_fixture.PolicyFixture())

        self.useFixture(capture.Logging())
        self.useFixture(output.CaptureOutput())
        # Filter ignorable warnings during test runs.
        self.useFixture(capture.WarningsFixture())
        self.useFixture(logging_error.get_logging_handle_error_fixture())

        self.placement_db = self.useFixture(fixtures.Database())
        self._reset_database()
        self.context = context.RequestContext()
        # Do database syncs, such as traits sync.
        deploy.update_database()
        self.addCleanup(self._reset_database)

    @staticmethod
    def _reset_database():
        """Reset database sync flags to base state."""
        resource_provider._TRAITS_SYNCED = False
        resource_provider._RC_CACHE = None
