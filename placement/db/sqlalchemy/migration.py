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

from migrate import exceptions as versioning_exceptions
from migrate.versioning import api as versioning_api
from migrate.versioning.repository import Repository
from oslo_log import log as logging
import sqlalchemy

from placement import db_api as placement_db

INIT_VERSION = 0
_REPOSITORY = None

LOG = logging.getLogger(__name__)


def get_engine(context=None):
    return placement_db.get_placement_engine()


def db_sync(version=None, context=None):
    if version is not None:
        # Let ValueError raise
        version = int(version)

    current_version = db_version(context=context)
    repository = _find_migrate_repo()
    if version is None or version > current_version:
        return versioning_api.upgrade(get_engine(context=context),
                repository, version)
    else:
        return versioning_api.downgrade(get_engine(context=context),
                repository, version)


def db_version(context=None):
    repository = _find_migrate_repo()
    try:
        return versioning_api.db_version(get_engine(context=context),
                                         repository)
    except versioning_exceptions.DatabaseNotControlledError as exc:
        meta = sqlalchemy.MetaData()
        engine = get_engine(context=context)
        meta.reflect(bind=engine)
        tables = meta.tables
        if len(tables) == 0:
            db_version_control(INIT_VERSION, context=context)
            return versioning_api.db_version(
                        get_engine(context=context), repository)
        else:
            LOG.exception(exc)
            raise exc


def db_initial_version():
    return INIT_VERSION


def db_version_control(version=None, context=None):
    repository = _find_migrate_repo()
    versioning_api.version_control(get_engine(context=context),
                                   repository,
                                   version)
    return version


def _find_migrate_repo():
    """Get the path for the migrate repository."""
    global _REPOSITORY
    rel_path = os.path.join('api_migrations', 'migrate_repo')
    path = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                        rel_path)
    assert os.path.exists(path)
    if _REPOSITORY is None:
        _REPOSITORY = Repository(path)
    return _REPOSITORY
