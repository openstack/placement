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
import copy
import itertools
import random

# NOTE(cdent): The resource provider objects are designed to never be
# used over RPC. Remote manipulation is done with the placement HTTP
# API. The 'remotable' decorators should not be used, the objects should
# not be registered and there is no need to express VERSIONs nor handle
# obj_make_compatible.

import os_resource_classes as orc
import os_traits
from oslo_concurrency import lockutils
from oslo_db import api as oslo_db_api
from oslo_db import exception as db_exc
from oslo_log import log as logging
from oslo_utils import encodeutils
import six
import sqlalchemy as sa
from sqlalchemy import exc as sqla_exc
from sqlalchemy import func
from sqlalchemy import sql
from sqlalchemy.sql import null

from placement.db.sqlalchemy import models
from placement import db_api
from placement import exception
from placement.i18n import _
from placement.objects import common as common_obj
from placement.objects import rp_candidates
from placement import resource_class_cache as rc_cache

_TRAIT_TBL = models.Trait.__table__
_ALLOC_TBL = models.Allocation.__table__
_INV_TBL = models.Inventory.__table__
_RP_TBL = models.ResourceProvider.__table__
# Not used in this file but used in tests.
_RC_TBL = models.ResourceClass.__table__
_AGG_TBL = models.PlacementAggregate.__table__
_RP_AGG_TBL = models.ResourceProviderAggregate.__table__
_RP_TRAIT_TBL = models.ResourceProviderTrait.__table__
_RESOURCE_CLASSES_LOCK = 'resource_classes_sync'
_RESOURCE_CLASSES_SYNCED = False
_TRAIT_LOCK = 'trait_sync'
_TRAITS_SYNCED = False

LOG = logging.getLogger(__name__)


@oslo_db_api.wrap_db_retry(max_retries=5, retry_on_deadlock=True)
# Bug #1760322: If the caller raises an exception, we don't want the trait
# sync rolled back; so use an .independent transaction
@db_api.placement_context_manager.writer
def _trait_sync(ctx):
    """Sync the os_traits symbols to the database.

    Reads all symbols from the os_traits library, checks if any of them do
    not exist in the database and bulk-inserts those that are not. This is
    done once per process using this code if either Trait.get_by_name or
    TraitList.get_all is called.

    :param ctx: `placement.context.RequestContext` that may be used to grab a
                 DB connection.
    """
    # Create a set of all traits in the os_traits library.
    std_traits = set(os_traits.get_traits())
    sel = sa.select([_TRAIT_TBL.c.name])
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
        {'name': six.text_type(trait)}
        for trait in need_sync
    ]
    if batch_args:
        try:
            ctx.session.execute(ins, batch_args)
            LOG.debug("Synced traits from os_traits into API DB: %s",
                      need_sync)
        except db_exc.DBDuplicateEntry:
            pass  # some other process sync'd, just ignore


def ensure_trait_sync(ctx):
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


