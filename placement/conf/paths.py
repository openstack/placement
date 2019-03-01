# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# Copyright 2012 Red Hat, Inc.
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

import os

from oslo_config import cfg


ALL_OPTS = [
    cfg.StrOpt(
        'pybasedir',
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), '../../')),
        sample_default='<Path>',
        help="""
The directory where the Placement python modules are installed.

This is the default path for other config options which need to persist
Placement internal data. It is very unlikely that you need to
change this option from its default value.

Possible values:

* The full path to a directory.

Related options:

* ``state_path``
"""),
    cfg.StrOpt(
        'state_path',
        default='$pybasedir',
        help="""
The top-level directory for maintaining state used in Placement.

This directory is used to store Placement's internal state. It is used by some
tests that have behaviors carried over from Nova.

Possible values:

* The full path to a directory. Defaults to value provided in ``pybasedir``.
"""),
]


def state_path_def(*args):
    """Return an uninterpolated path relative to $state_path."""
    return os.path.join('$state_path', *args)


def register_opts(conf):
    conf.register_opts(ALL_OPTS)


def list_opts():
    return {"DEFAULT": ALL_OPTS}
