# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
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

"""Fixtures for Placement tests."""


from oslo_config import cfg
from oslo_db.sqlalchemy import test_fixtures

from placement.db.sqlalchemy import migration
from placement import db_api as placement_db
from placement import deploy
from placement.objects import resource_class
from placement.objects import trait


class Database(test_fixtures.GeneratesSchema, test_fixtures.AdHocDbFixture):
    def __init__(self, conf_fixture, set_config=False):
        """Create a database fixture."""
        super(Database, self).__init__()
        if set_config:
            try:
                conf_fixture.register_opt(
                    cfg.StrOpt('connection'), group='placement_database')
            except cfg.DuplicateOptError:
                # already registered
                pass
            conf_fixture.config(connection='sqlite://',
                                group='placement_database')
        self.conf_fixture = conf_fixture
        self.get_engine = placement_db.get_placement_engine
        placement_db.configure(self.conf_fixture.conf)

    def get_enginefacade(self):
        return placement_db.placement_context_manager

    def generate_schema_create_all(self, engine):
        # note: at this point in oslo_db's fixtures, the incoming
        # Engine has **not** been associated with the global
        # context manager yet.
        migration.create_schema(engine)

        # so, to work around that placement's setup code really wants to
        # use the enginefacade, we will patch the engine into it early.
        # oslo_db is going to patch it anyway later.  So the bug in oslo.db
        # is that code these days really wants the facade to be set up fully
        # when it's time to create the database.  When oslo_db's fixtures
        # were written, enginefacade was not in use yet so it was not
        # anticipated that everyone would be doing things this way
        _reset_facade = placement_db.placement_context_manager.patch_engine(
            engine)
        self.addCleanup(_reset_facade)

        # Make sure db flags are correct at both the start and finish
        # of the test.
        self.addCleanup(self.cleanup)
        self.cleanup()

        # Sync traits and resource classes.
        deploy.update_database(self.conf_fixture.conf)

    def cleanup(self):
        trait._TRAITS_SYNCED = False
        resource_class._RESOURCE_CLASSES_SYNCED = False