@oslo_db_api.wrap_db_retry(max_retries=5, retry_on_deadlock=True)
@db_api.placement_context_manager.writer
def _resource_classes_sync(ctx):
    # Create a set of all resource class in the os_resource_classes library.
    sel = sa.select([_RC_TBL.c.name])
    res = ctx.session.execute(sel).fetchall()
    db_classes = [r[0] for r in res if not orc.is_custom(r[0])]
    LOG.debug("Found existing resource classes in db: %s", db_classes)
    # Determine those resource clases which are in os_resource_classes but not
    # currently in the database, and insert them.
    batch_args = [{'name': six.text_type(name), 'id': index}
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
            conn.execute("SET SESSION SQL_MODE='NO_AUTO_VALUE_ON_ZERO'")
        try:
            ctx.session.execute(ins, batch_args)
            LOG.debug("Synced resource_classes from os_resource_classes: %s",
                      batch_args)
        except db_exc.DBDuplicateEntry:
            pass  # some other process sync'd, just ignore


def ensure_resource_classes_sync(ctx):
    global _RESOURCE_CLASSES_SYNCED
    # If another thread is doing this work, wait for it to complete.
    # When that thread is done _RESOURCE_CLASSES_SYNCED will be true in this
    # thread and we'll simply return.
    with lockutils.lock(_RESOURCE_CLASSES_LOCK):
        if not _RESOURCE_CLASSES_SYNCED:
            _resource_classes_sync(ctx)
            _RESOURCE_CLASSES_SYNCED = True


def _usage_select(rc_ids):
    usage = sa.select([_ALLOC_TBL.c.resource_provider_id,
                       _ALLOC_TBL.c.resource_class_id,
                       sql.func.sum(_ALLOC_TBL.c.used).label('used')])
    usage = usage.where(_ALLOC_TBL.c.resource_class_id.in_(rc_ids))
    usage = usage.group_by(_ALLOC_TBL.c.resource_provider_id,
                           _ALLOC_TBL.c.resource_class_id)
    return sa.alias(usage, name='usage')


def _capacity_check_clause(amount, usage, inv_tbl=_INV_TBL):
    return sa.and_(
        sql.func.coalesce(usage.c.used, 0) + amount <= (
            (inv_tbl.c.total - inv_tbl.c.reserved) *
            inv_tbl.c.allocation_ratio),
        inv_tbl.c.min_unit <= amount,
        inv_tbl.c.max_unit >= amount,
        amount % inv_tbl.c.step_size == 0,
    )


def _get_current_inventory_resources(ctx, rp):
    """Returns a set() containing the resource class IDs for all resources
    currently having an inventory record for the supplied resource provider.

    :param ctx: `placement.context.RequestContext` that may be used to grab a
                DB connection.
    :param rp: Resource provider to query inventory for.
    """
    cur_res_sel = sa.select([_INV_TBL.c.resource_class_id]).where(
        _INV_TBL.c.resource_provider_id == rp.id)
    existing_resources = ctx.session.execute(cur_res_sel).fetchall()
    return set([r[0] for r in existing_resources])


def _delete_inventory_from_provider(ctx, rp, to_delete):
    """Deletes any inventory records from the supplied provider and set() of
    resource class identifiers.

    If there are allocations for any of the inventories to be deleted raise
    InventoryInUse exception.

    :param ctx: `placement.context.RequestContext` that contains an oslo_db
                Session
    :param rp: Resource provider from which to delete inventory.
    :param to_delete: set() containing resource class IDs for records to
                      delete.
    """
    allocation_query = sa.select(
        [_ALLOC_TBL.c.resource_class_id.label('resource_class')]
    ).where(
        sa.and_(_ALLOC_TBL.c.resource_provider_id == rp.id,
                _ALLOC_TBL.c.resource_class_id.in_(to_delete))
    ).group_by(_ALLOC_TBL.c.resource_class_id)
    allocations = ctx.session.execute(allocation_query).fetchall()
    if allocations:
        resource_classes = ', '.join(
            [rc_cache.RC_CACHE.string_from_id(alloc[0])
             for alloc in allocations])
        raise exception.InventoryInUse(resource_classes=resource_classes,
                                       resource_provider=rp.uuid)

    del_stmt = _INV_TBL.delete().where(
        sa.and_(
            _INV_TBL.c.resource_provider_id == rp.id,
            _INV_TBL.c.resource_class_id.in_(to_delete)))
    res = ctx.session.execute(del_stmt)
    return res.rowcount


def _add_inventory_to_provider(ctx, rp, inv_list, to_add):
    """Inserts new inventory records for the supplied resource provider.

    :param ctx: `placement.context.RequestContext` that contains an oslo_db
                Session
    :param rp: Resource provider to add inventory to.
    :param inv_list: InventoryList object
    :param to_add: set() containing resource class IDs to search inv_list for
                   adding to resource provider.
    """
    for rc_id in to_add:
        rc_str = rc_cache.RC_CACHE.string_from_id(rc_id)
        inv_record = inv_list.find(rc_str)
        ins_stmt = _INV_TBL.insert().values(
            resource_provider_id=rp.id,
            resource_class_id=rc_id,
            total=inv_record.total,
            reserved=inv_record.reserved,
            min_unit=inv_record.min_unit,
            max_unit=inv_record.max_unit,
            step_size=inv_record.step_size,
            allocation_ratio=inv_record.allocation_ratio)
        ctx.session.execute(ins_stmt)


def _update_inventory_for_provider(ctx, rp, inv_list, to_update):
    """Updates existing inventory records for the supplied resource provider.

    :param ctx: `placement.context.RequestContext` that contains an oslo_db
                Session
    :param rp: Resource provider on which to update inventory.
    :param inv_list: InventoryList object
    :param to_update: set() containing resource class IDs to search inv_list
                      for updating in resource provider.
    :returns: A list of (uuid, class) tuples that have exceeded their
              capacity after this inventory update.
    """
    exceeded = []
    for rc_id in to_update:
        rc_str = rc_cache.RC_CACHE.string_from_id(rc_id)
        inv_record = inv_list.find(rc_str)
        allocation_query = sa.select(
            [func.sum(_ALLOC_TBL.c.used).label('usage')])
        allocation_query = allocation_query.where(
            sa.and_(
                _ALLOC_TBL.c.resource_provider_id == rp.id,
                _ALLOC_TBL.c.resource_class_id == rc_id))
        allocations = ctx.session.execute(allocation_query).first()
        if (allocations and
                allocations['usage'] is not None and
                allocations['usage'] > inv_record.capacity):
            exceeded.append((rp.uuid, rc_str))
        upd_stmt = _INV_TBL.update().where(
            sa.and_(
                _INV_TBL.c.resource_provider_id == rp.id,
                _INV_TBL.c.resource_class_id == rc_id)
        ).values(
            total=inv_record.total,
            reserved=inv_record.reserved,
            min_unit=inv_record.min_unit,
            max_unit=inv_record.max_unit,
            step_size=inv_record.step_size,
            allocation_ratio=inv_record.allocation_ratio)
        res = ctx.session.execute(upd_stmt)
        if not res.rowcount:
            raise exception.InventoryWithResourceClassNotFound(
                resource_class=rc_str)
    return exceeded


@db_api.placement_context_manager.writer
def _add_inventory(context, rp, inventory):
    """Add one Inventory that wasn't already on the provider.

    :raises `exception.ResourceClassNotFound` if inventory.resource_class
            cannot be found in the DB.
    """
    rc_id = rc_cache.RC_CACHE.id_from_string(inventory.resource_class)
    inv_list = InventoryList(objects=[inventory])
    _add_inventory_to_provider(
        context, rp, inv_list, set([rc_id]))
    rp.increment_generation()


@db_api.placement_context_manager.writer
def _update_inventory(context, rp, inventory):
    """Update an inventory already on the provider.

    :raises `exception.ResourceClassNotFound` if inventory.resource_class
            cannot be found in the DB.
    """
    rc_id = rc_cache.RC_CACHE.id_from_string(inventory.resource_class)
    inv_list = InventoryList(objects=[inventory])
    exceeded = _update_inventory_for_provider(
        context, rp, inv_list, set([rc_id]))
    rp.increment_generation()
    return exceeded


@db_api.placement_context_manager.writer
def _delete_inventory(context, rp, resource_class):
    """Delete up to one Inventory of the given resource_class string.

    :raises `exception.ResourceClassNotFound` if resource_class
            cannot be found in the DB.
    """
    rc_id = rc_cache.RC_CACHE.id_from_string(resource_class)
    if not _delete_inventory_from_provider(context, rp, [rc_id]):
        raise exception.NotFound(
            'No inventory of class %s found for delete'
            % resource_class)
    rp.increment_generation()


@db_api.placement_context_manager.writer
def _set_inventory(context, rp, inv_list):
    """Given an InventoryList object, replaces the inventory of the
    resource provider in a safe, atomic fashion using the resource
    provider's generation as a consistent view marker.

    :param context: Nova RequestContext.
    :param rp: `ResourceProvider` object upon which to set inventory.
    :param inv_list: `InventoryList` object to save to backend storage.
    :returns: A list of (uuid, class) tuples that have exceeded their
              capacity after this inventory update.
    :raises placement.exception.ConcurrentUpdateDetected: if another thread
            updated the same resource provider's view of its inventory or
            allocations in between the time when this object was originally
            read and the call to set the inventory.
    :raises `exception.ResourceClassNotFound` if any resource class in any
            inventory in inv_list cannot be found in the DB.
    :raises `exception.InventoryInUse` if we attempt to delete inventory
            from a provider that has allocations for that resource class.
    """
    existing_resources = _get_current_inventory_resources(context, rp)
    these_resources = set([rc_cache.RC_CACHE.id_from_string(r.resource_class)
                           for r in inv_list.objects])

    # Determine which resources we should be adding, deleting and/or
    # updating in the resource provider's inventory by comparing sets
    # of resource class identifiers.
    to_add = these_resources - existing_resources
    to_delete = existing_resources - these_resources
    to_update = these_resources & existing_resources
    exceeded = []

    if to_delete:
        _delete_inventory_from_provider(context, rp, to_delete)
    if to_add:
        _add_inventory_to_provider(context, rp, inv_list, to_add)
    if to_update:
        exceeded = _update_inventory_for_provider(context, rp, inv_list,
                                                  to_update)

    # Here is where we update the resource provider's generation value.  If
    # this update updates zero rows, that means that another thread has updated
    # the inventory for this resource provider between the time the caller
    # originally read the resource provider record and inventory information
    # and this point. We raise an exception here which will rollback the above
    # transaction and return an error to the caller to indicate that they can
    # attempt to retry the inventory save after reverifying any capacity
    # conditions and re-reading the existing inventory information.
    rp.increment_generation()

    return exceeded


@db_api.placement_context_manager.reader
def _get_provider_by_uuid(context, uuid):
    """Given a UUID, return a dict of information about the resource provider
    from the database.

    :raises: NotFound if no such provider was found
    :param uuid: The UUID to look up
    """
    rpt = sa.alias(_RP_TBL, name="rp")
    parent = sa.alias(_RP_TBL, name="parent")
    root = sa.alias(_RP_TBL, name="root")
    # TODO(jaypipes): Change this to an inner join when we are sure all
    # root_provider_id values are NOT NULL
    rp_to_root = sa.outerjoin(rpt, root, rpt.c.root_provider_id == root.c.id)
    rp_to_parent = sa.outerjoin(
        rp_to_root, parent,
        rpt.c.parent_provider_id == parent.c.id)
    cols = [
        rpt.c.id,
        rpt.c.uuid,
        rpt.c.name,
        rpt.c.generation,
        root.c.uuid.label("root_provider_uuid"),
        parent.c.uuid.label("parent_provider_uuid"),
        rpt.c.updated_at,
        rpt.c.created_at,
    ]
    sel = sa.select(cols).select_from(rp_to_parent).where(rpt.c.uuid == uuid)
    res = context.session.execute(sel).fetchone()
    if not res:
        raise exception.NotFound(
            'No resource provider with uuid %s found' % uuid)
    return dict(res)


@db_api.placement_context_manager.reader
def _get_aggregates_by_provider_id(context, rp_id):
    """Returns a dict, keyed by internal aggregate ID, of aggregate UUIDs
    associated with the supplied internal resource provider ID.
    """
    join_statement = sa.join(
        _AGG_TBL, _RP_AGG_TBL, sa.and_(
            _AGG_TBL.c.id == _RP_AGG_TBL.c.aggregate_id,
            _RP_AGG_TBL.c.resource_provider_id == rp_id))
    sel = sa.select([_AGG_TBL.c.id, _AGG_TBL.c.uuid]).select_from(
        join_statement)
    return {r[0]: r[1] for r in context.session.execute(sel).fetchall()}


@db_api.placement_context_manager.reader
def _anchors_for_sharing_providers(context, rp_ids, get_id=False):
    """Given a list of internal IDs of sharing providers, returns a set of
    tuples of (sharing provider UUID, anchor provider UUID), where each of
    anchor is the unique root provider of a tree associated with the same
    aggregate as the sharing provider. (These are the providers that can
    "anchor" a single AllocationRequest.)

    The sharing provider may or may not itself be part of a tree; in either
    case, an entry for this root provider is included in the result.

    If the sharing provider is not part of any aggregate, the empty list is
    returned.

    If get_id is True, it returns a set of tuples of (sharing provider ID,
    anchor provider ID) instead.
    """
    # SELECT sps.uuid, COALESCE(rps.uuid, shr_with_sps.uuid)
    # FROM resource_providers AS sps
    # INNER JOIN resource_provider_aggregates AS shr_aggs
    #   ON sps.id = shr_aggs.resource_provider_id
    # INNER JOIN resource_provider_aggregates AS shr_with_sps_aggs
    #   ON shr_aggs.aggregate_id = shr_with_sps_aggs.aggregate_id
    # INNER JOIN resource_providers AS shr_with_sps
    #   ON shr_with_sps_aggs.resource_provider_id = shr_with_sps.id
    # LEFT JOIN resource_providers AS rps
    #   ON shr_with_sps.root_provider_id = rps.id
    # WHERE sps.id IN $(RP_IDs)
    rps = sa.alias(_RP_TBL, name='rps')
    sps = sa.alias(_RP_TBL, name='sps')
    shr_aggs = sa.alias(_RP_AGG_TBL, name='shr_aggs')
    shr_with_sps_aggs = sa.alias(_RP_AGG_TBL, name='shr_with_sps_aggs')
    shr_with_sps = sa.alias(_RP_TBL, name='shr_with_sps')
    join_chain = sa.join(
        sps, shr_aggs, sps.c.id == shr_aggs.c.resource_provider_id)
    join_chain = sa.join(
        join_chain, shr_with_sps_aggs,
        shr_aggs.c.aggregate_id == shr_with_sps_aggs.c.aggregate_id)
    join_chain = sa.join(
        join_chain, shr_with_sps,
        shr_with_sps_aggs.c.resource_provider_id == shr_with_sps.c.id)
    if get_id:
        # TODO(yikun): Change `func.coalesce(shr_with_sps.c.root_provider_id,
        # shr_with_sps.c.id)` to `shr_with_sps.c.root_provider_id` when we are
        # sure all root_provider_id values are NOT NULL
        sel = sa.select([sps.c.id, func.coalesce(
            shr_with_sps.c.root_provider_id, shr_with_sps.c.id)])
    else:
        # TODO(efried): Change this to an inner join and change
        # 'func.coalesce(rps.c.uuid, shr_with_sps.c.uuid)' to `rps.c.uuid`
        # when we are sure all root_provider_id values are NOT NULL
        join_chain = sa.outerjoin(
            join_chain, rps, shr_with_sps.c.root_provider_id == rps.c.id)
        sel = sa.select([sps.c.uuid, func.coalesce(rps.c.uuid,
                                                   shr_with_sps.c.uuid)])
    sel = sel.select_from(join_chain)
    sel = sel.where(sps.c.id.in_(rp_ids))
    return set([(r[0], r[1]) for r in context.session.execute(sel).fetchall()])


def _ensure_aggregate(ctx, agg_uuid):
    """Finds an aggregate and returns its internal ID. If not found, creates
    the aggregate and returns the new aggregate's internal ID.

    If there is a race to create the aggregate (which can happen under rare
    high load conditions), retry up to 10 times.
    """
    sel = sa.select([_AGG_TBL.c.id]).where(_AGG_TBL.c.uuid == agg_uuid)
    res = ctx.session.execute(sel).fetchone()
    if res:
        return res[0]

    LOG.debug("_ensure_aggregate() did not find aggregate %s. "
              "Attempting to create it.", agg_uuid)
    try:
        ins_stmt = _AGG_TBL.insert().values(uuid=agg_uuid)
        res = ctx.session.execute(ins_stmt)
        agg_id = res.inserted_primary_key[0]
        LOG.debug("_ensure_aggregate() created new aggregate %s (id=%d).",
                  agg_uuid, agg_id)
        return agg_id
    except db_exc.DBDuplicateEntry:
        # Something else added this agg_uuid in between our initial
        # fetch above and when we tried flushing this session.
        LOG.debug("_ensure_provider() failed to create new aggregate %s. "
                  "Another thread already created an aggregate record. ",
                  agg_uuid)
        raise


# _ensure_aggregate() can raise DBDuplicateEntry. Then we must start a new
# transaction because the new aggregate entry can't be found in the old
# transaction if the isolation level is set to "REPEATABLE_READ"
@oslo_db_api.wrap_db_retry(
    max_retries=10, inc_retry_interval=False,
    exception_checker=lambda exc: isinstance(exc, db_exc.DBDuplicateEntry))
@db_api.placement_context_manager.writer
def _set_aggregates(context, resource_provider, provided_aggregates,
                    increment_generation=False):
    rp_id = resource_provider.id
    # When aggregate uuids are persisted no validation is done
    # to ensure that they refer to something that has meaning
    # elsewhere. It is assumed that code which makes use of the
    # aggregates, later, will validate their fitness.
    # TODO(cdent): At the moment we do not delete
    # a PlacementAggregate that no longer has any associations
    # with at least one resource provider. We may wish to do that
    # to avoid bloat if it turns out we're creating a lot of noise.
    # Not doing now to move things along.
    provided_aggregates = set(provided_aggregates)
    existing_aggregates = _get_aggregates_by_provider_id(context, rp_id)
    agg_uuids_to_add = provided_aggregates - set(existing_aggregates.values())
    # A dict, keyed by internal aggregate ID, of aggregate UUIDs that will be
    # associated with the provider
    aggs_to_associate = {}
    # Same dict for those aggregates to remove the association with this
    # provider
    aggs_to_disassociate = {
        agg_id: agg_uuid for agg_id, agg_uuid in existing_aggregates.items()
        if agg_uuid not in provided_aggregates
    }

    # Create any aggregates that do not yet exist in
    # PlacementAggregates. This is different from
    # the set in existing_aggregates; those are aggregates for
    # which there are associations for the resource provider
    # at rp_id. The following loop checks for the existence of any
    # aggregate with the provided uuid. In this way we only
    # create a new row in the PlacementAggregate table if the
    # aggregate uuid has never been seen before. Code further
    # below will update the associations.
    for agg_uuid in agg_uuids_to_add:
        agg_id = _ensure_aggregate(context, agg_uuid)
        aggs_to_associate[agg_id] = agg_uuid

    for agg_id, agg_uuid in aggs_to_associate.items():
        try:
            ins_stmt = _RP_AGG_TBL.insert().values(
                resource_provider_id=rp_id, aggregate_id=agg_id)
            context.session.execute(ins_stmt)
            LOG.debug("Setting aggregates for provider %s. Successfully "
                      "associated aggregate %s.",
                      resource_provider.uuid, agg_uuid)
        except db_exc.DBDuplicateEntry:
            LOG.debug("Setting aggregates for provider %s. Another thread "
                      "already associated aggregate %s. Skipping.",
                      resource_provider.uuid, agg_uuid)
            pass

    for agg_id, agg_uuid in aggs_to_disassociate.items():
        del_stmt = _RP_AGG_TBL.delete().where(
            sa.and_(
                _RP_AGG_TBL.c.resource_provider_id == rp_id,
                _RP_AGG_TBL.c.aggregate_id == agg_id))
        context.session.execute(del_stmt)
        LOG.debug("Setting aggregates for provider %s. Successfully "
                  "disassociated aggregate %s.",
                  resource_provider.uuid, agg_uuid)

    if increment_generation:
        resource_provider.increment_generation()


@db_api.placement_context_manager.reader
def _get_traits_by_provider_id(context, rp_id):
    t = sa.alias(_TRAIT_TBL, name='t')
    rpt = sa.alias(_RP_TRAIT_TBL, name='rpt')

    join_cond = sa.and_(t.c.id == rpt.c.trait_id,
                        rpt.c.resource_provider_id == rp_id)
    join = sa.join(t, rpt, join_cond)
    sel = sa.select([t.c.id, t.c.name,
                     t.c.created_at, t.c.updated_at]).select_from(join)
    return [dict(r) for r in context.session.execute(sel).fetchall()]


def _add_traits_to_provider(ctx, rp_id, to_add):
    """Adds trait associations to the provider with the supplied ID.

    :param ctx: `placement.context.RequestContext` that has an oslo_db Session
    :param rp_id: Internal ID of the resource provider on which to add
                  trait associations
    :param to_add: set() containing internal trait IDs for traits to add
    """
    for trait_id in to_add:
        try:
            ins_stmt = _RP_TRAIT_TBL.insert().values(
                resource_provider_id=rp_id,
                trait_id=trait_id)
            ctx.session.execute(ins_stmt)
        except db_exc.DBDuplicateEntry:
            # Another thread already set this trait for this provider. Ignore
            # this for now (but ConcurrentUpdateDetected will end up being
            # raised almost assuredly when we go to increment the resource
            # provider's generation later, but that's also fine)
            pass


def _delete_traits_from_provider(ctx, rp_id, to_delete):
    """Deletes trait associations from the provider with the supplied ID and
    set() of internal trait IDs.

    :param ctx: `placement.context.RequestContext` that has an oslo_db Session
    :param rp_id: Internal ID of the resource provider from which to delete
                  trait associations
    :param to_delete: set() containing internal trait IDs for traits to
                      delete
    """
    del_stmt = _RP_TRAIT_TBL.delete().where(
        sa.and_(
            _RP_TRAIT_TBL.c.resource_provider_id == rp_id,
            _RP_TRAIT_TBL.c.trait_id.in_(to_delete)))
    ctx.session.execute(del_stmt)


@db_api.placement_context_manager.writer
def _set_traits(context, rp, traits):
    """Given a ResourceProvider object and a TraitList object, replaces the set
    of traits associated with the resource provider.

    :raises: ConcurrentUpdateDetected if the resource provider's traits or
             inventory was changed in between the time when we first started to
             set traits and the end of this routine.

    :param rp: The ResourceProvider object to set traits against
    :param traits: A TraitList object or list of Trait objects
    """
    # Get the internal IDs of our existing traits
    existing_traits = _get_traits_by_provider_id(context, rp.id)
    existing_traits = set(rec['id'] for rec in existing_traits)
    want_traits = set(trait.id for trait in traits)

    to_add = want_traits - existing_traits
    to_delete = existing_traits - want_traits

    if not to_add and not to_delete:
        return

    if to_delete:
        _delete_traits_from_provider(context, rp.id, to_delete)
    if to_add:
        _add_traits_to_provider(context, rp.id, to_add)
    rp.increment_generation()


@db_api.placement_context_manager.reader
def _has_child_providers(context, rp_id):
    """Returns True if the supplied resource provider has any child providers,
    False otherwise
    """
    child_sel = sa.select([_RP_TBL.c.id])
    child_sel = child_sel.where(_RP_TBL.c.parent_provider_id == rp_id)
    child_res = context.session.execute(child_sel.limit(1)).fetchone()
    if child_res:
        return True
    return False


@db_api.placement_context_manager.writer
def _set_root_provider_id(context, rp_id, root_id):
    """Simply sets the root_provider_id value for a provider identified by
    rp_id. Used in implicit online data migration via REST API getting
    resource providers.

    :param rp_id: Internal ID of the provider to update
    :param root_id: Value to set root provider to
    """
    upd = _RP_TBL.update().where(_RP_TBL.c.id == rp_id)
    upd = upd.values(root_provider_id=root_id)
    context.session.execute(upd)


@db_api.placement_context_manager.writer
def set_root_provider_ids(context, batch_size):
    """Simply sets the root_provider_id value for a provider identified by
    rp_id. Used in explicit online data migration via CLI.

    :param rp_id: Internal ID of the provider to update
    :param root_id: Value to set root provider to
    """
    # UPDATE resource_providers
    # SET root_provider_id=resource_providers.id
    # WHERE resource_providers.id
    # IN (SELECT subq_1.id
    #     FROM (SELECT resource_providers.id AS id
    #           FROM resource_providers
    #           WHERE resource_providers.root_provider_id IS NULL
    #           LIMIT :param_1)
    #     AS subq_1)

    subq_1 = context.session.query(_RP_TBL.c.id)
    subq_1 = subq_1.filter(_RP_TBL.c.root_provider_id.is_(None))
    subq_1 = subq_1.limit(batch_size)
    subq_1 = sa.alias(subq_1.as_scalar(), name="subq_1")

    subq_2 = sa.select([subq_1.c.id]).select_from(subq_1)

    upd = _RP_TBL.update().where(_RP_TBL.c.id.in_(subq_2.as_scalar()))
    upd = upd.values(root_provider_id=_RP_TBL.c.id)
    res = context.session.execute(upd)

    return res.rowcount, res.rowcount


ProviderIds = collections.namedtuple(
    'ProviderIds', 'id uuid parent_id parent_uuid root_id root_uuid')


def _provider_ids_from_rp_ids(context, rp_ids):
    """Given an iterable of internal resource provider IDs, returns a dict,
    keyed by internal provider Id, of ProviderIds namedtuples describing those
    providers.

    :returns: dict, keyed by internal provider Id, of ProviderIds namedtuples
    :param rp_ids: iterable of internal provider IDs to look up
    """
    # SELECT
    #   rp.id, rp.uuid,
    #   parent.id AS parent_id, parent.uuid AS parent_uuid,
    #   root.id AS root_id, root.uuid AS root_uuid
    # FROM resource_providers AS rp
    # LEFT JOIN resource_providers AS parent
    #   ON rp.parent_provider_id = parent.id
    # LEFT JOIN resource_providers AS root
    #   ON rp.root_provider_id = root.id
    # WHERE rp.id IN ($rp_ids)
    me = sa.alias(_RP_TBL, name="me")
    parent = sa.alias(_RP_TBL, name="parent")
    root = sa.alias(_RP_TBL, name="root")
    cols = [
        me.c.id,
        me.c.uuid,
        parent.c.id.label('parent_id'),
        parent.c.uuid.label('parent_uuid'),
        root.c.id.label('root_id'),
        root.c.uuid.label('root_uuid'),
    ]
    # TODO(jaypipes): Change this to an inner join when we are sure all
    # root_provider_id values are NOT NULL
    me_to_root = sa.outerjoin(me, root, me.c.root_provider_id == root.c.id)
    me_to_parent = sa.outerjoin(
        me_to_root, parent,
        me.c.parent_provider_id == parent.c.id)
    sel = sa.select(cols).select_from(me_to_parent)
    sel = sel.where(me.c.id.in_(rp_ids))

    ret = {}
    for r in context.session.execute(sel):
        # Use its id/uuid for the root id/uuid if the root id/uuid is None
        # TODO(tetsuro): Remove this to when we are sure all root_provider_id
        # values are NOT NULL
        d = dict(r)
        if d['root_id'] is None:
            d['root_id'] = d['id']
            d['root_uuid'] = d['uuid']
        ret[d['id']] = ProviderIds(**d)
    return ret


def _provider_ids_from_uuid(context, uuid):
    """Given the UUID of a resource provider, returns a namedtuple
    (ProviderIds) with the internal ID, the UUID, the parent provider's
    internal ID, parent provider's UUID, the root provider's internal ID and
    the root provider UUID.

    :returns: ProviderIds object containing the internal IDs and UUIDs of the
              provider identified by the supplied UUID
    :param uuid: The UUID of the provider to look up
    """
    # SELECT
    #   rp.id, rp.uuid,
    #   parent.id AS parent_id, parent.uuid AS parent_uuid,
    #   root.id AS root_id, root.uuid AS root_uuid
    # FROM resource_providers AS rp
    # LEFT JOIN resource_providers AS parent
    #   ON rp.parent_provider_id = parent.id
    # LEFT JOIN resource_providers AS root
    #   ON rp.root_provider_id = root.id
    me = sa.alias(_RP_TBL, name="me")
    parent = sa.alias(_RP_TBL, name="parent")
    root = sa.alias(_RP_TBL, name="root")
    cols = [
        me.c.id,
        me.c.uuid,
        parent.c.id.label('parent_id'),
        parent.c.uuid.label('parent_uuid'),
        root.c.id.label('root_id'),
        root.c.uuid.label('root_uuid'),
    ]
    # TODO(jaypipes): Change this to an inner join when we are sure all
    # root_provider_id values are NOT NULL
    me_to_root = sa.outerjoin(me, root, me.c.root_provider_id == root.c.id)
    me_to_parent = sa.outerjoin(
        me_to_root, parent,
        me.c.parent_provider_id == parent.c.id)
    sel = sa.select(cols).select_from(me_to_parent)
    sel = sel.where(me.c.uuid == uuid)
    res = context.session.execute(sel).fetchone()
    if not res:
        return None
    return ProviderIds(**dict(res))


def _provider_ids_matching_aggregates(context, member_of, rp_ids=None):
    """Given a list of lists of aggregate UUIDs, return the internal IDs of all
    resource providers associated with the aggregates.

    :param member_of: A list containing lists of aggregate UUIDs. Each item in
        the outer list is to be AND'd together. If that item contains multiple
        values, they are OR'd together.

        For example, if member_of is::

            [
                ['agg1'],
                ['agg2', 'agg3'],
            ]

        we will return all the resource providers that are
        associated with agg1 as well as either (agg2 or agg3)
    :param rp_ids: When present, returned resource providers are limited
        to only those in this value

    :returns: A set of internal resource provider IDs having all required
        aggregate associations
    """
    # Given a request for the following:
    #
    # member_of = [
    #   [agg1],
    #   [agg2],
    #   [agg3, agg4]
    # ]
    #
    # we need to produce the following SQL expression:
    #
    # SELECT
    #   rp.id
    # FROM resource_providers AS rp
    # JOIN resource_provider_aggregates AS rpa1
    #   ON rp.id = rpa1.resource_provider_id
    #   AND rpa1.aggregate_id IN ($AGG1_ID)
    # JOIN resource_provider_aggregates AS rpa2
    #   ON rp.id = rpa2.resource_provider_id
    #   AND rpa2.aggregate_id IN ($AGG2_ID)
    # JOIN resource_provider_aggregates AS rpa3
    #   ON rp.id = rpa3.resource_provider_id
    #   AND rpa3.aggregate_id IN ($AGG3_ID, $AGG4_ID)
    # # Only if we have rp_ids...
    # WHERE rp.id IN ($RP_IDs)

    # First things first, get a map of all the aggregate UUID to internal
    # aggregate IDs
    agg_uuids = set()
    for members in member_of:
        for member in members:
            agg_uuids.add(member)
    agg_tbl = sa.alias(_AGG_TBL, name='aggs')
    agg_sel = sa.select([agg_tbl.c.uuid, agg_tbl.c.id])
    agg_sel = agg_sel.where(agg_tbl.c.uuid.in_(agg_uuids))
    agg_uuid_map = {
        r[0]: r[1] for r in context.session.execute(agg_sel).fetchall()
    }

    rp_tbl = sa.alias(_RP_TBL, name='rp')
    join_chain = rp_tbl

    for x, members in enumerate(member_of):
        rpa_tbl = sa.alias(_RP_AGG_TBL, name='rpa%d' % x)

        agg_ids = [agg_uuid_map[member] for member in members
                   if member in agg_uuid_map]
        if not agg_ids:
            # This member_of list contains only non-existent aggregate UUIDs
            # and therefore we will always return 0 results, so short-circuit
            return set()

        join_cond = sa.and_(
            rp_tbl.c.id == rpa_tbl.c.resource_provider_id,
            rpa_tbl.c.aggregate_id.in_(agg_ids))
        join_chain = sa.join(join_chain, rpa_tbl, join_cond)
    sel = sa.select([rp_tbl.c.id]).select_from(join_chain)
    if rp_ids:
        sel = sel.where(rp_tbl.c.id.in_(rp_ids))
    return set(r[0] for r in context.session.execute(sel))


@db_api.placement_context_manager.writer
def _delete_rp_record(context, _id):
    query = context.session.query(models.ResourceProvider)
    query = query.filter(models.ResourceProvider.id == _id)
    return query.delete(synchronize_session=False)


class ResourceProvider(object):
    SETTABLE_FIELDS = ('name', 'parent_provider_uuid')

    def __init__(self, context, id=None, uuid=None, name=None,
                 generation=None, parent_provider_uuid=None,
                 root_provider_uuid=None, updated_at=None, created_at=None):
        self._context = context
        self.id = id
        self.uuid = uuid
        self.name = name
        self.generation = generation
        # UUID of the root provider in a hierarchy of providers. Will be equal
        # to the uuid field if this provider is the root provider of a
        # hierarchy. This field is never manually set by the user. Instead, it
        # is automatically set to either the root provider UUID of the parent
        # or the UUID of the provider itself if there is no parent. This field
        # is an optimization field that allows us to very quickly query for all
        # providers within a particular tree without doing any recursive
        # querying.
        self.root_provider_uuid = root_provider_uuid
        # UUID of the direct parent provider, or None if this provider is a
        # "root" provider.
        self.parent_provider_uuid = parent_provider_uuid
        self.updated_at = updated_at
        self.created_at = created_at

    def create(self):
        if self.id is not None:
            raise exception.ObjectActionError(action='create',
                                              reason='already created')
        if self.uuid is None:
            raise exception.ObjectActionError(action='create',
                                              reason='uuid is required')
        if not self.name:
            raise exception.ObjectActionError(action='create',
                                              reason='name is required')

        # These are the only fields we are willing to create with.
        # If there are others, ignore them.
        updates = {
            'name': self.name,
            'uuid': self.uuid,
            'parent_provider_uuid': self.parent_provider_uuid,
        }
        self._create_in_db(self._context, updates)

    def destroy(self):
        self._delete(self._context, self.id)

    def save(self):
        # These are the only fields we are willing to save with.
        # If there are others, ignore them.
        updates = {
            'name': self.name,
            'parent_provider_uuid': self.parent_provider_uuid,
        }
        self._update_in_db(self._context, self.id, updates)

    @classmethod
    def get_by_uuid(cls, context, uuid):
        """Returns a new ResourceProvider object with the supplied UUID.

        :raises NotFound if no such provider could be found
        :param uuid: UUID of the provider to search for
        """
        rp_rec = _get_provider_by_uuid(context, uuid)
        return cls._from_db_object(context, cls(context), rp_rec)

    def add_inventory(self, inventory):
        """Add one new Inventory to the resource provider.

        Fails if Inventory of the provided resource class is
        already present.
        """
        _add_inventory(self._context, self, inventory)

    def delete_inventory(self, resource_class):
        """Delete Inventory of provided resource_class."""
        _delete_inventory(self._context, self, resource_class)

    def set_inventory(self, inv_list):
        """Set all resource provider Inventory to be the provided list."""
        exceeded = _set_inventory(self._context, self, inv_list)
        for uuid, rclass in exceeded:
            LOG.warning('Resource provider %(uuid)s is now over-'
                        'capacity for %(resource)s',
                        {'uuid': uuid, 'resource': rclass})

    def update_inventory(self, inventory):
        """Update one existing Inventory of the same resource class.

        Fails if no Inventory of the same class is present.
        """
        exceeded = _update_inventory(self._context, self, inventory)
        for uuid, rclass in exceeded:
            LOG.warning('Resource provider %(uuid)s is now over-'
                        'capacity for %(resource)s',
                        {'uuid': uuid, 'resource': rclass})

    def get_aggregates(self):
        """Get the aggregate uuids associated with this resource provider."""
        return list(
            _get_aggregates_by_provider_id(self._context, self.id).values())

    def set_aggregates(self, aggregate_uuids, increment_generation=False):
        """Set the aggregate uuids associated with this resource provider.

        If an aggregate does not exist, one will be created using the
        provided uuid.

        The resource provider generation is incremented if and only if the
        increment_generation parameter is True.
        """
        _set_aggregates(self._context, self, aggregate_uuids,
                        increment_generation=increment_generation)

    def set_traits(self, traits):
        """Replaces the set of traits associated with the resource provider
        with the given list of Trait objects.

        :param traits: A list of Trait objects representing the traits to
                       associate with the provider.
        """
        _set_traits(self._context, self, traits)

    def increment_generation(self):
        """Increments this provider's generation value, supplying the
        currently-known generation.

        :raises placement.exception.ConcurrentUpdateDetected: if another thread
                updated the resource provider's view of its inventory or
                allocations in between the time when this object was originally
                read and the call to set the inventory.
        """
        rp_gen = self.generation
        new_generation = rp_gen + 1
        upd_stmt = _RP_TBL.update().where(sa.and_(
            _RP_TBL.c.id == self.id,
            _RP_TBL.c.generation == rp_gen)).values(
            generation=new_generation)

        res = self._context.session.execute(upd_stmt)
        if res.rowcount != 1:
            raise exception.ResourceProviderConcurrentUpdateDetected()
        self.generation = new_generation

    @db_api.placement_context_manager.writer
    def _create_in_db(self, context, updates):
        parent_id = None
        root_id = None
        # User supplied a parent, let's make sure it exists
        parent_uuid = updates.pop('parent_provider_uuid')
        if parent_uuid is not None:
            # Setting parent to ourselves doesn't make any sense
            if parent_uuid == self.uuid:
                raise exception.ObjectActionError(
                    action='create',
                    reason=_('parent provider UUID cannot be same as UUID. '
                             'Please set parent provider UUID to None if '
                             'there is no parent.'))

            parent_ids = _provider_ids_from_uuid(context, parent_uuid)
            if parent_ids is None:
                raise exception.ObjectActionError(
                    action='create',
                    reason=_('parent provider UUID does not exist.'))

            parent_id = parent_ids.id
            root_id = parent_ids.root_id
            updates['root_provider_id'] = root_id
            updates['parent_provider_id'] = parent_id
            self.root_provider_uuid = parent_ids.root_uuid

        db_rp = models.ResourceProvider()
        db_rp.update(updates)
        context.session.add(db_rp)
        context.session.flush()

        self.id = db_rp.id
        self.generation = db_rp.generation

        if root_id is None:
            # User did not specify a parent when creating this provider, so the
            # root_provider_id needs to be set to this provider's newly-created
            # internal ID
            db_rp.root_provider_id = db_rp.id
            context.session.add(db_rp)
            context.session.flush()
            self.root_provider_uuid = self.uuid

    @staticmethod
    @db_api.placement_context_manager.writer
    def _delete(context, _id):
        # Do a quick check to see if the provider is a parent. If it is, don't
        # allow deleting the provider. Note that the foreign key constraint on
        # resource_providers.parent_provider_id will prevent deletion of the
        # parent within the transaction below. This is just a quick
        # short-circuit outside of the transaction boundary.
        if _has_child_providers(context, _id):
            raise exception.CannotDeleteParentResourceProvider()

        # Don't delete the resource provider if it has allocations.
        rp_allocations = context.session.query(models.Allocation).filter(
            models.Allocation.resource_provider_id == _id).count()
        if rp_allocations:
            raise exception.ResourceProviderInUse()
        # Delete any inventory associated with the resource provider
        query = context.session.query(models.Inventory)
        query = query.filter(models.Inventory.resource_provider_id == _id)
        query.delete(synchronize_session=False)
        # Delete any aggregate associations for the resource provider
        # The name substitution on the next line is needed to satisfy pep8
        RPA_model = models.ResourceProviderAggregate
        context.session.query(RPA_model).filter(
            RPA_model.resource_provider_id == _id).delete()
        # delete any trait associations for the resource provider
        RPT_model = models.ResourceProviderTrait
        context.session.query(RPT_model).filter(
            RPT_model.resource_provider_id == _id).delete()
        # set root_provider_id to null to make deletion possible
        query = context.session.query(models.ResourceProvider)
        query = query.filter(
            models.ResourceProvider.id == _id,
            models.ResourceProvider.root_provider_id == _id)
        query.update({'root_provider_id': None})
        # Now delete the RP record
        try:
            result = _delete_rp_record(context, _id)
        except sqla_exc.IntegrityError:
            # NOTE(jaypipes): Another thread snuck in and parented this
            # resource provider in between the above check for
            # _has_child_providers() and our attempt to delete the record
            raise exception.CannotDeleteParentResourceProvider()
        if not result:
            raise exception.NotFound()

    @db_api.placement_context_manager.writer
    def _update_in_db(self, context, id, updates):
        # A list of resource providers in the same tree with the
        # resource provider to update
        same_tree = []
        if 'parent_provider_uuid' in updates:
            # TODO(jaypipes): For now, "re-parenting" and "un-parenting" are
            # not possible. If the provider already had a parent, we don't
            # allow changing that parent due to various issues, including:
            #
            # * if the new parent is a descendant of this resource provider, we
            #   introduce the possibility of a loop in the graph, which would
            #   be very bad
            # * potentially orphaning heretofore-descendants
            #
            # So, for now, let's just prevent re-parenting...
            my_ids = _provider_ids_from_uuid(context, self.uuid)
            parent_uuid = updates.pop('parent_provider_uuid')
            if parent_uuid is not None:
                parent_ids = _provider_ids_from_uuid(context, parent_uuid)
                # User supplied a parent, let's make sure it exists
                if parent_ids is None:
                    raise exception.ObjectActionError(
                        action='create',
                        reason=_('parent provider UUID does not exist.'))
                if (my_ids.parent_id is not None and
                        my_ids.parent_id != parent_ids.id):
                    raise exception.ObjectActionError(
                        action='update',
                        reason=_('re-parenting a provider is not currently '
                                 'allowed.'))
                if my_ids.parent_uuid is None:
                    # So the user specifies a parent for an RP that doesn't
                    # have one. We have to check that by this new parent we
                    # don't create a loop in the tree. Basically the new parent
                    # cannot be the RP itself or one of its descendants.
                    # However as the RP's current parent is None the above
                    # condition is the same as "the new parent cannot be any RP
                    # from the current RP tree".
                    same_tree = ResourceProviderList.get_all_by_filters(
                        context,
                        filters={'in_tree': self.uuid})
                    rp_uuids_in_the_same_tree = [rp.uuid for rp in same_tree]
                    if parent_uuid in rp_uuids_in_the_same_tree:
                        raise exception.ObjectActionError(
                            action='update',
                            reason=_('creating loop in the provider tree is '
                                     'not allowed.'))

                updates['root_provider_id'] = parent_ids.root_id
                updates['parent_provider_id'] = parent_ids.id
                self.root_provider_uuid = parent_ids.root_uuid
            else:
                if my_ids.parent_id is not None:
                    raise exception.ObjectActionError(
                        action='update',
                        reason=_('un-parenting a provider is not currently '
                                 'allowed.'))

        db_rp = context.session.query(models.ResourceProvider).filter_by(
            id=id).first()
        db_rp.update(updates)
        context.session.add(db_rp)

        # We should also update the root providers of resource providers
        # originally in the same tree. If re-parenting is supported,
        # this logic should be changed to update only descendents of the
        # re-parented resource providers, not all the providers in the tree.
        for rp in same_tree:
            # If the parent is not updated, this clause is skipped since the
            # `same_tree` has no element.
            rp.root_provider_uuid = parent_ids.root_uuid
            db_rp = context.session.query(
                models.ResourceProvider).filter_by(id=rp.id).first()
            data = {'root_provider_id': parent_ids.root_id}
            db_rp.update(data)
            context.session.add(db_rp)

        try:
            context.session.flush()
        except sqla_exc.IntegrityError:
            # NOTE(jaypipes): Another thread snuck in and deleted the parent
            # for this resource provider in between the above check for a valid
            # parent provider and here...
            raise exception.ObjectActionError(
                action='update',
                reason=_('parent provider UUID does not exist.'))

    @staticmethod
    @db_api.placement_context_manager.writer  # For online data migration
    def _from_db_object(context, resource_provider, db_resource_provider):
        # Online data migration to populate root_provider_id
        # TODO(jaypipes): Remove when all root_provider_id values are NOT NULL
        if db_resource_provider['root_provider_uuid'] is None:
            rp_id = db_resource_provider['id']
            uuid = db_resource_provider['uuid']
            db_resource_provider['root_provider_uuid'] = uuid
            _set_root_provider_id(context, rp_id, rp_id)
        for field in ['id', 'uuid', 'name', 'generation',
                      'root_provider_uuid', 'parent_provider_uuid',
                      'updated_at', 'created_at']:
            setattr(resource_provider, field, db_resource_provider[field])
        return resource_provider


@db_api.placement_context_manager.reader
def _get_providers_with_shared_capacity(ctx, rc_id, amount, member_of=None):
    """Returns a list of resource provider IDs (internal IDs, not UUIDs)
    that have capacity for a requested amount of a resource and indicate that
    they share resource via an aggregate association.

    Shared resource providers are marked with a standard trait called
    MISC_SHARES_VIA_AGGREGATE. This indicates that the provider allows its
    inventory to be consumed by other resource providers associated via an
    aggregate link.

    For example, assume we have two compute nodes, CN_1 and CN_2, each with
    inventory of VCPU and MEMORY_MB but not DISK_GB (in other words, these are
    compute nodes with no local disk). There is a resource provider called
    "NFS_SHARE" that has an inventory of DISK_GB and has the
    MISC_SHARES_VIA_AGGREGATE trait. Both the "CN_1" and "CN_2" compute node
    resource providers and the "NFS_SHARE" resource provider are associated
    with an aggregate called "AGG_1".

    The scheduler needs to determine the resource providers that can fulfill a
    request for 2 VCPU, 1024 MEMORY_MB and 100 DISK_GB.

    Clearly, no single provider can satisfy the request for all three
    resources, since neither compute node has DISK_GB inventory and the
    NFS_SHARE provider has no VCPU or MEMORY_MB inventories.

    However, if we consider the NFS_SHARE resource provider as providing
    inventory of DISK_GB for both CN_1 and CN_2, we can include CN_1 and CN_2
    as potential fits for the requested set of resources.

    To facilitate that matching query, this function returns all providers that
    indicate they share their inventory with providers in some aggregate and
    have enough capacity for the requested amount of a resource.

    To follow the example above, if we were to call
    _get_providers_with_shared_capacity(ctx, "DISK_GB", 100), we would want to
    get back the ID for the NFS_SHARE resource provider.

    :param rc_id: Internal ID of the requested resource class.
    :param amount: Amount of the requested resource.
    :param member_of: When present, contains a list of lists of aggregate
                      uuids that are used to filter the returned list of
                      resource providers that *directly* belong to the
                      aggregates referenced.
    """
    # The SQL we need to generate here looks like this:
    #
    # SELECT rp.id
    # FROM resource_providers AS rp
    #   INNER JOIN resource_provider_traits AS rpt
    #     ON rp.id = rpt.resource_provider_id
    #   INNER JOIN traits AS t
    #     ON rpt.trait_id = t.id
    #     AND t.name = "MISC_SHARES_VIA_AGGREGATE"
    #   INNER JOIN inventories AS inv
    #     ON rp.id = inv.resource_provider_id
    #     AND inv.resource_class_id = $rc_id
    #   LEFT JOIN (
    #     SELECT resource_provider_id, SUM(used) as used
    #     FROM allocations
    #     WHERE resource_class_id = $rc_id
    #     GROUP BY resource_provider_id
    #   ) AS usage
    #     ON rp.id = usage.resource_provider_id
    # WHERE COALESCE(usage.used, 0) + $amount <= (
    #   inv.total - inv.reserved) * inv.allocation_ratio
    # ) AND
    #   inv.min_unit <= $amount AND
    #   inv.max_unit >= $amount AND
    #   $amount % inv.step_size = 0
    # GROUP BY rp.id

    rp_tbl = sa.alias(_RP_TBL, name='rp')
    inv_tbl = sa.alias(_INV_TBL, name='inv')
    t_tbl = sa.alias(_TRAIT_TBL, name='t')
    rpt_tbl = sa.alias(_RP_TRAIT_TBL, name='rpt')

    rp_to_rpt_join = sa.join(
        rp_tbl, rpt_tbl,
        rp_tbl.c.id == rpt_tbl.c.resource_provider_id,
    )

    rpt_to_t_join = sa.join(
        rp_to_rpt_join, t_tbl,
        sa.and_(
            rpt_tbl.c.trait_id == t_tbl.c.id,
            # The traits table wants unicode trait names, but os_traits
            # presents native str, so we need to cast.
            t_tbl.c.name == six.text_type(os_traits.MISC_SHARES_VIA_AGGREGATE),
        ),
    )

    rp_to_inv_join = sa.join(
        rpt_to_t_join, inv_tbl,
        sa.and_(
            rpt_tbl.c.resource_provider_id == inv_tbl.c.resource_provider_id,
            inv_tbl.c.resource_class_id == rc_id,
        ),
    )

    usage = _usage_select([rc_id])

    inv_to_usage_join = sa.outerjoin(
        rp_to_inv_join, usage,
        inv_tbl.c.resource_provider_id == usage.c.resource_provider_id,
    )

    where_conds = _capacity_check_clause(amount, usage, inv_tbl=inv_tbl)

    # If 'member_of' has values, do a separate lookup to identify the
    # resource providers that meet the member_of constraints.
    if member_of:
        rps_in_aggs = _provider_ids_matching_aggregates(ctx, member_of)
        if not rps_in_aggs:
            # Short-circuit. The user either asked for a non-existing
            # aggregate or there were no resource providers that matched
            # the requirements...
            return []
        where_conds.append(rp_tbl.c.id.in_(rps_in_aggs))

    sel = sa.select([rp_tbl.c.id]).select_from(inv_to_usage_join)
    sel = sel.where(where_conds)
    sel = sel.group_by(rp_tbl.c.id)

    return [r[0] for r in ctx.session.execute(sel)]


class ResourceProviderList(common_obj.ObjectList):
    ITEM_CLS = ResourceProvider

    @staticmethod
    @db_api.placement_context_manager.reader
    def _get_all_by_filters_from_db(context, filters):
        # Eg. filters can be:
        #  filters = {
        #      'name': <name>,
        #      'uuid': <uuid>,
        #      'member_of': [[<aggregate_uuid>, <aggregate_uuid>],
        #                    [<aggregate_uuid>]]
        #      'resources': {
        #          'VCPU': 1,
        #          'MEMORY_MB': 1024
        #      },
        #      'in_tree': <uuid>,
        #      'required': [<trait_name>, ...]
        #  }
        if not filters:
            filters = {}
        else:
            # Since we modify the filters, copy them so that we don't modify
            # them in the calling program.
            filters = copy.deepcopy(filters)
        name = filters.pop('name', None)
        uuid = filters.pop('uuid', None)
        member_of = filters.pop('member_of', [])
        required = set(filters.pop('required', []))
        forbidden = set([trait for trait in required
                         if trait.startswith('!')])
        required = required - forbidden
        forbidden = set([trait.lstrip('!') for trait in forbidden])

        resources = filters.pop('resources', {})
        # NOTE(sbauza): We want to key the dict by the resource class IDs
        # and we want to make sure those class names aren't incorrect.
        resources = {rc_cache.RC_CACHE.id_from_string(r_name): amount
                     for r_name, amount in resources.items()}
        rp = sa.alias(_RP_TBL, name="rp")
        root_rp = sa.alias(_RP_TBL, name="root_rp")
        parent_rp = sa.alias(_RP_TBL, name="parent_rp")

        cols = [
            rp.c.id,
            rp.c.uuid,
            rp.c.name,
            rp.c.generation,
            rp.c.updated_at,
            rp.c.created_at,
            root_rp.c.uuid.label("root_provider_uuid"),
            parent_rp.c.uuid.label("parent_provider_uuid"),
        ]

        # TODO(jaypipes): Convert this to an inner join once all
        # root_provider_id values are NOT NULL
        rp_to_root = sa.outerjoin(
            rp, root_rp,
            rp.c.root_provider_id == root_rp.c.id)
        rp_to_parent = sa.outerjoin(
            rp_to_root, parent_rp,
            rp.c.parent_provider_id == parent_rp.c.id)

        query = sa.select(cols).select_from(rp_to_parent)

        if name:
            query = query.where(rp.c.name == name)
        if uuid:
            query = query.where(rp.c.uuid == uuid)
        if 'in_tree' in filters:
            # The 'in_tree' parameter is the UUID of a resource provider that
            # the caller wants to limit the returned providers to only those
            # within its "provider tree". So, we look up the resource provider
            # having the UUID specified by the 'in_tree' parameter and grab the
            # root_provider_id value of that record. We can then ask for only
            # those resource providers having a root_provider_id of that value.
            tree_uuid = filters.pop('in_tree')
            tree_ids = _provider_ids_from_uuid(context, tree_uuid)
            if tree_ids is None:
                # List operations should simply return an empty list when a
                # non-existing resource provider UUID is given.
                return []
            root_id = tree_ids.root_id
            # TODO(jaypipes): Remove this OR condition when root_provider_id
            # is not nullable in the database and all resource provider records
            # have populated the root provider ID.
            where_cond = sa.or_(
                rp.c.id == root_id,
                rp.c.root_provider_id == root_id)
            query = query.where(where_cond)

        # Get the provider IDs matching any specified traits and/or aggregates
        rp_ids, forbidden_rp_ids = _get_provider_ids_for_traits_and_aggs(
            context, required, forbidden, member_of)
        if rp_ids is None:
            # If no providers match the traits/aggs, we can short out
            return []
        if rp_ids:
            query = query.where(rp.c.id.in_(rp_ids))
        # forbidden providers, if found, are mutually exclusive with matching
        # providers above, so we only need to include this clause if we didn't
        # use the positive filter above.
        elif forbidden_rp_ids:
            query = query.where(~rp.c.id.in_(forbidden_rp_ids))

        if not resources:
            # Returns quickly the list in case we don't need to check the
            # resource usage
            res = context.session.execute(query).fetchall()
            return [dict(r) for r in res]

        # NOTE(sbauza): In case we want to look at the resource criteria, then
        # the SQL generated from this case looks something like:
        # SELECT
        #   rp.*
        # FROM resource_providers AS rp
        # JOIN inventories AS inv
        # ON rp.id = inv.resource_provider_id
        # LEFT JOIN (
        #    SELECT resource_provider_id, resource_class_id, SUM(used) AS used
        #    FROM allocations
        #    WHERE resource_class_id IN ($RESOURCE_CLASSES)
        #    GROUP BY resource_provider_id, resource_class_id
        # ) AS usage
        #     ON inv.resource_provider_id = usage.resource_provider_id
        #     AND inv.resource_class_id = usage.resource_class_id
        # AND (inv.resource_class_id = $X AND (used + $AMOUNT_X <= (
        #        total - reserved) * inv.allocation_ratio) AND
        #        inv.min_unit <= $AMOUNT_X AND inv.max_unit >= $AMOUNT_X AND
        #        $AMOUNT_X % inv.step_size == 0)
        #      OR (inv.resource_class_id = $Y AND (used + $AMOUNT_Y <= (
        #        total - reserved) * inv.allocation_ratio) AND
        #        inv.min_unit <= $AMOUNT_Y AND inv.max_unit >= $AMOUNT_Y AND
        #        $AMOUNT_Y % inv.step_size == 0)
        #      OR (inv.resource_class_id = $Z AND (used + $AMOUNT_Z <= (
        #        total - reserved) * inv.allocation_ratio) AND
        #        inv.min_unit <= $AMOUNT_Z AND inv.max_unit >= $AMOUNT_Z AND
        #        $AMOUNT_Z % inv.step_size == 0))
        # GROUP BY rp.id
        # HAVING
        #  COUNT(DISTINCT(inv.resource_class_id)) == len($RESOURCE_CLASSES)
        #
        # with a possible additional WHERE clause for the name and uuid that
        # comes from the above filters

        # First JOIN between inventories and RPs is here
        inv_join = sa.join(
            rp_to_parent,
            _INV_TBL,
            rp.c.id == _INV_TBL.c.resource_provider_id)

        # Now, below is the LEFT JOIN for getting the allocations usage
        usage = _usage_select(list(resources))
        usage_join = sa.outerjoin(
            inv_join, usage, sa.and_(
                usage.c.resource_provider_id == (
                    _INV_TBL.c.resource_provider_id),
                usage.c.resource_class_id == _INV_TBL.c.resource_class_id))

        # And finally, we verify for each resource class if the requested
        # amount isn't more than the left space (considering the allocation
        # ratio, the reserved space and the min and max amount possible sizes)
        where_clauses = [
            sa.and_(
                _INV_TBL.c.resource_class_id == r_idx,
                _capacity_check_clause(amount, usage)
            )
            for (r_idx, amount) in resources.items()]
        query = query.select_from(usage_join)
        query = query.where(sa.or_(*where_clauses))
        query = query.group_by(rp.c.id, root_rp.c.uuid, parent_rp.c.uuid)
        # NOTE(sbauza): Only RPs having all the asked resources can be provided
        query = query.having(sql.func.count(
            sa.distinct(_INV_TBL.c.resource_class_id)) == len(resources))

        res = context.session.execute(query).fetchall()
        return [dict(r) for r in res]

    @classmethod
    def get_all_by_filters(cls, context, filters=None):
        """Returns a list of `ResourceProvider` objects that have sufficient
        resources in their inventories to satisfy the amounts specified in the
        `filters` parameter.

        If no resource providers can be found, the function will return an
        empty list.

        :param context: `placement.context.RequestContext` that may be used to
                        grab a DB connection.
        :param filters: Can be `name`, `uuid`, `member_of`, `in_tree` or
                        `resources` where `member_of` is a list of list of
                        aggregate UUIDs, `in_tree` is a UUID of a resource
                        provider that we can use to find the root provider ID
                        of the tree of providers to filter results by and
                        `resources` is a dict of amounts keyed by resource
                        classes.
        :type filters: dict
        """
        resource_providers = cls._get_all_by_filters_from_db(context, filters)
        return cls._set_objects(context, resource_providers)


class Inventory(object):

    # kwargs included because some constructors pass resource_class_id
    # but it is not used.
    def __init__(self, id=None, resource_provider=None, resource_class=None,
                 total=None, reserved=0, min_unit=1, max_unit=1, step_size=1,
                 allocation_ratio=1.0, updated_at=None, created_at=None,
                 **kwargs):
        self.id = id
        self.resource_provider = resource_provider
        self.resource_class = resource_class
        self.total = total
        self.reserved = reserved
        self.min_unit = min_unit
        self.max_unit = max_unit
        self.step_size = step_size
        self.allocation_ratio = allocation_ratio
        self.updated_at = updated_at
        self.created_at = created_at

    @property
    def capacity(self):
        """Inventory capacity, adjusted by allocation_ratio."""
        return int((self.total - self.reserved) * self.allocation_ratio)


@db_api.placement_context_manager.reader
def _get_inventory_by_provider_id(ctx, rp_id):
    inv = sa.alias(_INV_TBL, name="i")
    cols = [
        inv.c.resource_class_id,
        inv.c.total,
        inv.c.reserved,
        inv.c.min_unit,
        inv.c.max_unit,
        inv.c.step_size,
        inv.c.allocation_ratio,
        inv.c.updated_at,
        inv.c.created_at,
    ]
    sel = sa.select(cols)
    sel = sel.where(inv.c.resource_provider_id == rp_id)

    return [dict(r) for r in ctx.session.execute(sel)]


class InventoryList(common_obj.ObjectList):
    ITEM_CLS = Inventory

    def find(self, res_class):
        """Return the inventory record from the list of Inventory records that
        matches the supplied resource class, or None.

        :param res_class: An integer or string representing a resource
                          class. If the value is a string, the method first
                          looks up the resource class identifier from the
                          string.
        """
        if not isinstance(res_class, six.string_types):
            raise ValueError

        for inv_rec in self.objects:
            if inv_rec.resource_class == res_class:
                return inv_rec

    @classmethod
    def get_all_by_resource_provider(cls, context, rp):
        db_inv = _get_inventory_by_provider_id(context, rp.id)
        # Build up a list of Inventory objects, setting the Inventory object
        # fields to the same-named database record field we got from
        # _get_inventory_by_provider_id(). We already have the ResourceProvider
        # object so we just pass that object to the Inventory object
        # constructor as-is
        objs = [
            Inventory(
                resource_provider=rp,
                resource_class=rc_cache.RC_CACHE.string_from_id(
                    rec['resource_class_id']),
                **rec)
            for rec in db_inv
        ]
        inv_list = cls(objects=objs)
        return inv_list


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
        rc = rc_cache.RC_CACHE.all_from_string(name)
        obj = cls(context, id=rc['id'], name=rc['name'],
                  updated_at=rc['updated_at'], created_at=rc['created_at'])
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
            msg = _("creating resource class %s") % self.name
            raise exception.MaxDBRetriesExceeded(action=msg)

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
        rc_cache.RC_CACHE.clear()

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
        rc_cache.RC_CACHE.clear()

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


class ResourceClassList(common_obj.ObjectList):
    ITEM_CLS = ResourceClass

    @staticmethod
    @db_api.placement_context_manager.reader
    def _get_all(context):
        return list(context.session.query(models.ResourceClass).all())

    @classmethod
    def get_all(cls, context):
        resource_classes = cls._get_all(context)
        return cls._set_objects(context, resource_classes)


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

    @staticmethod
    @db_api.placement_context_manager.writer  # trait sync can cause a write
    def _get_by_name_from_db(context, name):
        result = context.session.query(models.Trait).filter_by(
            name=name).first()
        if not result:
            raise exception.TraitNotFound(names=name)
        return result

    @classmethod
    def get_by_name(cls, context, name):
        db_trait = cls._get_by_name_from_db(context, six.text_type(name))
        return cls._from_db_object(context, cls(context), db_trait)

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
            raise exception.TraitNotFound(names=name)

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


class TraitList(common_obj.ObjectList):
    ITEM_CLS = Trait

    @staticmethod
    @db_api.placement_context_manager.writer  # trait sync can cause a write
    def _get_all_from_db(context, filters):
        if not filters:
            filters = {}

        query = context.session.query(models.Trait)
        if 'name_in' in filters:
            query = query.filter(models.Trait.name.in_(
                [six.text_type(n) for n in filters['name_in']]
            ))
        if 'prefix' in filters:
            query = query.filter(
                models.Trait.name.like(six.text_type(filters['prefix'] + '%')))
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
                ).filter(models.ResourceProviderTrait.trait_id == null())

        return query.all()

    @classmethod
    def get_all(cls, context, filters=None):
        db_traits = cls._get_all_from_db(context, filters)
        return cls._set_objects(context, db_traits)

    @classmethod
    def get_all_by_resource_provider(cls, context, rp):
        """Returns a TraitList containing Trait objects for any trait
        associated with the supplied resource provider.
        """
        db_traits = _get_traits_by_provider_id(context, rp.id)
        return cls._set_objects(context, db_traits)


