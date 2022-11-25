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


RP_ALLOC_LIST = 'placement:resource_providers:allocations:list'

ALLOC_PREFIX = 'placement:allocations:%s'
ALLOC_LIST = ALLOC_PREFIX % 'list'
ALLOC_MANAGE = ALLOC_PREFIX % 'manage'
ALLOC_UPDATE = ALLOC_PREFIX % 'update'
ALLOC_DELETE = ALLOC_PREFIX % 'delete'

rules = [
    policy.DocumentedRuleDefault(
        name=ALLOC_MANAGE,
        check_str=base.ADMIN_OR_SERVICE,
        description="Manage allocations.",
        operations=[
            {
                'method': 'POST',
                'path': '/allocations'
            }
        ],
        scope_types=['project'],
    ),
    policy.DocumentedRuleDefault(
        name=ALLOC_LIST,
        check_str=base.ADMIN_OR_SERVICE,
        description="List allocations.",
        operations=[
            {
                'method': 'GET',
                'path': '/allocations/{consumer_uuid}'
            }
        ],
        scope_types=['project'],
    ),
    policy.DocumentedRuleDefault(
        name=ALLOC_UPDATE,
        check_str=base.ADMIN_OR_SERVICE,
        description="Update allocations.",
        operations=[
            {
                'method': 'PUT',
                'path': '/allocations/{consumer_uuid}'
            }
        ],
        scope_types=['project'],
    ),
    policy.DocumentedRuleDefault(
        name=ALLOC_DELETE,
        check_str=base.ADMIN_OR_SERVICE,
        description="Delete allocations.",
        operations=[
            {
                'method': 'DELETE',
                'path': '/allocations/{consumer_uuid}'
            }
        ],
        scope_types=['project'],
    ),
    policy.DocumentedRuleDefault(
        name=RP_ALLOC_LIST,
        check_str=base.ADMIN_OR_SERVICE,
        description="List resource provider allocations.",
        operations=[
            {
                'method': 'GET',
                'path': '/resource_providers/{uuid}/allocations'
            }
        ],
        scope_types=['project'],
    ),
]


def list_rules():
    return rules
