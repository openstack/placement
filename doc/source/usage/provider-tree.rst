..
      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

==============================
 Modeling with Provider Trees
==============================

Overview
========

Placement supports modeling a hierarchical relationship between different
resource providers. While a parent provider can have multiple child providers,
a child provider can belong to only one parent provider. Therefore, the whole
architecture can be considered as a "tree" structure, and the resource provider
on top of the "tree" is called a "root provider". (See the
`Nested Resource Providers`_ spec for details.)

Modeling the relationship is done by specifying a parent provider via the
`POST /resource_providers`_ operation when creating a resource provider.

.. note:: If the parent provider hasn't been set, you can also parent a
          resource provider after the creation via the
          `PUT /resource_providers/{uuid}`_ operation. But re-parenting a
          resource provider is not supported.

The resource providers in a tree -- and sharing providers as described in the
next section -- can be returned in a single allocation request in the response
of the `GET /allocation_candidates`_ operation. This means that the placement
service looks up a resource provider tree in which resource providers can
*collectively* contain all of the requested resources.

This document describes some case studies to explain how sharing providers,
aggregates, and traits work if provider trees are involved in the
`GET /allocation_candidates`_ operation.

Sharing Resource Providers
==========================

Resources on sharing resource providers can be shared by multiple resource
provider trees. This means that a sharing provider can be in one allocation
request with resource providers from a different tree in the response of the
`GET /allocation_candidates`_ operation. As an example, this may be used for
shared storage that is connected to multiple compute hosts.

.. note:: Technically, a resource provider with the
          ``MISC_SHARES_VIA_AGGREGATE`` trait becomes a sharing resource
          provider and the resources on it are shared by other resource
          providers in the same aggregate.

For example, let's say we have the following environment::

      +-------------------------------+   +-------------------------------+
      | Sharing Storage (SS1)         |   | Sharing Storage (SS2)         |
      |  resources:                   |   |  resources:                   |
      |      DISK_GB: 1000            |   |      DISK_GB: 1000            |
      |  aggregate: [aggA]            |   |  aggregate: []                |
      |  trait:                       |   |  trait:                       |
      |   [MISC_SHARES_VIA_AGGREGATE] |   |   [MISC_SHARES_VIA_AGGREGATE] |
      +---------------+---------------+   +-------------------------------+
                      | Shared via aggA
          +-----------+-----------+           +-----------------------+
          | Compute Node (CN1)    |           | Compute Node (CN2)    |
          |   resources:          |           |   resources:          |
          |      VCPU: 8          |           |      VCPU: 8          |
          |      MEMORY_MB: 1024  |           |      MEMORY_MB: 1024  |
          |      DISK_GB: 1000    |           |      DISK_GB: 1000    |
          |   aggregate: [aggA]   |           |   aggregate: []       |
          |   trait: []           |           |   trait: []           |
          +-----------------------+           +-----------------------+

Assuming no allocations have yet been made against any of the resource
providers, the request::

    GET /allocation_candidates?resources=VCPU:1,MEMORY_MB:512,DISK_GB:500

would return three combinations as the allocation candidates.

1. ``CN1`` (``VCPU``, ``MEMORY_MB``, ``DISK_GB``)
2. ``CN2`` (``VCPU``, ``MEMORY_MB``, ``DISK_GB``)
3. ``CN1`` (``VCPU``, ``MEMORY_MB``) + ``SS1`` (``DISK_GB``)

``SS2`` is also a sharing provider, but not in the allocation candidates because
it can't satisfy the resource itself and it isn't in any aggregate, so it is
not shared by any resource providers.

When a provider tree structure is present, sharing providers are shared by
the whole tree if one of the resource providers from the tree is connected to
the sharing provider via an aggregate.

