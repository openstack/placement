#
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

"""
Tests for database migrations. There are "opportunistic" tests for sqlite in
memory, mysql and postgresql in here, which allows testing against these
databases in a properly configured unit test environment.

For the opportunistic testing you need to set up a db named 'openstack_citest'
with user 'openstack_citest' and password 'openstack_citest' on localhost. This
can be accomplished by running the `test-setup.sh` script in the `tools`
subdirectory. The test will then use that DB and username/password combo to run
the tests.
"""

import contextlib
import functools

from alembic import script
import mock
from oslo_config import cfg
from oslo_config import fixture as config_fixture
from oslo_db import exception as db_exc
from oslo_db.sqlalchemy import enginefacade
from oslo_db.sqlalchemy import provision
from oslo_db.sqlalchemy import test_migrations
from oslo_log import log as logging
from oslotest import base as test_base
import testtools

from placement import conf
from placement.db.sqlalchemy import migration
from placement.db.sqlalchemy import models
from placement import db_api
from placement.tests import fixtures as db_fixture


DB_NAME = 'openstack_citest'
LOG = logging.getLogger(__name__)


@contextlib.contextmanager
def patch_with_engine(engine):
    with mock.patch.object(enginefacade.writer,
                           'get_engine') as patch_engine:
        patch_engine.return_value = engine
        yield


def configure(conf_fixture, db_url):
    """Set database and lockfile configuration. Aggregate configure setting
    here, not done as a base class as the mess of mixins makes that
    inscrutable. So instead we create a nice simple function.
    """
    conf.register_opts(conf_fixture.conf)
    conf_fixture.config(group='placement_database', connection=db_url)
    # We need to retry at least once (and quickly) otherwise the connection
    # test routines in oslo_db do not run, and the exception handling for
    # determining if an opportunistic database is presents gets more
    # complicated.
    conf_fixture.config(group='placement_database', max_retries=1)
    conf_fixture.config(group='placement_database', retry_interval=0)


def generate_url(driver):
    """Make a database URL to be used with the opportunistic tests.

    NOTE(cdent): Because of the way we need to configure the
    [placement_database]/connection, we need to have a predictable database
    URL.
    """
    backend = provision.BackendImpl.impl(driver)
    db_url = backend.create_opportunistic_driver_url()
    if driver == 'sqlite':
        # For sqlite this is all we want since it's in memory.
        return db_url
    # if a dbname is present or the db_url ends with '/' take it off
    db_url = db_url[:db_url.rindex('/')]
    db_url = db_url + '/' + DB_NAME
    return db_url


class WalkVersionsMixin(object):
    def _walk_versions(self, engine=None, alembic_cfg=None):
        """Determine latest version script from the repo, then upgrade from 1
        through to the latest, with no data in the databases. This just checks
        that the schema itself upgrades successfully.
        """

        # Place the database under version control
        with patch_with_engine(engine):
            script_directory = script.ScriptDirectory.from_config(alembic_cfg)
            self.assertIsNone(self.migration_api.version(alembic_cfg))
            versions = [ver for ver in script_directory.walk_revisions()]
            for version in reversed(versions):
                self._migrate_up(engine, alembic_cfg,
                                 version.revision, with_data=True)

    def _migrate_up(self, engine, config, version, with_data=False):
        """Migrate up to a new version of the db.

        We allow for data insertion and post checks at every
        migration version with special _pre_upgrade_### and
        _check_### functions in the main test.
        """
        # NOTE(sdague): try block is here because it's impossible to debug
        # where a failed data migration happens otherwise
        try:
            if with_data:
                data = None
                pre_upgrade = getattr(
                    self, "_pre_upgrade_%s" % version, None)
                if pre_upgrade:
                    data = pre_upgrade(engine)

            self.migration_api.upgrade(version, config=config)
            self.assertEqual(version, self.migration_api.version(config))
            if with_data:
                check = getattr(self, "_check_%s" % version, None)
                if check:
                    check(engine, data)
        except Exception:
            LOG.error("Failed to migrate to version %(version)s on engine "
                      "%(engine)s",
                      {'version': version, 'engine': engine})
            raise


class TestWalkVersions(testtools.TestCase, WalkVersionsMixin):
    def setUp(self):
        super(TestWalkVersions, self).setUp()
        self.migration_api = mock.MagicMock()
        self.engine = mock.MagicMock()
        self.config = mock.MagicMock()
        self.versions = [mock.Mock(revision='2b2'), mock.Mock(revision='1a1')]

    def test_migrate_up(self):
        self.migration_api.version.return_value = 'dsa123'
        self._migrate_up(self.engine, self.config, 'dsa123')
        self.migration_api.upgrade.assert_called_with('dsa123',
                                                      config=self.config)
        self.migration_api.version.assert_called_with(self.config)

    def test_migrate_up_with_data(self):
        test_value = {"a": 1, "b": 2}
        self.migration_api.version.return_value = '141'
        self._pre_upgrade_141 = mock.MagicMock()
        self._pre_upgrade_141.return_value = test_value
        self._check_141 = mock.MagicMock()
        self._migrate_up(self.engine, self.config, '141', True)
        self._pre_upgrade_141.assert_called_with(self.engine)
        self._check_141.assert_called_with(self.engine, test_value)

    @mock.patch.object(script, 'ScriptDirectory')
    @mock.patch.object(WalkVersionsMixin, '_migrate_up')
    def test_walk_versions_all_default(self, _migrate_up, script_directory):
        fc = script_directory.from_config()
        fc.walk_revisions.return_value = self.versions
        self.migration_api.version.return_value = None
        self._walk_versions(self.engine, self.config)
        self.migration_api.version.assert_called_with(self.config)
        upgraded = [mock.call(self.engine, self.config, v.revision,
                    with_data=True) for v in reversed(self.versions)]
        self.assertEqual(self._migrate_up.call_args_list, upgraded)

    @mock.patch.object(script, 'ScriptDirectory')
    @mock.patch.object(WalkVersionsMixin, '_migrate_up')
    def test_walk_versions_all_false(self, _migrate_up, script_directory):
        fc = script_directory.from_config()
        fc.walk_revisions.return_value = self.versions
        self.migration_api.version.return_value = None
        self._walk_versions(self.engine, self.config)
        upgraded = [mock.call(self.engine, self.config, v.revision,
                    with_data=True) for v in reversed(self.versions)]
        self.assertEqual(upgraded, self._migrate_up.call_args_list)


