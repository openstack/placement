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
from __future__ import absolute_import

from oslo_config import cfg

from placement.conf import api
from placement.conf import base
from placement.conf import database
from placement.conf import keystone
from placement.conf import paths
from placement.conf import placement

CONF = cfg.CONF

api.register_opts(CONF)
base.register_opts(CONF)
database.register_opts(CONF)
keystone.register_opts(CONF)
paths.register_opts(CONF)
placement.register_opts(CONF)
