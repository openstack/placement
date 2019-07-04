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


from unittest import mock

from oslo_utils.fixture import uuidsentinel as uuids
from oslo_utils import timeutils

from placement.objects import allocation as alloc_obj
from placement.objects import resource_provider as rp_obj
from placement.tests.unit.objects import base


_RESOURCE_PROVIDER_ID = 1
_RESOURCE_PROVIDER_UUID = uuids.resource_provider
_RESOURCE_PROVIDER_NAME = str(uuids.resource_name)
_RESOURCE_CLASS_ID = 2
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
    'consumer_type_id': 1,
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


class TestAllocationListNoDB(base.TestCase):

    def setUp(self):
        super(TestAllocationListNoDB, self).setUp()

    @mock.patch('placement.objects.allocation.'
                '_get_allocations_by_provider_id',
                return_value=[_ALLOCATION_DB])
    def test_get_all_by_resource_provider(self, mock_get_allocations_from_db):
        rp = rp_obj.ResourceProvider(self.context,
                                     id=_RESOURCE_PROVIDER_ID,
                                     uuid=uuids.resource_provider)
        allocations = alloc_obj.get_all_by_resource_provider(self.context, rp)

        self.assertEqual(1, len(allocations))
        mock_get_allocations_from_db.assert_called_once_with(
            self.context, rp.id)
        self.assertEqual(_ALLOCATION_DB['used'], allocations[0].used)
        self.assertEqual(_ALLOCATION_DB['created_at'],
                         allocations[0].created_at)
        self.assertEqual(_ALLOCATION_DB['updated_at'],
                         allocations[0].updated_at)

    @mock.patch('placement.objects.allocation.'
                '_get_allocations_by_consumer_uuid',
                return_value=[_ALLOCATION_BY_CONSUMER_DB])
    def test_get_all_by_consumer_id(self, mock_get_allocations_from_db):
        allocations = alloc_obj.get_all_by_consumer_id(
            self.context, uuids.consumer)

        self.assertEqual(1, len(allocations))
        mock_get_allocations_from_db.assert_called_once_with(self.context,
                                                             uuids.consumer)
        self.assertEqual(_ALLOCATION_BY_CONSUMER_DB['used'],
                         allocations[0].used)
        self.assertEqual(_ALLOCATION_BY_CONSUMER_DB['created_at'],
                         allocations[0].created_at)
        self.assertEqual(_ALLOCATION_BY_CONSUMER_DB['updated_at'],
                         allocations[0].updated_at)
