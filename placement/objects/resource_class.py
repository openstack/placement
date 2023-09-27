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


import os_resource_classes as orc
from oslo_concurrency import lockutils
from oslo_db import api as oslo_db_api
from oslo_db import exception as db_exc
from oslo_log import log as logging
import sqlalchemy as sa
from sqlalchemy import func

from placement.db.sqlalchemy import models
from placement import db_api
from placement import exception

_RC_TBL = models.ResourceClass.__table__
_RESOURCE_CLASSES_LOCK = 'resource_classes_sync'
_RESOURCE_CLASSES_SYNCED = False

LOG = logging.getLogger(__name__)


class ResourceClass(object):

    MIN_CUSTOM_RESOURCE_CLASS_ID = 10000
    """Any user-defined resource classes must have an identifier greater than
    or equal to this number.
    """

    # Retry count for handling possible race condition in creating resource
    # class. We don't ever want to hit this, as it is simply a race when
    # creating these classes, but this is just a stopgap to prevent a potential
    # infinite loop.
    RESOURCE_CREATE_RETRY_COUNT = 100

    def __init__(self, context, id=None, name=None, updated_at=None,
                 created_at=None):
        self._context = context
        self.id = id
        self.name = name
        self.updated_at = updated_at
        self.created_at = created_at

    @staticmethod
    def _from_db_object(context, target, source):
        target._context = context
        target.id = source['id']
        target.name = source['name']
        target.updated_at = source['updated_at']
        target.created_at = source['created_at']
        return target

    @classmethod
    def get_by_name(cls, context, name):
        """Return a ResourceClass object with the given string name.

        :param name: String name of the resource class to find

        :raises: ResourceClassNotFound if no such resource class was found
        """
        rc = context.rc_cache.all_from_string(name)
        obj = cls(
            context,
            id=rc.id,
            name=rc.name,
            updated_at=rc.updated_at,
            created_at=rc.created_at,
        )
        return obj

    @staticmethod
    @db_api.placement_context_manager.reader
    def _get_next_id(context):
        """Utility method to grab the next resource class identifier to use for
         user-defined resource classes.
        """
        query = context.session.query(func.max(models.ResourceClass.id))
        max_id = query.one()[0]
        if not max_id or max_id < ResourceClass.MIN_CUSTOM_RESOURCE_CLASS_ID:
            return ResourceClass.MIN_CUSTOM_RESOURCE_CLASS_ID
        else:
            return max_id + 1

    def create(self):
        if self.id is not None:
            raise exception.ObjectActionError(action='create',
                                              reason='already created')
        if not self.name:
            raise exception.ObjectActionError(action='create',
                                              reason='name is required')
        if self.name in orc.STANDARDS:
            raise exception.ResourceClassExists(resource_class=self.name)

        if not self.name.startswith(orc.CUSTOM_NAMESPACE):
            raise exception.ObjectActionError(
                action='create',
                reason='name must start with ' + orc.CUSTOM_NAMESPACE)
        updates = {}
        for field in ['name', 'updated_at', 'created_at']:
            value = getattr(self, field, None)
            if value:
                updates[field] = value

        # There is the possibility of a race when adding resource classes, as
        # the ID is generated locally. This loop catches that exception, and
        # retries until either it succeeds, or a different exception is
        # encountered.
        retries = self.RESOURCE_CREATE_RETRY_COUNT
        while retries:
            retries -= 1
            try:
                rc = self._create_in_db(self._context, updates)
                self._from_db_object(self._context, self, rc)
                break
            except db_exc.DBDuplicateEntry as e:
                if 'id' in e.columns:
                    # Race condition for ID creation; try again
                    continue
                # The duplication is on the other unique column, 'name'. So do
                # not retry; raise the exception immediately.
                raise exception.ResourceClassExists(resource_class=self.name)
        else:
            # We have no idea how common it will be in practice for the retry
            # limit to be exceeded. We set it high in the hope that we never
            # hit this point, but added this log message so we know that this
            # specific situation occurred.
            LOG.warning("Exceeded retry limit on ID generation while "
                        "creating ResourceClass %(name)s",
                        {'name': self.name})
            msg = "creating resource class %s" % self.name
            raise exception.MaxDBRetriesExceeded(action=msg)
        self._context.rc_cache.clear()

    @staticmethod
    @db_api.placement_context_manager.writer
    def _create_in_db(context, updates):
        next_id = ResourceClass._get_next_id(context)
        rc = models.ResourceClass()
        rc.update(updates)
        rc.id = next_id
        context.session.add(rc)
        return rc

    def destroy(self):
        if self.id is None:
            raise exception.ObjectActionError(action='destroy',
                                              reason='ID attribute not found')
        # Never delete any standard resource class.
        if self.id < ResourceClass.MIN_CUSTOM_RESOURCE_CLASS_ID:
            raise exception.ResourceClassCannotDeleteStandard(
                resource_class=self.name)

        self._destroy(self._context, self.id, self.name)
        self._context.rc_cache.clear()

    @staticmethod
    @db_api.placement_context_manager.writer
    def _destroy(context, _id, name):
        # Don't delete the resource class if it is referred to in the
        # inventories table.
        num_inv = context.session.query(models.Inventory).filter(
            models.Inventory.resource_class_id == _id).count()
        if num_inv:
            raise exception.ResourceClassInUse(resource_class=name)

        res = context.session.query(models.ResourceClass).filter(
            models.ResourceClass.id == _id).delete()
        if not res:
            raise exception.NotFound()

    def save(self):
        if self.id is None:
            raise exception.ObjectActionError(action='save',
                                              reason='ID attribute not found')
        updates = {}
        for field in ['name', 'updated_at', 'created_at']:
            value = getattr(self, field, None)
            if value:
                updates[field] = value
        # Never update any standard resource class.
        if self.id < ResourceClass.MIN_CUSTOM_RESOURCE_CLASS_ID:
            raise exception.ResourceClassCannotUpdateStandard(
                resource_class=self.name)
        self._save(self._context, self.id, self.name, updates)
        self._context.rc_cache.clear()

    @staticmethod
    @db_api.placement_context_manager.writer
    def _save(context, id, name, updates):
        db_rc = context.session.query(models.ResourceClass).filter_by(
            id=id).first()
        db_rc.update(updates)
        try:
            db_rc.save(context.session)
        except db_exc.DBDuplicateEntry:
            raise exception.ResourceClassExists(resource_class=name)


