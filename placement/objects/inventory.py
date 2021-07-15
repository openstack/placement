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

import sqlalchemy as sa

from placement.db.sqlalchemy import models
from placement import db_api


_INV_TBL = models.Inventory.__table__


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


def find(inventories, res_class):
    """Return the inventory record from the list of Inventory records that
    matches the supplied resource class, or None.

    :param inventories: A list of Inventory objects.
    :param res_class: An integer or string representing a resource
                      class. If the value is a string, the method first
                      looks up the resource class identifier from the
                      string.
    """
    if not isinstance(res_class, str):
        raise ValueError

    for inv_rec in inventories:
        if inv_rec.resource_class == res_class:
            return inv_rec


def get_all_by_resource_provider(context, rp):
    db_inv = _get_inventory_by_provider_id(context, rp.id)
    # Build up a list of Inventory objects, setting the Inventory object
    # fields to the same-named database record field we got from
    # _get_inventory_by_provider_id(). We already have the ResourceProvider
    # object so we just pass that object to the Inventory object
    # constructor as-is
    inv_list = [
        Inventory(
            resource_provider=rp,
            resource_class=context.rc_cache.string_from_id(
                rec['resource_class_id']),
            **rec)
        for rec in db_inv
    ]
    return inv_list


@db_api.placement_context_manager.reader
def _get_inventory_by_provider_id(ctx, rp_id):
    inv = sa.alias(_INV_TBL, name="i")
    sel = sa.select(
        inv.c.resource_class_id,
        inv.c.total,
        inv.c.reserved,
        inv.c.min_unit,
        inv.c.max_unit,
        inv.c.step_size,
        inv.c.allocation_ratio,
        inv.c.updated_at,
        inv.c.created_at,
    )
    sel = sel.where(inv.c.resource_provider_id == rp_id)

    return [dict(r._mapping) for r in ctx.session.execute(sel)]
