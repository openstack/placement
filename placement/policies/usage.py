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


PROVIDER_USAGES = 'placement:resource_providers:usages'
TOTAL_USAGES = 'placement:usages'

rules = [
    policy.DocumentedRuleDefault(
        name=PROVIDER_USAGES,
        check_str=base.ADMIN_OR_SERVICE,
        description="List resource provider usages.",
        operations=[
            {
                'method': 'GET',
                'path': '/resource_providers/{uuid}/usages'
            }
        ],
        scope_types=['project'],
    ),
    policy.DocumentedRuleDefault(
        name=TOTAL_USAGES,
        # NOTE(gmann): Admin in any project (legacy admin) can get usage of
        # other project. Project member or reader roles can see usage of
        # their project only.
        check_str=base.ADMIN_OR_PROJECT_READER_OR_SERVICE,
        description="List total resource usages for a given project.",
        operations=[
            {
                'method': 'GET',
                'path': '/usages'
            }
        ],
        scope_types=['project'],
    ),
]


def list_rules():
    return rules