class AllocationRequestResource(object):

    def __init__(self, resource_provider=None, resource_class=None,
                 amount=None):
        self.resource_provider = resource_provider
        self.resource_class = resource_class
        self.amount = amount

    def __eq__(self, other):
        return ((self.resource_provider.id == other.resource_provider.id) and
                (self.resource_class == other.resource_class) and
                (self.amount == other.amount))

    def __hash__(self):
        return hash((self.resource_provider.id,
                     self.resource_class,
                     self.amount))


class AllocationRequest(object):

    def __init__(self, anchor_root_provider_uuid=None,
                 use_same_provider=None, resource_requests=None):
        # UUID of (the root of the tree including) the non-sharing resource
        # provider associated with this AllocationRequest. Internal use only,
        # not included when the object is serialized for output.
        self.anchor_root_provider_uuid = anchor_root_provider_uuid
        # Whether all AllocationRequestResources in this AllocationRequest are
        # required to be satisfied by the same provider (based on the
        # corresponding RequestGroup's use_same_provider attribute). Internal
        # use only, not included when the object is serialized for output.
        self.use_same_provider = use_same_provider
        self.resource_requests = resource_requests or []

    def __repr__(self):
        anchor = (self.anchor_root_provider_uuid[-8:]
                  if self.anchor_root_provider_uuid else '<?>')
        usp = (self.use_same_provider
               if self.use_same_provider is not None else '<?>')
        repr_str = ('%s(anchor=...%s, same_provider=%s, '
                    'resource_requests=[%s])' %
                    (self.__class__.__name__, anchor, usp,
                     ', '.join([str(arr) for arr in self.resource_requests])))
        if six.PY2:
            repr_str = encodeutils.safe_encode(repr_str, incoming='utf-8')
        return repr_str

    def __eq__(self, other):
        return set(self.resource_requests) == set(other.resource_requests)

    def __hash__(self):
        return hash(tuple(self.resource_requests))


