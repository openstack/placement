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


LIST = 'placement:allocation_candidates:list'

DEPRECATED_REASON = """
The allocation candidate API now supports read-only roles by default.
"""

deprecated_list_allocation_candidates = policy.DeprecatedRule(
    name=LIST,
    check_str=base.RULE_ADMIN_API
)


rules = [
    policy.DocumentedRuleDefault(
        name=LIST,
        check_str=base.SYSTEM_READER,
        description="List allocation candidates.",
        operations=[
            {
                'method': 'GET',
                'path': '/allocation_candidates'
            }
        ],
        scope_types=['system'],
        deprecated_rule=deprecated_list_allocation_candidates,
        deprecated_reason=DEPRECATED_REASON,
        deprecated_since=versionutils.deprecated.WALLABY
    )
]


def list_rules():
    return rules
