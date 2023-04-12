# Copyright 2024 OpenStack Foundation
# All Rights Reserved.
#
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

from oslo_config import cfg

audit_group = cfg.OptGroup(
    "audit",
    title="Audit options",
    help="Options that enable and configure audit middleware",
)

audit_opts = [
    cfg.BoolOpt(
        "enabled",
        default=False,
        help="Enable auditing of API requests (for placement-api service).",
    ),
    cfg.StrOpt(
        "audit_map_file",
        default="/etc/placement/api_audit_map.conf",
        help="Path to audit map file for placement-api service. "
        "Used only when API audit is enabled.",
    ),
    cfg.StrOpt(
        "ignore_req_list",
        default="",
        help="Comma separated list of Placement REST API HTTP methods "
        "to be ignored during audit logging. For example: "
        "auditing will not be done on any GET or POST "
        "requests if this is set to 'GET,POST'. It is used "
        "only when API audit is enabled.",
    ),
]


def register_opts(conf):
    conf.register_group(audit_group)
    conf.register_opts(audit_opts, group=audit_group)


def list_opts():
    return {audit_group: audit_opts}