For example, let's say we have the following environment where NUMA resource
providers are child providers of the compute host resource providers::

                           +------------------------------+
                           | Sharing Storage (SS1)        |
                           |  resources:                  |
                           |      DISK_GB: 1000           |
                           |  agg: [aggA]                 |
                           |  trait:                      |
                           |   [MISC_SHARES_VIA_AGGREGATE]|
                           +--------------+---------------+
                                          | aggA
      +--------------------------------+  |  +--------------------------------+
      |  +--------------------------+  |  |  |  +--------------------------+  |
      |  | Compute Node (CN1)       |  |  |  |  | Compute Node (CN2)       |  |
      |  |   resources:             +-----+-----+   resources:             |  |
      |  |     MEMORY_MB: 1024      |  |     |  |     MEMORY_MB: 1024      |  |
      |  |     DISK_GB: 1000        |  |     |  |     DISK_GB: 1000        |  |
      |  |   agg: [aggA, aggB]      |  |     |  |   agg: [aggA]            |  |
      |  +-----+-------------+------+  |     |  +-----+-------------+------+  |
      |        | nested      | nested  |     |        | nested      | nested  |
      |  +-----+------+ +----+------+  |     |  +-----+------+ +----+------+  |
      |  | NUMA1_1    | | NUMA1_2   |  |     |  | NUMA2_1    | | NUMA2_2   |  |
      |  |  VCPU: 8   | |  VCPU: 8  |  |     |  |  VCPU: 8   | |  VCPU: 8  |  |
      |  |  agg:[]    | |  agg:[]   |  |     |  |  agg:[aggB]| |  agg:[]   |  |
      |  +------------+ +-----------+  |     |  +------------+ +-----------+  |
      +--------------------------------+     +--------------------------------+

Assuming no allocations have yet been made against any of the resource
providers, the request::

    GET /allocation_candidates?resources=VCPU:1,MEMORY_MB:512,DISK_GB:500

would return eight combinations as the allocation candidates.

1. ``NUMA1_1`` (``VCPU``) + ``CN1`` (``MEMORY_MB``, ``DISK_GB``)
2. ``NUMA1_2`` (``VCPU``) + ``CN1`` (``MEMORY_MB``, ``DISK_GB``)
3. ``NUMA2_1`` (``VCPU``) + ``CN2`` (``MEMORY_MB``, ``DISK_GB``)
4. ``NUMA2_2`` (``VCPU``) + ``CN2`` (``MEMORY_MB``, ``DISK_GB``)
5. ``NUMA1_1`` (``VCPU``) + ``CN1`` (``MEMORY_MB``) + ``SS1`` (``DISK_GB``)
6. ``NUMA1_2`` (``VCPU``) + ``CN1`` (``MEMORY_MB``) + ``SS1`` (``DISK_GB``)
7. ``NUMA2_1`` (``VCPU``) + ``CN2`` (``MEMORY_MB``) + ``SS1`` (``DISK_GB``)
8. ``NUMA2_2`` (``VCPU``) + ``CN2`` (``MEMORY_MB``) + ``SS1`` (``DISK_GB``)

Note that ``NUMA1_1`` and ``SS1``, for example, are not in the same aggregate,
but they can be in one allocation request since the tree of ``CN1`` is
connected to ``SS1`` via aggregate A on ``CN1``.

Filtering Aggregates
====================

What differs between the ``CN1`` and ``CN2`` in the example above emerges when you
specify the aggregate explicitly in the `GET /allocation_candidates`_ operation
with the ``member_of`` query parameter. The ``member_of`` query parameter
accepts aggregate uuids and filters candidates to the resource providers in the
given aggregate. See the `Filtering by Aggregate Membership`_ spec for details.

Note that the `GET /allocation_candidates`_ operation assumes that "an
aggregate on a root provider spans the whole tree, while an aggregate on a
non-root provider does NOT span the whole tree."

For example, in the environment above, the request::

    GET /allocation_candidates?resources=VCPU:1,MEMORY_MB:512,DISK_GB:500&member_of=<aggA uuid>

would return eight candidates,

