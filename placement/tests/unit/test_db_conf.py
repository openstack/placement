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

from oslo_config import cfg
from oslo_config import fixture as config_fixture

from placement import conf


class TestPlacementDBConf(testtools.TestCase):
    """Test cases for Placement DB Setup."""

    def setUp(self):
        super(TestPlacementDBConf, self).setUp()
        config = cfg.ConfigOpts()
        self.conf_fixture = self.useFixture(config_fixture.Config(config))
        conf.register_opts(config)

    def test_missing_config_raises(self):
        """Not setting [placement_database]/connection is an error."""
        exc = self.assertRaises(
            cfg.RequiredOptError, self.conf_fixture.conf,
            [], default_config_files=[])
        self.assertIn(
            'option connection in group [placement_database]',
            str(exc))
