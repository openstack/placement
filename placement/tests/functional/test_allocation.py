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

import fixtures
import os_resource_classes as orc
from oslo_serialization import jsonutils
from oslo_utils.fixture import uuidsentinel as uuids

from placement import direct
from placement import exception
from placement.objects import project as project_obj
from placement.tests.functional import base


class TestAllocationProjectCreateRace(base.TestCase):
    """Test that two allocation update request racing to create the project in
    the database. This test is added to reproduce the bug
    https://storyboard.openstack.org/#!/story/2009159 where the transaction
    that lost the project creation race fails as it tries to read the created
    project in the same transaction which is inactive due to the previous
    'Duplicate entry' error.
    """

    def setUp(self):
        super(TestAllocationProjectCreateRace, self).setUp()

        # Create resource provider and inventory for tests
        conf = self.conf_fixture.conf
        rp_data = jsonutils.dump_as_bytes({
            'name': 'a provider',
            'uuid': uuids.rp,
        })
        inv_data = jsonutils.dump_as_bytes({
            'inventories': {
                orc.VCPU: {
                    'total': 5,
                }
            },
            'resource_provider_generation': 0,
        })
        self.headers = {
            'x-auth-token': 'admin',
            'content-type': 'application/json',
            'OpenStack-API-Version': 'placement 1.38',
            'X_ROLES': 'admin,service'
        }
        with direct.PlacementDirect(conf) as client:
            # Create a resource provider
            url = '/resource_providers'
            resp = client.post(url, data=rp_data, headers=self.headers)
            self.assertEqual(200, resp.status_code)

            # Add inventory to the resource provider
            url = '/resource_providers/%s/inventories' % uuids.rp
            resp = client.put(url, data=inv_data, headers=self.headers)
            self.assertEqual(200, resp.status_code)

        # simulate that when the below allocation update call tries to fetch
        # the project it gets ProjectNotFound but at the same time a
        # "parallel" transaction creates the project, so the project creation
        # will fail
        real_get_project = project_obj.Project.get_by_external_id

        def fake_get_project(cls, ctx, external_id):
            if not hasattr(fake_get_project, 'called'):
                proj = project_obj.Project(ctx, external_id=external_id)
                proj.create()
                fake_get_project.called = True
                raise exception.ProjectNotFound(external_id)
            else:
                return real_get_project(ctx, external_id)

        self.useFixture(
            fixtures.MonkeyPatch(
                'placement.objects.project.Project.get_by_external_id',
                fake_get_project)
        )

    def test_set_allocations_for_consumer(self):
        alloc_data = jsonutils.dump_as_bytes({
            'allocations': {
                uuids.rp: {
                    'resources': {
                        orc.VCPU: 1,
                    },
                }
            },
            'project_id': uuids.project,
            'user_id': uuids.user,
            'consumer_generation': None,
            'consumer_type': 'INSTANCE',
        })
        conf = self.conf_fixture.conf
        with direct.PlacementDirect(conf) as client:
            # Create allocations
            url = '/allocations/%s' % uuids.consumer
            resp = client.put(url, data=alloc_data, headers=self.headers)

            # https://storyboard.openstack.org/#!/story/2009159 The expected
            # behavior would be that the allocation update succeeds as the
            # transaction can fetch the Project created by a racing transaction
            self.assertEqual(204, resp.status_code)

    def test_set_allocations(self):
        alloc_data = jsonutils.dump_as_bytes({
            uuids.consumer: {
                'project_id': uuids.project,
                'user_id': uuids.user,
                'consumer_generation': None,
                'consumer_type': 'INSTANCE',
                'allocations': {
                    uuids.rp: {
                        'resources': {
                            orc.VCPU: 1,
                        },
                    }
                }
            }
        })
        conf = self.conf_fixture.conf
        with direct.PlacementDirect(conf) as client:
            # Create allocations
            url = '/allocations'
            resp = client.post(url, data=alloc_data, headers=self.headers)
            self.assertEqual(204, resp.status_code)

    def test_reshape(self):
        alloc_data = jsonutils.dump_as_bytes({
            'allocations': {
                uuids.consumer: {
                    'allocations': {
                        uuids.rp: {
                            'resources': {
                                orc.VCPU: 1,
                            },
                        }
                    },
                    'project_id': uuids.project,
                    'user_id': uuids.user,
                    'consumer_generation': None,
                    'consumer_type': 'INSTANCE',
                }
            },
            'inventories': {
                uuids.rp: {
                    'inventories': {
                        orc.VCPU: {
                            'total': 5,
                        }
                    },
                    'resource_provider_generation': 1,
                }
            }
        })
        conf = self.conf_fixture.conf
        with direct.PlacementDirect(conf) as client:
            # Create allocations
            url = '/reshaper'
            resp = client.post(url, data=alloc_data, headers=self.headers)
            self.assertEqual(204, resp.status_code)