1. ``NUMA1_1`` (``VCPU``) + ``CN1`` (``MEMORY_MB``, ``DISK_GB``)
2. ``NUMA1_2`` (``VCPU``) + ``CN1`` (``MEMORY_MB``, ``DISK_GB``)
3. ``NUMA2_1`` (``VCPU``) + ``CN2`` (``MEMORY_MB``, ``DISK_GB``)
4. ``NUMA2_2`` (``VCPU``) + ``CN2`` (``MEMORY_MB``, ``DISK_GB``)
5. ``NUMA1_1`` (``VCPU``) + ``CN1`` (``MEMORY_MB``) + ``SS1`` (``DISK_GB``)
6. ``NUMA1_2`` (``VCPU``) + ``CN1`` (``MEMORY_MB``) + ``SS1`` (``DISK_GB``)
7. ``NUMA2_1`` (``VCPU``) + ``CN2`` (``MEMORY_MB``) + ``SS1`` (``DISK_GB``)
8. ``NUMA2_2`` (``VCPU``) + ``CN2`` (``MEMORY_MB``) + ``SS1`` (``DISK_GB``)

This is because aggregate A is on the root providers, ``CN1`` and ``CN2``, so
the API assumes the child providers ``NUMA1_1``, ``NUMA1_2``, ``NUMA2_1`` and
``NUMA2_2`` are also in the aggregate A.

Specifying aggregate B::

    GET /allocation_candidates?resources=VCPU:1,MEMORY_MB:512,DISK_GB:500&member_of=<aggB uuid>

would return two candidates.

1. ``NUMA1_1`` (``VCPU``) + ``CN1`` (``MEMORY_MB``, ``DISK_GB``)
2. ``NUMA1_2`` (``VCPU``) + ``CN1`` (``MEMORY_MB``, ``DISK_GB``)

This is because ``SS1`` is not in aggregate A, and because aggregate B on
``NUMA2_1`` doesn't span the whole tree since the ``NUMA2_1`` resource
provider isn't a root resource provider.

Filtering by Traits
===================

Traits are not only used to indicate sharing providers. They are used to denote
capabilities of resource providers. (See `The Traits API`_ spec for details.)

Traits can be requested explicitly in the `GET /allocation_candidates`_
operation with the ``required`` query parameter, but traits on resource
providers never span other resource providers. If a trait is requested, one of
the resource providers that appears in the allocation candidate should have
the trait regardless of sharing or nested providers. See the `Request Traits`_
spec for details. The ``required`` query parameter also supports negative
expression, via the ``!`` prefix, for forbidden traits. If a forbidden trait
is specified, none of the resource providers that appear in the allocation
candidate may have that trait. See the `Forbidden Traits`_ spec for details.

For example, let's say we have the following environment::

      +----------------------------------------------------+
      |  +----------------------------------------------+  |
      |  | Compute Node (CN1)                           |  |
      |  |   resources:                                 |  |
      |  |     VCPU: 8, MEMORY_MB: 1024, DISK_GB: 1000  |  |
      |  |   trait: []                                  |  |
      |  +----------+------------------------+----------+  |
      |             | nested                 | nested      |
      |  +----------+-----------+ +----------+----------+  |
      |  | NIC1_1               | | NIC1_2              |  |
      |  |   resources:         | |   resources:        |  |
      |  |     SRIOV_NET_VF:8   | |     SRIOV_NET_VF:8  |  |
      |  |   trait:             | |   trait:            |  |
      |  |    [HW_NIC_ACCEL_SSL]| |     []              |  |
      |  +----------------------+ +---------------------+  |
      +----------------------------------------------------+

Assuming no allocations have yet been made against any of the resource
providers, the request::

    GET /allocation_candidates?resources=VCPU:1,MEMORY_MB:512,DISK_GB:500,SRIOV_NET_VF:2
                              &required=HW_NIC_ACCEL_SSL

would return only ``NIC1_1`` for ``SRIOV_NET_VF``. As a result, we get one
candidate.

1. ``CN1`` (``VCPU``, ``MEMORY_MB``, ``DISK_GB``) + ``NIC1_1`` (``SRIOV_NET_VF``)

In contrast, for forbidden traits::

    GET /allocation_candidates?resources=VCPU:1,MEMORY_MB:512,DISK_GB:500,SRIOV_NET_VF:2
                              &required=!HW_NIC_ACCEL_SSL

would exclude ``NIC1_1`` for ``SRIOV_NET_VF``.

1. ``CN1`` (``VCPU, ``MEMORY_MB``, ``DISK_GB``) + ``NIC1_2`` (``SRIOV_NET_VF``)

