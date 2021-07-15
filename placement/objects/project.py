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

from oslo_db import exception as db_exc
import sqlalchemy as sa

from placement.db.sqlalchemy import models
from placement import db_api
from placement import exception

PROJECT_TBL = models.Project.__table__


@db_api.placement_context_manager.writer
def ensure_incomplete_project(ctx):
    """Ensures that a project record is created for the "incomplete consumer
    project". Returns the internal ID of that record.
    """
    incomplete_id = ctx.config.placement.incomplete_consumer_project_id
    sel = sa.select(PROJECT_TBL.c.id).where(
        PROJECT_TBL.c.external_id == incomplete_id)
    res = ctx.session.execute(sel).fetchone()
    if res:
        return res[0]
    ins = PROJECT_TBL.insert().values(external_id=incomplete_id)
    res = ctx.session.execute(ins)
    return res.inserted_primary_key[0]


@db_api.placement_context_manager.reader
def _get_project_by_external_id(ctx, external_id):
    projects = sa.alias(PROJECT_TBL, name="p")
    sel = sa.select(
        projects.c.id,
        projects.c.external_id,
        projects.c.updated_at,
        projects.c.created_at,
    )
    sel = sel.where(projects.c.external_id == external_id)
    res = ctx.session.execute(sel).fetchone()
    if not res:
        raise exception.ProjectNotFound(external_id=external_id)

    return dict(res._mapping)


class Project(object):

    def __init__(self, context, id=None, external_id=None, updated_at=None,
                 created_at=None):
        self._context = context
        self.id = id
        self.external_id = external_id
        self.updated_at = updated_at
        self.created_at = created_at

    @staticmethod
    def _from_db_object(ctx, target, source):
        target._context = ctx
        target.id = source['id']
        target.external_id = source['external_id']
        target.updated_at = source['updated_at']
        target.created_at = source['created_at']
        return target

    @classmethod
    def get_by_external_id(cls, ctx, external_id):
        res = _get_project_by_external_id(ctx, external_id)
        return cls._from_db_object(ctx, cls(ctx), res)

    def create(self):
        @db_api.placement_context_manager.writer
        def _create_in_db(ctx):
            db_obj = models.Project(external_id=self.external_id)
            try:
                db_obj.save(ctx.session)
            except db_exc.DBDuplicateEntry:
                raise exception.ProjectExists(external_id=self.external_id)
            self._from_db_object(ctx, self, db_obj)
        _create_in_db(self._context)
