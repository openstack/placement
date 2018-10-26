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

import functools
import six
import sys

from oslo_config import cfg
import pbr.version

from placement import conf
from placement.db.sqlalchemy import migration
from placement import db_api
from placement.i18n import _

version_info = pbr.version.VersionInfo('openstack-placement')


class DbCommands(object):
    def __init__(self, config):
        self.config = config

    def db_sync(self):
        # Let exceptions raise for now, they will go to stderr.
        migration.upgrade('head')
        return 0

    def db_version(self):
        print(migration.version())
        return 0

    def db_stamp(self):
        migration.stamp(self.config.command.version)
        return 0


def add_db_command_parsers(subparsers, config):
    command_object = DbCommands(config)

    # If we set False here, we avoid having an exit during the parse
    # args part of CONF processing and we can thus print out meaningful
    # help text.
    subparsers.required = False
    parser = subparsers.add_parser('db')
    # Avoid https://bugs.python.org/issue9351 with cpython < 2.7.9
    if not six.PY2:
        parser.set_defaults(func=parser.print_help)
    db_parser = parser.add_subparsers(description='database commands')

    help = _('Sync the datatabse to the current version.')
    sync_parser = db_parser.add_parser('sync', help=help, description=help)
    sync_parser.set_defaults(func=command_object.db_sync)

    help = _('Report the current database version.')
    version_parser = db_parser.add_parser(
        'version', help=help, description=help)
    version_parser.set_defaults(func=command_object.db_version)

    help = _('Stamp the revision table with the given version.')
    stamp_parser = db_parser.add_parser('stamp', help=help, description=help)
    stamp_parser.add_argument('version', help=_('the version to stamp'))
    stamp_parser.set_defaults(func=command_object.db_stamp)


def setup_commands(config):
    # This is a separate method because it facilitates unit testing.
    # Use an additional SubCommandOpt and parser for each new sub command.
    add_db_cmd_parsers = functools.partial(
        add_db_command_parsers, config=config)
    command_opt = cfg.SubCommandOpt(
        'db', dest='command', title='Command', help=_('Available DB commands'),
        handler=add_db_cmd_parsers)
    return [command_opt]


def main():
    config = cfg.ConfigOpts()
    conf.register_opts(config)
    command_opts = setup_commands(config)
    config.register_cli_opts(command_opts)
    config(sys.argv[1:], project='placement',
           version=version_info.version_string(),
           default_config_files=None)
    db_api.configure(config)

    try:
        func = config.command.func
        return_code = func()
        # If return_code ends up None we assume 0.
        sys.exit(return_code or 0)
    except cfg.NoSuchOptError:
        config.print_help()
        sys.exit(1)
