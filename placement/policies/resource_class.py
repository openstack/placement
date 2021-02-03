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


PREFIX = 'placement:resource_classes:%s'
LIST = PREFIX % 'list'
CREATE = PREFIX % 'create'
SHOW = PREFIX % 'show'
UPDATE = PREFIX % 'update'
DELETE = PREFIX % 'delete'

DEPRECATED_REASON = """
The resource classes API now supports a read-only role by default.
"""

deprecated_list_resource_classes = policy.DeprecatedRule(
    name=LIST,
    check_str=base.RULE_ADMIN_API
)
deprecated_show_resource_class = policy.DeprecatedRule(
    name=SHOW,
    check_str=base.RULE_ADMIN_API
)
deprecated_create_resource_class = policy.DeprecatedRule(
    name=CREATE,
    check_str=base.RULE_ADMIN_API
)
deprecated_update_resource_class = policy.DeprecatedRule(
    name=UPDATE,
    check_str=base.RULE_ADMIN_API
)
deprecated_delete_resource_class = policy.DeprecatedRule(
    name=DELETE,
    check_str=base.RULE_ADMIN_API
)


rules = [
    policy.DocumentedRuleDefault(
        name=LIST,
        check_str=base.SYSTEM_READER,
        description="List resource classes.",
        operations=[
            {
                'method': 'GET',
                'path': '/resource_classes'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_list_resource_classes,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY),
    policy.DocumentedRuleDefault(
        name=CREATE,
        check_str=base.SYSTEM_ADMIN,
        description="Create resource class.",
        operations=[
            {
                'method': 'POST',
                'path': '/resource_classes'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_create_resource_class,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY),
    policy.DocumentedRuleDefault(
        name=SHOW,
        check_str=base.SYSTEM_READER,
        description="Show resource class.",
        operations=[
            {
                'method': 'GET',
                'path': '/resource_classes/{name}'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_show_resource_class,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY),
    policy.DocumentedRuleDefault(
        name=UPDATE,
        check_str=base.SYSTEM_ADMIN,
        description="Update resource class.",
        operations=[
            {
                'method': 'PUT',
                'path': '/resource_classes/{name}'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_update_resource_class,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY),
    policy.DocumentedRuleDefault(
        name=DELETE,
        check_str=base.SYSTEM_ADMIN,
        description="Delete resource class.",
        operations=[
            {
                'method': 'DELETE',
                'path': '/resource_classes/{name}'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_delete_resource_class,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY),
]


def list_rules():
    return rules
