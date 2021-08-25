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

from placement.db.sqlalchemy import models
from placement import db_api
from placement import exception

CONSUMER_TYPE_TBL = models.ConsumerType.__table__
_CONSUMER_TYPES_LOCK = 'consumer_types_sync'
_CONSUMER_TYPES_SYNCED = False
NULL_CONSUMER_TYPE_ALIAS = 'unknown'


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

    # NOTE(cdent): get_by_id and get_by_name are not currently used
    # but are left in place to indicate the smooth migration from
    # direct db access to using the AttributeCache.
    @classmethod
    def get_by_id(cls, ctx, id):
        return ctx.ct_cache.all_from_string(ctx.ct_cache.string_from_id(id))

    @classmethod
    def get_by_name(cls, ctx, name):
        return ctx.ct_cache.all_from_string(name)

    def create(self):
        ct = _create_in_db(self._context, self.name)
        self._from_db_object(self._context, self, ct)
        self._context.ct_cache.clear()
