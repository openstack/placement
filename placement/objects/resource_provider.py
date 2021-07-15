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

# NOTE(cdent): The resource provider objects are designed to never be
# used over RPC. Remote manipulation is done with the placement HTTP
# API. The 'remotable' decorators should not be used, the objects should
# not be registered and there is no need to express VERSIONs nor handle
# obj_make_compatible.

from oslo_db import api as oslo_db_api
from oslo_db import exception as db_exc
from oslo_log import log as logging
from oslo_utils import excutils
import sqlalchemy as sa
from sqlalchemy import exc as sqla_exc
from sqlalchemy import func

from placement.db.sqlalchemy import models
from placement import db_api
from placement import exception
from placement.objects import inventory as inv_obj
from placement.objects import research_context as res_ctx
from placement.objects import trait as trait_obj

_ALLOC_TBL = models.Allocation.__table__
_INV_TBL = models.Inventory.__table__
_RP_TBL = models.ResourceProvider.__table__
_AGG_TBL = models.PlacementAggregate.__table__
_RP_AGG_TBL = models.ResourceProviderAggregate.__table__
_RP_TRAIT_TBL = models.ResourceProviderTrait.__table__

LOG = logging.getLogger(__name__)


def _get_current_inventory_resources(ctx, rp):
    """Returns a set() containing the resource class IDs for all resources
    currently having an inventory record for the supplied resource provider.

    :param ctx: `placement.context.RequestContext` that may be used to grab a
                DB connection.
    :param rp: Resource provider to query inventory for.
    """
    cur_res_sel = sa.select(_INV_TBL.c.resource_class_id).where(
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
        _ALLOC_TBL.c.resource_class_id.label('resource_class'),
    ).where(
        sa.and_(_ALLOC_TBL.c.resource_provider_id == rp.id,
                _ALLOC_TBL.c.resource_class_id.in_(to_delete))
    ).group_by(_ALLOC_TBL.c.resource_class_id)
    allocations = ctx.session.execute(allocation_query).fetchall()
    if allocations:
        resource_classes = ', '.join(
            [ctx.rc_cache.string_from_id(alloc[0])
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
    :param inv_list: List of Inventory objects
    :param to_add: set() containing resource class IDs to search inv_list for
                   adding to resource provider.
    """
    for rc_id in to_add:
        rc_str = ctx.rc_cache.string_from_id(rc_id)
        inv_record = inv_obj.find(inv_list, rc_str)
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
    :param inv_list: List of Inventory objects
    :param to_update: set() containing resource class IDs to search inv_list
                      for updating in resource provider.
    :returns: A list of (uuid, class) tuples that have exceeded their
              capacity after this inventory update.
    """
    exceeded = []
    for rc_id in to_update:
        rc_str = ctx.rc_cache.string_from_id(rc_id)
        inv_record = inv_obj.find(inv_list, rc_str)
        allocation_query = sa.select(
            func.sum(_ALLOC_TBL.c.used).label('usage'))
        allocation_query = allocation_query.where(
            sa.and_(
                _ALLOC_TBL.c.resource_provider_id == rp.id,
                _ALLOC_TBL.c.resource_class_id == rc_id))
        allocations = ctx.session.execute(allocation_query).first()
        if (
            allocations and
            allocations.usage is not None and
            allocations.usage > inv_record.capacity
        ):
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
    rc_id = context.rc_cache.id_from_string(inventory.resource_class)
    _add_inventory_to_provider(
        context, rp, [inventory], set([rc_id]))
    rp.increment_generation()


@db_api.placement_context_manager.writer
def _update_inventory(context, rp, inventory):
    """Update an inventory already on the provider.

    :raises `exception.ResourceClassNotFound` if inventory.resource_class
            cannot be found in the DB.
    """
    rc_id = context.rc_cache.id_from_string(inventory.resource_class)
    exceeded = _update_inventory_for_provider(
        context, rp, [inventory], set([rc_id]))
    rp.increment_generation()
    return exceeded


@db_api.placement_context_manager.writer
def _delete_inventory(context, rp, resource_class):
    """Delete up to one Inventory of the given resource_class string.

    :raises `exception.ResourceClassNotFound` if resource_class
            cannot be found in the DB.
    """
    rc_id = context.rc_cache.id_from_string(resource_class)
    if not _delete_inventory_from_provider(context, rp, [rc_id]):
        raise exception.NotFound(
            'No inventory of class %s found for delete'
            % resource_class)
    rp.increment_generation()


@db_api.placement_context_manager.writer
def _set_inventory(context, rp, inv_list):
    """Given a list of Inventory objects, replaces the inventory of the
    resource provider in a safe, atomic fashion using the resource
    provider's generation as a consistent view marker.

    :param context: Nova RequestContext.
    :param rp: `ResourceProvider` object upon which to set inventory.
    :param inv_list: A list of `Inventory` objects to save to backend storage.
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
    these_resources = set([context.rc_cache.id_from_string(r.resource_class)
                           for r in inv_list])

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
    rp_to_root = sa.join(rpt, root, rpt.c.root_provider_id == root.c.id)
    rp_to_parent = sa.outerjoin(
        rp_to_root, parent,
        rpt.c.parent_provider_id == parent.c.id)
    sel = sa.select(
        rpt.c.id,
        rpt.c.uuid,
        rpt.c.name,
        rpt.c.generation,
        root.c.uuid.label("root_provider_uuid"),
        parent.c.uuid.label("parent_provider_uuid"),
        rpt.c.updated_at,
        rpt.c.created_at,
    ).select_from(rp_to_parent).where(rpt.c.uuid == uuid)
    res = context.session.execute(sel).fetchone()
    if not res:
        raise exception.NotFound(
            'No resource provider with uuid %s found' % uuid)
    return dict(res._mapping)


@db_api.placement_context_manager.reader
def _get_aggregates_by_provider_id(context, rp_id):
    """Returns a dict, keyed by internal aggregate ID, of aggregate UUIDs
    associated with the supplied internal resource provider ID.
    """
    join_statement = sa.join(
        _AGG_TBL, _RP_AGG_TBL, sa.and_(
            _AGG_TBL.c.id == _RP_AGG_TBL.c.aggregate_id,
            _RP_AGG_TBL.c.resource_provider_id == rp_id))
    sel = sa.select(_AGG_TBL.c.id, _AGG_TBL.c.uuid).select_from(
        join_statement)
    return {r[0]: r[1] for r in context.session.execute(sel).fetchall()}


def _ensure_aggregate(ctx, agg_uuid):
    """Finds an aggregate and returns its internal ID. If not found, creates
    the aggregate and returns the new aggregate's internal ID.

    If there is a race to create the aggregate (which can happen under rare
    high load conditions), retry up to 10 times.
    """
    sel = sa.select(_AGG_TBL.c.id).where(_AGG_TBL.c.uuid == agg_uuid)
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
        with excutils.save_and_reraise_exception():
            LOG.debug("_ensure_provider() failed to create new aggregate %s. "
                      "Another thread already created an aggregate record. ",
                      agg_uuid)


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
    """Given a ResourceProvider object and a list of Trait objects, replaces
    the set of traits associated with the resource provider.

    :raises: ConcurrentUpdateDetected if the resource provider's traits or
             inventory was changed in between the time when we first started to
             set traits and the end of this routine.

    :param rp: The ResourceProvider object to set traits against
    :param traits: List of Trait objects
    """
    # Get the internal IDs of our existing traits
    existing_traits = trait_obj.get_traits_by_provider_id(context, rp.id)
    existing_traits = set(rec.id for rec in existing_traits)
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
    child_sel = sa.select(_RP_TBL.c.id)
    child_sel = child_sel.where(_RP_TBL.c.parent_provider_id == rp_id)
    child_res = context.session.execute(child_sel.limit(1)).fetchone()
    if child_res:
        return True
    return False


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
    subq_1 = subq_1.subquery(name="subq_1")

    subq_2 = sa.select(subq_1.c.id).select_from(subq_1).scalar_subquery()

    upd = _RP_TBL.update().where(_RP_TBL.c.id.in_(subq_2))
    upd = upd.values(root_provider_id=_RP_TBL.c.id)
    res = context.session.execute(upd)

    return res.rowcount, res.rowcount


@db_api.placement_context_manager.writer
def _delete_rp_record(context, _id):
    query = context.session.query(models.ResourceProvider)
    query = query.filter(models.ResourceProvider.id == _id)
    return query.delete(synchronize_session=False)


class ResourceProvider(object):
    SETTABLE_FIELDS = ('name', 'parent_provider_uuid')

    __slots__ = ('_context', 'id', 'uuid', 'name', 'generation',
                 'parent_provider_uuid', 'root_provider_uuid', 'updated_at',
                 'created_at')

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

    def save(self, allow_reparenting=False):
        """Save the changes to the database

        :param allow_reparenting: If True then it allows changing the parent RP
        to a different RP as well as changing it to None (un-parenting).
        If False, then only changing the parent from None to an RP is allowed
        the rest is rejected with ObjectActionError.
        """
        # These are the only fields we are willing to save with.
        # If there are others, ignore them.
        updates = {
            'name': self.name,
            'parent_provider_uuid': self.parent_provider_uuid,
        }
        self._update_in_db(self._context, self.id, updates, allow_reparenting)

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
                    reason='parent provider UUID cannot be same as UUID. '
                           'Please set parent provider UUID to None if '
                           'there is no parent.')

            parent_ids = res_ctx.provider_ids_from_uuid(context, parent_uuid)
            if parent_ids is None:
                raise exception.ObjectActionError(
                    action='create',
                    reason='parent provider UUID does not exist.')

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
    def _update_in_db(self, context, id, updates, allow_reparenting):
        # A list of resource providers in the subtree of resource provider to
        # update
        subtree_rps = []
        # The new root RP if changed
        new_root_id = None
        new_root_uuid = None
        if 'parent_provider_uuid' in updates:
            my_ids = res_ctx.provider_ids_from_uuid(context, self.uuid)
            parent_uuid = updates.pop('parent_provider_uuid')
            if parent_uuid is not None:
                parent_ids = res_ctx.provider_ids_from_uuid(
                    context, parent_uuid)
                # User supplied a parent, let's make sure it exists
                if parent_ids is None:
                    raise exception.ObjectActionError(
                        action='create',
                        reason='parent provider UUID does not exist.')
                if (my_ids.parent_id is not None and
                        my_ids.parent_id != parent_ids.id and
                        not allow_reparenting):
                    raise exception.ObjectActionError(
                        action='update',
                        reason='re-parenting a provider is not currently '
                               'allowed.')
                # So the user specified a new parent. We have to make sure
                # that the new parent is not a descendant of the
                # current RP to avoid a loop in the graph. It could be
                # easily checked by traversing the tree from the new parent
                # up to the root and see if we ever hit the current RP
                # along the way. However later we need to update every
                # descendant of the current RP with a possibly new root
                # so we go with the more expensive way and gather every
                # descendant for the current RP and check if the new
                # parent is part of that set.
                subtree_rps = self.get_subtree(context)
                subtree_rp_uuids = {rp.uuid for rp in subtree_rps}
                if parent_uuid in subtree_rp_uuids:
                    raise exception.ObjectActionError(
                        action='update',
                        reason='creating loop in the provider tree is '
                               'not allowed.')

                updates['root_provider_id'] = parent_ids.root_id
                updates['parent_provider_id'] = parent_ids.id
                self.root_provider_uuid = parent_ids.root_uuid
                new_root_id = parent_ids.root_id
                new_root_uuid = parent_ids.root_uuid
            else:
                if my_ids.parent_id is not None:
                    if not allow_reparenting:
                        raise exception.ObjectActionError(
                            action='update',
                            reason='un-parenting a provider is not currently '
                                   'allowed.')

                    # we don't need to do loop detection but we still need to
                    # collect the RPs from the subtree so that the new root
                    # value is updated in the whole subtree below.
                    subtree_rps = self.get_subtree(context)

                    # this RP becomes a new root RP
                    updates['root_provider_id'] = my_ids.id
                    updates['parent_provider_id'] = None
                    self.root_provider_uuid = my_ids.uuid
                    new_root_id = my_ids.id
                    new_root_uuid = my_ids.uuid

        db_rp = context.session.query(models.ResourceProvider).filter_by(
            id=id).first()
        db_rp.update(updates)
        context.session.add(db_rp)

        # We should also update the root providers of the resource providers
        # that are in our subtree
        for rp in subtree_rps:
            # If the parent is not updated, this clause is skipped since the
            # `subtree_rps` has no element.
            rp.root_provider_uuid = new_root_uuid
            db_rp = context.session.query(
                models.ResourceProvider).filter_by(id=rp.id).first()
            data = {'root_provider_id': new_root_id}
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
                reason='parent provider UUID does not exist.')

    @staticmethod
    @db_api.placement_context_manager.reader
    def _from_db_object(context, resource_provider, db_resource_provider):
        for field in ['id', 'uuid', 'name', 'generation',
                      'root_provider_uuid', 'parent_provider_uuid',
                      'updated_at', 'created_at']:
            setattr(resource_provider, field, db_resource_provider[field])
        return resource_provider

    def get_subtree(self, context, rp_uuid_to_child_rps=None):
        """Return every RP from the same tree that is part of the subtree
        rooted at the current RP.

        :param context: the request context
        :param rp_uuid_to_child_rps: a dict of list of children
            ResourceProviders keyed by the UUID of their parent RP. If it is
            None then this dict is calculated locally.
        :return: a list of ResourceProvider objects
        """
        # if we are at a start of a recursion then prepare some data structure
        if rp_uuid_to_child_rps is None:
            same_tree = get_all_by_filters(
                context, filters={'in_tree': self.uuid})
            rp_uuid_to_child_rps = collections.defaultdict(set)
            for rp in same_tree:
                if rp.parent_provider_uuid:
                    rp_uuid_to_child_rps[rp.parent_provider_uuid].add(rp)

        subtree = [self]
        for child_rp in rp_uuid_to_child_rps[self.uuid]:
            subtree.extend(
                child_rp.get_subtree(context, rp_uuid_to_child_rps))
        return subtree


@db_api.placement_context_manager.reader
def _get_all_by_filters_from_db(context, filters):
    # Eg. filters can be:
    #  filters = {
    #      'name': <name>,
    #      'uuid': <uuid>,
    #      'member_of': [[<aggregate_uuid>, <aggregate_uuid>],
    #                    [<aggregate_uuid>]]
    #      'forbidden_aggs': [<aggregate_uuid>, <aggregate_uuid>]
    #      'resources': {
    #          'VCPU': 1,
    #          'MEMORY_MB': 1024
    #      },
    #      'in_tree': <uuid>,
    #      'required_traits': [{<trait_name>, ...}, {...}]
    #      'forbidden_traits': {<trait_name>, ...}
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
    forbidden_aggs = filters.pop('forbidden_aggs', [])
    required_traits = filters.pop('required_traits', [])
    forbidden_traits = filters.pop('forbidden_traits', {})
    resources = filters.pop('resources', {})
    in_tree = filters.pop('in_tree', None)

    rp = sa.alias(_RP_TBL, name="rp")
    root_rp = sa.alias(_RP_TBL, name="root_rp")
    parent_rp = sa.alias(_RP_TBL, name="parent_rp")

    rp_to_root = sa.join(
        rp, root_rp,
        rp.c.root_provider_id == root_rp.c.id)
    rp_to_parent = sa.outerjoin(
        rp_to_root, parent_rp,
        rp.c.parent_provider_id == parent_rp.c.id)

    query = sa.select(
        rp.c.id,
        rp.c.uuid,
        rp.c.name,
        rp.c.generation,
        rp.c.updated_at,
        rp.c.created_at,
        root_rp.c.uuid.label("root_provider_uuid"),
        parent_rp.c.uuid.label("parent_provider_uuid"),
    ).select_from(rp_to_parent)

    if name:
        query = query.where(rp.c.name == name)
    if uuid:
        query = query.where(rp.c.uuid == uuid)
    if in_tree:
        # The 'in_tree' parameter is the UUID of a resource provider that
        # the caller wants to limit the returned providers to only those
        # within its "provider tree". So, we look up the resource provider
        # having the UUID specified by the 'in_tree' parameter and grab the
        # root_provider_id value of that record. We can then ask for only
        # those resource providers having a root_provider_id of that value.
        tree_ids = res_ctx.provider_ids_from_uuid(context, in_tree)
        if tree_ids is None:
            # List operations should simply return an empty list when a
            # non-existing resource provider UUID is given.
            return []
        root_id = tree_ids.root_id
        query = query.where(rp.c.root_provider_id == root_id)
    if required_traits:
        # translate trait names to trait internal IDs while keeping the nested
        # structure
        required_traits = [
            {
                context.trait_cache.id_from_string(trait)
                for trait in any_traits
            }
            for any_traits in required_traits
        ]

        rps_with_matching_traits = (
            res_ctx.provider_ids_matching_required_traits(
                context, required_traits))
        if not rps_with_matching_traits:
            return []
        query = query.where(rp.c.id.in_(rps_with_matching_traits))
    if forbidden_traits:
        trait_map = trait_obj.ids_from_names(context, forbidden_traits)
        trait_rps = res_ctx.get_provider_ids_having_any_trait(
            context, trait_map.values())
        if trait_rps:
            query = query.where(~rp.c.id.in_(trait_rps))
    if member_of:
        rps_in_aggs = res_ctx.provider_ids_matching_aggregates(
            context, member_of)
        if not rps_in_aggs:
            return []
        query = query.where(rp.c.id.in_(rps_in_aggs))
    if forbidden_aggs:
        rps_bad_aggs = res_ctx.provider_ids_matching_aggregates(
            context, [forbidden_aggs])
        if rps_bad_aggs:
            query = query.where(~rp.c.id.in_(rps_bad_aggs))
    for rc_name, amount in resources.items():
        rc_id = context.rc_cache.id_from_string(rc_name)
        rps_with_resource = res_ctx.get_providers_with_resource(
            context, rc_id, amount)
        rps_with_resource = (rp[0] for rp in rps_with_resource)
        query = query.where(rp.c.id.in_(rps_with_resource))

    return context.session.execute(query).fetchall()


def get_all_by_filters(context, filters=None):
    """Returns a list of `ResourceProvider` objects that have sufficient
    resources in their inventories to satisfy the amounts specified in the
    `filters` parameter.

    If no resource providers can be found, the function will return an
    empty list.

    :param context: `placement.context.RequestContext` that may be used to
        grab a DB connection.
    :param filters: Can be `name`, `uuid`, `member_of`, `in_tree`,
        `required_traits`, `forbidden_traits`, or `resources` where
        `member_of` is a list of list of aggregate UUIDs, `required_traits` is
        a list of set of trait names, `forbidden_traits` is a set of trait
        names, `in_tree` is a UUID of a resource provider that we can use to
        find the root provider ID of the tree of providers to filter results
        by and `resources` is a dict of amounts keyed by resource classes.
    :type filters: dict
    """
    resource_providers = _get_all_by_filters_from_db(context, filters)
    return [
        ResourceProvider(context, **rp._mapping) for rp in resource_providers
    ]
