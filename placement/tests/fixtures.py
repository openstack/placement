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

"""Fixtures for Nova tests."""
from __future__ import absolute_import


import fixtures
from oslo_config import cfg

from placement.db import migration
from placement import db_api as placement_db


CONF = cfg.CONF
DB_SCHEMA = {'placement': ""}
SESSION_CONFIGURED = False


class Database(fixtures.Fixture):
    def __init__(self, database='placement', connection=None):
        """Create a database fixture.

        :param database: The type of database: 'placement'
        :param connection: The connection string to use
        """
        super(Database, self).__init__()
        # NOTE(pkholkin): oslo_db.enginefacade is configured in tests the same
        # way as it is done for any other service that uses db
        global SESSION_CONFIGURED
        if not SESSION_CONFIGURED:
            placement_db.configure(CONF)
            SESSION_CONFIGURED = True
        self.database = database
        self.get_engine = placement_db.get_placement_engine

    def _cache_schema(self):
        global DB_SCHEMA
        if not DB_SCHEMA[self.database]:
            engine = self.get_engine()
            conn = engine.connect()
            migration.db_sync(database=self.database)
            DB_SCHEMA[self.database] = "".join(line for line
                                               in conn.connection.iterdump())
            engine.dispose()

    def cleanup(self):
        engine = self.get_engine()
        engine.dispose()

    def reset(self):
        self._cache_schema()
        engine = self.get_engine()
        engine.dispose()
        conn = engine.connect()
        conn.connection.executescript(DB_SCHEMA[self.database])

    def setUp(self):
        super(Database, self).setUp()
        self.reset()
        self.addCleanup(self.cleanup)
