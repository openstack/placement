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


RP_TRAIT_PREFIX = 'placement:resource_providers:traits:%s'
RP_TRAIT_LIST = RP_TRAIT_PREFIX % 'list'
RP_TRAIT_UPDATE = RP_TRAIT_PREFIX % 'update'
RP_TRAIT_DELETE = RP_TRAIT_PREFIX % 'delete'

TRAITS_PREFIX = 'placement:traits:%s'
TRAITS_LIST = TRAITS_PREFIX % 'list'
TRAITS_SHOW = TRAITS_PREFIX % 'show'
TRAITS_UPDATE = TRAITS_PREFIX % 'update'
TRAITS_DELETE = TRAITS_PREFIX % 'delete'

DEPRECATED_REASON = """
The traits API now supports a read-only role by default.
"""

deprecated_list_traits = policy.DeprecatedRule(
    name=TRAITS_LIST,
    check_str=base.RULE_ADMIN_API
)
deprecated_show_trait = policy.DeprecatedRule(
    name=TRAITS_SHOW,
    check_str=base.RULE_ADMIN_API
)
deprecated_rp_traits_list = policy.DeprecatedRule(
    name=RP_TRAIT_LIST,
    check_str=base.RULE_ADMIN_API
)
deprecated_traits_update = policy.DeprecatedRule(
    name=TRAITS_UPDATE,
    check_str=base.RULE_ADMIN_API
)
deprecated_traits_delete = policy.DeprecatedRule(
    name=TRAITS_DELETE,
    check_str=base.RULE_ADMIN_API
)
deprecated_rp_trait_update = policy.DeprecatedRule(
    name=RP_TRAIT_UPDATE,
    check_str=base.RULE_ADMIN_API
)
deprecated_rp_trait_delete = policy.DeprecatedRule(
    name=RP_TRAIT_DELETE,
    check_str=base.RULE_ADMIN_API
)


rules = [
    policy.DocumentedRuleDefault(
        name=TRAITS_LIST,
        check_str=base.SYSTEM_READER,
        description="List traits.",
        operations=[
            {
                'method': 'GET',
                'path': '/traits'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_list_traits,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY
    ),
    policy.DocumentedRuleDefault(
        name=TRAITS_SHOW,
        check_str=base.SYSTEM_READER,
        description="Show trait.",
        operations=[
            {
                'method': 'GET',
                'path': '/traits/{name}'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_show_trait,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY
    ),
    policy.DocumentedRuleDefault(
        name=TRAITS_UPDATE,
        check_str=base.SYSTEM_ADMIN,
        description="Update trait.",
        operations=[
            {
                'method': 'PUT',
                'path': '/traits/{name}'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_traits_update,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY
    ),
    policy.DocumentedRuleDefault(
        name=TRAITS_DELETE,
        check_str=base.SYSTEM_ADMIN,
        description="Delete trait.",
        operations=[
            {
                'method': 'DELETE',
                'path': '/traits/{name}'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_traits_delete,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY
    ),
    policy.DocumentedRuleDefault(
        name=RP_TRAIT_LIST,
        check_str=base.SYSTEM_READER,
        description="List resource provider traits.",
        operations=[
            {
                'method': 'GET',
                'path': '/resource_providers/{uuid}/traits'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_rp_traits_list,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY
    ),
    policy.DocumentedRuleDefault(
        name=RP_TRAIT_UPDATE,
        check_str=base.SYSTEM_ADMIN,
        description="Update resource provider traits.",
        operations=[
            {
                'method': 'PUT',
                'path': '/resource_providers/{uuid}/traits'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_rp_trait_update,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY
    ),
    policy.DocumentedRuleDefault(
        name=RP_TRAIT_DELETE,
        check_str=base.SYSTEM_ADMIN,
        description="Delete resource provider traits.",
        operations=[
            {
                'method': 'DELETE',
                'path': '/resource_providers/{uuid}/traits'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_rp_trait_delete,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY
    ),
]


def list_rules():
    return rules