class MigrationCheckersMixin(object):
    def setUp(self):
        self.addCleanup(db_fixture.reset)
        db_url = generate_url(self.DRIVER)
        conf_fixture = self.useFixture(config_fixture.Config(cfg.ConfigOpts()))
        configure(conf_fixture, db_url)
        self.useFixture(db_fixture.ExternalLockFixture('test_mig'))
        db_fixture.reset()
        db_api.configure(conf_fixture.conf)
        try:
            self.engine = db_api.get_placement_engine()
        except (db_exc.DBNonExistentDatabase, db_exc.DBConnectionError):
            self.skipTest('%s not available' % self.DRIVER)
        self.config = migration._alembic_config()
        self.migration_api = migration
        super(MigrationCheckersMixin, self).setUp()
        # The following is done here instead of in the fixture because it is
        # much slower for the RAM-based DB tests, and isn't needed. But it is
        # needed for the migration tests, so we do the complete drop/rebuild
        # here.
        backend = provision.Backend(self.engine.name, self.engine.url)
        self.addCleanup(functools.partial(
                backend.drop_all_objects, self.engine))
        # This is required to prevent the global opportunistic db settings
        # leaking into other tests.
        self.addCleanup(self.engine.dispose)

    def test_walk_versions(self):
        self._walk_versions(self.engine, self.config)

#    # Leaving this here as a sort of template for when we do migration tests.
#    def _check_fb3f10dd262e(self, engine, data):
#        nodes_tbl = db_utils.get_table(engine, 'nodes')
#        col_names = [column.name for column in nodes_tbl.c]
#        self.assertIn('fault', col_names)
#        self.assertIsInstance(nodes_tbl.c.fault.type,
#                              sqlalchemy.types.String)

    def test_upgrade_and_version(self):
        self.migration_api.upgrade('head')
        self.assertIsNotNone(self.migration_api.version())

    def test_upgrade_twice(self):
        # Start with the empty version
        self.migration_api.upgrade('base')
        v1 = self.migration_api.version()
        # Now upgrade to head
        self.migration_api.upgrade('head')
        v2 = self.migration_api.version()
        self.assertNotEqual(v1, v2)


class TestMigrationsSQLite(MigrationCheckersMixin,
                           WalkVersionsMixin,
                           test_base.BaseTestCase):
    DRIVER = "sqlite"


class TestMigrationsMySQL(MigrationCheckersMixin,
                          WalkVersionsMixin,
                          test_base.BaseTestCase):
    DRIVER = 'mysql'


class TestMigrationsPostgresql(MigrationCheckersMixin,
                               WalkVersionsMixin,
                               test_base.BaseTestCase):
    DRIVER = 'postgresql'


class ModelsMigrationSyncMixin(object):
    def setUp(self):
        url = generate_url(self.DRIVER)
        conf_fixture = self.useFixture(config_fixture.Config(cfg.ConfigOpts()))
        configure(conf_fixture, url)
        self.useFixture(db_fixture.ExternalLockFixture('test_mig'))
        db_fixture.reset()
        db_api.configure(conf_fixture.conf)
        super(ModelsMigrationSyncMixin, self).setUp()
        # This is required to prevent the global opportunistic db settings
        # leaking into other tests.
        self.addCleanup(db_fixture.reset)

    def get_metadata(self):
        return models.BASE.metadata

    def get_engine(self):
        try:
            return db_api.get_placement_engine()
        except (db_exc.DBNonExistentDatabase, db_exc.DBConnectionError):
            self.skipTest('%s not available' % self.DRIVER)

    def db_sync(self, engine):
        migration.upgrade('head')


class ModelsMigrationsSyncSqlite(ModelsMigrationSyncMixin,
                                 test_migrations.ModelsMigrationsSync,
                                 test_base.BaseTestCase):
    DRIVER = 'sqlite'


class ModelsMigrationsSyncMysql(ModelsMigrationSyncMixin,
                                test_migrations.ModelsMigrationsSync,
                                test_base.BaseTestCase):
    DRIVER = 'mysql'


class ModelsMigrationsSyncPostgresql(ModelsMigrationSyncMixin,
                                test_migrations.ModelsMigrationsSync,
                                test_base.BaseTestCase):
    DRIVER = 'postgresql'