class ProviderSummaryResource(object):

    def __init__(self, resource_class=None, capacity=None, used=None,
                 max_unit=None):
        self.resource_class = resource_class
        self.capacity = capacity
        self.used = used
        # Internal use only; not included when the object is serialized for
        # output.
        self.max_unit = max_unit


class ProviderSummary(object):

    def __init__(self, resource_provider=None, resources=None, traits=None):
        self.resource_provider = resource_provider
        self.resources = resources or []
        self.traits = traits or []

    @property
    def resource_class_names(self):
        """Helper property that returns a set() of resource class string names
        that are included in the provider summary.
        """
        return set(res.resource_class for res in self.resources)


@db_api.placement_context_manager.reader
def _get_usages_by_provider_tree(ctx, root_ids):
    """Returns a row iterator of usage records grouped by provider ID
    for all resource providers in all trees indicated in the ``root_ids``.
    """
    # We build up a SQL expression that looks like this:
    # SELECT
    #   rp.id as resource_provider_id
    # , rp.uuid as resource_provider_uuid
    # , inv.resource_class_id
    # , inv.total
    # , inv.reserved
    # , inv.allocation_ratio
    # , inv.max_unit
    # , usage.used
    # FROM resource_providers AS rp
    # LEFT JOIN inventories AS inv
    #  ON rp.id = inv.resource_provider_id
    # LEFT JOIN (
    #   SELECT resource_provider_id, resource_class_id, SUM(used) as used
    #   FROM allocations
    #   JOIN resource_providers
    #     ON allocations.resource_provider_id = resource_providers.id
    #     AND (resource_providers.root_provider_id IN($root_ids)
    #          OR resource_providers.id IN($root_ids))
    #   GROUP BY resource_provider_id, resource_class_id
    # )
    # AS usage
    #   ON inv.resource_provider_id = usage.resource_provider_id
    #   AND inv.resource_class_id = usage.resource_class_id
    # WHERE (rp.root_provider_id IN ($root_ids)
    #        OR resource_providers.id IN($root_ids))
    rpt = sa.alias(_RP_TBL, name="rp")
    inv = sa.alias(_INV_TBL, name="inv")
    # Build our derived table (subquery in the FROM clause) that sums used
    # amounts for resource provider and resource class
    derived_alloc_to_rp = sa.join(
        _ALLOC_TBL, _RP_TBL,
        sa.and_(_ALLOC_TBL.c.resource_provider_id == _RP_TBL.c.id,
                # TODO(tetsuro): Remove this OR condition when all
                # root_provider_id values are NOT NULL
                sa.or_(_RP_TBL.c.root_provider_id.in_(root_ids),
                       _RP_TBL.c.id.in_(root_ids))
                )
    )
    usage = sa.alias(
        sa.select([
            _ALLOC_TBL.c.resource_provider_id,
            _ALLOC_TBL.c.resource_class_id,
            sql.func.sum(_ALLOC_TBL.c.used).label('used'),
        ]).select_from(derived_alloc_to_rp).group_by(
            _ALLOC_TBL.c.resource_provider_id,
            _ALLOC_TBL.c.resource_class_id
        ),
        name='usage')
    # Build a join between the resource providers and inventories table
    rpt_inv_join = sa.outerjoin(rpt, inv,
                                rpt.c.id == inv.c.resource_provider_id)
    # And then join to the derived table of usages
    usage_join = sa.outerjoin(
        rpt_inv_join,
        usage,
        sa.and_(
            usage.c.resource_provider_id == inv.c.resource_provider_id,
            usage.c.resource_class_id == inv.c.resource_class_id,
        ),
    )
    query = sa.select([
        rpt.c.id.label("resource_provider_id"),
        rpt.c.uuid.label("resource_provider_uuid"),
        inv.c.resource_class_id,
        inv.c.total,
        inv.c.reserved,
        inv.c.allocation_ratio,
        inv.c.max_unit,
        usage.c.used,
    ]).select_from(usage_join).where(
        # TODO(tetsuro): Remove this or condition when all
        # root_provider_id values are NOT NULL
        sa.or_(
            rpt.c.root_provider_id.in_(root_ids),
            rpt.c.id.in_(root_ids)
        )
    )
    return ctx.session.execute(query).fetchall()


