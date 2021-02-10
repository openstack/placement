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


PREFIX = 'placement:reshaper:%s'
RESHAPE = PREFIX % 'reshape'

deprecated_reshape = policy.DeprecatedRule(
    name=RESHAPE,
    check_str=base.RULE_ADMIN_API,
)

DEPRECATED_REASON = """
The reshape API now supports scoped rule by default.
"""

rules = [
    policy.DocumentedRuleDefault(
        RESHAPE,
        base.SYSTEM_ADMIN,
        "Reshape Inventory and Allocations.",
        [
            {
                'method': 'POST',
                'path': '/reshaper'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_reshape,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY,
    ),
]


def list_rules():
    return rules
