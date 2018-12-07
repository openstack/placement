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

from oslo_concurrency import lockutils
import sqlalchemy as sa

from placement.db.sqlalchemy import models
from placement import db_api
from placement import exception

_RC_TBL = models.ResourceClass.__table__
_LOCKNAME = 'rc_cache'


@db_api.placement_context_manager.reader
def _refresh_from_db(ctx, cache):
    """Grabs all resource classes from the DB table and populates the
    supplied cache object's internal integer and string identifier dicts.

    :param cache: ResourceClassCache object to refresh.
    """
    sel = sa.select([_RC_TBL.c.id, _RC_TBL.c.name, _RC_TBL.c.updated_at,
                     _RC_TBL.c.created_at])
    res = ctx.session.execute(sel).fetchall()
    cache.id_cache = {r[1]: r[0] for r in res}
    cache.str_cache = {r[0]: r[1] for r in res}
    cache.all_cache = {r[1]: r for r in res}


class ResourceClassCache(object):
    """A  cache of integer and string lookup values for resource classes."""

    def __init__(self, ctx):
        """Initialize the cache of resource class identifiers.

        :param ctx: `placement.context.RequestContext` from which we can grab a
                    `SQLAlchemy.Connection` object to use for any DB lookups.
        """
        self.ctx = ctx
        self.id_cache = {}
        self.str_cache = {}
        self.all_cache = {}

    def clear(self):
        with lockutils.lock(_LOCKNAME):
            self.id_cache = {}
            self.str_cache = {}
            self.all_cache = {}

    def id_from_string(self, rc_str):
        """Given a string representation of a resource class -- e.g. "DISK_GB"
        or "CUSTOM_IRON_SILVER" -- return the integer code for the resource
        class by doing a DB lookup into the resource_classes table; however,
        the results of these DB lookups are cached since the lookups are so
        frequent.

        :param rc_str: The string representation of the resource class to look
                       up a numeric identifier for.
        :returns Integer identifier for the resource class.
        :raises `exception.ResourceClassNotFound` if rc_str cannot be found in
                the DB.
        """
        rc_id = self.id_cache.get(rc_str)
        if rc_id is not None:
            return rc_id

        # Otherwise, check the database table
        with lockutils.lock(_LOCKNAME):
            _refresh_from_db(self.ctx, self)
            if rc_str in self.id_cache:
                return self.id_cache[rc_str]
            raise exception.ResourceClassNotFound(resource_class=rc_str)

    def all_from_string(self, rc_str):
        """Given a string representation of a resource class -- e.g. "DISK_GB"
        or "CUSTOM_IRON_SILVER" -- return all the resource class info.

        :param rc_str: The string representation of the resource class for
                       which to look up a resource_class.
        :returns: dict representing the resource class fields, if the
                  resource class was found in the resource_classes database
                  table.
        :raises: `exception.ResourceClassNotFound` if rc_str cannot be found in
                 the DB.
        """
        rc_id_str = self.all_cache.get(rc_str)
        if rc_id_str is not None:
            return rc_id_str

        # Otherwise, check the database table
        with lockutils.lock(_LOCKNAME):
            _refresh_from_db(self.ctx, self)
            if rc_str in self.all_cache:
                return self.all_cache[rc_str]
            raise exception.ResourceClassNotFound(resource_class=rc_str)

    def string_from_id(self, rc_id):
        """The reverse of the id_from_string() method. Given a supplied numeric
        identifier for a resource class, we look up the corresponding string
        representation, via a DB lookup. The results of these DB lookups are
        cached since the lookups are so frequent.

        :param rc_id: The numeric representation of the resource class to look
                      up a string identifier for.
        :returns: String identifier for the resource class.
        :raises `exception.ResourceClassNotFound` if rc_id cannot be found in
                the DB.
        """
        rc_str = self.str_cache.get(rc_id)
        if rc_str is not None:
            return rc_str

        # Otherwise, check the database table
        with lockutils.lock(_LOCKNAME):
            _refresh_from_db(self.ctx, self)
            if rc_id in self.str_cache:
                return self.str_cache[rc_id]
            raise exception.ResourceClassNotFound(resource_class=rc_id)
