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

from oslo_db import api as oslo_db_api
from oslo_log import log as logging
import sqlalchemy as sa
from sqlalchemy import sql

from placement.db.sqlalchemy import models
from placement import db_api
from placement import exception
from placement.objects import consumer as consumer_obj
from placement.objects import project as project_obj
from placement.objects import resource_provider as rp_obj
from placement.objects import user as user_obj


_ALLOC_TBL = models.Allocation.__table__
_CONSUMER_TBL = models.Consumer.__table__
_INV_TBL = models.Inventory.__table__
_PROJECT_TBL = models.Project.__table__
_RP_TBL = models.ResourceProvider.__table__
_USER_TBL = models.User.__table__

LOG = logging.getLogger(__name__)


class Allocation(object):

    def __init__(self, id=None, resource_provider=None, consumer=None,
                 resource_class=None, used=0, updated_at=None,
                 created_at=None):
        self.id = id
        self.resource_provider = resource_provider
        self.resource_class = resource_class
        self.consumer = consumer
        self.used = used
        self.updated_at = updated_at
        self.created_at = created_at


@db_api.placement_context_manager.writer
def _delete_allocations_for_consumer(ctx, consumer_id):
    """Deletes any existing allocations that correspond to the allocations to
    be written. This is wrapped in a transaction, so if the write subsequently
    fails, the deletion will also be rolled back.
    """
    del_sql = _ALLOC_TBL.delete().where(
        _ALLOC_TBL.c.consumer_id == consumer_id)
    ctx.session.execute(del_sql)


@db_api.placement_context_manager.writer
def _delete_allocations_by_ids(ctx, alloc_ids):
    """Deletes allocations having an internal id value in the set of supplied
    IDs
    """
    del_sql = _ALLOC_TBL.delete().where(_ALLOC_TBL.c.id.in_(alloc_ids))
    ctx.session.execute(del_sql)


