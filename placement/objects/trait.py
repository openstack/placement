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

import os_traits
from oslo_concurrency import lockutils
from oslo_db import api as oslo_db_api
from oslo_db import exception as db_exc
from oslo_log import log as logging
import sqlalchemy as sa
from sqlalchemy.engine import row as sa_row

from placement.db.sqlalchemy import models
from placement import db_api
from placement import exception


_RP_TBL = models.ResourceProvider.__table__
_RP_TRAIT_TBL = models.ResourceProviderTrait.__table__
_TRAIT_TBL = models.Trait.__table__
_TRAIT_LOCK = 'trait_sync'
_TRAITS_SYNCED = False

LOG = logging.getLogger(__name__)


class Trait(object):

    # All the user-defined traits must begin with this prefix.
    CUSTOM_NAMESPACE = 'CUSTOM_'

    def __init__(self, context, id=None, name=None, updated_at=None,
                 created_at=None):
        self._context = context
        self.id = id
        self.name = name
        self.updated_at = updated_at
        self.created_at = created_at

    # FIXME(cdent): Duped from resource_class.
    @staticmethod
    def _from_db_object(context, target, source):
        target._context = context
        target.id = source['id']
        target.name = source['name']
        target.updated_at = source['updated_at']
        target.created_at = source['created_at']
        return target

    @staticmethod
    @db_api.placement_context_manager.writer
    def _create_in_db(context, updates):
        trait = models.Trait()
        trait.update(updates)
        context.session.add(trait)
        return trait

    def create(self):
        if self.id is not None:
            raise exception.ObjectActionError(action='create',
                                              reason='already created')
        if not self.name:
            raise exception.ObjectActionError(action='create',
                                              reason='name is required')

        # FIXME(cdent): duped from resource class
        updates = {}
        for field in ['name', 'updated_at', 'created_at']:
            value = getattr(self, field, None)
            if value:
                updates[field] = value

        try:
            db_trait = self._create_in_db(self._context, updates)
        except db_exc.DBDuplicateEntry:
            raise exception.TraitExists(name=self.name)

        self._from_db_object(self._context, self, db_trait)
        self._context.trait_cache.clear()

    @classmethod
    def get_by_name(cls, context, name):
        trait = context.trait_cache.all_from_string(name)
        return cls._from_db_object(context, cls(context), trait._asdict())

    @staticmethod
    @db_api.placement_context_manager.writer
    def _destroy_in_db(context, _id, name):
        num = context.session.query(models.ResourceProviderTrait).filter(
            models.ResourceProviderTrait.trait_id == _id).count()
        if num:
            raise exception.TraitInUse(name=name)

        res = context.session.query(models.Trait).filter_by(
            name=name).delete()
        if not res:
            raise exception.TraitNotFound(name=name)

    def destroy(self):
        if not self.name:
            raise exception.ObjectActionError(action='destroy',
                                              reason='name is required')

        if not self.name.startswith(self.CUSTOM_NAMESPACE):
            raise exception.TraitCannotDeleteStandard(name=self.name)

        if self.id is None:
            raise exception.ObjectActionError(action='destroy',
                                              reason='ID attribute not found')

        self._destroy_in_db(self._context, self.id, self.name)
        self._context.trait_cache.clear()


def ensure_sync(ctx):
    """Ensures that the os_traits library is synchronized to the traits db.

    If _TRAITS_SYNCED is False then this process has not tried to update the
    traits db. Do so by calling _trait_sync. Since the placement API server
    could be multi-threaded, lock around testing _TRAITS_SYNCED to avoid
    duplicating work.

    Different placement API server processes that talk to the same database
    will avoid issues through the power of transactions.

    :param ctx: `placement.context.RequestContext` that may be used to grab a
                DB connection.
    """
    global _TRAITS_SYNCED
    # If another thread is doing this work, wait for it to complete.
    # When that thread is done _TRAITS_SYNCED will be true in this
    # thread and we'll simply return.
    with lockutils.lock(_TRAIT_LOCK):
        if not _TRAITS_SYNCED:
            _trait_sync(ctx)
            _TRAITS_SYNCED = True


def get_all(context, filters=None):
    db_traits = _get_all_from_db(context, filters)
    # FIXME(stephenfin): This is necessary because our cached object type is
    # different from what we're getting from the database. We should use the
    # same
    result = []
    for trait in db_traits:
        if isinstance(trait, sa_row.Row):
            result.append(Trait(context, **trait._mapping))
        else:
            result.append(Trait(context, **trait))
    return result


def get_all_by_resource_provider(context, rp):
    """Returns a list containing Trait objects for any trait
    associated with the supplied resource provider.
    """
    db_traits = get_traits_by_provider_id(context, rp.id)
    return [Trait(context, **data._mapping) for data in db_traits]


