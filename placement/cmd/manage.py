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

import collections
import functools
import prettytable
import sys

from oslo_config import cfg
from oslo_log import log as logging
import pbr.version

from placement import conf
from placement import context
from placement.db.sqlalchemy import migration
from placement import db_api
from placement.objects import consumer as consumer_obj
from placement.objects import resource_provider as rp_obj

version_info = pbr.version.VersionInfo('openstack-placement')
LOG = logging.getLogger(__name__)

online_migrations = (
    # These functions are called with a DB context and a count, which is the
    # maximum batch size requested by the user. They must be idempotent.
    # At most $count records should be migrated. The function must return a
    # tuple of (found, done). The found value indicates how many
    # unmigrated/candidate records existed in the database prior to the
    # migration (either total, or up to the $count limit provided), and a
    # nonzero found value may tell the user that there is still work to do.
    # The done value indicates whether or not any records were actually
    # migrated by the function. Thus if both (found, done) are nonzero, work
    # was done and some work remains. If found is nonzero and done is zero,
    # some records are not migratable, but all migrations that can complete
    # have finished.

    # Added in Stein
    rp_obj.set_root_provider_ids,
    # Added in Stein (copied from migration added to Nova in Rocky)
    consumer_obj.create_incomplete_consumers,
)


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

    def db_online_data_migrations(self):
        """Processes online data migration.

        :returns: 0 if no (further) updates are possible, 1 if the
                  ``--max-count`` option was used and some updates were
                  completed successfully (even if others generated errors),
                  2 if some updates generated errors and no other migrations
                  were able to take effect in the last batch attempted, or
                  127 if invalid input is provided.
        """
        max_count = self.config.command.max_count
        if max_count is not None:
            try:
                max_count = int(max_count)
            except ValueError:
                max_count = -1
            if max_count < 1:
                print('Must supply a positive value for max_count')
                return 127
            limited = True
        else:
            max_count = 50
            limited = False
            print('Running batches of %i until complete' % max_count)

        ran = None
        migration_info = collections.OrderedDict()
        exceptions = False
        while ran is None or ran != 0:
            migrations, exceptions = self._run_online_migration(max_count)
            ran = 0
            # For each batch of migration method results, build the cumulative
            # set of results.
            for name in migrations:
                migration_info.setdefault(name, (0, 0))
                migration_info[name] = (
                    migration_info[name][0] + migrations[name][0],
                    migration_info[name][1] + migrations[name][1],
                )
                ran += migrations[name][1]
            if limited:
                break

        t = prettytable.PrettyTable(
            ['Migration', 'Total Found', 'Completed'])
        for name, info in migration_info.items():
            t.add_row([name, info[0], info[1]])
        print(t)

        # NOTE(tetsuro): In "limited" case, if some update has been "ran",
        # exceptions are not considered fatal because work may still remain
        # to be done, and that work may resolve dependencies for the failing
        # migrations.
        if exceptions and not (limited and ran):
            print("Some migrations failed unexpectedly. Check log for "
                  "details.")
            return 2

        # TODO(mriedem): Potentially add another return code for
        # "there are more migrations, but not completable right now"
        return ran and 1 or 0

    def _run_online_migration(self, max_count):
        ctxt = context.RequestContext(config=self.config)
        ran = 0
        exceptions = False
        migrations = collections.OrderedDict()
        for migration_meth in online_migrations:
            count = max_count - ran
            try:
                found, done = migration_meth(ctxt, count)
            except Exception:
                msg = ("Error attempting to run %(method)s" % dict(
                    method=migration_meth))
                print(msg)
                LOG.exception(msg)
                exceptions = True
                found = done = 0

            name = migration_meth.__name__
            if found:
                print('%(total)i rows matched query %(meth)s, %(done)i '
                      'migrated' % {'total': found,
                                    'meth': name,
                                    'done': done})
            # This is the per-migration method result for this batch, and
            # _run_online_migration will either continue on to the next
            # migration, or stop if up to this point we've processed max_count
            # of records across all migration methods.
            migrations[name] = found, done
            ran += done
            if ran >= max_count:
                break
        return migrations, exceptions


def add_db_command_parsers(subparsers, config):
    command_object = DbCommands(config)

    # If we set False here, we avoid having an exit during the parse
    # args part of CONF processing and we can thus print out meaningful
    # help text.
    subparsers.required = False
    parser = subparsers.add_parser('db')
    # Avoid https://bugs.python.org/issue9351 with cpython < 2.7.9
    parser.set_defaults(func=parser.print_help)
    db_parser = parser.add_subparsers(description='database commands')

    help = 'Sync the database to the current version.'
    sync_parser = db_parser.add_parser('sync', help=help, description=help)
    sync_parser.set_defaults(func=command_object.db_sync)

    help = 'Report the current database version.'
    version_parser = db_parser.add_parser(
        'version', help=help, description=help)
    version_parser.set_defaults(func=command_object.db_version)

    help = 'Stamp the revision table with the given version.'
    stamp_parser = db_parser.add_parser('stamp', help=help, description=help)
    stamp_parser.add_argument('version', help='the version to stamp')
    stamp_parser.set_defaults(func=command_object.db_stamp)

    help = 'Run the online data migrations.'
    online_dm_parser = db_parser.add_parser(
        'online_data_migrations', help=help, description=help)
    online_dm_parser.add_argument(
        '--max-count', metavar='<number>',
        help='Maximum number of objects to consider')
    online_dm_parser.set_defaults(
        func=command_object.db_online_data_migrations)


def setup_commands(config):
    # This is a separate method because it facilitates unit testing.
    # Use an additional SubCommandOpt and parser for each new sub command.
    add_db_cmd_parsers = functools.partial(
        add_db_command_parsers, config=config)
    command_opt = cfg.SubCommandOpt(
        'db', dest='command', title='Command', help='Available DB commands',
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