def _check_capacity_exceeded(ctx, allocs):
    """Checks to see if the supplied allocation records would result in any of
    the inventories involved having their capacity exceeded.

    Raises an InvalidAllocationCapacityExceeded exception if any inventory
    would be exhausted by the allocation. Raises an
    InvalidAllocationConstraintsViolated exception if any of the `step_size`,
    `min_unit` or `max_unit` constraints in an inventory will be violated
    by any one of the allocations.

    If no inventories would be exceeded or violated by the allocations, the
    function returns a list of `ResourceProvider` objects that contain the
    generation at the time of the check.

    :param ctx: `placement.context.RequestContext` that has an oslo_db
                Session
    :param allocs: List of `Allocation` objects to check
    """
    # The SQL generated below looks like this:
    # SELECT
    #   rp.id,
    #   rp.uuid,
    #   rp.generation,
    #   inv.resource_class_id,
    #   inv.total,
    #   inv.reserved,
    #   inv.allocation_ratio,
    #   allocs.used
    # FROM resource_providers AS rp
    # JOIN inventories AS i1
    # ON rp.id = i1.resource_provider_id
    # LEFT JOIN (
    #    SELECT resource_provider_id, resource_class_id, SUM(used) AS used
    #    FROM allocations
    #    WHERE resource_class_id IN ($RESOURCE_CLASSES)
    #    AND resource_provider_id IN ($RESOURCE_PROVIDERS)
    #    GROUP BY resource_provider_id, resource_class_id
    # ) AS allocs
    # ON inv.resource_provider_id = allocs.resource_provider_id
    # AND inv.resource_class_id = allocs.resource_class_id
    # WHERE rp.id IN ($RESOURCE_PROVIDERS)
    # AND inv.resource_class_id IN ($RESOURCE_CLASSES)
    #
    # We then take the results of the above and determine if any of the
    # inventory will have its capacity exceeded.
    rc_ids = set([ctx.rc_cache.id_from_string(a.resource_class)
                  for a in allocs])
    provider_uuids = set([a.resource_provider.uuid for a in allocs])
    provider_ids = set([a.resource_provider.id for a in allocs])
    usage = sa.select(
        _ALLOC_TBL.c.resource_provider_id,
        _ALLOC_TBL.c.resource_class_id,
        sql.func.sum(_ALLOC_TBL.c.used).label('used'),
    )
    usage = usage.where(
        sa.and_(_ALLOC_TBL.c.resource_class_id.in_(rc_ids),
                _ALLOC_TBL.c.resource_provider_id.in_(provider_ids)))
    usage = usage.group_by(_ALLOC_TBL.c.resource_provider_id,
                           _ALLOC_TBL.c.resource_class_id)
    usage = usage.subquery(name='usage')

    inv_join = sql.join(
        _RP_TBL, _INV_TBL,
        sql.and_(_RP_TBL.c.id == _INV_TBL.c.resource_provider_id,
                 _INV_TBL.c.resource_class_id.in_(rc_ids)))
    primary_join = sql.outerjoin(
        inv_join, usage,
        sql.and_(
            _INV_TBL.c.resource_provider_id == usage.c.resource_provider_id,
            _INV_TBL.c.resource_class_id == usage.c.resource_class_id)
    )

    sel = sa.select(
        _RP_TBL.c.id.label('resource_provider_id'),
        _RP_TBL.c.uuid,
        _RP_TBL.c.generation,
        _INV_TBL.c.resource_class_id,
        _INV_TBL.c.total,
        _INV_TBL.c.reserved,
        _INV_TBL.c.allocation_ratio,
        _INV_TBL.c.min_unit,
        _INV_TBL.c.max_unit,
        _INV_TBL.c.step_size,
        usage.c.used,
    ).select_from(primary_join)
    sel = sel.where(
        sa.and_(_RP_TBL.c.id.in_(provider_ids),
                _INV_TBL.c.resource_class_id.in_(rc_ids)))
    records = ctx.session.execute(sel)
    # Create a map keyed by (rp_uuid, res_class) for the records in the DB
    usage_map = {}
    provs_with_inv = set()
    for record in records:
        map_key = (record.uuid, record.resource_class_id)
        if map_key in usage_map:
            raise KeyError("%s already in usage_map, bad query" % str(map_key))
        usage_map[map_key] = record
        provs_with_inv.add(record.uuid)
    # Ensure that all providers have existing inventory
    missing_provs = provider_uuids - provs_with_inv
    if missing_provs:
        class_str = ', '.join([ctx.rc_cache.string_from_id(rc_id)
                               for rc_id in rc_ids])
        provider_str = ', '.join(missing_provs)
        raise exception.InvalidInventory(
            resource_class=class_str, resource_provider=provider_str)

    res_providers = {}
    rp_resource_class_sum = collections.defaultdict(
        lambda: collections.defaultdict(int))
    for alloc in allocs:
        rc_id = ctx.rc_cache.id_from_string(alloc.resource_class)
        rp_uuid = alloc.resource_provider.uuid
        if rp_uuid not in res_providers:
            res_providers[rp_uuid] = alloc.resource_provider
        amount_needed = alloc.used
        rp_resource_class_sum[rp_uuid][rc_id] += amount_needed
        # No use checking usage if we're not asking for anything
        if amount_needed == 0:
            continue
        key = (rp_uuid, rc_id)
        try:
            usage = usage_map[key]
        except KeyError:
            # The resource class at rc_id is not in the usage map.
            raise exception.InvalidInventory(
                resource_class=alloc.resource_class,
                resource_provider=rp_uuid)
        allocation_ratio = usage.allocation_ratio
        min_unit = usage.min_unit
        max_unit = usage.max_unit
        step_size = usage.step_size

        # check min_unit, max_unit, step_size
        if (amount_needed < min_unit or amount_needed > max_unit or
                amount_needed % step_size != 0):
            LOG.warning(
                "Allocation for %(rc)s on resource provider %(rp)s "
                "violates min_unit, max_unit, or step_size. "
                "Requested: %(requested)s, min_unit: %(min_unit)s, "
                "max_unit: %(max_unit)s, step_size: %(step_size)s",
                {'rc': alloc.resource_class,
                 'rp': rp_uuid,
                 'requested': amount_needed,
                 'min_unit': min_unit,
                 'max_unit': max_unit,
                 'step_size': step_size})
            raise exception.InvalidAllocationConstraintsViolated(
                resource_class=alloc.resource_class,
                resource_provider=rp_uuid)

        # usage.used can be returned as None
        used = usage.used or 0
        capacity = (usage.total - usage.reserved) * allocation_ratio
        if (capacity < (used + amount_needed) or
                capacity < (used + rp_resource_class_sum[rp_uuid][rc_id])):
            LOG.warning(
                "Over capacity for %(rc)s on resource provider %(rp)s. "
                "Needed: %(needed)s, Used: %(used)s, Capacity: %(cap)s",
                {'rc': alloc.resource_class,
                 'rp': rp_uuid,
                 'needed': amount_needed,
                 'used': used,
                 'cap': capacity})
            raise exception.InvalidAllocationCapacityExceeded(
                resource_class=alloc.resource_class,
                resource_provider=rp_uuid)
    return res_providers


