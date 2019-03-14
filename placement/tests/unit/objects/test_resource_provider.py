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

import mock
import os_resource_classes as orc
from oslo_utils.fixture import uuidsentinel as uuids
from oslo_utils import timeutils
import six

from placement import exception
from placement.objects import resource_provider
from placement.tests.unit.objects import base


_RESOURCE_CLASS_NAME = 'DISK_GB'
_RESOURCE_CLASS_ID = 2
IPV4_ADDRESS_ID = orc.STANDARDS.index(
    orc.IPV4_ADDRESS)
VCPU_ID = orc.STANDARDS.index(
    orc.VCPU)

_RESOURCE_PROVIDER_ID = 1
_RESOURCE_PROVIDER_UUID = uuids.resource_provider
_RESOURCE_PROVIDER_NAME = six.text_type(uuids.resource_name)
_RESOURCE_PROVIDER_DB = {
    'id': _RESOURCE_PROVIDER_ID,
    'uuid': _RESOURCE_PROVIDER_UUID,
    'name': _RESOURCE_PROVIDER_NAME,
    'generation': 0,
    'root_provider_uuid': _RESOURCE_PROVIDER_UUID,
    'parent_provider_uuid': None,
    'updated_at': None,
    'created_at': timeutils.utcnow(with_timezone=True),
}

_RESOURCE_PROVIDER_ID2 = 2
_RESOURCE_PROVIDER_UUID2 = uuids.resource_provider2
_RESOURCE_PROVIDER_NAME2 = uuids.resource_name2
_RESOURCE_PROVIDER_DB2 = {
    'id': _RESOURCE_PROVIDER_ID2,
    'uuid': _RESOURCE_PROVIDER_UUID2,
    'name': _RESOURCE_PROVIDER_NAME2,
    'generation': 0,
    'root_provider_uuid': _RESOURCE_PROVIDER_UUID,
    'parent_provider_uuid': _RESOURCE_PROVIDER_UUID,
}


_INVENTORY_ID = 2
_INVENTORY_DB = {
    'id': _INVENTORY_ID,
    'resource_provider_id': _RESOURCE_PROVIDER_ID,
    'resource_class_id': _RESOURCE_CLASS_ID,
    'total': 16,
    'reserved': 2,
    'min_unit': 1,
    'max_unit': 8,
    'step_size': 1,
    'allocation_ratio': 1.0,
    'updated_at': None,
    'created_at': timeutils.utcnow(with_timezone=True),
}
_ALLOCATION_ID = 2
_ALLOCATION_DB = {
    'id': _ALLOCATION_ID,
    'resource_provider_id': _RESOURCE_PROVIDER_ID,
    'resource_class_id': _RESOURCE_CLASS_ID,
    'consumer_uuid': uuids.fake_instance,
    'consumer_id': 1,
    'consumer_generation': 0,
    'used': 8,
    'user_id': 1,
    'user_external_id': uuids.user_id,
    'project_id': 1,
    'project_external_id': uuids.project_id,
    'updated_at': timeutils.utcnow(with_timezone=True),
    'created_at': timeutils.utcnow(with_timezone=True),
}

_ALLOCATION_BY_CONSUMER_DB = {
    'id': _ALLOCATION_ID,
    'resource_provider_id': _RESOURCE_PROVIDER_ID,
    'resource_class_id': _RESOURCE_CLASS_ID,
    'consumer_uuid': uuids.fake_instance,
    'consumer_id': 1,
    'consumer_generation': 0,
    'used': 8,
    'user_id': 1,
    'user_external_id': uuids.user_id,
    'project_id': 1,
    'project_external_id': uuids.project_id,
    'updated_at': timeutils.utcnow(with_timezone=True),
    'created_at': timeutils.utcnow(with_timezone=True),
    'resource_provider_name': _RESOURCE_PROVIDER_NAME,
    'resource_provider_uuid': _RESOURCE_PROVIDER_UUID,
    'resource_provider_generation': 0,
}


