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

import os_resource_classes as orc
from oslo_utils.fixture import uuidsentinel

import placement
from placement import exception
from placement.objects import inventory as inv_obj
from placement.objects import resource_class as rc_obj
from placement.objects import resource_provider as rp_obj
from placement.tests.functional.db import test_base as tb


class ResourceClassListTestCase(tb.PlacementDbBaseTestCase):

    def test_get_all_no_custom(self):
        """Test that if we haven't yet added any custom resource classes, that
        we only get a list of ResourceClass objects representing the standard
        classes.
        """
        rcs = rc_obj.get_all(self.ctx)
        self.assertEqual(len(orc.STANDARDS), len(rcs))

    def test_get_all_with_custom(self):
        """Test that if we add some custom resource classes, that we get a list
        of ResourceClass objects representing the standard classes as well as
        the custom classes.
        """
        customs = [
            ('CUSTOM_IRON_NFV', 10001),
            ('CUSTOM_IRON_ENTERPRISE', 10002),
        ]
        with self.placement_db.get_engine().connect() as conn:
            with conn.begin():
                for custom in customs:
                    c_name, c_id = custom
                    ins = rc_obj._RC_TBL.insert().values(id=c_id, name=c_name)
                    conn.execute(ins)

        rcs = rc_obj.get_all(self.ctx)
        expected_count = (len(orc.STANDARDS) + len(customs))
        self.assertEqual(expected_count, len(rcs))