@db_api.placement_context_manager.reader
def _get_allocations_by_provider_id(ctx, rp_id):
    allocs = sa.alias(_ALLOC_TBL, name="a")
    consumers = sa.alias(_CONSUMER_TBL, name="c")
    projects = sa.alias(_PROJECT_TBL, name="p")
    users = sa.alias(_USER_TBL, name="u")

    # TODO(jaypipes): change this join to be on ID not UUID
    consumers_join = sa.join(
        allocs, consumers, allocs.c.consumer_id == consumers.c.uuid)
    projects_join = sa.join(
        consumers_join, projects, consumers.c.project_id == projects.c.id)
    users_join = sa.join(
        projects_join, users, consumers.c.user_id == users.c.id)

    sel = sa.select(
        allocs.c.id,
        allocs.c.resource_class_id,
        allocs.c.used,
        allocs.c.updated_at,
        allocs.c.created_at,
        consumers.c.id.label("consumer_id"),
        consumers.c.generation.label("consumer_generation"),
        consumers.c.uuid.label("consumer_uuid"),
        projects.c.id.label("project_id"),
        projects.c.external_id.label("project_external_id"),
        users.c.id.label("user_id"),
        users.c.external_id.label("user_external_id"),
    ).select_from(users_join)
    sel = sel.where(allocs.c.resource_provider_id == rp_id)

    return [dict(r._mapping) for r in ctx.session.execute(sel)]


@db_api.placement_context_manager.reader
def _get_allocations_by_consumer_uuid(ctx, consumer_uuid):
    allocs = sa.alias(_ALLOC_TBL, name="a")
    rp = sa.alias(_RP_TBL, name="rp")
    consumer = sa.alias(_CONSUMER_TBL, name="c")
    project = sa.alias(_PROJECT_TBL, name="p")
    user = sa.alias(_USER_TBL, name="u")

    # Build up the joins of the five tables we need to interact with.
    rp_join = sa.join(allocs, rp, allocs.c.resource_provider_id == rp.c.id)
    consumer_join = sa.join(
        rp_join, consumer, allocs.c.consumer_id == consumer.c.uuid)
    project_join = sa.join(
        consumer_join, project, consumer.c.project_id == project.c.id)
    user_join = sa.join(
        project_join, user, consumer.c.user_id == user.c.id)

    sel = sa.select(
        allocs.c.id,
        allocs.c.resource_provider_id,
        rp.c.name.label("resource_provider_name"),
        rp.c.uuid.label("resource_provider_uuid"),
        rp.c.generation.label("resource_provider_generation"),
        allocs.c.resource_class_id,
        allocs.c.used,
        consumer.c.id.label("consumer_id"),
        consumer.c.generation.label("consumer_generation"),
        consumer.c.consumer_type_id,
        consumer.c.uuid.label("consumer_uuid"),
        project.c.id.label("project_id"),
        project.c.external_id.label("project_external_id"),
        user.c.id.label("user_id"),
        user.c.external_id.label("user_external_id"),
        allocs.c.created_at,
        allocs.c.updated_at,
    ).select_from(user_join)
    sel = sel.where(allocs.c.consumer_id == consumer_uuid)

    return [dict(r._mapping) for r in ctx.session.execute(sel)]


