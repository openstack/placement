# Copyright 2015 OpenStack Foundation
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
from oslo_db import options as oslo_db_options

_ENRICHED = False


def enrich_help_text(alt_db_opts):

    def get_db_opts():
        for group_name, db_opts in oslo_db_options.list_opts():
            if group_name == 'database':
                return db_opts
        return []

    for db_opt in get_db_opts():
        for alt_db_opt in alt_db_opts:
            if alt_db_opt.name == db_opt.name:
                # NOTE(markus_z): We can append alternative DB specific help
                # texts here if needed.
                alt_db_opt.help = db_opt.help + alt_db_opt.help


# NOTE(markus_z): We cannot simply do:
# conf.register_opts(oslo_db_options.database_opts, 'placement_database')
# If we reuse a db config option for two different groups ("placement_database"
# and "database") and deprecate or rename a config option in one of these
# groups, "oslo.config" cannot correctly determine which one to update.
# That's why we copied & pasted these config options for the
# "placement_database" group here. See nova commit ba407e3 ("Add support
# for multiple database engines") for more details.
# TODO(cdent): Consider our future options of using 'database' instead of
# 'placement_database' for the group. This is already loose in the wild,
# explicit, and safe if there will ever be more than one database, so may
# be good to leave it.
placement_db_group = cfg.OptGroup('placement_database',
                                  title='Placement API database options',
                                  help="""
The *Placement API Database* is a the database used with the placement
service. If the connection option is not set, the placement service will
not start.
""")

placement_db_opts = [
    cfg.StrOpt(
        'connection',
        help='',
        required=True,
        secret=True),
    cfg.StrOpt(
        'connection_parameters',
        default='',
        help=''),
    cfg.BoolOpt(
        'sqlite_synchronous',
        default=True,
        help=''),
    cfg.StrOpt(
        'slave_connection',
        secret=True,
        help=''),
    cfg.StrOpt(
        'mysql_sql_mode',
        default='TRADITIONAL',
        help=''),
    cfg.IntOpt(
        'connection_recycle_time',
        default=3600,
        help=''),
    cfg.IntOpt(
        'max_pool_size',
        help=''),
    cfg.IntOpt(
        'max_retries',
        default=10,
        help=''),
    cfg.IntOpt(
        'retry_interval',
        default=10,
        help=''),
    cfg.IntOpt(
        'max_overflow',
        help=''),
    cfg.IntOpt(
        'connection_debug',
        default=0,
        help=''),
    cfg.BoolOpt(
        'connection_trace',
        default=False,
        help=''),
    cfg.IntOpt(
        'pool_timeout',
        help=''),
    cfg.BoolOpt(
        'sync_on_startup',
        default=False,
        help='If True, database schema migrations will be attempted when the'
             ' web service starts.'),
]


def register_opts(conf):
    conf.register_opts(placement_db_opts, group=placement_db_group)


def list_opts():
    # NOTE(markus_z): 2016-04-04: If we list the oslo_db_options here, they
    # get emitted twice(!) in the "sample.conf" file. First under the
    # namespace "nova.conf" and second under the namespace "oslo.db". This
    # is due to the setting in file "etc/nova/nova-config-generator.conf".
    # As I think it is useful to have the "oslo.db" namespace information
    # in the "sample.conf" file, I omit the listing of the "oslo_db_options"
    # here.
    global _ENRICHED
    if not _ENRICHED:
        enrich_help_text(placement_db_opts)
        _ENRICHED = True
    return {
        placement_db_group: placement_db_opts,
    }
