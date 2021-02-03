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

import itertools

from placement.policies import aggregate
from placement.policies import allocation
from placement.policies import allocation_candidate
from placement.policies import base
from placement.policies import inventory
from placement.policies import reshaper
from placement.policies import resource_class
from placement.policies import resource_provider
from placement.policies import trait
from placement.policies import usage


def list_rules():
    rules = itertools.chain(
        base.list_rules(),
        resource_provider.list_rules(),
        resource_class.list_rules(),
        inventory.list_rules(),
        aggregate.list_rules(),
        usage.list_rules(),
        trait.list_rules(),
        allocation.list_rules(),
        allocation_candidate.list_rules(),
        reshaper.list_rules(),
    )
    return list(rules)