@db_api.placement_context_manager.reader
def _get_provider_ids_having_any_trait(ctx, traits):
    """Returns a set of resource provider internal IDs that have ANY of the
    supplied traits.

    :param ctx: Session context to use
    :param traits: A map, keyed by trait string name, of trait internal IDs, at
                   least one of which each provider must have associated with
                   it.
    :raise ValueError: If traits is empty or None.
    """
    if not traits:
        raise ValueError(_('traits must not be empty'))

    rptt = sa.alias(_RP_TRAIT_TBL, name="rpt")
    sel = sa.select([rptt.c.resource_provider_id])
    sel = sel.where(rptt.c.trait_id.in_(traits.values()))
    sel = sel.group_by(rptt.c.resource_provider_id)
    return set(r[0] for r in ctx.session.execute(sel))


@db_api.placement_context_manager.reader
def _get_provider_ids_having_all_traits(ctx, required_traits):
    """Returns a set of resource provider internal IDs that have ALL of the
    required traits.

    NOTE: Don't call this method with no required_traits.

    :param ctx: Session context to use
    :param required_traits: A map, keyed by trait string name, of required
                            trait internal IDs that each provider must have
                            associated with it
    :raise ValueError: If required_traits is empty or None.
    """
    if not required_traits:
        raise ValueError(_('required_traits must not be empty'))

    rptt = sa.alias(_RP_TRAIT_TBL, name="rpt")
    sel = sa.select([rptt.c.resource_provider_id])
    sel = sel.where(rptt.c.trait_id.in_(required_traits.values()))
    sel = sel.group_by(rptt.c.resource_provider_id)
    # Only get the resource providers that have ALL the required traits, so we
    # need to GROUP BY the resource provider and ensure that the
    # COUNT(trait_id) is equal to the number of traits we are requiring
    num_traits = len(required_traits)
    cond = sa.func.count(rptt.c.trait_id) == num_traits
    sel = sel.having(cond)
    return set(r[0] for r in ctx.session.execute(sel))


@db_api.placement_context_manager.reader
def _has_provider_trees(ctx):
    """Simple method that returns whether provider trees (i.e. nested resource
    providers) are in use in the deployment at all. This information is used to
    switch code paths when attempting to retrieve allocation candidate
    information. The code paths are eminently easier to execute and follow for
    non-nested scenarios...

    NOTE(jaypipes): The result of this function can be cached extensively.
    """
    sel = sa.select([_RP_TBL.c.id])
    sel = sel.where(_RP_TBL.c.parent_provider_id.isnot(None))
    sel = sel.limit(1)
    res = ctx.session.execute(sel).fetchall()
    return len(res) > 0


def _get_provider_ids_for_traits_and_aggs(ctx, required_traits,
                                          forbidden_traits, member_of):
    """Get internal IDs for all providers matching the specified traits/aggs.

    :return: A tuple of:
        filtered_rp_ids: A set of internal provider IDs matching the specified
            criteria. If None, work was done and resulted in no matching
            providers. This is in contrast to the empty set, which indicates
            that no filtering was performed.
        forbidden_rp_ids: A set of internal IDs of providers having any of the
            specified forbidden_traits.
    """
    filtered_rps = set()
    if required_traits:
        if not isinstance(required_traits, dict):
            required_traits = _trait_ids_from_names(ctx, required_traits)
        trait_rps = _get_provider_ids_having_all_traits(ctx, required_traits)
        filtered_rps = trait_rps
        LOG.debug("found %d providers after applying required traits filter "
                  "(%s)",
                  len(filtered_rps), list(required_traits))
        if not filtered_rps:
            return None, []

    # If 'member_of' has values, do a separate lookup to identify the
    # resource providers that meet the member_of constraints.
    if member_of:
        rps_in_aggs = _provider_ids_matching_aggregates(ctx, member_of)
        if filtered_rps:
            filtered_rps &= rps_in_aggs
        else:
            filtered_rps = rps_in_aggs
        LOG.debug("found %d providers after applying aggregates filter (%s)",
                  len(filtered_rps), member_of)
        if not filtered_rps:
            return None, []

    forbidden_rp_ids = set()
    if forbidden_traits:
        if isinstance(forbidden_traits, dict):
            trait_map = forbidden_traits
        else:
            trait_map = _trait_ids_from_names(ctx, forbidden_traits)
        forbidden_rp_ids = _get_provider_ids_having_any_trait(ctx, trait_map)
        if filtered_rps:
            filtered_rps -= forbidden_rp_ids
            LOG.debug("found %d providers after applying forbidden traits "
                      "filter (%s)", len(filtered_rps),
                      list(forbidden_traits))
            if not filtered_rps:
                return None, []

    return filtered_rps, forbidden_rp_ids


@db_api.placement_context_manager.reader
def _get_provider_ids_matching(ctx, resources, required_traits,
                               forbidden_traits, member_of, tree_root_id):
    """Returns a list of tuples of (internal provider ID, root provider ID)
    that have available inventory to satisfy all the supplied requests for
    resources. If no providers match, the empty list is returned.

    :note: This function is used to get results for (a) a RequestGroup with
           use_same_provider=True in a granular request, or (b) a short cut
           path for scenarios that do NOT involve sharing or nested providers.
           Each `internal provider ID` represents a *single* provider that
           can satisfy *all* of the resource/trait/aggregate criteria. This is
           in contrast with _get_trees_matching_all(), where each provider
           might only satisfy *some* of the resources, the rest of which are
           satisfied by other providers in the same tree or shared via
           aggregate.

    :param ctx: Session context to use
    :param resources: A dict, keyed by resource class ID, of the amount
                      requested of that resource class.
    :param required_traits: A map, keyed by trait string name, of required
                            trait internal IDs that each provider must have
                            associated with it
    :param forbidden_traits: A map, keyed by trait string name, of forbidden
                             trait internal IDs that each provider must not
                             have associated with it
    :param member_of: An optional list of list of aggregate UUIDs. If provided,
                      the allocation_candidates returned will only be for
                      resource providers that are members of one or more of the
                      supplied aggregates of each aggregate UUID list.
    :param tree_root_id: An optional root resource provider ID. If provided,
                         the result will be restricted to providers in the tree
                         with this root ID.
    """
    # The iteratively filtered set of resource provider internal IDs that match
    # all the constraints in the request
    filtered_rps, forbidden_rp_ids = _get_provider_ids_for_traits_and_aggs(
        ctx, required_traits, forbidden_traits, member_of)
    if filtered_rps is None:
        # If no providers match the traits/aggs, we can short out
        return []

    # Instead of constructing a giant complex SQL statement that joins multiple
    # copies of derived usage tables and inventory tables to each other, we do
    # one query for each requested resource class. This allows us to log a
    # rough idea of which resource class query returned no results (for
    # purposes of rough debugging of a single allocation candidates request) as
    # well as reduce the necessary knowledge of SQL in order to understand the
    # queries being executed here.
    #
    # NOTE(jaypipes): The efficiency of this operation may be improved by
    # passing the trait_rps and/or forbidden_ip_ids iterables to the
    # _get_providers_with_resource() function so that we don't have to process
    # as many records inside the loop below to remove providers from the
    # eventual results list
    provs_with_resource = set()
    first = True
    for rc_id, amount in resources.items():
        rc_name = rc_cache.RC_CACHE.string_from_id(rc_id)
        provs_with_resource = _get_providers_with_resource(
            ctx, rc_id, amount, tree_root_id=tree_root_id)
        LOG.debug("found %d providers with available %d %s",
                  len(provs_with_resource), amount, rc_name)
        if not provs_with_resource:
            return []

        rc_rp_ids = set(p[0] for p in provs_with_resource)
        # The branching below could be collapsed code-wise, but is in place to
        # make the debug logging clearer.
        if first:
            first = False
            if filtered_rps:
                filtered_rps &= rc_rp_ids
                LOG.debug("found %d providers after applying initial "
                          "aggregate and trait filters", len(filtered_rps))
            else:
                filtered_rps = rc_rp_ids
                # The following condition is not necessary for the logic; just
                # prevents the message from being logged unnecessarily.
                if forbidden_rp_ids:
                    # Forbidden trait filters only need to be applied
                    # a) on the first iteration; and
                    # b) if not already set up before the loop
                    # ...since any providers in the resulting set are the basis
                    # for intersections, and providers with forbidden traits
                    # are already absent from that set after we've filtered
                    # them once.
                    filtered_rps -= forbidden_rp_ids
                    LOG.debug("found %d providers after applying forbidden "
                              "traits", len(filtered_rps))
        else:
            filtered_rps &= rc_rp_ids
            LOG.debug("found %d providers after filtering by previous result",
                      len(filtered_rps))

        if not filtered_rps:
            return []

    # provs_with_resource will contain a superset of providers with IDs still
    # in our filtered_rps set. We return the list of tuples of
    # (internal provider ID, root internal provider ID)
    return [rpids for rpids in provs_with_resource if rpids[0] in filtered_rps]


