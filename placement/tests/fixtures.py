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
from __future__ import absolute_import

import tempfile

import fixtures
from oslo_concurrency.fixture import lockutils as lock_fixture
from oslo_concurrency import lockutils
from oslo_config import cfg

from placement.db.sqlalchemy import migration
from placement import db_api as placement_db
from placement import deploy
from placement.objects import resource_provider


def reset():
    """Call this to allow the placement db fixture to be reconfigured
    in the same process.
    """
    placement_db.placement_context_manager.dispose_pool()
    # TODO(cdent): Future handling in sqlalchemy may allow doing this
    # in a less hacky way.
    placement_db.placement_context_manager._factory._started = False
    # Reset the run once decorator.
    placement_db.configure.reset()


class Database(fixtures.Fixture):
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

    def setUp(self):
        super(Database, self).setUp()
        reset()
        placement_db.configure(self.conf_fixture.conf)
        migration.create_schema()
        resource_provider._TRAITS_SYNCED = False
        resource_provider._RC_CACHE = None
        deploy.update_database()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        reset()
        resource_provider._TRAITS_SYNCED = False
        resource_provider._RC_CACHE = None


class ExternalLockFixture(lock_fixture.LockFixture):
    """Provide a predictable inter-process file-based lock that doesn't
    require oslo.config, by setting its own lock_path.

    This is used to prevent live database test from conflicting with
    one another in a concurrent enviornment.
    """
    def __init__(self, name):
        lock_path = tempfile.gettempdir()
        self.mgr = lockutils.lock(name, external=True, lock_path=lock_path)