@oslo_db_api.wrap_db_retry(max_retries=5, retry_on_deadlock=True)
@db_api.placement_context_manager.writer
def _set_allocations(context, allocs):
    """Write a set of allocations.

    We must check that there is capacity for each allocation.
    If there is not we roll back the entire set.

    :raises `exception.ResourceClassNotFound` if any resource class in any
            allocation in allocs cannot be found in either the DB.
    :raises `exception.InvalidAllocationCapacityExceeded` if any inventory
            would be exhausted by the allocation.
    :raises `InvalidAllocationConstraintsViolated` if any of the
            `step_size`, `min_unit` or `max_unit` constraints in an
            inventory will be violated by any one of the allocations.
    :raises `ConcurrentUpdateDetected` if a generation for a resource
            provider or consumer failed its increment check.
    """
    # First delete any existing allocations for any consumers. This
    # provides a clean slate for the consumers mentioned in the list of
    # allocations being manipulated.
    consumer_ids = set(alloc.consumer.uuid for alloc in allocs)
    for consumer_id in consumer_ids:
        _delete_allocations_for_consumer(context, consumer_id)

    # Before writing any allocation records, we check that the submitted
    # allocations do not cause any inventory capacity to be exceeded for
    # any resource provider and resource class involved in the allocation
    # transaction. _check_capacity_exceeded() raises an exception if any
    # inventory capacity is exceeded. If capacity is not exceeded, the
    # function returns a list of ResourceProvider objects containing the
    # generation of the resource provider at the time of the check. These
    # objects are used at the end of the allocation transaction as a guard
    # against concurrent updates.
    #
    # Don't check capacity when alloc.used is zero. Zero is not a valid
    # amount when making an allocation (the minimum consumption of a
    # resource is one) but is used in this method to indicate a need for
    # removal. Providing 0 is controlled at the HTTP API layer where PUT
    # /allocations does not allow empty allocations. When POST /allocations
    # is implemented it will for the special case of atomically setting and
    # removing different allocations in the same request.
    # _check_capacity_exceeded will raise a ResourceClassNotFound # if any
    # allocation is using a resource class that does not exist.
    visited_consumers = {}
    visited_rps = _check_capacity_exceeded(context, allocs)
    for alloc in allocs:
        if alloc.consumer.id not in visited_consumers:
            visited_consumers[alloc.consumer.id] = alloc.consumer

        # If alloc.used is set to zero that is a signal that we don't want
        # to (re-)create any allocations for this resource class.
        # _delete_current_allocs has already wiped out allocations so just
        # continue
        if alloc.used == 0:
            continue
        consumer_id = alloc.consumer.uuid
        rp = alloc.resource_provider
        rc_id = context.rc_cache.id_from_string(alloc.resource_class)
        ins_stmt = _ALLOC_TBL.insert().values(
            resource_provider_id=rp.id,
            resource_class_id=rc_id,
            consumer_id=consumer_id,
            used=alloc.used)
        res = context.session.execute(ins_stmt)
        alloc.id = res.lastrowid

    # Generation checking happens here. If the inventory for this resource
    # provider changed out from under us, this will raise a
    # ConcurrentUpdateDetected which can be caught by the caller to choose
    # to try again. It will also rollback the transaction so that these
    # changes always happen atomically.
    for rp in visited_rps.values():
        rp.increment_generation()
    for consumer in visited_consumers.values():
        consumer.increment_generation()
    # If any consumers involved in this transaction ended up having no
    # allocations, delete the consumer records. Exclude consumers that had
    # *some resource* in the allocation list with a total > 0 since clearly
    # those consumers have allocations...
    cons_with_allocs = set(a.consumer.uuid for a in allocs if a.used > 0)
    all_cons = set(c.uuid for c in visited_consumers.values())
    consumers_to_check = all_cons - cons_with_allocs
    consumer_obj.delete_consumers_if_no_allocations(
        context, consumers_to_check)


def get_all_by_resource_provider(context, rp):
    db_allocs = _get_allocations_by_provider_id(context, rp.id)
    # Build up a list of Allocation objects, setting the Allocation object
    # fields to the same-named database record field we got from
    # _get_allocations_by_provider_id(). We already have the
    # ResourceProvider object so we just pass that object to the Allocation
    # object constructor as-is
    objs = []
    for rec in db_allocs:
        consumer = consumer_obj.Consumer(
            context, id=rec['consumer_id'],
            uuid=rec['consumer_uuid'],
            generation=rec['consumer_generation'],
            project=project_obj.Project(
                context, id=rec['project_id'],
                external_id=rec['project_external_id']),
            user=user_obj.User(
                context, id=rec['user_id'],
                external_id=rec['user_external_id']))
        objs.append(
            Allocation(
                id=rec['id'], resource_provider=rp,
                resource_class=context.rc_cache.string_from_id(
                    rec['resource_class_id']),
                consumer=consumer,
                used=rec['used'],
                created_at=rec['created_at'],
                updated_at=rec['updated_at']))
    return objs


