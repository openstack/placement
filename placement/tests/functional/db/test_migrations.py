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

from unittest import mock

from alembic import script
from oslo_db.sqlalchemy import test_fixtures
from oslo_db.sqlalchemy import test_migrations
from oslo_db.sqlalchemy import utils as db_utils
from oslo_log import log as logging
from oslo_utils.fixture import uuidsentinel as uuids
from sqlalchemy import inspect

from placement.db.sqlalchemy import migration
from placement.db.sqlalchemy import models
from placement import db_api
from placement.tests.functional import base


LOG = logging.getLogger(__name__)


class WalkVersionsMixin(object):
    def _walk_versions(self):
        """Determine latest version script from the repo, then upgrade from 1
        through to the latest, with no data in the databases. This just checks
        that the schema itself upgrades successfully.
        """

        # Place the database under version control
        script_directory = script.ScriptDirectory.from_config(self.config)
        self.assertIsNone(self.migration_api.version(self.config))
        versions = [ver for ver in script_directory.walk_revisions()]
        for version in reversed(versions):
            self._migrate_up(version.revision, with_data=True)

    def _migrate_up(self, version, with_data=False):
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
                    data = pre_upgrade(self.engine)

            self.migration_api.upgrade(version, config=self.config)
            self.assertEqual(version, self.migration_api.version(self.config))
            if with_data:
                check = getattr(self, "_check_%s" % version, None)
                if check:
                    check(self.engine, data)
        except Exception:
            LOG.error("Failed to migrate to version %(version)s on engine "
                      "%(engine)s",
                      {'version': version, 'engine': self.engine})
            raise


class TestWalkVersions(base.NoDBTestCase, WalkVersionsMixin):
    def setUp(self):
        super(TestWalkVersions, self).setUp()
        self.migration_api = mock.MagicMock()
        self.engine = mock.MagicMock()
        self.config = mock.MagicMock()
        self.versions = [mock.Mock(revision='2b2'), mock.Mock(revision='1a1')]

    def test_migrate_up(self):
        self.migration_api.version.return_value = 'dsa123'
        self._migrate_up('dsa123')
        self.migration_api.upgrade.assert_called_with('dsa123',
                                                      config=self.config)
        self.migration_api.version.assert_called_with(self.config)

    def test_migrate_up_with_data(self):
        test_value = {"a": 1, "b": 2}
        self.migration_api.version.return_value = '141'
        self._pre_upgrade_141 = mock.MagicMock()
        self._pre_upgrade_141.return_value = test_value
        self._check_141 = mock.MagicMock()
        self._migrate_up('141', True)
        self._pre_upgrade_141.assert_called_with(self.engine)
        self._check_141.assert_called_with(self.engine, test_value)

    @mock.patch.object(script, 'ScriptDirectory')
    @mock.patch.object(WalkVersionsMixin, '_migrate_up')
    def test_walk_versions_all_default(self, _migrate_up, script_directory):
        fc = script_directory.from_config()
        fc.walk_revisions.return_value = self.versions
        self.migration_api.version.return_value = None
        self._walk_versions()
        self.migration_api.version.assert_called_with(self.config)
        upgraded = [mock.call(v.revision,
                    with_data=True) for v in reversed(self.versions)]
        self.assertEqual(self._migrate_up.call_args_list, upgraded)

    @mock.patch.object(script, 'ScriptDirectory')
    @mock.patch.object(WalkVersionsMixin, '_migrate_up')
    def test_walk_versions_all_false(self, _migrate_up, script_directory):
        fc = script_directory.from_config()
        fc.walk_revisions.return_value = self.versions
        self.migration_api.version.return_value = None
        self._walk_versions()
        upgraded = [mock.call(v.revision,
                    with_data=True) for v in reversed(self.versions)]
        self.assertEqual(upgraded, self._migrate_up.call_args_list)


