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
from oslo_config import cfg
from oslo_config import fixture as config_fixture
from oslotest import output
import six
import testtools

from placement.cmd import manage


class TestCommandParsers(testtools.TestCase):

    def setUp(self):
        super(TestCommandParsers, self).setUp()
        self.conf = cfg.CONF
        conf_fixture = config_fixture.Config(self.conf)
        self.useFixture(conf_fixture)
        # Quiet output from argparse (used within oslo_config).
        # If you are debugging, commenting this out might be useful.
        self.useFixture(output.CaptureOutput(do_stderr=True))
        # We don't use a database, but we need to set the opt as
        # it's required for a valid config.
        conf_fixture.config(group="placement_database", connection='sqlite://')
        command_opts = manage.setup_commands()
        # Command line opts must be registered on the conf_fixture, otherwise
        # they carry over globally.
        conf_fixture.register_cli_opts(command_opts)

    def test_commands_associated(self):
        """Test that commands get parsed as desired.

        This leaves out --version, which is built into oslo.config's handling.
        """
        for command, args in [
                ('db_version', ['db', 'version']),
                ('db_sync', ['db', 'sync']),
            ]:
            with mock.patch('placement.cmd.manage.DbCommands.'
                    + command) as mock_command:
                self.conf(args, default_config_files=[])
                self.conf.command.func()
                mock_command.assert_called_once_with()

    def test_non_command(self):
        """A non-existent command should fail."""
        self.assertRaises(SystemExit,
                          self.conf, ['pony'], default_config_files=[])

    def test_empty_command(self):
        """An empty command should create no func."""
        # Python 2.7 and 3.x behave differently here, but the result is
        # satisfactory. Both result in some help output, but the Python 3
        # help is better.
        def parse_conf():
            self.conf([], default_config_files=[])

        def get_func():
            return self.conf.command.func

        if six.PY2:
            self.assertRaises(SystemExit, parse_conf)
        else:
            parse_conf()
            self.assertRaises(cfg.NoSuchOptError, get_func)

    def test_too_many_args(self):
        self.assertRaises(SystemExit,
                          self.conf, ['version', '5'], default_config_files=[])