def get_all_by_consumer_id(context, consumer_id):
    db_allocs = _get_allocations_by_consumer_uuid(context, consumer_id)

    if not db_allocs:
        return []

    # Build up the Consumer object (it's the same for all allocations
    # since we looked up by consumer ID)
    db_first = db_allocs[0]
    consumer = consumer_obj.Consumer(
        context, id=db_first['consumer_id'],
        uuid=db_first['consumer_uuid'],
        generation=db_first['consumer_generation'],
        consumer_type_id=db_first['consumer_type_id'],
        project=project_obj.Project(
            context, id=db_first['project_id'],
            external_id=db_first['project_external_id']),
        user=user_obj.User(
            context, id=db_first['user_id'],
            external_id=db_first['user_external_id']))

    # Build up a list of Allocation objects, setting the Allocation object
    # fields to the same-named database record field we got from
    # _get_allocations_by_consumer_id().
    #
    # NOTE(jaypipes):  Unlike with get_all_by_resource_provider(), we do
    # NOT already have the ResourceProvider object so we construct a new
    # ResourceProvider object below by looking at the resource provider
    # fields returned by _get_allocations_by_consumer_id().
    alloc_list = [
        Allocation(
            id=rec['id'],
            resource_provider=rp_obj.ResourceProvider(
                context,
                id=rec['resource_provider_id'],
                uuid=rec['resource_provider_uuid'],
                name=rec['resource_provider_name'],
                generation=rec['resource_provider_generation']),
            resource_class=context.rc_cache.string_from_id(
                rec['resource_class_id']),
            consumer=consumer,
            used=rec['used'],
            created_at=rec['created_at'],
            updated_at=rec['updated_at'])
        for rec in db_allocs
    ]
    return alloc_list


def replace_all(context, alloc_list):
    """Replace the supplied allocations.

    :note: This method always deletes all allocations for all consumers
           referenced in the list of Allocation objects and then replaces
           the consumer's allocations with the Allocation objects. In doing
           so, it will end up setting the Allocation.id attribute of each
           Allocation object.
    """
    # Retry _set_allocations server side if there is a
    # ResourceProviderConcurrentUpdateDetected. We don't care about
    # sleeping, we simply want to reset the resource provider objects
    # and try again. For sake of simplicity (and because we don't have
    # easy access to the information) we reload all the resource
    # providers that may be present.
    retries = context.config.placement.allocation_conflict_retry_count
    while retries:
        retries -= 1
        try:
            _set_allocations(context, alloc_list)
            break
        except exception.ResourceProviderConcurrentUpdateDetected:
            LOG.debug('Retrying allocations write on resource provider '
                      'generation conflict')
            # We only want to reload each unique resource provider once.
            alloc_rp_uuids = set(
                alloc.resource_provider.uuid for alloc in alloc_list)
            seen_rps = {}
            for rp_uuid in alloc_rp_uuids:
                # NOTE(melwitt): We use a separate database transaction to read
                # the resource provider because we might be wrapped in an outer
                # database transaction when we reach here. We want to get an
                # up-to-date generation value in case a racing request has
                # changed it after we began an outer transaction and this is
                # the first time we are reading the resource provider records
                # during our transaction.
                db_context_manager = db_api.placement_context_manager
                with db_context_manager.reader.independent.using(context):
                    seen_rps[rp_uuid] = rp_obj.ResourceProvider.get_by_uuid(
                        context, rp_uuid)
            for alloc in alloc_list:
                rp_uuid = alloc.resource_provider.uuid
                alloc.resource_provider = seen_rps[rp_uuid]
    else:
        # We ran out of retries so we need to raise again.
        # The log will automatically have request id info associated with
        # it that will allow tracing back to specific allocations.
        # Attempting to extract specific consumer or resource provider
        # information from the allocations is not coherent as this
        # could be multiple consumers and providers.
        LOG.warning('Exceeded retry limit of %d on allocations write',
                    context.config.placement.allocation_conflict_retry_count)
        raise exception.ResourceProviderConcurrentUpdateDetected()


def delete_all(context, alloc_list):
    consumer_uuids = set(alloc.consumer.uuid for alloc in alloc_list)
    alloc_ids = [alloc.id for alloc in alloc_list]
    _delete_allocations_by_ids(context, alloc_ids)
    consumer_obj.delete_consumers_if_no_allocations(
        context, consumer_uuids)
