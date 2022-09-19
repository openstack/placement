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
import collections

import sqlalchemy as sa

from placement.db.sqlalchemy import models
from placement import db_api
from placement import exception
from placement.objects import consumer_type as ct_obj

_CONSUMER_TYPE_TBL = models.ConsumerType.__table__
_RC_TBL = models.ResourceClass.__table__
_TRAIT_TBL = models.Trait.__table__


class _AttributeCache(object):
    """A cache of integer and string lookup values for string-based attributes.

    Subclasses must define `_table` and `_not_found` members describing the
    database table which is the authoritative source of data and the exception
    raised if data for an attribute is not found, respectively.

    The cache is required to be correct for the extent of any individual API
    request and be used only for those entities where any change to the
    underlying data is only making that change and will have no subsequent
    queries into the cache. For example, when we add a new resource class we
    do not then list all the resource classes from within the same session.

    Despite that requirement, any time an entity associated with a cache is
    created, updated, or deleted `clear()` should be called on the cache.
    """
    _table = None
    _not_found = None

    # The cache internally stores either sqlalchemy Row objects or
    # Attrs namedtuples but Row is compatible with namedtuple interface too.
    Attrs = collections.namedtuple(
        "Attrs", ["id", "name", "updated_at", "created_at"]
    )

    def __init__(self, ctx):
        """Initialize the cache of resource class identifiers.

        :param ctx: `placement.context.RequestContext` from which we can grab a
                    `SQLAlchemy.Connection` object to use for any DB lookups.
        """
        # Prevent this class being created directly, relevant during
        # development.
        assert self._table is not None, "_table must be defined"
        assert self._not_found is not None, "_not_found must be defined"
        self._ctx = ctx
        self.clear()

    def clear(self):
        self._id_cache = {}
        self._str_cache = {}
        self._all_cache = {}

    def id_from_string(self, attr_str):
        """Given a string representation of an attribute -- e.g. "DISK_GB"
        or "CUSTOM_IRON_SILVER" -- return the integer code for the attribute
        by doing a DB lookup into the appropriate table; however, the results
        of these DB lookups are cached since the lookups are so frequent.

        :param attr_str: The string representation of the attribute to look up
                         a numeric identifier for.
        :returns Integer identifier for the attribute.
        :raises An instance of the subclass' _not_found exception if attribute
                cannot be found in the DB.
        """
        attr_id = self._id_cache.get(attr_str)
        if attr_id is not None:
            return attr_id

        # Otherwise, check the database table
        self._refresh_from_db(self._ctx)
        if attr_str in self._id_cache:
            return self._id_cache[attr_str]
        raise self._not_found(name=attr_str)

    def all_from_string(self, attr_str):
        """Given a string representation of an attribute -- e.g. "DISK_GB"
        or "CUSTOM_IRON_SILVER" -- return all the attribute info.

        :param attr_str: The string representation of the attribute for which
                         to look up the object.
        :returns: namedtuple representing the attribute fields, if the
                  attribute was found in the appropriate database table.
        :raises An instance of the subclass' _not_found exception if attr_str
                cannot be found in the DB.
        """
        attrs = self._all_cache.get(attr_str)
        if attrs is not None:
            return attrs

        # Otherwise, check the database table
        self._refresh_from_db(self._ctx)
        if attr_str in self._all_cache:
            return self._all_cache[attr_str]
        raise self._not_found(name=attr_str)

    def string_from_id(self, attr_id):
        """The reverse of the id_from_string() method. Given a supplied numeric
        identifier for an attribute, we look up the corresponding string
        representation, via a DB lookup. The results of these DB lookups are
        cached since the lookups are so frequent.

        :param attr_id: The numeric representation of the attribute to look
                        up a string identifier for.
        :returns: String identifier for the attribute.
        :raises An instances of the subclass' _not_found exception if attr_id
                cannot be found in the DB.
        """
        attr_str = self._str_cache.get(attr_id)
        if attr_str is not None:
            return attr_str

        # Otherwise, check the database table
        self._refresh_from_db(self._ctx)
        if attr_id in self._str_cache:
            return self._str_cache[attr_id]
        raise self._not_found(name=attr_id)

    def get_all(self):
        """Return an iterator of all the resources in the cache with all their
        attributes as a namedtuple.

        In Python3 the return value is a generator.
        """
        if not self._all_cache:
            self._refresh_from_db(self._ctx)
        return self._all_cache.values()

    @db_api.placement_context_manager.reader
    def _refresh_from_db(self, ctx):
        """Grabs all resource classes or traits from the respective DB table
        and populates the supplied cache object's internal integer and string
        identifier dicts.

        :param ctx: RequestContext with the the database session.
        """
        table = self._table
        sel = sa.select(
            table.c.id,
            table.c.name,
            table.c.updated_at,
            table.c.created_at,
        )
        res = ctx.session.execute(sel).fetchall()
        self._id_cache = {r[1]: r[0] for r in res}
        self._str_cache = {r[0]: r[1] for r in res}
        # Note that r is Row object that is compatible with the namedtuple
        # interface of the cache
        self._all_cache = {r[1]: r for r in res}

    def _add_attribute(self, attr_id, name, created_at, updated_at):
        """Use this to add values to the cache that are not coming from the
        database, like defaults.
        """
        self._id_cache[name] = attr_id
        self._str_cache[attr_id] = name
        attrs = self.Attrs(attr_id, name, updated_at, created_at)
        self._all_cache[name] = attrs


class ConsumerTypeCache(_AttributeCache):
    """An _AttributeCache for consumer types."""

    _table = _CONSUMER_TYPE_TBL
    _not_found = exception.ConsumerTypeNotFound

    @db_api.placement_context_manager.reader
    def _refresh_from_db(self, ctx):
        super(ConsumerTypeCache, self)._refresh_from_db(ctx)
        # The consumer_type_id is nullable and records with a NULL (None)
        # consumer_type_id are considered as 'unknown'. Also the 'unknown'
        # consumer_type is not created in the database so we need to manually
        # populate it in the cache here.
        self._add_attribute(
            attr_id=None,
            name=ct_obj.NULL_CONSUMER_TYPE_ALIAS,
            # should we synthesize some dates in the past instead?
            created_at=None,
            updated_at=None,
        )


class ResourceClassCache(_AttributeCache):
    """An _AttributeCache for resource classes."""

    _table = _RC_TBL
    _not_found = exception.ResourceClassNotFound


class TraitCache(_AttributeCache):
    """An _AttributeCache for traits."""

    _table = _TRAIT_TBL
    _not_found = exception.TraitNotFound