class ResourceClassTestCase(tb.PlacementDbBaseTestCase):

    def test_get_by_name(self):
        rc = rc_obj.ResourceClass.get_by_name(
            self.ctx,
            orc.VCPU
        )
        vcpu_id = orc.STANDARDS.index(orc.VCPU)
        self.assertEqual(vcpu_id, rc.id)
        self.assertEqual(orc.VCPU, rc.name)

    def test_get_by_name_not_found(self):
        self.assertRaises(exception.ResourceClassNotFound,
                          rc_obj.ResourceClass.get_by_name,
                          self.ctx,
                          'CUSTOM_NO_EXISTS')

    def test_get_by_name_custom(self):
        rc = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_NFV',
        )
        rc.create()
        get_rc = rc_obj.ResourceClass.get_by_name(
            self.ctx,
            'CUSTOM_IRON_NFV',
        )
        self.assertEqual(rc.id, get_rc.id)
        self.assertEqual(rc.name, get_rc.name)

    def test_create_fail_not_using_namespace(self):
        rc = rc_obj.ResourceClass(
            context=self.ctx,
            name='IRON_NFV',
        )
        exc = self.assertRaises(exception.ObjectActionError, rc.create)
        self.assertIn('name must start with', str(exc))

    def test_create_duplicate_standard(self):
        rc = rc_obj.ResourceClass(
            context=self.ctx,
            name=orc.VCPU,
        )
        self.assertRaises(exception.ResourceClassExists, rc.create)

    def test_create(self):
        rc = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_NFV',
        )
        rc.create()
        min_id = rc_obj.ResourceClass.MIN_CUSTOM_RESOURCE_CLASS_ID
        self.assertEqual(min_id, rc.id)

        rc = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_ENTERPRISE',
        )
        rc.create()
        self.assertEqual(min_id + 1, rc.id)

    @mock.patch.object(placement.objects.resource_class.ResourceClass,
                       "_get_next_id")
    def test_create_duplicate_id_retry(self, mock_get):
        # This order of ID generation will create rc1 with an ID of 42, try to
        # create rc2 with the same ID, and then return 43 in the retry loop.
        mock_get.side_effect = (42, 42, 43)
        rc1 = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_NFV',
        )
        rc1.create()
        rc2 = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_TWO',
        )
        rc2.create()
        self.assertEqual(rc1.id, 42)
        self.assertEqual(rc2.id, 43)

    @mock.patch.object(placement.objects.resource_class.ResourceClass,
                       "_get_next_id")
    def test_create_duplicate_id_retry_failing(self, mock_get):
        """negative case for test_create_duplicate_id_retry"""
        # This order of ID generation will create rc1 with an ID of 44, try to
        # create rc2 with the same ID, and then return 45 in the retry loop.
        mock_get.side_effect = (44, 44, 44, 44)
        rc1 = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_NFV',
        )
        rc1.create()
        rc2 = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_TWO',
        )
        rc2.RESOURCE_CREATE_RETRY_COUNT = 3
        self.assertRaises(exception.MaxDBRetriesExceeded, rc2.create)

    def test_create_duplicate_custom(self):
        rc = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_NFV',
        )
        rc.create()
        self.assertEqual(rc_obj.ResourceClass.MIN_CUSTOM_RESOURCE_CLASS_ID,
                         rc.id)
        rc = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_NFV',
        )
        self.assertRaises(exception.ResourceClassExists, rc.create)

    def test_destroy_fail_no_id(self):
        rc = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_NFV',
        )
        self.assertRaises(exception.ObjectActionError, rc.destroy)

    def test_destroy_fail_standard(self):
        rc = rc_obj.ResourceClass.get_by_name(
            self.ctx,
            'VCPU',
        )
        self.assertRaises(exception.ResourceClassCannotDeleteStandard,
                          rc.destroy)

    def test_destroy(self):
        rc = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_NFV',
        )
        rc.create()
        rc_list = rc_obj.get_all(self.ctx)
        rc_ids = (r.id for r in rc_list)
        self.assertIn(rc.id, rc_ids)

        rc = rc_obj.ResourceClass.get_by_name(
            self.ctx,
            'CUSTOM_IRON_NFV',
        )

        rc.destroy()
        rc_list = rc_obj.get_all(self.ctx)
        rc_ids = (r.id for r in rc_list)
        self.assertNotIn(rc.id, rc_ids)

        # Verify rc cache was purged of the old entry
        self.assertRaises(exception.ResourceClassNotFound,
                          rc_obj.ResourceClass.get_by_name,
                          self.ctx,
                          'CUSTOM_IRON_NFV')

    def test_destroy_fail_with_inventory(self):
        """Test that we raise an exception when attempting to delete a resource
        class that is referenced in an inventory record.
        """
        rc = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_NFV',
        )
        rc.create()
        rp = rp_obj.ResourceProvider(
            self.ctx,
            name='my rp',
            uuid=uuidsentinel.rp,
        )
        rp.create()
        inv = inv_obj.Inventory(
            resource_provider=rp,
            resource_class='CUSTOM_IRON_NFV',
            total=1,
        )
        rp.set_inventory([inv])

        self.assertRaises(exception.ResourceClassInUse,
                          rc.destroy)

        rp.set_inventory([])
        rc.destroy()
        rc_list = rc_obj.get_all(self.ctx)
        rc_ids = (r.id for r in rc_list)
        self.assertNotIn(rc.id, rc_ids)

    def test_save_fail_no_id(self):
        rc = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_NFV',
        )
        self.assertRaises(exception.ObjectActionError, rc.save)

    def test_save_fail_standard(self):
        rc = rc_obj.ResourceClass.get_by_name(
            self.ctx,
            'VCPU',
        )
        self.assertRaises(exception.ResourceClassCannotUpdateStandard,
                          rc.save)

    def test_save(self):
        rc = rc_obj.ResourceClass(
            self.ctx,
            name='CUSTOM_IRON_NFV',
        )
        rc.create()

        rc = rc_obj.ResourceClass.get_by_name(
            self.ctx,
            'CUSTOM_IRON_NFV',
        )
        rc.name = 'CUSTOM_IRON_SILVER'
        rc.save()

        # Verify rc cache was purged of the old entry
        self.assertRaises(exception.NotFound,
                          rc_obj.ResourceClass.get_by_name,
                          self.ctx,
                          'CUSTOM_IRON_NFV')
