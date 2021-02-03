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


from oslo_log import versionutils
from oslo_policy import policy

from placement.policies import base


PREFIX = 'placement:resource_providers:inventories:%s'
LIST = PREFIX % 'list'
CREATE = PREFIX % 'create'
SHOW = PREFIX % 'show'
UPDATE = PREFIX % 'update'
DELETE = PREFIX % 'delete'
BASE_PATH = '/resource_providers/{uuid}/inventories'

DEPRECATED_REASON = """
The inventory API now supports a read-only role by default.
"""

deprecated_list_inventories = policy.DeprecatedRule(
    name=LIST,
    check_str=base.RULE_ADMIN_API
)
deprecated_create_inventory = policy.DeprecatedRule(
    name=CREATE,
    check_str=base.RULE_ADMIN_API
)
deprecated_show_inventory = policy.DeprecatedRule(
    name=SHOW,
    check_str=base.RULE_ADMIN_API
)
deprecated_update_inventory = policy.DeprecatedRule(
    name=UPDATE,
    check_str=base.RULE_ADMIN_API
)
deprecated_delete_inventory = policy.DeprecatedRule(
    name=DELETE,
    check_str=base.RULE_ADMIN_API
)


rules = [
    policy.DocumentedRuleDefault(
        name=LIST,
        check_str=base.SYSTEM_READER,
        description="List resource provider inventories.",
        operations=[
            {
                'method': 'GET',
                'path': BASE_PATH
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_list_inventories,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY),
    policy.DocumentedRuleDefault(
        name=CREATE,
        check_str=base.SYSTEM_ADMIN,
        description="Create one resource provider inventory.",
        operations=[
            {
                'method': 'POST',
                'path': BASE_PATH
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_create_inventory,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY),
    policy.DocumentedRuleDefault(
        name=SHOW,
        check_str=base.SYSTEM_READER,
        description="Show resource provider inventory.",
        operations=[
            {
                'method': 'GET',
                'path': BASE_PATH + '/{resource_class}'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_show_inventory,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY),
    policy.DocumentedRuleDefault(
        name=UPDATE,
        check_str=base.SYSTEM_ADMIN,
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
        scope_types=['system'],
        deprecated_rule=deprecated_update_inventory,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY),
    policy.DocumentedRuleDefault(
        name=DELETE,
        check_str=base.SYSTEM_ADMIN,
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
        scope_types=['system'],
        deprecated_rule=deprecated_delete_inventory,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY),
]


def list_rules():
    return rules
