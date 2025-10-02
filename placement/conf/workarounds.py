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

workarounds_group = cfg.OptGroup(
    'workarounds',
    title='Workaround Options',
    help="""
A collection of workarounds used to mitigate bugs or issues found under
certain conditions. These should only be enabled in exceptional circumstances.
All options are linked against bug IDs, where more information on the issue can
be found.
""")

workaround_opts = [
    cfg.BoolOpt(
        "optimize_for_wide_provider_trees",
        default=False,
        help="""
Enable optimization of allocation candidate generation for wide provider trees.

As reported in `bug #2126751`_ in the situation where many similar child
provider is defined under the same root provider, placement's allocation
candidate generation algorithm scales poorly. This config option enables
certain optimizations that help decrease the time it takes to generate the
GET /allocation_candidates response for queries requesting multiple resources
from those child providers.

For example if a compute has 8 or more child resource providers providing one
resource each (e.g. 8 individual PGPU) and a VM requests 8 or more such
resources each in independent request groups then without this optimization
enabled the GET /allocation_candidates query takes too long to compute and
the scheduling will fail.

Setting the ``[placement]max_allocation_candidates``
config option to a small number (e.g. 100) can help to a certain degree but
alone cannot solve the problem when the number of devices available or the
number of requested devices increases.

**When to enable:** If you have at least 8 child resource providers within a
tree providing inventory of the same resource class. And you are trying
to support VMs with more than 4 such resources.
E.g.:

* Nova's PCI in Placement feature is enabled and you have at least 8 PCI
  devices with the same product_id in a single compute and you are using
  flavors requesting more than 4 such devices.

* Nova's GPU support is enabled and you have at least 8 GPUs per compute node
  while requesting more than 4 per VM.

**When not to enable:** If you have a flat resource provider tree, i.e. all
resources reported on the root provider. Or if your flavors are not requesting
more than 4 PCI or GPU resources of the same type.

Related options:

* ``[placement]max_allocation_candidates``: If you need to enable the
  this optimization then you are also in a situation where you want to set
  ``max_allocation_candidates`` to a number not more than 1000.
* ``[placement]allocation_candidates_generation_strategy``: If you use
  ``max_allocation_candidates`` then it is suggested to configure
  ``allocation_candidates_generation_strategy`` to ``breadth-first`` which will
  return candidates balanced across available compute nodes.

.. _bug #2126751: https://bugs.launchpad.net/placement/+bug/2126751
"""),
]


def register_opts(conf):
    conf.register_group(workarounds_group)
    conf.register_opts(workaround_opts, group=workarounds_group)


def list_opts():
    return {workarounds_group: workaround_opts}