class MigrationCheckersMixin(object):
    def setUp(self):
        super(MigrationCheckersMixin, self).setUp()
        self.engine = db_api.placement_context_manager.writer.get_engine()
        self.config = migration._alembic_config()
        self.migration_api = migration

    def test_walk_versions(self):
        self._walk_versions()

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

    def test_block_on_null_root_provider_id(self):
        """Upgrades the schema to b4ed3a175331 (initial), injects a resource
        provider with no root provider and then tries to upgrade to head which
        should fail on the 611cd6dffd7b blocker migration.
        """
        # Upgrade to populate the schema.
        self.migration_api.upgrade('b4ed3a175331')
        # Now insert a resource provider with no root.
        rps = db_utils.get_table(self.engine, 'resource_providers')
        ins_stmt = rps.insert().values(
            name='fake-rp-name',
            uuid=uuids.rp_uuid,
        )
        with self.engine.connect() as conn, conn.begin():
            rp_id = conn.execute(ins_stmt).inserted_primary_key[0]
        # Now run the blocker migration and it should raise an error.
        ex = self.assertRaises(  # noqa H202
            Exception, self.migration_api.upgrade, '611cd6dffd7b')
        # Make sure it's the error we expect.
        self.assertIn('There is at least one resource provider table '
                      'record which is missing its root provider id.',
                      str(ex))
        # Now update the resource provider with a root_provider_id.
        update_stmt = rps.update().values(
            root_provider_id=rp_id,
        ).where(rps.c.id == rp_id)
        with self.engine.connect() as conn, conn.begin():
            conn.execute(update_stmt)
        # Re-run the upgrade and it should be OK.
        self.migration_api.upgrade('611cd6dffd7b')

    def test_block_on_missing_consumer(self):
        """Upgrades the schema to b4ed3a175331 (initial), injects an allocation
        without a corresponding consumer record and then tries to upgrade to
        head which should fail on the b5c396305c25 blocker migration.
        """
        # Upgrade to populate the schema.
        self.migration_api.upgrade('b4ed3a175331')
        # Now insert a resource provider to build off
        rps = db_utils.get_table(self.engine, 'resource_providers')
        ins_stmt = rps.insert().values(
            name='fake-rp-name',
            uuid=uuids.rp_uuid,
            root_provider_id=1,
        )
        with self.engine.connect() as conn, conn.begin():
            rp_id = conn.execute(ins_stmt).inserted_primary_key[0]
        # Now insert an allocation
        allocations = db_utils.get_table(self.engine, 'allocations')
        ins_stmt = allocations.insert().values(
            resource_provider_id=rp_id,
            resource_class_id=1,
            used=5,
            consumer_id=uuids.consumer1,
        )
        with self.engine.connect() as conn, conn.begin():
            conn.execute(ins_stmt).inserted_primary_key[0]
        # Now run the blocker migration and it should raise an error.
        ex = self.assertRaises(  # noqa H202
            Exception, self.migration_api.upgrade, 'b5c396305c25')
        # Make sure it's the error we expect.
        self.assertIn('There is at least one allocation record which is '
                      'missing a consumer record.',
                      str(ex))
        # Add a (faked) consumer record and try again
        consumers = db_utils.get_table(self.engine, 'consumers')
        ins_stmt = consumers.insert().values(
            uuid=uuids.consumer1,
            project_id=1,
            user_id=1,
        )
        with self.engine.connect() as conn, conn.begin():
            conn.execute(ins_stmt).inserted_primary_key[0]
        self.migration_api.upgrade('b5c396305c25')

    def test_consumer_types_422ece571366(self):
        # Upgrade to populate the schema.
        self.migration_api.upgrade('422ece571366')
        insp = inspect(self.engine)
        # Test creation of consumer_types table
        con = db_utils.get_table(self.engine, 'consumer_types')
        col_names = [column.name for column in con.c]
        self.assertIn('created_at', col_names)
        self.assertIn('updated_at', col_names)
        self.assertIn('id', col_names)
        self.assertIn('name', col_names)
        # check constraints
        pkey = insp.get_pk_constraint("consumer_types")
        self.assertEqual(['id'], pkey['constrained_columns'])
        ukey = insp.get_unique_constraints("consumer_types")
        self.assertEqual('uniq_consumer_types0name', ukey[0]['name'])

    def test_consumer_type_id_column_422ece571366(self):
        # Upgrade to populate the schema.
        self.migration_api.upgrade('422ece571366')
        insp = inspect(self.engine)
        # Test creation of consumer_types table
        consumers = db_utils.get_table(self.engine, 'consumers')
        col_names = [column.name for column in consumers.c]
        self.assertIn('consumer_type_id', col_names)
        # Check index and constraints
        fkey = insp.get_foreign_keys("consumers")
        self.assertEqual(['consumer_type_id'], fkey[0]['constrained_columns'])
        ind = insp.get_indexes('consumers')
        names = [r['name'] for r in ind]
        self.assertIn('consumers_consumer_type_id_idx', names)


class PlacementOpportunisticFixture(object):
    def get_enginefacade(self):
        return db_api.placement_context_manager


class SQLiteOpportunisticFixture(
        PlacementOpportunisticFixture, test_fixtures.OpportunisticDbFixture):
    pass


class MySQLOpportunisticFixture(
        PlacementOpportunisticFixture,
        test_fixtures.MySQLOpportunisticFixture):
    pass


class PostgresqlOpportunisticFixture(
        PlacementOpportunisticFixture,
        test_fixtures.PostgresqlOpportunisticFixture):
    pass


class TestMigrationsSQLite(MigrationCheckersMixin,
                           WalkVersionsMixin,
                           test_fixtures.OpportunisticDBTestMixin,
                           base.NoDBTestCase):
    FIXTURE = SQLiteOpportunisticFixture


class TestMigrationsMySQL(MigrationCheckersMixin,
                          WalkVersionsMixin,
                          test_fixtures.OpportunisticDBTestMixin,
                          base.NoDBTestCase):
    FIXTURE = MySQLOpportunisticFixture


class TestMigrationsPostgresql(MigrationCheckersMixin,
                               WalkVersionsMixin,
                               test_fixtures.OpportunisticDBTestMixin,
                               base.NoDBTestCase):
    FIXTURE = PostgresqlOpportunisticFixture


class _TestModelsMigrations(test_migrations.ModelsMigrationsSync):
    def get_metadata(self):
        return models.BASE.metadata

    def get_engine(self):
        return db_api.get_placement_engine()

    def db_sync(self, engine):
        migration.upgrade('head')


class ModelsMigrationsSyncSqlite(_TestModelsMigrations,
                                 test_fixtures.OpportunisticDBTestMixin,
                                 base.NoDBTestCase):
    FIXTURE = SQLiteOpportunisticFixture


class ModelsMigrationsSyncMysql(_TestModelsMigrations,
                                test_fixtures.OpportunisticDBTestMixin,
                                base.NoDBTestCase):
    FIXTURE = MySQLOpportunisticFixture


class ModelsMigrationsSyncPostgresql(_TestModelsMigrations,
                                     test_fixtures.OpportunisticDBTestMixin,
                                     base.NoDBTestCase):
    FIXTURE = PostgresqlOpportunisticFixture
