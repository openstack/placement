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

import os

import alembic
from alembic import config as alembic_config
from alembic import migration as alembic_migration

from placement.db.sqlalchemy import models
from placement import db_api as placement_db


def get_engine():
    return placement_db.get_placement_engine()


def _alembic_config():
    path = os.path.join(os.path.dirname(__file__), "alembic.ini")
    config = alembic_config.Config(path)
    return config


def create_schema(engine=None):
    """Create schema from models, without a migration."""
    base = models.BASE

    if engine is None:
        engine = get_engine()
    base.metadata.create_all(engine)


def version(config=None, engine=None):
    """Current database version.

    :returns: Database version
    :rtype: string
    """
    if engine is None:
        engine = get_engine()
    with engine.connect() as conn:
        context = alembic_migration.MigrationContext.configure(conn)
        return context.get_current_revision()


def upgrade(revision, config=None):
    """Used for upgrading database.

    :param version: Desired database version
    :type version: string
    """
    revision = revision or "head"
    config = config or _alembic_config()
    alembic.command.upgrade(config, revision)


def stamp(version, config=None):
    """Used for stamp the database version.

    :param version: Database version to stamp
    :type version: string
    """
    config = config or _alembic_config()
    alembic.command.stamp(config, version)
