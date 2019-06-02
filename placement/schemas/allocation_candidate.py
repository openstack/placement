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
"""Placement API schemas for getting allocation candidates."""

import copy

from placement.schemas import common


# Represents the allowed query string parameters to the GET
# /allocation_candidates API call
GET_SCHEMA_1_10 = {
    "type": "object",
    "properties": {
        "resources": {
            "type": "string"
        },
    },
    "required": [
        "resources",
    ],
    "additionalProperties": False,
}


# Add limit query parameter.
GET_SCHEMA_1_16 = copy.deepcopy(GET_SCHEMA_1_10)
GET_SCHEMA_1_16['properties']['limit'] = {
    # A query parameter is always a string in webOb, but
    # we'll handle integer here as well.
    "type": ["integer", "string"],
    "pattern": "^[1-9][0-9]*$",
    "minimum": 1,
    "minLength": 1
}

# Add required parameter.
GET_SCHEMA_1_17 = copy.deepcopy(GET_SCHEMA_1_16)
GET_SCHEMA_1_17['properties']['required'] = {
    "type": ["string"]
}

# Add member_of parameter.
GET_SCHEMA_1_21 = copy.deepcopy(GET_SCHEMA_1_17)
GET_SCHEMA_1_21['properties']['member_of'] = {
    "type": ["string"]
}

GET_SCHEMA_1_25 = copy.deepcopy(GET_SCHEMA_1_21)
# We're going to *replace* 'resources', 'required', and 'member_of'.
del GET_SCHEMA_1_25["properties"]["resources"]
del GET_SCHEMA_1_25["required"]
del GET_SCHEMA_1_25["properties"]["required"]
del GET_SCHEMA_1_25["properties"]["member_of"]
# Pattern property key format for a numbered or un-numbered grouping
_GROUP_PAT_FMT = "^%s(" + common.GROUP_PAT + ")?$"
GET_SCHEMA_1_25["patternProperties"] = {
    _GROUP_PAT_FMT % "resources": {
        "type": "string",
    },
    _GROUP_PAT_FMT % "required": {
        "type": "string",
    },
    _GROUP_PAT_FMT % "member_of": {
        "type": "string",
    },
}
GET_SCHEMA_1_25["properties"]["group_policy"] = {
    "type": "string",
    "enum": ["none", "isolate"],
}

# Add in_tree parameter.
GET_SCHEMA_1_31 = copy.deepcopy(GET_SCHEMA_1_25)
GET_SCHEMA_1_31["patternProperties"][_GROUP_PAT_FMT % "in_tree"] = {
    "type": "string"}

# Microversion 1.33 allows more complex resource group suffixes.
GET_SCHEMA_1_33 = copy.deepcopy(GET_SCHEMA_1_31)
_GROUP_PAT_FMT_1_33 = "^%s(" + common.GROUP_PAT_1_33 + ")?$"
GET_SCHEMA_1_33["patternProperties"] = {
    _GROUP_PAT_FMT_1_33 % group_type: {"type": "string"}
    for group_type in ('resources', 'required', 'member_of', 'in_tree')}

# Microversion 1.35 supports root_required.
GET_SCHEMA_1_35 = copy.deepcopy(GET_SCHEMA_1_33)
GET_SCHEMA_1_35["properties"]['root_required'] = {
    "type": ["string"]
}

# Microversion 1.36 supports same_subtree.
GET_SCHEMA_1_36 = copy.deepcopy(GET_SCHEMA_1_35)
GET_SCHEMA_1_36["properties"]['same_subtree'] = {
    "type": ["string"]
}