@db_api.placement_context_manager.reader
def get_traits_by_provider_id(context, rp_id):
    rp_traits_id = _RP_TRAIT_TBL.c.resource_provider_id
    trait_id = _RP_TRAIT_TBL.c.trait_id
    trait_cache = context.trait_cache

    sel = sa.select(trait_id).where(rp_traits_id == rp_id)
    return [
        trait_cache.all_from_string(trait_cache.string_from_id(r.trait_id))
        for r in context.session.execute(sel).fetchall()]


@db_api.placement_context_manager.reader
def get_traits_by_provider_tree(ctx, root_ids):
    """Returns a dict, keyed by provider IDs for all resource providers
    in all trees indicated in the ``root_ids``, of string trait names
    associated with that provider.

    :raises: ValueError when root_ids is empty.

    :param ctx: placement.context.RequestContext object
    :param root_ids: list of root resource provider IDs
    """
    if not root_ids:
        raise ValueError("Expected root_ids to be a list of root resource "
                         "provider internal IDs, but got an empty list.")

    rpt = sa.alias(_RP_TBL, name='rpt')
    rptt = sa.alias(_RP_TRAIT_TBL, name='rptt')
    rpt_rptt = sa.join(rpt, rptt, rpt.c.id == rptt.c.resource_provider_id)
    sel = sa.select(rptt.c.resource_provider_id, rptt.c.trait_id)
    sel = sel.select_from(rpt_rptt)
    sel = sel.where(rpt.c.root_provider_id.in_(
        sa.bindparam('root_ids', expanding=True)))
    res = collections.defaultdict(list)
    for r in ctx.session.execute(sel, {'root_ids': list(root_ids)}):
        res[r[0]].append(ctx.trait_cache.string_from_id(r[1]))
    return res


def ids_from_names(ctx, names):
    """Given a list of string trait names, returns a dict, keyed by those
    string names, of the corresponding internal integer trait ID.

    :raises: ValueError when names is empty.

    :param ctx: placement.context.RequestContext object
    :param names: list of string trait names
    :raise TraitNotFound: if any named trait doesn't exist in the database.
    """
    if not names:
        raise ValueError("Expected names to be a list of string trait "
                         "names, but got an empty list.")

    return {name: ctx.trait_cache.id_from_string(name) for name in names}


def _get_all_from_db(context, filters):
    # If no filters are required, returns everything from the cache.
    if not filters:
        return context.trait_cache.get_all()
    return _get_all_filtered_from_db(context, filters)


@db_api.placement_context_manager.reader
def _get_all_filtered_from_db(context, filters):

    query = context.session.query(models.Trait)
    if 'name_in' in filters:
        query = query.filter(models.Trait.name.in_(
            [str(n) for n in filters['name_in']]
        ))
    if 'prefix' in filters:
        query = query.filter(
            models.Trait.name.like(str(filters['prefix'] + '%')))
    if 'associated' in filters:
        if filters['associated']:
            query = query.join(
                models.ResourceProviderTrait,
                models.Trait.id == models.ResourceProviderTrait.trait_id
            ).distinct()
        else:
            query = query.outerjoin(
                models.ResourceProviderTrait,
                models.Trait.id == models.ResourceProviderTrait.trait_id
            ).filter(models.ResourceProviderTrait.trait_id == sa.null())

    return query.all()


@oslo_db_api.wrap_db_retry(max_retries=5, retry_on_deadlock=True)
# Bug #1760322: If the caller raises an exception, we don't want the trait
# sync rolled back; so use an .independent transaction
@db_api.placement_context_manager.writer
def _trait_sync(ctx):
    """Sync the os_traits symbols to the database.

    Reads all symbols from the os_traits library, checks if any of them do
    not exist in the database and bulk-inserts those that are not. This is
    done once per web-service process, at startup.

    :param ctx: `placement.context.RequestContext` that may be used to grab a
                 DB connection.
    """
    # Create a set of all traits in the os_traits library.
    std_traits = set(os_traits.get_traits())
    sel = sa.select(_TRAIT_TBL.c.name)
    res = ctx.session.execute(sel).fetchall()
    # Create a set of all traits in the db that are not custom
    # traits.
    db_traits = set(
        r[0] for r in res
        if not os_traits.is_custom(r[0])
    )
    # Determine those traits which are in os_traits but not
    # currently in the database, and insert them.
    need_sync = std_traits - db_traits
    ins = _TRAIT_TBL.insert()
    batch_args = [
        {'name': str(trait)}
        for trait in need_sync
    ]
    if batch_args:
        try:
            ctx.session.execute(ins, batch_args)
            LOG.debug("Synced traits from os_traits into API DB: %s",
                      need_sync)
        except db_exc.DBDuplicateEntry:
            pass  # some other process sync'd, just ignore