If the trait is not in the ``required`` parameter, that trait will simply be
ignored in the `GET /allocation_candidates`_ operation.

For example::

    GET /allocation_candidates?resources=VCPU:1,MEMORY_MB:512,DISK_GB:500,SRIOV_NET_VF:2

would return two candidates.

1. ``CN1`` (``VCPU``, ``MEMORY_MB``, ``DISK_GB``) + ``NIC1_1`` (``SRIOV_NET_VF``)
2. ``CN1`` (``VCPU``, ``MEMORY_MB``, ``DISK_GB``) + ``NIC1_2`` (``SRIOV_NET_VF``)

Granular Resource Requests
==========================

If you want to get the same kind of resources from multiple resource providers
at once, or if you require a provider of a particular requested resource
class to have a specific trait or aggregate membership, you can use the
`Granular Resource Request`_ feature.

This feature is enabled by numbering the ``resources``, ``member_of`` and
``required`` query parameters respectively.

For example, in the environment above, the request::

    GET /allocation_candidates?resources=VCPU:1,MEMORY_MB:512,DISK_GB:500
                              &resources1=SRIOV_NET_VF:1&required1=HW_NIC_ACCEL_SSL
                              &resources2=SRIOV_NET_VF:1
                              &group_policy=isolate

would return one candidate where two providers serve ``SRIOV_NET_VF`` resource.

1. ``CN1`` (``VCPU``, ``MEMORY_MB``, ``DISK_GB``) + ``NIC1_1`` (``SRIOV_NET_VF:1``) + ``NIC1_2`` (``SRIOV_NET_VF:1``)

The ``group_policy=isolate`` ensures that the one resource is from a provider
with the ``HW_NIC_ACCEL_SSL`` trait and the other is from *another* provider
with no trait constraints.

If the ``group_policy`` is set to ``none``, it allows multiple granular
requests to be served by one provider. Namely::

    GET /allocation_candidates?resources=VCPU:1,MEMORY_MB:512,DISK_GB:500
                              &resources1=SRIOV_NET_VF:1&required1=HW_NIC_ACCEL_SSL
                              &resources2=SRIOV_NET_VF:1
                              &group_policy=none

would return two candidates.

1. ``CN1`` (``VCPU``, ``MEMORY_MB``, ``DISK_GB``) + ``NIC1_1`` (``SRIOV_NET_VF:1``) + ``NIC1_2`` (``SRIOV_NET_VF:1``)
2. ``CN1`` (``VCPU``, ``MEMORY_MB``, ``DISK_GB``) + ``NIC1_1`` (``SRIOV_NET_VF:2``)

This is because ``NIC1_1`` satisfies both request 1 (with ``HW_NIC_ACCEL_SSL``
trait) and request 2 (with no trait constraints).

Note that if ``member_of<N>`` is specified in granular requests, the API
doesn't assume that "an aggregate on a root provider spans the whole tree."
It just sees whether the specified aggregate is directly associated with the
resource provider when looking up the candidates.

.. _`Nested Resource Providers`: https://specs.openstack.org/openstack/nova-specs/specs/queens/approved/nested-resource-providers.html
.. _`POST /resource_providers`: https://developer.openstack.org/api-ref/placement/
.. _`PUT /resource_providers/{uuid}`: https://developer.openstack.org/api-ref/placement/
.. _`GET /allocation_candidates`: https://developer.openstack.org/api-ref/placement/
.. _`Filtering by Aggregate Membership`: https://specs.openstack.org/openstack/nova-specs/specs/rocky/implemented/alloc-candidates-member-of.html
.. _`The Traits API`: http://specs.openstack.org/openstack/nova-specs/specs/pike/implemented/resource-provider-traits.html
.. _`Request Traits`: https://specs.openstack.org/openstack/nova-specs/specs/queens/implemented/request-traits-in-nova.html
.. _`Forbidden Traits`: https://specs.openstack.org/openstack/nova-specs/specs/rocky/implemented/placement-forbidden-traits.html
.. _`Granular Resource Request`: https://specs.openstack.org/openstack/nova-specs/specs/rocky/implemented/granular-resource-requests.html
