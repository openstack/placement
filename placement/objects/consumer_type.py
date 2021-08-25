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

CONSUMER_TYPE_TBL = models.ConsumerType.__table__
_CONSUMER_TYPES_LOCK = 'consumer_types_sync'
_CONSUMER_TYPES_SYNCED = False
NULL_CONSUMER_TYPE_ALIAS = 'unknown'


@db_api.placement_context_manager.reader
def _get_consumer_type_by_id(ctx, id):
    # The SQL for this looks like the following:
    # SELECT
    #   c.id, c.name,
    #   c.updated_at, c.created_at
    # FROM consumer_types c
    # WHERE c.id = $id
    consumer_types = sa.alias(CONSUMER_TYPE_TBL, name="c")
    cols = [
        consumer_types.c.id,
        consumer_types.c.name,
        consumer_types.c.updated_at,
        consumer_types.c.created_at
    ]
    sel = sa.select(cols).where(consumer_types.c.id == id)
    res = ctx.session.execute(sel).fetchone()
    if not res:
        raise exception.ConsumerTypeNotFound(name=id)

    return dict(res)


@db_api.placement_context_manager.reader
def _get_consumer_type_by_name(ctx, name):
    # The SQL for this looks like the following:
    # SELECT
    #   c.id, c.name,
    #   c.updated_at, c.created_at
    # FROM consumer_types c
    # WHERE c.name = $name
    consumer_types = sa.alias(CONSUMER_TYPE_TBL, name="c")
    cols = [
        consumer_types.c.id,
        consumer_types.c.name,
        consumer_types.c.updated_at,
        consumer_types.c.created_at
    ]
    sel = sa.select(cols).where(consumer_types.c.name == name)
    res = ctx.session.execute(sel).fetchone()
    if not res:
        raise exception.ConsumerTypeNotFound(name=name)

    return dict(res)


@db_api.placement_context_manager.writer
def _create_in_db(ctx, name):
    db_obj = models.ConsumerType(name=name)
    try:
        db_obj.save(ctx.session)
        return db_obj
    except db_exc.DBDuplicateEntry:
        raise exception.ConsumerTypeExists(name=name)


class ConsumerType(object):

    def __init__(self, context, id=None, name=None,
                 updated_at=None, created_at=None):
        self._context = context
        self.id = id
        self.name = name
        self.updated_at = updated_at
        self.created_at = created_at

    @staticmethod
    def _from_db_object(ctx, target, source):
        target.id = source['id']
        target.name = source['name']
        target.created_at = source['created_at']
        target.updated_at = source['updated_at']

        target._context = ctx
        return target

    @classmethod
    def get_by_id(cls, ctx, id):
        res = _get_consumer_type_by_id(ctx, id)
        return cls._from_db_object(ctx, cls(ctx), res)

    @classmethod
    def get_by_name(cls, ctx, name):
        res = _get_consumer_type_by_name(ctx, name)
        return cls._from_db_object(ctx, cls(ctx), res)

    def create(self):
        ct = _create_in_db(self._context, self.name)
        return self._from_db_object(self._context, self, ct)