def ensure_sync(ctx):
    global _RESOURCE_CLASSES_SYNCED
    # If another thread is doing this work, wait for it to complete.
    # When that thread is done _RESOURCE_CLASSES_SYNCED will be true in this
    # thread and we'll simply return.
    with lockutils.lock(_RESOURCE_CLASSES_LOCK):
        if not _RESOURCE_CLASSES_SYNCED:
            _resource_classes_sync(ctx)
            _RESOURCE_CLASSES_SYNCED = True


def get_all(context):
    """Get a list of all the resource classes in the database."""
    resource_classes = context.rc_cache.get_all()
    return [ResourceClass(context, **rc._mapping) for rc in resource_classes]


@oslo_db_api.wrap_db_retry(max_retries=5, retry_on_deadlock=True)
@db_api.placement_context_manager.writer
def _resource_classes_sync(ctx):
    # Create a set of all resource class in the os_resource_classes library.
    sel = sa.select(_RC_TBL.c.name)
    res = ctx.session.execute(sel).fetchall()
    db_classes = [r[0] for r in res if not orc.is_custom(r[0])]
    LOG.debug("Found existing resource classes in db: %s", db_classes)
    # Determine those resource classes which are in os_resource_classes but not
    # currently in the database, and insert them.
    batch_args = [{'name': str(name), 'id': index}
                  for index, name in enumerate(orc.STANDARDS)
                  if name not in db_classes]
    ins = _RC_TBL.insert()
    if batch_args:
        conn = ctx.session.connection()
        if conn.engine.dialect.name == 'mysql':
            # We need to do a literal insert of 0 to preserve the order
            # of the resource class ids from the previous style of
            # managing them. In some mysql settings a 0 is the same as
            # "give me a default key".
            conn.execute(
                sa.text("SET SESSION SQL_MODE='NO_AUTO_VALUE_ON_ZERO'")
            )
        try:
            ctx.session.execute(ins, batch_args)
            LOG.debug("Synced resource_classes from os_resource_classes: %s",
                      batch_args)
        except db_exc.DBDuplicateEntry:
            pass  # some other process sync'd, just ignore