@db_api.placement_context_manager.reader
def _get_providers_with_resource(ctx, rc_id, amount, tree_root_id=None):
    """Returns a set of tuples of (provider ID, root provider ID) of providers
    that satisfy the request for a single resource class.

    :param ctx: Session context to use
    :param rc_id: Internal ID of resource class to check inventory for
    :param amount: Amount of resource being requested
    :param tree_root_id: An optional root provider ID. If provided, the results
                         are limited to the resource providers under the given
                         root resource provider.
    """
    # SELECT rp.id, rp.root_provider_id
    # FROM resource_providers AS rp
    # JOIN inventories AS inv
    #  ON rp.id = inv.resource_provider_id
    #  AND inv.resource_class_id = $RC_ID
    # LEFT JOIN (
    #  SELECT
    #    alloc.resource_provider_id,
    #    SUM(allocs.used) AS used
    #  FROM allocations AS alloc
    #  WHERE allocs.resource_class_id = $RC_ID
    #  GROUP BY allocs.resource_provider_id
    # ) AS usage
    #  ON inv.resource_provider_id = usage.resource_provider_id
    # WHERE
    #  used + $AMOUNT <= ((total - reserved) * inv.allocation_ratio)
    #  AND inv.min_unit <= $AMOUNT
    #  AND inv.max_unit >= $AMOUNT
    #  AND $AMOUNT % inv.step_size == 0
    rpt = sa.alias(_RP_TBL, name="rp")
    inv = sa.alias(_INV_TBL, name="inv")
    usage = _usage_select([rc_id])
    rp_to_inv = sa.join(
        rpt, inv, sa.and_(
            rpt.c.id == inv.c.resource_provider_id,
            inv.c.resource_class_id == rc_id))
    inv_to_usage = sa.outerjoin(
        rp_to_inv, usage,
        inv.c.resource_provider_id == usage.c.resource_provider_id)
    sel = sa.select([rpt.c.id, rpt.c.root_provider_id])
    sel = sel.select_from(inv_to_usage)
    where_conds = _capacity_check_clause(amount, usage, inv_tbl=inv)
    if tree_root_id is not None:
        where_conds = sa.and_(
            # TODO(tetsuro): Bug#1799892: Remove this "or" condition in Train
            sa.or_(rpt.c.root_provider_id == tree_root_id,
                   rpt.c.id == tree_root_id),
            where_conds)
    sel = sel.where(where_conds)
    res = ctx.session.execute(sel).fetchall()
    res = set((r[0], r[1]) for r in res)
    # TODO(tetsuro): Bug#1799892: We could have old providers with no root
    # provider set and they haven't undergone a data migration yet,
    # so we need to set the root_id explicitly here. We remove
    # this and when all root_provider_id values are NOT NULL
    ret = []
    for rp_tuple in res:
        rp_id = rp_tuple[0]
        root_id = rp_id if rp_tuple[1] is None else rp_tuple[1]
        ret.append((rp_id, root_id))
    return ret


@db_api.placement_context_manager.reader
def _get_trees_with_traits(ctx, rp_ids, required_traits, forbidden_traits):
    """Given a list of provider IDs, filter them to return a set of tuples of
    (provider ID, root provider ID) of providers which belong to a tree that
    can satisfy trait requirements.

    :param ctx: Session context to use
    :param rp_ids: a set of resource provider IDs
    :param required_traits: A map, keyed by trait string name, of required
                            trait internal IDs that each provider TREE must
                            COLLECTIVELY have associated with it
    :param forbidden_traits: A map, keyed by trait string name, of trait
                             internal IDs that a resource provider must
                             not have.
    """
    # We now want to restrict the returned providers to only those provider
    # trees that have all our required traits.
    #
    # The SQL we want looks like this:
    #
    # SELECT outer_rp.id, outer_rp.root_provider_id
    # FROM resource_providers AS outer_rp
    # JOIN (
    #   SELECT rp.root_provider_id
    #   FROM resource_providers AS rp
    #   # Only if we have required traits...
    #   INNER JOIN resource_provider_traits AS rptt
    #   ON rp.id = rptt.resource_provider_id
    #   AND rptt.trait_id IN ($REQUIRED_TRAIT_IDS)
    #   # Only if we have forbidden_traits...
    #   LEFT JOIN resource_provider_traits AS rptt_forbid
    #   ON rp.id = rptt_forbid.resource_provider_id
    #   AND rptt_forbid.trait_id IN ($FORBIDDEN_TRAIT_IDS)
    #   WHERE rp.id IN ($RP_IDS)
    #   # Only if we have forbidden traits...
    #   AND rptt_forbid.resource_provider_id IS NULL
    #   GROUP BY rp.root_provider_id
    #   # Only if have required traits...
    #   HAVING COUNT(DISTINCT rptt.trait_id) == $NUM_REQUIRED_TRAITS
    # ) AS trees_with_traits
    #  ON outer_rp.root_provider_id = trees_with_traits.root_provider_id
    rpt = sa.alias(_RP_TBL, name="rp")
    cond = [rpt.c.id.in_(rp_ids)]
    subq = sa.select([rpt.c.root_provider_id])
    subq_join = None
    if required_traits:
        rptt = sa.alias(_RP_TRAIT_TBL, name="rptt")
        rpt_to_rptt = sa.join(
            rpt, rptt, sa.and_(
                rpt.c.id == rptt.c.resource_provider_id,
                rptt.c.trait_id.in_(required_traits.values())))
        subq_join = rpt_to_rptt
        # Only get the resource providers that have ALL the required traits,
        # so we need to GROUP BY the root provider and ensure that the
        # COUNT(trait_id) is equal to the number of traits we are requiring
        num_traits = len(required_traits)
        having_cond = sa.func.count(sa.distinct(rptt.c.trait_id)) == num_traits
        subq = subq.having(having_cond)

    # Tack on an additional LEFT JOIN clause inside the derived table if we've
    # got forbidden traits in the mix.
    if forbidden_traits:
        rptt_forbid = sa.alias(_RP_TRAIT_TBL, name="rptt_forbid")
        join_to = rpt
        if subq_join is not None:
            join_to = subq_join
        rpt_to_rptt_forbid = sa.outerjoin(
            join_to, rptt_forbid, sa.and_(
                rpt.c.id == rptt_forbid.c.resource_provider_id,
                rptt_forbid.c.trait_id.in_(forbidden_traits.values())))
        cond.append(rptt_forbid.c.resource_provider_id == sa.null())
        subq_join = rpt_to_rptt_forbid

    subq = subq.select_from(subq_join)
    subq = subq.where(sa.and_(*cond))
    subq = subq.group_by(rpt.c.root_provider_id)
    trees_with_traits = sa.alias(subq, name="trees_with_traits")

    outer_rps = sa.alias(_RP_TBL, name="outer_rps")
    outer_to_subq = sa.join(
        outer_rps, trees_with_traits,
        outer_rps.c.root_provider_id == trees_with_traits.c.root_provider_id)
    sel = sa.select([outer_rps.c.id, outer_rps.c.root_provider_id])
    sel = sel.select_from(outer_to_subq)
    res = ctx.session.execute(sel).fetchall()

    return [(rp_id, root_id) for rp_id, root_id in res]


@db_api.placement_context_manager.reader
def _get_trees_matching_all(ctx, resources, required_traits, forbidden_traits,
                            sharing, member_of, tree_root_id):
    """Returns a RPCandidates object representing the providers that satisfy
    the request for resources.

    If traits are also required, this function only returns results where the
    set of providers within a tree that satisfy the resource request
    collectively have all the required traits associated with them. This means
    that given the following provider tree:

    cn1
     |
     --> pf1 (SRIOV_NET_VF:2)
     |
     --> pf2 (SRIOV_NET_VF:1, HW_NIC_OFFLOAD_GENEVE)

    If a user requests 1 SRIOV_NET_VF resource and no required traits will
    return both pf1 and pf2. However, a request for 2 SRIOV_NET_VF and required
    trait of HW_NIC_OFFLOAD_GENEVE will return no results (since pf1 is the
    only provider with enough inventory of SRIOV_NET_VF but it does not have
    the required HW_NIC_OFFLOAD_GENEVE trait).

    :note: This function is used for scenarios to get results for a
    RequestGroup with use_same_provider=False. In this scenario, we are able
    to use multiple providers within the same provider tree including sharing
    providers to satisfy different resources involved in a single RequestGroup.

    :param ctx: Session context to use
    :param resources: A dict, keyed by resource class ID, of the amount
                      requested of that resource class.
    :param required_traits: A map, keyed by trait string name, of required
                            trait internal IDs that each provider TREE must
                            COLLECTIVELY have associated with it
    :param forbidden_traits: A map, keyed by trait string name, of trait
                             internal IDs that a resource provider must
                             not have.
    :param sharing: dict, keyed by resource class ID, of lists of resource
                    provider IDs that share that resource class and can
                    contribute to the overall allocation request
    :param member_of: An optional list of lists of aggregate UUIDs. If
                      provided, the allocation_candidates returned will only be
                      for resource providers that are members of one or more of
                      the supplied aggregates in each aggregate UUID list.
    :param tree_root_id: An optional root provider ID. If provided, the results
                         are limited to the resource providers under the given
                         root resource provider.
    """
    # To get all trees that collectively have all required resource,
    # aggregates and traits, we use `RPCandidateList` which has a list of
    # three-tuples with the first element being resource provider ID, the
    # second element being the root provider ID and the third being resource
    # class ID.
    provs_with_inv = rp_candidates.RPCandidateList()

    for rc_id, amount in resources.items():
        rc_name = rc_cache.RC_CACHE.string_from_id(rc_id)

        provs_with_inv_rc = rp_candidates.RPCandidateList()
        rc_provs_with_inv = _get_providers_with_resource(
            ctx, rc_id, amount, tree_root_id=tree_root_id)
        provs_with_inv_rc.add_rps(rc_provs_with_inv, rc_id)
        LOG.debug("found %d providers under %d trees with available %d %s",
                  len(provs_with_inv_rc), len(provs_with_inv_rc.trees),
                  amount, rc_name)
        if not provs_with_inv_rc:
            # If there's no providers that have one of the resource classes,
            # then we can short-circuit
            return []

        sharing_providers = sharing.get(rc_id)
        if sharing_providers and tree_root_id is None:
            # There are sharing providers for this resource class, so we
            # should also get combinations of (sharing provider, anchor root)
            # in addition to (non-sharing provider, anchor root) we've just
            # got via _get_providers_with_resource() above. We must skip this
            # process if tree_root_id is provided via the ?in_tree=<rp_uuid>
            # queryparam, because it restricts resources from another tree.
            rc_provs_with_inv = _anchors_for_sharing_providers(
                ctx, sharing_providers, get_id=True)
            provs_with_inv_rc.add_rps(rc_provs_with_inv, rc_id)
            LOG.debug(
                "considering %d sharing providers with %d %s, "
                "now we've got %d provider trees",
                len(sharing_providers), amount, rc_name,
                len(provs_with_inv_rc.trees))

        # Adding the resource providers we've got for this resource class,
        # filter provs_with_inv to have only trees with enough inventories
        # for this resource class. Here "tree" includes sharing providers
        # in its terminology
        provs_with_inv.merge_common_trees(provs_with_inv_rc)
        LOG.debug(
            "found %d providers under %d trees after filtering by "
            "previous result",
            len(provs_with_inv.rps), len(provs_with_inv_rc.trees))
        if not provs_with_inv:
            return []

    # If 'member_of' has values, do a separate lookup to identify the
    # resource providers that meet the member_of constraints.
    if member_of:
        rps_in_aggs = _provider_ids_matching_aggregates(
            ctx, member_of, rp_ids=provs_with_inv.all_rps)
        if not rps_in_aggs:
            # Short-circuit. The user either asked for a non-existing
            # aggregate or there were no resource providers that matched
            # the requirements...
            return []
        # Aggregate on root spans the whole tree, so the rp itself
        # *or its root* should be in the aggregate
        provs_with_inv.filter_by_rp_or_tree(rps_in_aggs)
        LOG.debug("found %d providers under %d trees after applying "
                  "aggregate filter %s",
                  len(provs_with_inv.rps), len(provs_with_inv_rc.trees),
                  member_of)

    if (not required_traits and not forbidden_traits) or (
            any(sharing.values())):
        # If there were no traits required, there's no difference in how we
        # calculate allocation requests between nested and non-nested
        # environments, so just short-circuit and return. Or if sharing
        # providers are in play, we check the trait constraints later
        # in _alloc_candidates_multiple_providers(), so skip.
        return provs_with_inv

    # Return the providers where the providers have the available inventory
    # capacity and that set of providers (grouped by their tree) have all
    # of the required traits and none of the forbidden traits
    rp_tuples_with_trait = _get_trees_with_traits(
        ctx, provs_with_inv.rps, required_traits, forbidden_traits)
    provs_with_inv.filter_by_rp(rp_tuples_with_trait)
    LOG.debug("found %d providers under %d trees after applying "
              "traits filter - required: %s, forbidden: %s",
              len(provs_with_inv.rps), len(provs_with_inv_rc.trees),
              list(required_traits), list(forbidden_traits))

    return provs_with_inv


def _build_provider_summaries(context, usages, prov_traits):
    """Given a list of dicts of usage information and a map of providers to
    their associated string traits, returns a dict, keyed by resource provider
    ID, of ProviderSummary objects.

    :param context: placement.context.RequestContext object
    :param usages: A list of dicts with the following format:

        {
            'resource_provider_id': <internal resource provider ID>,
            'resource_provider_uuid': <UUID>,
            'resource_class_id': <internal resource class ID>,
            'total': integer,
            'reserved': integer,
            'allocation_ratio': float,
        }
    :param prov_traits: A dict, keyed by internal resource provider ID, of
                        string trait names associated with that provider
    """
    # Before we go creating provider summary objects, first grab all the
    # provider information (including root, parent and UUID information) for
    # all providers involved in our operation
    rp_ids = set(usage['resource_provider_id'] for usage in usages)
    provider_ids = _provider_ids_from_rp_ids(context, rp_ids)

    # Build up a dict, keyed by internal resource provider ID, of
    # ProviderSummary objects containing one or more ProviderSummaryResource
    # objects representing the resources the provider has inventory for.
    summaries = {}
    for usage in usages:
        rp_id = usage['resource_provider_id']
        summary = summaries.get(rp_id)
        if not summary:
            pids = provider_ids[rp_id]
            summary = ProviderSummary(
                resource_provider=ResourceProvider(
                    context, id=pids.id, uuid=pids.uuid,
                    root_provider_uuid=pids.root_uuid,
                    parent_provider_uuid=pids.parent_uuid),
                resources=[],
            )
            summaries[rp_id] = summary

        traits = prov_traits[rp_id]
        summary.traits = [Trait(context, name=tname) for tname in traits]

        rc_id = usage['resource_class_id']
        if rc_id is None:
            # NOTE(tetsuro): This provider doesn't have any inventory itself.
            # But we include this provider in summaries since another
            # provider in the same tree will be in the "allocation_request".
            # Let's skip the following and leave "ProviderSummary.resources"
            # field empty.
            continue
        # NOTE(jaypipes): usage['used'] may be None due to the LEFT JOIN of
        # the usages subquery, so we coerce NULL values to 0 here. It may
        # also be a Decimal, as that's the type that mysql tends to return
        # when func.sum is used in a query. We need an int, otherwise later
        # JSON serialization will not work.
        used = int(usage['used'] or 0)
        allocation_ratio = usage['allocation_ratio']
        cap = int((usage['total'] - usage['reserved']) * allocation_ratio)
        rc_name = rc_cache.RC_CACHE.string_from_id(rc_id)
        rpsr = ProviderSummaryResource(
            resource_class=rc_name,
            capacity=cap,
            used=used,
            max_unit=usage['max_unit'],
        )
        summary.resources.append(rpsr)
    return summaries


