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


PREFIX = 'placement:resource_providers:aggregates:%s'
LIST = PREFIX % 'list'
UPDATE = PREFIX % 'update'
BASE_PATH = '/resource_providers/{uuid}/aggregates'

rules = [
    policy.DocumentedRuleDefault(
        LIST,
        base.ADMIN_OR_SERVICE,
        "List resource provider aggregates.",
        [
            {
                'method': 'GET',
                'path': BASE_PATH
            }
        ],
        scope_types=['project'],
    ),
    policy.DocumentedRuleDefault(
        UPDATE,
        base.ADMIN_OR_SERVICE,
        "Update resource provider aggregates.",
        [
            {
                'method': 'PUT',
                'path': BASE_PATH
            }
        ],
        scope_types=['project'],
    ),
]


def list_rules():
    return rules
