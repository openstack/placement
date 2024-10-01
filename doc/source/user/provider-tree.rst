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

This is because ``SS1`` is not in aggregate B, and because aggregate B on
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
The ``required`` parameter also supports the syntax ``in:T1,T2,...`` which
means we are looking for resource providers that have either T1 or T2 traits on
them. The two trait query syntax can be combined by repeating the ``required``
query parameter. So querying providers having (T1 or T2) and T3 and not T4 can
be expressed with ``required=in:T1,T2&required=T3,!T4``.

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

1. ``CN1`` (``VCPU``, ``MEMORY_MB``, ``DISK_GB``) + ``NIC1_2`` (``SRIOV_NET_VF``)

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

Filtering by Tree
=================

If you want to filter the result by a specific provider tree, use the
`Filter Allocation Candidates by Provider Tree`_ feature with the ``in_tree``
query parameter. For example, let's say we have the following environment::

         +-----------------------+          +-----------------------+
         | Sharing Storage (SS1) |          | Sharing Storage (SS2) |
         |   DISK_GB: 1000       |          |   DISK_GB: 1000       |
         +-----------+-----------+          +-----------+-----------+
                     |                                  |
                     +-----------------+----------------+
                                       | Shared via an aggregate
                     +-----------------+----------------+
                     |                                  |
      +--------------|---------------+   +--------------|--------------+
      | +------------+-------------+ |   | +------------+------------+ |
      | | Compute Node (CN1)       | |   | | Compute Node (CN2)      | |
      | |   DISK_GB: 1000          | |   | |  DISK_GB: 1000          | |
      | +-----+-------------+------+ |   | +----+-------------+------+ |
      |       | nested      | nested |   |      | nested      | nested |
      | +-----+------+ +----+------+ |   | +----+------+ +----+------+ |
      | | NUMA1_1    | | NUMA1_2   | |   | | NUMA2_1   | | NUMA2_2   | |
      | |   VCPU: 4  | |   VCPU: 4 | |   | |  VCPU: 4  | |   VCPU: 4 | |
      | +------------+ +-----------+ |   | +-----------+ +-----------+ |
      +------------------------------+   +-----------------------------+

The request::

    GET /allocation_candidates?resources=VCPU:1,DISK_GB:50&in_tree=<CN1 uuid>

will filter out candidates by ``CN1`` and return 2 combinations of allocation
candidates.

1. ``NUMA1_1`` (``VCPU``) + ``CN1`` (``DISK_GB``)
2. ``NUMA1_2`` (``VCPU``) + ``CN1`` (``DISK_GB``)

The specified tree can be a non-root provider. The request::

    GET /allocation_candidates?resources=VCPU:1,DISK_GB:50&in_tree=<NUMA1_1 uuid>

will return the same result being aware of resource providers in the same tree
with ``NUMA1_1`` resource provider.

1. ``NUMA1_1`` (``VCPU``) + ``CN1`` (``DISK_GB``)
2. ``NUMA1_2`` (``VCPU``) + ``CN1`` (``DISK_GB``)

.. note::

    We don't exclude ``NUMA1_2`` in the case above. That kind of feature is
    proposed separately and in progress. See the `Support subtree filter`_
    specification for details.

The suffixed syntax ``in_tree<$S>`` (where ``$S`` is a number in microversions
``1.25-1.32`` and ``[a-zA-Z0-9_-]{1,64}`` from ``1.33``) is also supported
according to `Granular Resource Requests`_. This restricts providers satisfying
the suffixed granular request group to the tree of the specified provider.

For example, in the environment above, when you want to have ``VCPU`` from
``CN1`` and ``DISK_GB`` from wherever, the request may look like::

    GET /allocation_candidates?resources=VCPU:1&in_tree=<CN1 uuid>
                              &resources1=DISK_GB:10

which will return the sharing providers as well as the local disk.

1. ``NUMA1_1`` (``VCPU``) + ``CN1`` (``DISK_GB``)
2. ``NUMA1_2`` (``VCPU``) + ``CN1`` (``DISK_GB``)
3. ``NUMA1_1`` (``VCPU``) + ``SS1`` (``DISK_GB``)
4. ``NUMA1_2`` (``VCPU``) + ``SS1`` (``DISK_GB``)
5. ``NUMA1_1`` (``VCPU``) + ``SS2`` (``DISK_GB``)
6. ``NUMA1_2`` (``VCPU``) + ``SS2`` (``DISK_GB``)