def _allocation_request_for_provider(ctx, requested_resources, provider):
    """Returns an AllocationRequest object containing AllocationRequestResource
    objects for each resource class in the supplied requested resources dict.

    :param ctx: placement.context.RequestContext object
    :param requested_resources: dict, keyed by resource class ID, of amounts
                                being requested for that resource class
    :param provider: ResourceProvider object representing the provider of the
                     resources.
    """
    resource_requests = [
        AllocationRequestResource(
            resource_provider=provider,
            resource_class=rc_cache.RC_CACHE.string_from_id(rc_id),
            amount=amount,
        ) for rc_id, amount in requested_resources.items()
    ]
    # NOTE(efried): This method only produces an AllocationRequest with its
    # anchor in its own tree.  If the provider is a sharing provider, the
    # caller needs to identify the other anchors with which it might be
    # associated.
    return AllocationRequest(
        resource_requests=resource_requests,
        anchor_root_provider_uuid=provider.root_provider_uuid)


def _check_traits_for_alloc_request(res_requests, summaries, prov_traits,
                                    required_traits, forbidden_traits):
    """Given a list of AllocationRequestResource objects, check if that
    combination can provide trait constraints. If it can, returns all
    resource provider internal IDs in play, else return an empty list.

    TODO(tetsuro): For optimization, we should move this logic to SQL in
                   _get_trees_matching_all().

    :param res_requests: a list of AllocationRequestResource objects that have
                         resource providers to be checked if they collectively
                         satisfy trait constraints in the required_traits and
                         forbidden_traits parameters.
    :param summaries: dict, keyed by resource provider ID, of ProviderSummary
                      objects containing usage and trait information for
                      resource providers involved in the overall request
    :param prov_traits: A dict, keyed by internal resource provider ID, of
                        string trait names associated with that provider
    :param required_traits: A map, keyed by trait string name, of required
                            trait internal IDs that each *allocation request's
                            set of providers* must *collectively* have
                            associated with them
    :param forbidden_traits: A map, keyed by trait string name, of trait
                             internal IDs that a resource provider must
                             not have.
    """
    all_prov_ids = []
    all_traits = set()
    for res_req in res_requests:
        rp_uuid = res_req.resource_provider.uuid
        for rp_id, summary in summaries.items():
            if summary.resource_provider.uuid == rp_uuid:
                break
        rp_traits = set(prov_traits.get(rp_id, []))

        # Check if there are forbidden_traits
        conflict_traits = set(forbidden_traits) & set(rp_traits)
        if conflict_traits:
            LOG.debug('Excluding resource provider %s, it has '
                      'forbidden traits: (%s).',
                      rp_id, ', '.join(conflict_traits))
            return []

        all_prov_ids.append(rp_id)
        all_traits |= rp_traits

    # Check if there are missing traits
    missing_traits = set(required_traits) - all_traits
    if missing_traits:
        LOG.debug('Excluding a set of allocation candidate %s : '
                  'missing traits %s are not satisfied.',
                  all_prov_ids, ','.join(missing_traits))
        return []

    return all_prov_ids


def _alloc_candidates_single_provider(ctx, requested_resources, rp_tuples):
    """Returns a tuple of (allocation requests, provider summaries) for a
    supplied set of requested resource amounts and resource providers. The
    supplied resource providers have capacity to satisfy ALL of the resources
    in the requested resources as well as ALL required traits that were
    requested by the user.

    This is used in two circumstances:
    - To get results for a RequestGroup with use_same_provider=True.
    - As an optimization when no sharing providers satisfy any of the requested
      resources, and nested providers are not in play.
    In these scenarios, we can more efficiently build the list of
    AllocationRequest and ProviderSummary objects due to not having to
    determine requests across multiple providers.

    :param ctx: placement.context.RequestContext object
    :param requested_resources: dict, keyed by resource class ID, of amounts
                                being requested for that resource class
    :param rp_tuples: List of two-tuples of (provider ID, root provider ID)s
                      for providers that matched the requested resources
    """
    if not rp_tuples:
        return [], []

    # Get all root resource provider IDs.
    root_ids = set(p[1] for p in rp_tuples)

    # Grab usage summaries for each provider
    usages = _get_usages_by_provider_tree(ctx, root_ids)

    # Get a dict, keyed by resource provider internal ID, of trait string names
    # that provider has associated with it
    prov_traits = _get_traits_by_provider_tree(ctx, root_ids)

    # Get a dict, keyed by resource provider internal ID, of ProviderSummary
    # objects for all providers
    summaries = _build_provider_summaries(ctx, usages, prov_traits)

    # Next, build up a list of allocation requests. These allocation requests
    # are AllocationRequest objects, containing resource provider UUIDs,
    # resource class names and amounts to consume from that resource provider
    alloc_requests = []
    for rp_id, root_id in rp_tuples:
        rp_summary = summaries[rp_id]
        req_obj = _allocation_request_for_provider(
            ctx, requested_resources, rp_summary.resource_provider)
        alloc_requests.append(req_obj)
        # If this is a sharing provider, we have to include an extra
        # AllocationRequest for every possible anchor.
        traits = [trait.name for trait in rp_summary.traits]
        if os_traits.MISC_SHARES_VIA_AGGREGATE in traits:
            anchors = set([p[1] for p in _anchors_for_sharing_providers(
                ctx, [rp_summary.resource_provider.id])])
            for anchor in anchors:
                # We already added self
                if anchor == rp_summary.resource_provider.root_provider_uuid:
                    continue
                req_obj = copy.copy(req_obj)
                req_obj.anchor_root_provider_uuid = anchor
                alloc_requests.append(req_obj)
    return alloc_requests, list(summaries.values())


def _alloc_candidates_multiple_providers(
    ctx, requested_resources, required_traits, forbidden_traits,
        rp_candidates):
    """Returns a tuple of (allocation requests, provider summaries) for a
    supplied set of requested resource amounts and tuples of
    (rp_id, root_id, rc_id). The supplied resource provider trees have
    capacity to satisfy ALL of the resources in the requested resources as
    well as ALL required traits that were requested by the user.

    This is a code path to get results for a RequestGroup with
    use_same_provider=False. In this scenario, we are able to use multiple
    providers within the same provider tree including sharing providers to
    satisfy different resources involved in a single request group.

    :param ctx: placement.context.RequestContext object
    :param requested_resources: dict, keyed by resource class ID, of amounts
                                being requested for that resource class
    :param required_traits: A map, keyed by trait string name, of required
                            trait internal IDs that each *allocation request's
                            set of providers* must *collectively* have
                            associated with them
    :param forbidden_traits: A map, keyed by trait string name, of trait
                             internal IDs that a resource provider must
                             not have.
    :param rp_candidates: RPCandidates object representing the providers
                          that satisfy the request for resources.
    """
    if not rp_candidates:
        return [], []

    # Get all the root resource provider IDs. We should include the first
    # values of rp_tuples because while sharing providers are root providers,
    # they have their "anchor" providers for the second value.
    root_ids = rp_candidates.all_rps

    # Grab usage summaries for each provider in the trees
    usages = _get_usages_by_provider_tree(ctx, root_ids)

    # Get a dict, keyed by resource provider internal ID, of trait string names
    # that provider has associated with it
    prov_traits = _get_traits_by_provider_tree(ctx, root_ids)

    # Get a dict, keyed by resource provider internal ID, of ProviderSummary
    # objects for all providers
    summaries = _build_provider_summaries(ctx, usages, prov_traits)

    # Get a dict, keyed by root provider internal ID, of a dict, keyed by
    # resource class internal ID, of lists of AllocationRequestResource objects
    tree_dict = collections.defaultdict(lambda: collections.defaultdict(list))

    for rp in rp_candidates.rps_info:
        rp_summary = summaries[rp.id]
        tree_dict[rp.root_id][rp.rc_id].append(
            AllocationRequestResource(
                resource_provider=rp_summary.resource_provider,
                resource_class=rc_cache.RC_CACHE.string_from_id(rp.rc_id),
                amount=requested_resources[rp.rc_id]))

    # Next, build up a set of allocation requests. These allocation requests
    # are AllocationRequest objects, containing resource provider UUIDs,
    # resource class names and amounts to consume from that resource provider
    alloc_requests = set()

    # Let's look into each tree
    for root_id, alloc_dict in tree_dict.items():
        # Get request_groups, which is a list of lists of
        # AllocationRequestResource(ARR) per requested resource class(rc).
        # For example, if we have the alloc_dict:
        # {rc1_id: [ARR(rc1, rp1), ARR(rc1, rp2)],
        #  rc2_id: [ARR(rc2, rp1), ARR(rc2, rp2)],
        #  rc3_id: [ARR(rc3, rp1)]}
        # then the request_groups would be something like
        # [[ARR(rc1, rp1), ARR(rc1, rp2)],
        #  [ARR(rc2, rp1), ARR(rc2, rp2)],
        #  [ARR(rc3, rp1)]]
        # , which should be ordered by the resource class id.
        request_groups = [val for key, val in sorted(alloc_dict.items())]

        root_summary = summaries[root_id]
        root_uuid = root_summary.resource_provider.uuid
        root_alloc_reqs = set()

        # Using itertools.product, we get all the combinations of resource
        # providers in a tree.
        # For example, the sample in the comment above becomes:
        # [(ARR(rc1, ss1), ARR(rc2, ss1), ARR(rc3, ss1)),
        #  (ARR(rc1, ss1), ARR(rc2, ss2), ARR(rc3, ss1)),
        #  (ARR(rc1, ss2), ARR(rc2, ss1), ARR(rc3, ss1)),
        #  (ARR(rc1, ss2), ARR(rc2, ss2), ARR(rc3, ss1))]
        for res_requests in itertools.product(*request_groups):
            if not _check_traits_for_alloc_request(
                    res_requests, summaries, prov_traits, required_traits,
                    forbidden_traits):
                # This combination doesn't satisfy trait constraints
                continue
            root_alloc_reqs.add(
                AllocationRequest(resource_requests=list(res_requests),
                                  anchor_root_provider_uuid=root_uuid))
        LOG.debug("got %d allocation requests under root provider %s",
                  len(root_alloc_reqs), root_uuid)
        alloc_requests |= root_alloc_reqs
    return list(alloc_requests), list(summaries.values())


@db_api.placement_context_manager.reader
def _get_traits_by_provider_tree(ctx, root_ids):
    """Returns a dict, keyed by provider IDs for all resource providers
    in all trees indicated in the ``root_ids``, of string trait names
    associated with that provider.

    :raises: ValueError when root_ids is empty.

    :param ctx: placement.context.RequestContext object
    :param root_ids: list of root resource provider IDs
    """
    if not root_ids:
        raise ValueError(_("Expected root_ids to be a list of root resource "
                           "provider internal IDs, but got an empty list."))

    rpt = sa.alias(_RP_TBL, name='rpt')
    rptt = sa.alias(_RP_TRAIT_TBL, name='rptt')
    tt = sa.alias(_TRAIT_TBL, name='t')
    rpt_rptt = sa.join(rpt, rptt, rpt.c.id == rptt.c.resource_provider_id)
    j = sa.join(rpt_rptt, tt, rptt.c.trait_id == tt.c.id)
    sel = sa.select([rptt.c.resource_provider_id, tt.c.name]).select_from(j)
    sel = sel.where(rpt.c.root_provider_id.in_(root_ids))
    res = collections.defaultdict(list)
    for r in ctx.session.execute(sel):
        res[r[0]].append(r[1])
    return res


@db_api.placement_context_manager.reader
def _trait_ids_from_names(ctx, names):
    """Given a list of string trait names, returns a dict, keyed by those
    string names, of the corresponding internal integer trait ID.

    :raises: ValueError when names is empty.

    :param ctx: placement.context.RequestContext object
    :param names: list of string trait names
    :raise TraitNotFound: if any named trait doesn't exist in the database.
    """
    if not names:
        raise ValueError(_("Expected names to be a list of string trait "
                           "names, but got an empty list."))

    # Avoid SAWarnings about unicode types...
    unames = map(six.text_type, names)
    tt = sa.alias(_TRAIT_TBL, name='t')
    sel = sa.select([tt.c.name, tt.c.id]).where(tt.c.name.in_(unames))
    trait_map = {r[0]: r[1] for r in ctx.session.execute(sel)}
    if len(trait_map) != len(names):
        missing = names - set(trait_map)
        raise exception.TraitNotFound(names=', '.join(missing))
    return trait_map


def _rp_rc_key(rp, rc):
    """Creates hashable key unique to a provider + resource class."""
    return rp.uuid, rc


def _consolidate_allocation_requests(areqs):
    """Consolidates a list of AllocationRequest into one.

    :param areqs: A list containing one AllocationRequest for each input
            RequestGroup.  This may mean that multiple resource_requests
            contain resource amounts of the same class from the same provider.
    :return: A single consolidated AllocationRequest, containing no
            resource_requests with duplicated (resource_provider,
            resource_class).
    """
    # Construct a dict, keyed by resource provider UUID + resource class, of
    # AllocationRequestResource, consolidating as we go.
    arrs_by_rp_rc = {}
    # areqs must have at least one element.  Save the anchor to populate the
    # returned AllocationRequest.
    anchor_rp_uuid = areqs[0].anchor_root_provider_uuid
    for areq in areqs:
        # Sanity check: the anchor should be the same for every areq
        if anchor_rp_uuid != areq.anchor_root_provider_uuid:
            # This should never happen.  If it does, it's a dev bug.
            raise ValueError(
                _("Expected every AllocationRequest in "
                  "`_consolidate_allocation_requests` to have the same "
                  "anchor!"))
        for arr in areq.resource_requests:
            key = _rp_rc_key(arr.resource_provider, arr.resource_class)
            if key not in arrs_by_rp_rc:
                arrs_by_rp_rc[key] = copy.copy(arr)
            else:
                arrs_by_rp_rc[key].amount += arr.amount
    return AllocationRequest(
        resource_requests=list(arrs_by_rp_rc.values()),
        anchor_root_provider_uuid=anchor_rp_uuid)


def _satisfies_group_policy(areqs, group_policy, num_granular_groups):
    """Applies group_policy to a list of AllocationRequest.

    Returns True or False, indicating whether this list of
    AllocationRequest satisfies group_policy, as follows:

    * "isolate": Each AllocationRequest with use_same_provider=True
                 is satisfied by a single resource provider.  If the "isolate"
                 policy is in effect, each such AllocationRequest must be
                 satisfied by a *unique* resource provider.
    * "none" or None: Always returns True.

    :param areqs: A list containing one AllocationRequest for each input
            RequestGroup.
    :param group_policy: String indicating how RequestGroups should interact
            with each other.  If the value is "isolate", we will return False
            if AllocationRequests that came from RequestGroups keyed by
            nonempty suffixes are satisfied by the same provider.
    :param num_granular_groups: The number of granular (use_same_provider=True)
            RequestGroups in the request.
    :return: True if areqs satisfies group_policy; False otherwise.
    """
    if group_policy != 'isolate':
        # group_policy="none" means no filtering
        return True

    # The number of unique resource providers referenced in the request groups
    # having use_same_provider=True must be equal to the number of granular
    # groups.
    num_granular_groups_in_areqs = len(set(
        # We can reliably use the first resource_request's provider: all the
        # resource_requests are satisfied by the same provider by definition
        # because use_same_provider is True.
        areq.resource_requests[0].resource_provider.uuid
        for areq in areqs
        if areq.use_same_provider))
    if num_granular_groups == num_granular_groups_in_areqs:
        return True
    LOG.debug('Excluding the following set of AllocationRequest because '
              'group_policy=isolate and the number of granular groups in the '
              'set (%d) does not match the number of granular groups in the '
              'request (%d): %s',
              num_granular_groups_in_areqs, num_granular_groups, str(areqs))
    return False


