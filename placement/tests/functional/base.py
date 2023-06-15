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

from placement import conf
from placement import context
from placement.tests import fixtures
from placement.tests.functional.fixtures import capture
from placement.tests.unit import policy_fixture


class TestCase(testtools.TestCase):
    """A base test case for placement functional tests.

    Sets up minimum configuration for database and policy handling
    and establishes the placement database.
    """

    USES_DB = True

    def setUp(self):
        super(TestCase, self).setUp()

        # Manage required configuration
        self.conf_fixture = self.useFixture(
            config_fixture.Config(cfg.ConfigOpts()))
        conf.register_opts(self.conf_fixture.conf)
        if self.USES_DB:
            self.placement_db = self.useFixture(fixtures.Database(
                self.conf_fixture, set_config=True))
        else:
            self.conf_fixture.config(
                connection='sqlite://',
                group='placement_database',
            )
        self.conf_fixture.conf([], default_config_files=[])

        self.useFixture(policy_fixture.PolicyFixture(self.conf_fixture))

        self.useFixture(capture.Logging())
        self.useFixture(output.CaptureOutput())
        # Filter ignorable warnings during test runs.
        self.useFixture(capture.WarningsFixture())
        self.useFixture(logging_error.get_logging_handle_error_fixture())

        self.context = context.RequestContext()
        self.context.config = self.conf_fixture.conf


class NoDBTestCase(TestCase):
    USES_DB = False