This is because the unsuffixed ``in_tree`` is applied to only the unsuffixed
resource of ``VCPU``, and not applied to the suffixed resource, ``DISK_GB``.

When you want to have ``VCPU`` from wherever and ``DISK_GB`` from ``SS1``,
the request may look like::

    GET /allocation_candidates?resources=VCPU:1
                              &resources1=DISK_GB:10&in_tree1=<SS1 uuid>

which will stick to the first sharing provider for ``DISK_GB``.

1. ``NUMA1_1`` (``VCPU``) + ``SS1`` (``DISK_GB``)
2. ``NUMA1_2`` (``VCPU``) + ``SS1`` (``DISK_GB``)
3. ``NUMA2_1`` (``VCPU``) + ``SS1`` (``DISK_GB``)
4. ``NUMA2_2`` (``VCPU``) + ``SS1`` (``DISK_GB``)

When you want to have ``VCPU`` from ``CN1`` and ``DISK_GB`` from ``SS1``,
the request may look like::

    GET /allocation_candidates?resources1=VCPU:1&in_tree1=<CN1 uuid>
                              &resources2=DISK_GB:10&in_tree2=<SS1 uuid>
                              &group_policy=isolate

which will return only 2 candidates.

1. ``NUMA1_1`` (``VCPU``) + ``SS1`` (``DISK_GB``)
2. ``NUMA1_2`` (``VCPU``) + ``SS1`` (``DISK_GB``)

.. _`filtering by root provider traits`:

Filtering by Root Provider Traits
=================================

When traits are associated with a particular resource, the provider tree should
be constructed such that the traits are associated with the provider possessing
the inventory of that resource. For example, trait ``HW_CPU_X86_AVX2`` is a
trait associated with the ``VCPU`` resource, so it should be placed on the
resource provider with ``VCPU`` inventory, wherever that provider is positioned
in the tree structure. (A NUMA-aware host may model ``VCPU`` inventory in a
child provider, whereas a non-NUMA-aware host may model it in the root
provider.)

On the other hand, some traits are associated not with a resource, but with the
provider itself. For example, a compute host may be capable of
``COMPUTE_VOLUME_MULTI_ATTACH``, or be associated with a
``CUSTOM_WINDOWS_LICENSE_POOL``. In this case it is recommended that the root
resource provider be used to represent the concept of the "compute host"; so
these kinds of traits should always be placed on the root resource provider.

The following environment illustrates the above concepts::

  +---------------------------------+ +-------------------------------------------+
  |+-------------------------------+| |    +-------------------------------+      |
  || Compute Node (NON_NUMA_CN)    || |    | Compute Node (NUMA_CN)        |      |
  ||  VCPU: 8,                     || |    |  DISK_GB: 1000                |      |
  ||  MEMORY_MB: 1024              || |    | traits:                       |      |
  ||  DISK_GB: 1000                || |    |  STORAGE_DISK_SSD,            |      |
  || traits:                       || |    |  COMPUTE_VOLUME_MULTI_ATTACH  |      |
  ||  HW_CPU_X86_AVX2,             || |    +-------+-------------+---------+      |
  ||  STORAGE_DISK_SSD,            || |     nested |             | nested         |
  ||  COMPUTE_VOLUME_MULTI_ATTACH, || |+-----------+-------+ +---+---------------+|
  ||  CUSTOM_WINDOWS_LICENSE_POOL  || || NUMA1             | | NUMA2             ||
  |+-------------------------------+| ||  VCPU: 4          | |  VCPU: 4          ||
  +---------------------------------+ ||  MEMORY_MB: 1024  | |  MEMORY_MB: 1024  ||
                                      ||                   | | traits:           ||
                                      ||                   | |  HW_CPU_X86_AVX2  ||
                                      |+-------------------+ +-------------------+|
                                      +-------------------------------------------+

