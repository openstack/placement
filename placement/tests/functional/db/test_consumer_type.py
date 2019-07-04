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


from placement import exception
from placement.objects import consumer_type as ct_obj
from placement.tests.functional.db import test_base as tb


class ConsumerTypeTestCase(tb.PlacementDbBaseTestCase):

    def test_get_by_name_and_id(self):

        ct = ct_obj.ConsumerType(self.context, name='MIGRATION')
        ct.create()

        named_ct = ct_obj.ConsumerType.get_by_name(self.context, 'MIGRATION')
        self.assertEqual(ct.id, named_ct.id)

        id_ct = ct_obj.ConsumerType.get_by_id(self.context, ct.id)
        self.assertEqual(ct.name, id_ct.name)

    def test_id_not_found(self):
        self.assertRaises(
            exception.ConsumerTypeNotFound, ct_obj.ConsumerType.get_by_id,
            self.context, 999999)

    def test_name_not_found(self):
        self.assertRaises(
            exception.ConsumerTypeNotFound, ct_obj.ConsumerType.get_by_name,
            self.context, 'LOSTPONY')

    def test_duplicate_create(self):
        ct = ct_obj.ConsumerType(self.context, name='MIGRATION')
        ct.create()

        ct2 = ct_obj.ConsumerType(self.context, name='MIGRATION')
        self.assertRaises(exception.ConsumerTypeExists, ct2.create)