class TestResourceProviderNoDB(base.TestCase):

    def test_create_id_fail(self):
        obj = resource_provider.ResourceProvider(context=self.context,
                                                 uuid=_RESOURCE_PROVIDER_UUID,
                                                 id=_RESOURCE_PROVIDER_ID)
        self.assertRaises(exception.ObjectActionError,
                          obj.create)

    def test_create_no_uuid_fail(self):
        obj = resource_provider.ResourceProvider(context=self.context)
        self.assertRaises(exception.ObjectActionError,
                          obj.create)


class TestInventoryNoDB(base.TestCase):

    @mock.patch('placement.resource_class_cache.ensure_rc_cache',
                side_effect=base.fake_ensure_cache)
    @mock.patch('placement.objects.resource_provider.'
                '_get_inventory_by_provider_id')
    def test_get_all_by_resource_provider(self, mock_get, mock_ensure_cache):
        mock_ensure_cache(self.context)
        expected = [dict(_INVENTORY_DB,
                         resource_provider_id=_RESOURCE_PROVIDER_ID),
                    dict(_INVENTORY_DB,
                         id=_INVENTORY_DB['id'] + 1,
                         resource_provider_id=_RESOURCE_PROVIDER_ID)]
        mock_get.return_value = expected
        rp = resource_provider.ResourceProvider(self.context,
                                                id=_RESOURCE_PROVIDER_ID,
                                                uuid=_RESOURCE_PROVIDER_UUID)
        objs = resource_provider.InventoryList.get_all_by_resource_provider(
            self.context, rp)
        self.assertEqual(2, len(objs))
        self.assertEqual(_INVENTORY_DB['id'], objs[0].id)
        self.assertEqual(_INVENTORY_DB['id'] + 1, objs[1].id)
        self.assertEqual(_RESOURCE_PROVIDER_ID, objs[0].resource_provider.id)

    def test_set_defaults(self):
        rp = resource_provider.ResourceProvider(self.context,
                                                id=_RESOURCE_PROVIDER_ID,
                                                uuid=_RESOURCE_PROVIDER_UUID)
        kwargs = dict(resource_provider=rp,
                      resource_class=_RESOURCE_CLASS_NAME,
                      total=16)
        inv = resource_provider.Inventory(self.context, **kwargs)

        self.assertEqual(0, inv.reserved)
        self.assertEqual(1, inv.min_unit)
        self.assertEqual(1, inv.max_unit)
        self.assertEqual(1, inv.step_size)
        self.assertEqual(1.0, inv.allocation_ratio)

    def test_capacity(self):
        rp = resource_provider.ResourceProvider(self.context,
                                                id=_RESOURCE_PROVIDER_ID,
                                                uuid=_RESOURCE_PROVIDER_UUID)
        kwargs = dict(resource_provider=rp,
                      resource_class=_RESOURCE_CLASS_NAME,
                      total=16,
                      reserved=16)
        inv = resource_provider.Inventory(self.context, **kwargs)

        self.assertEqual(0, inv.capacity)
        inv.reserved = 15
        self.assertEqual(1, inv.capacity)
        inv.allocation_ratio = 2.0
        self.assertEqual(2, inv.capacity)


class TestInventoryList(base.TestCase):

    def test_find(self):
        rp = resource_provider.ResourceProvider(
            self.context, uuid=uuids.rp_uuid)
        inv_list = resource_provider.InventoryList(
            objects=[
                resource_provider.Inventory(
                    resource_provider=rp,
                    resource_class=orc.VCPU,
                    total=24),
                resource_provider.Inventory(
                    resource_provider=rp,
                    resource_class=orc.MEMORY_MB,
                    total=10240),
            ])

        found = inv_list.find(orc.MEMORY_MB)
        self.assertIsNotNone(found)
        self.assertEqual(10240, found.total)

        found = inv_list.find(orc.VCPU)
        self.assertIsNotNone(found)
        self.assertEqual(24, found.total)

        found = inv_list.find(orc.DISK_GB)
        self.assertIsNone(found)

        # Try an integer resource class identifier...
        self.assertRaises(ValueError, inv_list.find, VCPU_ID)

        # Use an invalid string...
        self.assertIsNone(inv_list.find('HOUSE'))