A tree modeled in this fashion can take advantage of the `root_required`_
query parameter to return only allocation candidates from trees which possess
(or do not possess) specific traits on their root provider. For example,
to return allocation candidates including ``VCPU`` with the ``HW_CPU_X86_AVX2``
instruction set from hosts capable of ``COMPUTE_VOLUME_MULTI_ATTACH``, a
request may look like::

  GET /allocation_candidates
    ?resources1=VCPU:1,MEMORY_MB:512&required1=HW_CPU_X86_AVX2
    &resources2=DISK_GB:100
    &group_policy=none
    &root_required=COMPUTE_VOLUME_MULTI_ATTACH

This will return results from both ``NUMA_CN`` and ``NON_NUMA_CN`` because
both have the ``COMPUTE_VOLUME_MULTI_ATTACH`` trait on the root provider; but
only ``NUMA2`` has ``HW_CPU_X86_AVX2`` so there will only be one result from
``NUMA_CN``.

1. ``NON_NUMA_CN`` (``VCPU``, ``MEMORY_MB``, ``DISK_GB``)
2. ``NUMA_CN`` (``DISK_GB``) + ``NUMA2`` (``VCPU``, ``MEMORY_MB``)

To restrict allocation candidates to only those not in your
``CUSTOM_WINDOWS_LICENSE_POOL``, a request may look like::

  GET /allocation_candidates
    ?resources1=VCPU:1,MEMORY_MB:512
    &resources2=DISK_GB:100
    &group_policy=none
    &root_required=!CUSTOM_WINDOWS_LICENSE_POOL

This will return results only from ``NUMA_CN`` because ``NON_NUMA_CN`` has the
forbidden ``CUSTOM_WINDOWS_LICENSE_POOL`` on the root provider.

1. ``NUMA_CN`` (``DISK_GB``) + ``NUMA1`` (``VCPU``, ``MEMORY_MB``)
2. ``NUMA_CN`` (``DISK_GB``) + ``NUMA2`` (``VCPU``, ``MEMORY_MB``)

The syntax of the ``root_required`` query parameter is identical to that of
``required[$S]``: multiple trait strings may be specified, separated by commas,
each optionally prefixed with ``!`` to indicate that it is forbidden.

.. note:: ``root_required`` may not be suffixed, and may be specified only
          once, as it applies only to the root provider.

.. note:: When sharing providers are involved in the request, ``root_required``
          applies only to the root of the non-sharing provider tree.

.. note:: While the ``required`` param supports the any-traits query with the
          ``in:`` prefix syntax since microversion 1.39 the ``root_required``
          parameter does not support it yet.

Filtering by Same Subtree
=========================

If you want to express affinity among allocations in separate request groups,
use the `same_subtree`_ query parameter. It accepts a comma-separated list of
request group suffix strings ($S). Each must exactly match a suffix on a
granular group somewhere else in the request. If this is provided, at least one
of the resource providers satisfying a specified request group must be an
ancestor of the rest.

For example, given a model like::

                   +---------------------------+
                   |  Compute Node (CN)        |
                   +-------------+-------------+
                                 |
            +--------------------+-------------------+
            |                                        |
  +-----------+-----------+              +-----------+-----------+
  | NUMA NODE (NUMA0)     |              | NUMA NODE (NUMA1)     |
  |   VCPU: 4             |              |   VCPU: 4             |
  |   MEMORY_MB: 2048     |              |   MEMORY_MB: 2048     |
  | traits:               |              | traits:               |
  |   HW_NUMA_ROOT        |              |   HW_NUMA_ROOT        |
  +-----------+-----------+              +----+-------------+----+
              |                               |             |
  +-----------+-----------+  +----------------+-----+ +-----+----------------+
  | FPGA (FPGA0_0)        |  | FPGA (FPGA1_0)       | | FPGA (FPGA1_1)       |
  |   ACCELERATOR_FPGA:1  |  |   ACCELERATOR_FPGA:1 | |   ACCELERATOR_FPGA:1 |
  | traits:               |  | traits:              | | traits:              |
  |   CUSTOM_TYPE1        |  |   CUSTOM_TYPE1       | |   CUSTOM_TYPE2       |
  +-----------------------+  +----------------------+ +----------------------+

To request FPGAs on the same NUMA node with VCPUs and MEMORY, a request may
look like::

  GET /allocation_candidates
    ?resources_COMPUTE=VCPU:1,MEMORY_MB:256
    &resources_ACCEL=ACCELERATOR_FPGA:1
    &group_policy=none
    &same_subtree=_COMPUTE,_ACCEL

This will produce candidates including:

1. ``NUMA0`` (``VCPU``, ``MEMORY_MB``) + ``FPGA0_0`` (``ACCELERATOR_FPGA``)
2. ``NUMA1`` (``VCPU``, ``MEMORY_MB``) + ``FPGA1_0`` (``ACCELERATOR_FPGA``)
3. ``NUMA1`` (``VCPU``, ``MEMORY_MB``) + ``FPGA1_1`` (``ACCELERATOR_FPGA``)

but not:

4. ``NUMA0`` (``VCPU``, ``MEMORY_MB``) + ``FPGA1_0`` (``ACCELERATOR_FPGA``)
5. ``NUMA0`` (``VCPU``, ``MEMORY_MB``) + ``FPGA1_1`` (``ACCELERATOR_FPGA``)
6. ``NUMA1`` (``VCPU``, ``MEMORY_MB``) + ``FPGA0_0`` (``ACCELERATOR_FPGA``)

The request groups specified in the ``same_subtree`` need not have a
resources$S. For example, to request 2 FPGAs with different traits on the same
NUMA node, a request may look like::

  GET /allocation_candidates
    ?required_NUMA=HW_NUMA_ROOT
    &resources_ACCEL1=ACCELERATOR_FPGA:1
    &required_ACCEL1=CUSTOM_TYPE1
    &resources_ACCEL2=ACCELERATOR_FPGA:1
    &required_ACCEL2=CUSTOM_TYPE2
    &group_policy=none
    &same_subtree=_NUMA,_ACCEL1,_ACCEL2

This will produce candidates including:

1. ``FPGA1_0`` (``ACCELERATOR_FPGA``) + ``FPGA1_1`` (``ACCELERATOR_FPGA``) + ``NUMA1``

but not:

2. ``FPGA0_0`` (``ACCELERATOR_FPGA``) + ``FPGA1_1`` (``ACCELERATOR_FPGA``) + ``NUMA0``
3. ``FPGA0_0`` (``ACCELERATOR_FPGA``) + ``FPGA1_1`` (``ACCELERATOR_FPGA``) + ``NUMA1``
4. ``FPGA1_0`` (``ACCELERATOR_FPGA``) + ``FPGA1_1`` (``ACCELERATOR_FPGA``) + ``NUMA0``

The resource provider that satisfies the resourceless request group
``?required_NUMA=HW_NUMA_ROOT``, ``NUMA1`` in the first example above, will
not be in the ``allocation_request`` field of the response, but is shown in
the ``mappings`` field.

The ``same_subtree`` query parameter can be repeated and each repeat group is
treated independently.

.. _`Nested Resource Providers`: https://specs.openstack.org/openstack/nova-specs/specs/queens/approved/nested-resource-providers.html
.. _`POST /resource_providers`: https://docs.openstack.org/api-ref/placement/#create-resource-provider
.. _`PUT /resource_providers/{uuid}`: https://docs.openstack.org/api-ref/placement/#update-resource-provider
.. _`GET /allocation_candidates`: https://docs.openstack.org/api-ref/placement/#list-allocation-candidates
.. _`Filtering by Aggregate Membership`: https://specs.openstack.org/openstack/nova-specs/specs/rocky/implemented/alloc-candidates-member-of.html
.. _`The Traits API`: http://specs.openstack.org/openstack/nova-specs/specs/pike/implemented/resource-provider-traits.html
.. _`Request Traits`: https://specs.openstack.org/openstack/nova-specs/specs/queens/implemented/request-traits-in-nova.html
.. _`Forbidden Traits`: https://specs.openstack.org/openstack/nova-specs/specs/rocky/implemented/placement-forbidden-traits.html
.. _`Granular Resource Request`: https://specs.openstack.org/openstack/nova-specs/specs/rocky/implemented/granular-resource-requests.html
.. _`Filter Allocation Candidates by Provider Tree`: https://specs.openstack.org/openstack/nova-specs/specs/stein/implemented/alloc-candidates-in-tree.html
.. _`Support subtree filter`: https://review.opendev.org/#/c/595236/
.. _`root_required`: https://docs.openstack.org/placement/latest/specs/train/approved/2005575-nested-magic-1.html#root-required
.. _`same_subtree`: https://docs.openstack.org/placement/latest/specs/train/approved/2005575-nested-magic-1.html#same-subtree