def _exceeds_capacity(areq, psum_res_by_rp_rc):
    """Checks a (consolidated) AllocationRequest against the provider summaries
    to ensure that it does not exceed capacity.

    Exceeding capacity can mean the total amount (already used plus this
    allocation) exceeds the total inventory amount; or this allocation exceeds
    the max_unit in the inventory record.

    :param areq: An AllocationRequest produced by the
            `_consolidate_allocation_requests` method.
    :param psum_res_by_rp_rc: A dict, keyed by provider + resource class via
            _rp_rc_key, of ProviderSummaryResource.
    :return: True if areq exceeds capacity; False otherwise.
    """
    for arr in areq.resource_requests:
        key = _rp_rc_key(arr.resource_provider, arr.resource_class)
        psum_res = psum_res_by_rp_rc[key]
        if psum_res.used + arr.amount > psum_res.capacity:
            LOG.debug('Excluding the following AllocationRequest because used '
                      '(%d) + amount (%d) > capacity (%d) for resource class '
                      '%s: %s',
                      psum_res.used, arr.amount, psum_res.capacity,
                      arr.resource_class, str(areq))
            return True
        if arr.amount > psum_res.max_unit:
            LOG.debug('Excluding the following AllocationRequest because '
                      'amount (%d) > max_unit (%d) for resource class %s: %s',
                      arr.amount, psum_res.max_unit, arr.resource_class,
                      str(areq))
            return True
    return False


def _merge_candidates(candidates, group_policy=None):
    """Given a dict, keyed by RequestGroup suffix, of tuples of
    (allocation_requests, provider_summaries), produce a single tuple of
    (allocation_requests, provider_summaries) that appropriately incorporates
    the elements from each.

    Each (alloc_reqs, prov_sums) in `candidates` satisfies one RequestGroup.
    This method creates a list of alloc_reqs, *each* of which satisfies *all*
    of the RequestGroups.

    For that merged list of alloc_reqs, a corresponding provider_summaries is
    produced.

    :param candidates: A dict, keyed by integer suffix or '', of tuples of
            (allocation_requests, provider_summaries) to be merged.
    :param group_policy: String indicating how RequestGroups should interact
            with each other.  If the value is "isolate", we will filter out
            candidates where AllocationRequests that came from RequestGroups
            keyed by nonempty suffixes are satisfied by the same provider.
    :return: A tuple of (allocation_requests, provider_summaries).
    """
    # Build a dict, keyed by anchor root provider UUID, of dicts, keyed by
    # suffix, of nonempty lists of AllocationRequest.  Each inner dict must
    # possess all of the suffix keys to be viable (i.e. contains at least
    # one AllocationRequest per RequestGroup).
    #
    # areq_lists_by_anchor =
    #   { anchor_root_provider_uuid: {
    #         '': [AllocationRequest, ...],   \  This dict must contain
    #         '1': [AllocationRequest, ...],   \ exactly one nonempty list per
    #         ...                              / suffix to be viable. That
    #         '42': [AllocationRequest, ...], /  filtering is done later.
    #     },
    #     ...
    #   }
    areq_lists_by_anchor = collections.defaultdict(
        lambda: collections.defaultdict(list))
    # Save off all the provider summaries lists - we'll use 'em later.
    all_psums = []
    # Construct a dict, keyed by resource provider + resource class, of
    # ProviderSummaryResource.  This will be used to do a final capacity
    # check/filter on each merged AllocationRequest.
    psum_res_by_rp_rc = {}
    for suffix, (areqs, psums) in candidates.items():
        for areq in areqs:
            anchor = areq.anchor_root_provider_uuid
            areq_lists_by_anchor[anchor][suffix].append(areq)
        for psum in psums:
            all_psums.append(psum)
            for psum_res in psum.resources:
                key = _rp_rc_key(
                    psum.resource_provider, psum_res.resource_class)
                psum_res_by_rp_rc[key] = psum_res

    # Create all combinations picking one AllocationRequest from each list
    # for each anchor.
    areqs = set()
    all_suffixes = set(candidates)
    num_granular_groups = len(all_suffixes - set(['']))
    for areq_lists_by_suffix in areq_lists_by_anchor.values():
        # Filter out any entries that don't have allocation requests for
        # *all* suffixes (i.e. all RequestGroups)
        if set(areq_lists_by_suffix) != all_suffixes:
            continue
        # We're using itertools.product to go from this:
        # areq_lists_by_suffix = {
        #     '':   [areq__A,   areq__B,   ...],
        #     '1':  [areq_1_A,  areq_1_B,  ...],
        #     ...
        #     '42': [areq_42_A, areq_42_B, ...],
        # }
        # to this:
        # [ [areq__A, areq_1_A, ..., areq_42_A],  Each of these lists is one
        #   [areq__A, areq_1_A, ..., areq_42_B],  areq_list in the loop below.
        #   [areq__A, areq_1_B, ..., areq_42_A],  each areq_list contains one
        #   [areq__A, areq_1_B, ..., areq_42_B],  AllocationRequest from each
        #   [areq__B, areq_1_A, ..., areq_42_A],  RequestGroup. So taken as a
        #   [areq__B, areq_1_A, ..., areq_42_B],  whole, each list is a viable
        #   [areq__B, areq_1_B, ..., areq_42_A],  (preliminary) candidate to
        #   [areq__B, areq_1_B, ..., areq_42_B],  return.
        #   ...,
        # ]
        for areq_list in itertools.product(
                *list(areq_lists_by_suffix.values())):
            # At this point, each AllocationRequest in areq_list is still
            # marked as use_same_provider. This is necessary to filter by group
            # policy, which enforces how these interact with each other.
            if not _satisfies_group_policy(
                    areq_list, group_policy, num_granular_groups):
                continue
            # Now we go from this (where 'arr' is AllocationRequestResource):
            # [ areq__B(arrX, arrY, arrZ),
            #   areq_1_A(arrM, arrN),
            #   ...,
            #   areq_42_B(arrQ)
            # ]
            # to this:
            # areq_combined(arrX, arrY, arrZ, arrM, arrN, arrQ)
            # Note that this discards the information telling us which
            # RequestGroup led to which piece of the final AllocationRequest.
            # We needed that to be present for the previous filter; we need it
            # to be *absent* for the next one (and for the final output).
            areq = _consolidate_allocation_requests(areq_list)
            # Since we sourced this AllocationRequest from multiple
            # *independent* queries, it's possible that the combined result
            # now exceeds capacity where amounts of the same RP+RC were
            # folded together.  So do a final capacity check/filter.
            if _exceeds_capacity(areq, psum_res_by_rp_rc):
                continue
            areqs.add(areq)

    # It's possible we've filtered out everything.  If so, short out.
    if not areqs:
        return [], []

    # Now we have to produce provider summaries.  The provider summaries in
    # the candidates input contain all the information; we just need to
    # filter it down to only the providers in trees represented by our merged
    # list of allocation requests.
    tree_uuids = set()
    for areq in areqs:
        for arr in areq.resource_requests:
            tree_uuids.add(arr.resource_provider.root_provider_uuid)
    psums = [psum for psum in all_psums if
             psum.resource_provider.root_provider_uuid in tree_uuids]

    return list(areqs), psums


class AllocationCandidates(object):
    """The AllocationCandidates object is a collection of possible allocations
    that match some request for resources, along with some summary information
    about the resource providers involved in these allocation candidates.
    """

    def __init__(self, allocation_requests=None, provider_summaries=None):
        # A collection of allocation possibilities that can be attempted by the
        # caller that would, at the time of calling, meet the requested
        # resource constraints
        self.allocation_requests = allocation_requests
        # Information about usage and inventory that relate to any provider
        # contained in any of the AllocationRequest objects in the
        # allocation_requests field
        self.provider_summaries = provider_summaries

    @classmethod
    def get_by_requests(cls, context, requests, limit=None, group_policy=None):
        """Returns an AllocationCandidates object containing all resource
        providers matching a set of supplied resource constraints, with a set
        of allocation requests constructed from that list of resource
        providers. If CONF.placement.randomize_allocation_candidates (on
        contex.config) is True (default is False) then the order of the
        allocation requests will be randomized.

        :param context: Nova RequestContext.
        :param requests: Dict, keyed by suffix, of placement.lib.RequestGroup
        :param limit: An integer, N, representing the maximum number of
                      allocation candidates to return. If
                      CONF.placement.randomize_allocation_candidates is True
                      this will be a random sampling of N of the available
                      results. If False then the first N results, in whatever
                      order the database picked them, will be returned. In
                      either case if there are fewer than N total results,
                      all the results will be returned.
        :param group_policy: String indicating how RequestGroups with
                             use_same_provider=True should interact with each
                             other.  If the value is "isolate", we will filter
                             out allocation requests where any such
                             RequestGroups are satisfied by the same RP.
        :return: An instance of AllocationCandidates with allocation_requests
                 and provider_summaries satisfying `requests`, limited
                 according to `limit`.
        """
        alloc_reqs, provider_summaries = cls._get_by_requests(
            context, requests, limit=limit, group_policy=group_policy)
        return cls(
            allocation_requests=alloc_reqs,
            provider_summaries=provider_summaries,
        )

    @staticmethod
    def _get_by_one_request(context, request, sharing_providers, has_trees):
        """Get allocation candidates for one RequestGroup.

        Must be called from within an placement_context_manager.reader
        (or writer) context.

        :param context: Nova RequestContext.
        :param request: One placement.lib.RequestGroup
        :param sharing_providers: dict, keyed by resource class internal ID, of
                                  the set of provider IDs containing shared
                                  inventory of that resource class
        :param has_trees: bool indicating there is some level of nesting in the
                          environment (if there isn't, we take faster, simpler
                          code paths)
        :return: A tuple of (allocation_requests, provider_summaries)
                 satisfying `request`.
        """
        # Transform resource string names to internal integer IDs
        resources = {
            rc_cache.RC_CACHE.id_from_string(key): value
            for key, value in request.resources.items()
        }

        # maps the trait name to the trait internal ID
        required_trait_map = {}
        forbidden_trait_map = {}
        for trait_map, traits in (
                (required_trait_map, request.required_traits),
                (forbidden_trait_map, request.forbidden_traits)):
            if traits:
                trait_map.update(_trait_ids_from_names(context, traits))

        member_of = request.member_of
        tree_root_id = None
        if request.in_tree:
            tree_ids = _provider_ids_from_uuid(context, request.in_tree)
            if tree_ids is None:
                # List operations should simply return an empty list when a
                # non-existing resource provider UUID is given for in_tree.
                return [], []
            tree_root_id = tree_ids.root_id
            LOG.debug("getting allocation candidates in the same tree"
                      "with the root provider %s", tree_ids.root_uuid)

        any_sharing = any(sharing_providers.values())
        if not request.use_same_provider and (has_trees or any_sharing):
            # TODO(jaypipes): The check/callout to handle trees goes here.
            # Build a dict, keyed by resource class internal ID, of lists of
            # internal IDs of resource providers that share some inventory for
            # each resource class requested.
            # If there aren't any providers that have any of the
            # required traits, just exit early...
            if required_trait_map:
                # TODO(cdent): Now that there is also a forbidden_trait_map
                # it should be possible to further optimize this attempt at
                # a quick return, but we leave that to future patches for
                # now.
                trait_rps = _get_provider_ids_having_any_trait(
                    context, required_trait_map)
                if not trait_rps:
                    return [], []
            rp_candidates = _get_trees_matching_all(
                context, resources, required_trait_map, forbidden_trait_map,
                sharing_providers, member_of, tree_root_id)
            return _alloc_candidates_multiple_providers(
                context, resources, required_trait_map, forbidden_trait_map,
                rp_candidates)

        # Either we are processing a single-RP request group, or there are no
        # sharing providers that (help) satisfy the request.  Get a list of
        # tuples of (internal provider ID, root provider ID) that have ALL
        # the requested resources and more efficiently construct the
        # allocation requests.
        rp_tuples = _get_provider_ids_matching(
            context, resources, required_trait_map, forbidden_trait_map,
            member_of, tree_root_id)
        return _alloc_candidates_single_provider(context, resources, rp_tuples)

    @classmethod
    # TODO(efried): This is only a writer context because it accesses the
    # resource_providers table via ResourceProvider.get_by_uuid, which does
    # data migration to populate the root_provider_uuid.  Change this back to a
    # reader when that migration is no longer happening.
    @db_api.placement_context_manager.writer
    def _get_by_requests(cls, context, requests, limit=None,
                         group_policy=None):
        # TODO(jaypipes): Make a RequestGroupContext object and put these
        # pieces of information in there, passing the context to the various
        # internal functions handling that part of the request.
        sharing = {}
        for request in requests.values():
            member_of = request.member_of
            for rc_name, amount in request.resources.items():
                rc_id = rc_cache.RC_CACHE.id_from_string(rc_name)
                if rc_id not in sharing:
                    sharing[rc_id] = _get_providers_with_shared_capacity(
                        context, rc_id, amount, member_of)
        has_trees = _has_provider_trees(context)

        candidates = {}
        for suffix, request in requests.items():
            alloc_reqs, summaries = cls._get_by_one_request(
                context, request, sharing, has_trees)
            LOG.debug("%s (suffix '%s') returned %d matches",
                      str(request), str(suffix), len(alloc_reqs))
            if not alloc_reqs:
                # Shortcut: If any one request resulted in no candidates, the
                # whole operation is shot.
                return [], []
            # Mark each allocation request according to whether its
            # corresponding RequestGroup required it to be restricted to a
            # single provider.  We'll need this later to evaluate group_policy.
            for areq in alloc_reqs:
                areq.use_same_provider = request.use_same_provider
            candidates[suffix] = alloc_reqs, summaries

        # At this point, each (alloc_requests, summary_obj) in `candidates` is
        # independent of the others. We need to fold them together such that
        # each allocation request satisfies *all* the incoming `requests`.  The
        # `candidates` dict is guaranteed to contain entries for all suffixes,
        # or we would have short-circuited above.
        alloc_request_objs, summary_objs = _merge_candidates(
            candidates, group_policy=group_policy)

        return cls._limit_results(context, alloc_request_objs, summary_objs,
                                  limit)

    @staticmethod
    def _limit_results(context, alloc_request_objs, summary_objs, limit):
        # Limit the number of allocation request objects. We do this after
        # creating all of them so that we can do a random slice without
        # needing to mess with the complex sql above or add additional
        # columns to the DB.
        if limit and limit < len(alloc_request_objs):
            if context.config.placement.randomize_allocation_candidates:
                alloc_request_objs = random.sample(alloc_request_objs, limit)
            else:
                alloc_request_objs = alloc_request_objs[:limit]
            # Limit summaries to only those mentioned in the allocation reqs.
            kept_summary_objs = []
            alloc_req_rp_uuids = set()
            # Extract resource provider uuids from the resource requests.
            for aro in alloc_request_objs:
                for arr in aro.resource_requests:
                    alloc_req_rp_uuids.add(arr.resource_provider.uuid)
            for summary in summary_objs:
                rp_uuid = summary.resource_provider.uuid
                # Skip a summary if we are limiting and haven't selected an
                # allocation request that uses the resource provider.
                if rp_uuid not in alloc_req_rp_uuids:
                    continue
                kept_summary_objs.append(summary)
            summary_objs = kept_summary_objs
        elif context.config.placement.randomize_allocation_candidates:
            random.shuffle(alloc_request_objs)

        return alloc_request_objs, summary_objs
