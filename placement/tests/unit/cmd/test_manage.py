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


import sys
from unittest import mock

from oslo_config import cfg
from oslo_config import fixture as config_fixture
from oslotest import output
import testtools

from placement.cmd import manage
from placement import conf
from placement.tests.unit import base


class TestCommandParsers(testtools.TestCase):

    def setUp(self):
        super(TestCommandParsers, self).setUp()
        self.conf = cfg.ConfigOpts()
        conf_fixture = config_fixture.Config(self.conf)
        self.useFixture(conf_fixture)
        conf.register_opts(conf_fixture.conf)
        # Quiet output from argparse (used within oslo_config).
        # If you are debugging, commenting this out might be useful.
        self.output = self.useFixture(
            output.CaptureOutput(do_stderr=True, do_stdout=True))
        # We don't use a database, but we need to set the opt as
        # it's required for a valid config.
        conf_fixture.config(group="placement_database", connection='sqlite://')
        command_opts = manage.setup_commands(conf_fixture)
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
                ('db_stamp', ['db', 'stamp', 'b4ed3a175331']),
                ('db_online_data_migrations',
                 ['db', 'online_data_migrations'])]:
            with mock.patch('placement.cmd.manage.DbCommands.' +
                            command) as mock_command:
                self.conf(args, default_config_files=[])
                self.conf.command.func()
                mock_command.assert_called_once_with()

    def test_non_command(self):
        """A non-existent command should fail."""
        self.assertRaises(SystemExit,
                          self.conf, ['pony'], default_config_files=[])

    def test_empty_command(self):
        """An empty command should create no func."""
        def parse_conf():
            self.conf([], default_config_files=[])

        def get_func():
            return self.conf.command.func

        parse_conf()
        self.assertRaises(cfg.NoSuchOptError, get_func)

    def test_too_many_args(self):
        self.assertRaises(SystemExit,
                          self.conf, ['version', '5'], default_config_files=[])
        self.output.stderr.seek(0)
        if sys.version_info >= (3, 12, 8):
            message = "choose from db"
        else:
            message = "choose from 'db'"
        self.assertIn(message, self.output.stderr.read())

    def test_help_message(self):
        """Test that help output for sub commands shows right commands."""
        self.conf(['db'], default_config_files=[])
        self.conf.command.func()

        self.output.stdout.seek(0)
        self.output.stderr.seek(0)

        self.assertIn('{sync,version,stamp,online_data_migrations}',
                      self.output.stdout.read())


class TestDBCommands(base.ContextTestCase):

    def setUp(self):
        super(TestDBCommands, self).setUp()
        self.conf = cfg.ConfigOpts()
        conf_fixture = config_fixture.Config(self.conf)
        self.useFixture(conf_fixture)
        conf.register_opts(conf_fixture.conf)
        conf_fixture.config(group="placement_database", connection='sqlite://')
        command_opts = manage.setup_commands(conf_fixture)
        conf_fixture.register_cli_opts(command_opts)
        self.output = self.useFixture(
            output.CaptureOutput(do_stderr=True, do_stdout=True))

    def _command_setup(self, max_count=None):
        command_list = ["db", "online_data_migrations"]
        if max_count is not None:
            command_list.extend(["--max-count", str(max_count)])
        self.conf(command_list,
                  project='placement',
                  default_config_files=None)
        return manage.DbCommands(self.conf)

    def test_online_migrations(self):
        # Mock two online migrations
        mock_mig1 = mock.MagicMock(__name__="mock_mig_1")
        mock_mig2 = mock.MagicMock(__name__="mock_mig_2")
        mock_mig1.side_effect = [(10, 10), (0, 0)]
        mock_mig2.side_effect = [(15, 15), (0, 0)]
        mock_migrations = (mock_mig1, mock_mig2)

        with mock.patch('placement.cmd.manage.online_migrations',
                        new=mock_migrations):
            commands = self._command_setup()
            commands.db_online_data_migrations()
            expected = '''\
Running batches of 50 until complete
10 rows matched query mock_mig_1, 10 migrated
15 rows matched query mock_mig_2, 15 migrated
+------------+-------------+-----------+
| Migration  | Total Found | Completed |
+------------+-------------+-----------+
| mock_mig_1 |      10     |     10    |
| mock_mig_2 |      15     |     15    |
+------------+-------------+-----------+
'''
            self.output.stdout.seek(0)
            self.assertEqual(expected, self.output.stdout.read())

    def test_online_migrations_error(self):
        good_remaining = [50]

        def good_migration(context, count):
            found = good_remaining[0]
            done = min(found, count)
            good_remaining[0] -= done
            return found, done

        bad_migration = mock.MagicMock()
        bad_migration.side_effect = Exception("Mock Exception")
        bad_migration.__name__ = 'bad'

        mock_migrations = (bad_migration, good_migration)

        with mock.patch('placement.cmd.manage.online_migrations',
                        new=mock_migrations):

            # bad_migration raises an exception, but it could be because
            # good_migration had not completed yet. We should get 1 in this
            # case, because some work was done, and the command should be
            # reiterated.
            commands = self._command_setup(max_count=50)
            self.assertEqual(1, commands.db_online_data_migrations())

            # When running this for the second time, there's no work left for
            # good_migration to do, but bad_migration still fails - should
            # get 2 this time.
            self.assertEqual(2, commands.db_online_data_migrations())

            # When --max-count is not used, we should get 2 if all possible
            # migrations completed but some raise exceptions
            commands = self._command_setup()
            good_remaining = [125]
            self.assertEqual(2, commands.db_online_data_migrations())

    def test_online_migrations_bad_max(self):
        commands = self._command_setup(max_count=-2)
        self.assertEqual(127, commands.db_online_data_migrations())

        commands = self._command_setup(max_count="a")
        self.assertEqual(127, commands.db_online_data_migrations())

        commands = self._command_setup(max_count=0)
        self.assertEqual(127, commands.db_online_data_migrations())

    def test_online_migrations_no_max(self):
        with mock.patch('placement.cmd.manage.DbCommands.'
                        '_run_online_migration') as rm:
            rm.return_value = {}, False
            commands = self._command_setup()
            self.assertEqual(0, commands.db_online_data_migrations())

    def test_online_migrations_finished(self):
        with mock.patch('placement.cmd.manage.DbCommands.'
                        '_run_online_migration') as rm:
            rm.return_value = {}, False
            commands = self._command_setup(max_count=5)
            self.assertEqual(0, commands.db_online_data_migrations())

    def test_online_migrations_not_finished(self):
        with mock.patch('placement.cmd.manage.DbCommands.'
                        '_run_online_migration') as rm:
            rm.return_value = {'mig': (10, 5)}, False
            commands = self._command_setup(max_count=5)
            self.assertEqual(1, commands.db_online_data_migrations())
