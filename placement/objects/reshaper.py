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
from oslo_log import log as logging

from placement import db_api
from placement.objects import allocation as alloc_obj
from placement.objects import inventory as inv_obj


LOG = logging.getLogger(__name__)


@db_api.placement_context_manager.writer
def reshape(ctx, inventories, allocations):
    """The 'replace the world' strategy that is executed when we want to
    completely replace a set of provider inventory, allocation and consumer
    information in a single transaction.

    :note: The reason this has to be done in a single monolithic function is so
           we have a single top-level function on which to decorate with the
           @db_api.placement_context_manager.writer transaction context
           manager. Each time a top-level function that is decorated with this
           exits, the transaction is either COMMIT'd or ROLLBACK'd. We need to
           avoid calling two functions that are already decorated with a
           transaction context manager from a function that *isn't* decorated
           with the transaction context manager if we want all changes involved
           in the sub-functions to operate within a single DB transaction.

    :param ctx: `placement.context.RequestContext` object
                containing the DB transaction context.
    :param inventories: dict, keyed by ResourceProvider, of lists of
                        `Inventory` objects representing the replaced inventory
                        information for the provider.
    :param allocations: `AllocationList` object containing all allocations for
                        all consumers being modified by the reshape operation.
    :raises: `exception.ConcurrentUpdateDetected` when any resource provider or
             consumer generation increment fails due to concurrent changes to
             the same objects.
    """
    # The resource provider objects, keyed by provider UUID, that are involved
    # in this transaction. We keep a cache of these because as we perform the
    # various operations on the providers, their generations increment and we
    # want to "inject" the changed resource provider objects into the
    # AllocationList's objects before calling AllocationList.replace_all().
    # We start with the providers in the allocation objects, but only use one
    # if we don't find it in the inventories.
    affected_providers = {alloc.resource_provider.uuid: alloc.resource_provider
                          for alloc in allocations}
    # We have to do the inventory changes in two steps because:
    # - we can't delete inventories with allocations; and
    # - we can't create allocations on nonexistent inventories.
    # So in the first step we create a kind of "union" inventory for each
    # provider. It contains all the inventories that the request wishes to
    # exist in the end, PLUS any inventories that the request wished to remove
    # (in their original form).
    # Note that this can cause us to end up with an interim situation where we
    # have modified an inventory to have less capacity than is currently
    # allocated, but that's allowed by the code. If the final picture is
    # overcommitted, we'll get an appropriate exception when we replace the
    # allocations at the end.
    for rp, new_inv_list in inventories.items():
        LOG.debug("reshaping: *interim* inventory replacement for provider %s",
                  rp.uuid)
        # Update the cache. This may be replacing an entry that came from
        # allocations, or adding a new entry from inventories.
        affected_providers[rp.uuid] = rp

        # Optimization: If the new inventory is empty, the below would be
        # replacing it with itself (and incrementing the generation)
        # unnecessarily.
        if not new_inv_list:
            continue

        # A dict, keyed by resource class, of the Inventory objects. We start
        # with the original inventory list.
        inv_by_rc = {
            inv.resource_class: inv for inv in
            inv_obj.get_all_by_resource_provider(ctx, rp)}
        # Now add each inventory in the new inventory list. If an inventory for
        # that resource class existed in the original inventory list, it is
        # overwritten.
        for inv in new_inv_list:
            inv_by_rc[inv.resource_class] = inv
        # Set the interim inventory structure.
        rp.set_inventory(list(inv_by_rc.values()))

    # NOTE(jaypipes): The above inventory replacements will have
    # incremented the resource provider generations, so we need to look in
    # the AllocationList and swap the resource provider object with the one we
    # saved above that has the updated provider generation in it.
    for alloc in allocations:
        rp_uuid = alloc.resource_provider.uuid
        if rp_uuid in affected_providers:
            alloc.resource_provider = affected_providers[rp_uuid]

    # Now we can replace all the allocations
    LOG.debug("reshaping: attempting allocation replacement")
    alloc_obj.replace_all(ctx, allocations)

    # And finally, we can set the inventories to their actual desired state.
    for rp, new_inv_list in inventories.items():
        LOG.debug("reshaping: *final* inventory replacement for provider %s",
                  rp.uuid)
        rp.set_inventory(new_inv_list)
