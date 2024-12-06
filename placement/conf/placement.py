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


DEFAULT_CONSUMER_MISSING_ID = '00000000-0000-0000-0000-000000000000'

placement_group = cfg.OptGroup(
    'placement',
    title='Placement Service Options',
    help="Configuration options for connecting to the placement API service")

placement_opts = [
    cfg.BoolOpt(
        'randomize_allocation_candidates',
        default=False,
        help="""
If True, when limiting allocation candidate results, the results will be
a random sampling of the full result set. The
[placement]max_allocation_candidates config might limit the size of the full
set used as the input of the sampling.

If False, allocation candidates are returned in a deterministic but undefined
order. That is, all things being equal, two requests for allocation candidates
will return the same results in the same order; but no guarantees are made as
to how that order is determined.
"""),
    cfg.StrOpt(
        'incomplete_consumer_project_id',
        default=DEFAULT_CONSUMER_MISSING_ID,
        help="""
Early API microversions (<1.8) allowed creating allocations and not specifying
a project or user identifier for the consumer. In cleaning up the data
modeling, we no longer allow missing project and user information. If an older
client makes an allocation, we'll use this in place of the information it
doesn't provide.
"""),
    cfg.StrOpt(
        'incomplete_consumer_user_id',
        default=DEFAULT_CONSUMER_MISSING_ID,
        help="""
Early API microversions (<1.8) allowed creating allocations and not specifying
a project or user identifier for the consumer. In cleaning up the data
modeling, we no longer allow missing project and user information. If an older
client makes an allocation, we'll use this in place of the information it
doesn't provide.
"""),
    cfg.IntOpt(
        'allocation_conflict_retry_count',
        default=10,
        help="""
The number of times to retry, server-side, writing allocations when there is
a resource provider generation conflict. Raising this value may be useful
when many concurrent allocations to the same resource provider are expected.
"""),
    cfg.IntOpt(
        'max_allocation_candidates',
        default=-1,
        help="""
The maximum number of allocation candidates placement generates for a single
request. This is a global limit to avoid excessive memory use and query
runtime. If set to -1 it means that the number of generated candidates are
only limited by the number and structure of the resource providers and the
content of the allocation_candidates query.

Note that the limit param of the allocation_candidates query is applied after
all the viable candidates are generated so that limit alone is not enough to
restrict the runtime or memory consumption of the query.

In a deployment with thousands of resource providers or if the deployment has
wide and symmetric provider trees, i.e. there are multiple children providers
under the same root having inventory from the same resource class
(e.g. in case of nova's mdev GPU or PCI in Placement features) we recommend
to tune this config option based on the memory available for the
placement service and the client timeout setting on the client side. A good
initial value could be around 100000.

In a deployment with wide and symmetric provider trees we also recommend to
change the [placement]allocation_candidates_generation_strategy to
breadth-first.
"""),
    cfg.StrOpt(
        'allocation_candidates_generation_strategy',
        default="depth-first",
        choices=("depth-first", "breadth-first"),
        help="""
Defines the order placement visits viable root providers during allocation
candidate generation:

* depth-first, generates all candidates from the first viable root provider
  before moving to the next.

* breadth-first, generates candidates from viable roots in a round-robin
  fashion, creating one candidate from each viable root before creating the
  second candidate from the first root.

If the deployment has wide and symmetric provider trees, i.e. there are
multiple children providers under the same root having inventory from the same
resource class (e.g. in case of nova's mdev GPU or PCI in Placement features)
then the depth-first strategy with a max_allocation_candidates
limit might produce candidates from a limited set of root providers. On the
other hand breadth-first strategy will ensure that the candidates are returned
from all viable roots in a balanced way.

Both strategies produce the candidates in the API response in an undefined but
deterministic order. That is, all things being equal, two requests for
allocation candidates will return the same results in the same order; but no
guarantees are made as to how that order is determined.
"""),
]


# Duplicate log_options from oslo_service so that we don't have to import
# that package into placement.
# NOTE(cdent): Doing so ends up requiring eventlet and other unnecessary
# packages for just this one setting.
service_opts = [
    cfg.BoolOpt('log_options',
                default=True,
                help='Enables or disables logging values of all registered '
                     'options when starting a service (at DEBUG level).'),
]


def register_opts(conf):
    conf.register_group(placement_group)
    conf.register_opts(placement_opts, group=placement_group)
    conf.register_opts(service_opts)


def list_opts():
    return {placement_group.name: placement_opts}
