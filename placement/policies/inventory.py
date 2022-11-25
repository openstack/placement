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


from oslo_policy import policy

from placement.policies import base


PREFIX = 'placement:resource_providers:inventories:%s'
LIST = PREFIX % 'list'
CREATE = PREFIX % 'create'
SHOW = PREFIX % 'show'
UPDATE = PREFIX % 'update'
DELETE = PREFIX % 'delete'
BASE_PATH = '/resource_providers/{uuid}/inventories'

rules = [
    policy.DocumentedRuleDefault(
        name=LIST,
        check_str=base.ADMIN_OR_SERVICE,
        description="List resource provider inventories.",
        operations=[
            {
                'method': 'GET',
                'path': BASE_PATH
            }
        ],
        scope_types=['project'],
    ),
    policy.DocumentedRuleDefault(
        name=CREATE,
        check_str=base.ADMIN_OR_SERVICE,
        description="Create one resource provider inventory.",
        operations=[
            {
                'method': 'POST',
                'path': BASE_PATH
            }
        ],
        scope_types=['project'],
    ),
    policy.DocumentedRuleDefault(
        name=SHOW,
        check_str=base.ADMIN_OR_SERVICE,
        description="Show resource provider inventory.",
        operations=[
            {
                'method': 'GET',
                'path': BASE_PATH + '/{resource_class}'
            }
        ],
        scope_types=['project'],
    ),
    policy.DocumentedRuleDefault(
        name=UPDATE,
        check_str=base.ADMIN_OR_SERVICE,
        description="Update resource provider inventory.",
        operations=[
            {
                'method': 'PUT',
                'path': BASE_PATH
            },
            {
                'method': 'PUT',
                'path': BASE_PATH + '/{resource_class}'
            }
        ],
        scope_types=['project'],
    ),
    policy.DocumentedRuleDefault(
        name=DELETE,
        check_str=base.ADMIN_OR_SERVICE,
        description="Delete resource provider inventory.",
        operations=[
            {
                'method': 'DELETE',
                'path': BASE_PATH
            },
            {
                'method': 'DELETE',
                'path': BASE_PATH + '/{resource_class}'
            }
        ],
        scope_types=['project'],
    ),
]


def list_rules():
    return rules
