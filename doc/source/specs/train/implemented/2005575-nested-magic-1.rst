..
 This work is licensed under a Creative Commons Attribution 3.0 Unported
 License.

 http://creativecommons.org/licenses/by/3.0/legalcode

===================================
Getting On The Nested Magic Train 1
===================================

https://storyboard.openstack.org/#!/story/2005575

This spec describes a cluster of Placement API work to support several
interrelated use cases for Train around:

* Modeling complex trees such as NUMA layouts, multiple devices, networks.
* Requesting affinity [#]_ between/among the various providers/allocations in
  allocation candidates against such layouts.
* Describing granular groups more richly to facilitate the above.
* Requesting candidates based on traits that are not necessarily associated
  with resources.

An additional spec, for a feature known as `can_split`_ has been separated out
to its own spec to ensure that any delay in it does not impact these features,
which are less controversial.

.. [#] The kind of affinity we're talking about is best understood by
   referring to the use case for the `same_subtree`_ feature below.

Principles
==========
In developing this design, some fundamental concepts have come to light. These
are not really changes from the existing architecture, but understanding them
becomes more important in light of the changes introduced herein.

Resource versus Provider Traits
-------------------------------
The database model associates traits with resource providers, not with
inventories of resource classes. However, conceptually there are two different
categories of traits to consider.

.. _`resource traits`:

**Resource Traits** are tied to specific resources. For example,
``HW_CPU_X86_AVX2`` describes a characteristic of ``VCPU`` (or ``PCPU``)
resources.

.. _`provider traits`:

**Provider Traits** are characteristics of a provider, regardless of the
resources it provides. For example, ``COMPUTE_VOLUME_MULTI_ATTACH`` is a
capability of a compute host, not of any specific resource inventory.
``HW_NUMA_ROOT`` describes NUMA affinity among *all* the resources in the
inventories of that provider *and* all its descendants.
``CUSTOM_PHYSNET_PUBLIC`` indicates connectivity to the ``public`` network,
regardless of whether the associated resources are ``VF``, ``PF``, ``VNIC``,
etc.; and regardless of whether those resources reside on the provider marked
with the trait or on its descendants.

This distinction becomes important when deciding how to model. **Resource
traits** need to "follow" their resource class. For example,
``HW_CPU_X86_AVX2`` should be on the provider of ``VCPU`` (or ``PCPU``)
resource, whether that's the root or a NUMA child. On the other hand,
**provider traits** must stick to their provider, regardless of where resources
inventories are placed. For example, ``COMPUTE_VOLUME_MULTI_ATTACH`` should
always be on the root provider, as the root provider conceptually represents
"the compute host".

.. _`Traits Flow Down`:

**Alternative: "Traits Flow Down":** There have_ been_ discussions_ around a
provider implicitly inheriting the traits of its parent (and therefore all its
ancestors). This would (mostly) allow us not to think about the distinction
between "resource" and "provider" traits. We ultimately decided against this by
a hair, mainly because of this:

   It makes no sense to say my PGPU is capable of MULTI_ATTACH

   In addition, IIUC, there are SmartNICs [1] that have CPUs on cards.
   If someone will want to report/model those CPUs in placement, they
   will be scared that CPU traits on compute side flow down to those
   CPUs on NIC despite they are totally different CPUs.

   [1] https://www.netronome.com/products/smartnic/overview/

...and because we were able to come up with other satisfactory solutions to our
use cases.

.. _have: http://lists.openstack.org/pipermail/openstack-discuss/2019-April/005201.html
.. _been: http://lists.openstack.org/pipermail/openstack-discuss/2019-April/004817.html
.. _discussions: https://review.opendev.org/#/c/662191/3/doc/source/specs/train/approved/2005575-nested-magic-1.rst@266

Group-Specific versus Request-Wide Query Parameters
---------------------------------------------------
`granular resource requests`_ introduced a divide between ``GET
/allocation_candidates`` query parameters which apply to a particular request
group

* resources[$S]
* required[$S]
* member_of[$S]
* in_tree[$S]

.. _`request-wide`:

...and those which apply to the request as a whole

* limit
* group_policy

This has been fairly obvious thus far; but this spec introduces concepts (such
as `root_required`_ and `same_subtree`_) that make it important to keep this
distinction in mind.  Moving forward, we should consider whether new features
and syntax additions make more sense to be group-specific or request-wide.

.. _`granular resource requests`: http://specs.openstack.org/openstack/nova-specs/specs/rocky/implemented/granular-resource-requests.html

Proposed change
===============

All changes are to the ``GET /allocation_candidates`` operation via new
microversions, one per feature described below.

arbitrary group suffixes
------------------------
**Use case:** Client code managing request groups for different kinds of
resources - which will often come from different providers - may reside in
different places in the codebase. For example, the management of compute
resources vs. networks vs. accelerators. However, there still needs to be a way
for the consuming code to express relationships (such as affinity) among these
request groups. For this purpose, API consumers wish to be able to use
conventions for request group identifiers. It would also be nice for
development and debugging purposes if these designations had some element of
human readability.

(Merged) code is here: https://review.opendev.org/#/c/657419/

Granular groups are currently restricted to using integer suffixes. We will
change this so they can be case-sensitive strings up to 64 characters long
comprising alphanumeric (either case), underscore, and hyphen.

* 64c so we can fit a stringified UUID (with hyphens) as well as some kind of
  handy type designation. Like ``resources_PORT_$UUID``.
  https://review.opendev.org/#/c/657419/4/placement/schemas/allocation_candidate.py@19
* We want to allow uppercase so consumers can make nice visual distinctions
  like ``resources_PORT...``; we want to allow lowercase because openstack
  consumers tend to use lowercase UUIDs and this makes them not have to convert
  them. Placement will use the string in the form it is given and transform
  it neither on input nor output. If the form does not match constraints a
  ``400`` response will be returned.
  https://review.opendev.org/#/c/657419/4/placement/schemas/allocation_candidate.py@19
* **Alternative** Uppercase only so we don't have to worry about case
  sensitivity or confusing differentiation from the prefixes (which are
  lowercase). **Rejected** because we prefer allowing lowercase UUIDs, and are
  willing to give the consumer the rope.
  https://review.opendev.org/#/c/657419/1/placement/lib.py@31
* Hyphens so we can use UUIDs without too much scrubbing.

For purposes of documentation (and this spec), we'll rename the "unnumbered"
group to "unspecified" or "unsuffixed", and anywhere we reference "numbered"
groups we can call them "suffixed" or "granular" (I think this label is already
used in some places).

same_subtree
------------
**Use case:** I want to express affinity between/among allocations in separate
request groups. For example, that a ``VGPU`` come from a GPU affined to the
NUMA node that provides my ``VCPU`` and ``MEMORY_MB``; or that multiple network
``VF``\ s come from the same NIC.

A new ``same_subtree`` query parameter will be accepted. The value is a
comma-separated list of request group suffix strings ``$S``. Each must exactly
match a suffix on a granular group somewhere else in the request.  Importantly,
the identified request groups need not have a ``resources$S`` (see
`resourceless request groups`_).

We define "same subtree" as "all of the resource providers satisfying the
request group must be rooted at one of the resource providers satisfying the
request group". Or put another way: "one of the resource providers satisfying
the request group must be the direct ancestor of all the other resource
providers satisfying the request group".

For example, given a model like::

                +--------------+
                | compute node |
                +-------+------+
                        |
              +---------+----------+
              |                    |
    +---------+--------+ +---------+--------+
    | numa0            | | numa1            |
    | VCPU: 4 (2 used) | | VCPU: 4          |
    | MEMORY_MB: 2048  | | MEMORY_MB: 2048  |
    +---+--------------+ +---+----------+---+
        |                    |          |
    +---+----+           +---+---+  +---+---+
    |fpga0_0 |           |fpga1_0|  |fpga1_1|
    |FPGA:1  |           |FPGA:1 |  |FPGA:1 |
    +--------+           +-------+  +-------+

to request "two VCPUs, 512MB of memory, and one FPGA from the same NUMA
node," my request could include::

 ?resources_COMPUTE=VCPU:2,MEMORY_MB:512
 &resources_ACCEL=FPGA:1
 # NOTE: The suffixes include the leading underscore!
 &same_subtree=_COMPUTE,_ACCEL

This will produce candidates including::

 - numa0: {VCPU:2, MEMORY_MB:512}, fpga0_0: {FPGA:1}
 - numa1: {VCPU:2, MEMORY_MB:512}, fpga1_0: {FPGA:1}
 - numa1: {VCPU:2, MEMORY_MB:512}, fpga1_1: {FPGA:1}

but *not*::

 - numa0: {VCPU:2, MEMORY_MB:512}, fpga1_0: {FPGA:1}
 - numa0: {VCPU:2, MEMORY_MB:512}, fpga1_1: {FPGA:1}
 - numa1: {VCPU:2, MEMORY_MB:512}, fpga0_0: {FPGA:1}

The ``same_subtree`` query parameter is `request-wide`_, but may be repeated.
Each grouping is treated independently.

Anti-affinity
~~~~~~~~~~~~~
There were discussions about supporting ``!`` syntax in ``same_subtree`` to
express anti-affinity (e.g. ``same_subtree=$X,!$Y`` meaning "resources from
group ``$Y`` shall *not* come from the same subtree as resources from group
``$X``"). This shall be deferred to a future release.

resourceless request groups
---------------------------
**Use case:** When making use of `same_subtree`_, I want to be able to
identify a provider as a placeholder in the subtree structure even if I don't
need any resources from that provider.

It is currently a requirement that a ``resources$S`` exist for all ``$S`` in a
request. This restriction shall be removed such that a request group may exist
e.g. with only ``required$S`` or ``member_of$S``.

There must be at least one ``resources`` or ``resources$S`` somewhere in the
request, otherwise there will be no inventory to allocate and thus no
allocation candidates. If neither is present a ``400`` response will be
returned.

Furthermore, resourceless request groups must be used with `same_subtree`_.
That is, the suffix for each resourceless request group must feature in a
``same_subtree`` somewhere in the request. Otherwise a ``400`` response will be
returned. (The reasoning for this restriction_ is explained below.)

For example, given a model like::

                +--------------+
                | compute node |
                +-------+------+
                        |
            +-----------+-----------+
            |                       |
      +-----+-----+           +-----+-----+
      |nic1       |           |nic2       |
      |HW_NIC_ROOT|           |HW_NIC_ROOT|
      +-----+-----+           +-----+-----+
            |                       |
       +----+----+            +-----+---+
       |         |            |         |
    +--+--+   +--+--+      +--+--+   +--+--+
    |pf1_1|   |pf1_2|      |pf2_1|   |pf2_2|
    |NET1 |   |NET2 |      |NET1 |   |NET2 |
    |VF:4 |   |VF:4 |      |VF:2 |   |VF:2 |
    +-----+   +-----+      +-----+   +-----+

a request such as the following, meaning, "Two VFs from the same NIC,
one on each of network NET1 and NET2," is legal::

 ?resources_VIF_NET1=VF:1
 &required_VIF_NET1=NET1
 &resources_VIF_NET2=VF:1
 &required_VIF_NET2=NET2
 # NOTE: there is no resources_NIC_AFFINITY
 &required_NIC_AFFINITY=HW_NIC_ROOT
 &same_subtree=_VIF_NET1,_VIF_NET2,_NIC_AFFINITY

The returned candidates will include::

 - pf1_1: {VF:1}, pf1_2: {VF:1}
 - pf2_1: {VF:1}, pf2_2: {VF:1}

but *not*::

 - pf1_1: {VF:1}, pf2_2: {VF:1}
 - pf2_1: {VF:1}, pf1_2: {VF:1}

.. _restriction:

Why enforce resourceless + same_subtree?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Taken by itself (without `same_subtree`_), a resourceless request group
intuitively means, "There must exist in the solution space a resource provider
that satisfies these constraints." But what does "solution space" mean? Clearly
it's not the same as `solution path`_, or we wouldn't be able to use it to add
resourceless providers to that solution path. So it must encompass at least the
entire non-sharing tree around the solution path. Does it also encompass
sharing providers associated via aggregate? What would that mean?

Since we have not identified any real use cases for resourceless *without*
`same_subtree`_ (other than `root_member_of`_ -- see below) making this an
error allows us to not have to deal with these questions.

root_required
-------------
**Use case:** I want to limit allocation candidates to trees `whose root
provider`_ has (or does not have) certain traits. For example, I want to limit
candidates to only multi-attach-capable hosts; or preserve my Windows-licensed
hosts for special use.

A new ``root_required`` query parameter will be accepted. The value syntax is
identical to that of ``required[$S]``: that is, it accepts a comma-delimited
list of trait names, each optionally prefixed with ``!`` to indicate
"forbidden" rather than "required".

This is a `request-wide`_ query parameter designed for `provider traits`_
specifically on the root provider of the non-sharing tree involved in the
allocation candidate. That is, regardless of any group-specific constraints,
and regardless of whether the root actually provides resource to the request,
results will be filtered such that the root of the non-sharing tree conforms to
the constraints specified in ``root_required``.

``root_required`` may not be repeated.

.. _`whose root provider`:

The fact that this feature is (somewhat awkwardly) restricted to "...trees
whose root provider ..." deserves some explanation. This is to fill a gap
in use cases that cannot be adequately covered by other query parameters.

* To land on a tree (host) with a given trait *anywhere* in its hierarchy,
  `resourceless request groups`_ without `same_subtree`_ could be used.
  However, there is no way to express the "forbidden" side of this in a way
  that makes sense:

  * A resourceless ``required$S=!FOO`` would simply ensure that a provider
    *anywhere in the tree* does not have ``FOO`` - which would end up not being
    restrictive as intended in most cases.
  * We could define "resourceless forbidden" to mean "nowhere in the tree", but
    this would be inconsistent and hard to explain.

* To ensure that the desired trait is present (or absent) in the *result set*,
  it would be necessary to attach the trait to a group whose resource
  constraints will be satisfied by the provider possessing (or lacking) that
  trait.

  * This requires the API consumer to understand too much about how the
    provider trees are modeled; and
  * It doesn't work in heterogeneous environments where such `provider traits`_
    may or may not stick with providers of a specific resource class.

  This could possibly be mitigated by careful use of `same_subtree`_, but
  that again requires deep understanding of the tree model, and also confuses
  the meaning of `same_subtree`_ and `resource versus provider traits`_.

* The `traits flow down`_ concept described earlier could help here; but that
  would still entail attaching `provider traits`_ to a particular request
  group. Which one? Because the trait isn't associated with a specific
  resource, it would be arbitrary and thus difficult to explain and justify.

.. _`solution path`:

**Alternative: "Solution Path":** A more general solution was discussed whereby
we would define a "solution path" as: **The set of resource providers which
satisfy all the request groups *plus* all the ancestors of those providers, up
to the root.** This would allow us to introduce a `request-wide`_ query
parameter such as ``solution_path_required``. The idea would be the same as
``root_required``, but the specified trait constraints would be applied to all
providers in the "solution path" (required traits must be present *somewhere*
in the solution path; forbidden traits must not be present *anywhere* in the
solution path).

This alternative was rejected because:

* Describing the "solution path" concept to API consumers would be hard.
* We decided the only real use cases where the trait constraints needed to be
  applied to providers *other than the root* could be satisfied (and more
  naturally) in other ways.

This section was the result of long discussions `in IRC`_ and on `the review
for this spec`_

.. _`in IRC`: http://eavesdrop.openstack.org/irclogs/%23openstack-placement/%23openstack-placement.2019-06-12.log.html#t2019-06-12T15:04:48
.. _`the review for this spec`: https://review.opendev.org/#/c/662191/

root_member_of
--------------
.. note:: When this spec was initially written it was not clear whether there
          was immediate need to implement this feature. This turned out to be
          the case. The feature was not implemented in the Train cycle. It will
          be revisted in the future if needed.

**Use case:** I want to limit allocation candidates to trees `whose root
provider`_ is (or is not) a member of a certain aggregate. For example, I want
to limit candidates to only hosts in (or not in) a specific availability zone.

.. note:: We "need" this because of the restriction_ that resourceless request
          groups must be used with `same_subtree`_. Without that restriction, a
          resourceless ``member_of`` would match a provider anywhere in the
          tree, including the root.

``root_member_of`` is conceptually identical to `root_required`_, but for
aggregates. Like ``member_of[$S]``, ``root_member_of`` supports ``in:``, and
can be repeated (in contrast to ``[root_]required[$S]``).

Default group_policy to none
----------------------------
A single ``isolate`` setting that applies to the whole request has consistently
been shown to be inadequate/confusing/frustrating for all but the simplest
anti-affinity use cases. We're not going to get rid of ``group_policy``, but
we're going to make it no longer required, defaulting to ``none``. This will
allow us to get rid of `at least one hack`_ in nova and provide a clearer user
experience, while still allowing us to satisfy simple NUMA use cases. In the
future a `granular isolation`_ syntax should make it possible to satisfy more
complex scenarios.

.. _at least one hack: https://review.opendev.org/657796

.. _granular isolation:

(Future) Granular Isolation
---------------------------
.. note:: This is currently out of scope, but we wanted to get it written down.

The features elsewhere in this spec allow us to specify affinity pretty richly.
But anti-affinity (within a provider tree - not between providers) is still all
(``group_policy=isolate``) or nothing (``group_policy=none``). We would like to
be able to express anti-affinity between/among subsets of the suffixed groups
in the request.

We propose a new `request-wide`_ query parameter key ``isolate``. The value is
a comma-separated list of request group suffix strings ``$S``. Each must
exactly match a suffix on a granular group somewhere else in the request. This
works on `resourceless request groups`_ as well as those with resources. It is
mutually exclusive with the ``group_policy`` query parameter: 400 if both are
specified.

The effect is the resource providers satisfying each group ``$S`` must satisfy
*only* their respective group ``$S``.

At one point I thought it made sense for ``isolate`` to be repeatable. But now
I can't convince myself that ``isolate={set1}&isolate={set2}`` can ever produce
an effect different from ``isolate={set1|set2}``. Perhaps it's because
different ``isolate``\ s could be coming from different parts of the calling
code?

Another alternative would be to isolate the groups from *each other* but not
from *other groups*, in which case repeating ``isolate`` could be meaningful.
But confusing. Thought will be needed.


Interactions
------------
Some discussion on these can be found in the neighborhood of
http://eavesdrop.openstack.org/irclogs/%23openstack-placement/%23openstack-placement.2019-05-10.log.html#t2019-05-10T22:02:43

group_policy + same_subtree
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``group_policy=isolate`` forces the request groups identified in
``same_subtree`` to be satisfied by different providers, whereas
``group_policy=none`` would also allow ``same_subtree`` to degenerate to
"same provider".

For example, given the following model::

              +--------------+
              | compute node |
              +-------+------+
                      |
          +-----------+-----------+
          |                       |
    +-----+-----+           +-----+-----+
    |nic1       |           |nic2       |
    |HW_NIC_ROOT|           |HW_NIC_ROOT|
    +-----+-----+           +-----+-----+
          |                       |
     +----+----+                 ...
     |         |
  +--+--+   +--+--+
  |pf1_1|   |pf1_2|
  |VF:4 |   |VF:4 |
  +-----+   +-----+

a request for "Two VFs from different PFs on the same NIC"::

 ?resources_VIF1=VF:1
 &resources_VIF2=VF:1
 &required_NIC_AFFINITY=HW_NIC_ROOT
 &same_subtree=_VIF1,_VIF2,_NIC_AFFINITY
 &group_policy=isolate

will return only one candidate::

 - pf1_1: {VF:1}, pf1_2: {VF:1}

whereas the same request with ``group_policy=none``, meaning "Two VFs
from the same NIC"::

 ?resources_VIF1=VF:1
 &resources_VIF2=VF:1
 &required_NIC_AFFINITY=HW_NIC_ROOT
 &same_subtree=_VIF1,_VIF2,_NIC_AFFINITY
 &group_policy=none

will return two additional candidates where both ``VF``\ s are satisfied by
the same provider::

 - pf1_1: {VF:1}, pf1_2: {VF:1}
 - pf1_1: {VF:2}
 - pf1_2: {VF:2}

group_policy + resourceless request groups
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Resourceless request groups are treated the same as any other for the
purposes of ``group_policy``:

* If your resourceless request group is suffixed,
  ``group_policy=isolate`` means the provider satisfying the resourceless
  request group will not be able to satisfy any other suffixed group.
* If your resourceless request group is unsuffixed, it can be satisfied by
  *any* provider in the tree, since the unsuffixed group isn't isolated (even
  with ``group_policy=isolate``). This is important because there are_ cases_
  where we want to require certain traits (usually `provider traits`_), and
  don't want to figure out which other request group might be requesting
  resources from the same provider.

same_subtree + resourceless request groups
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
These *must* be used together -- see `Why enforce resourceless +
same_subtree?`_

Impacts
=======

Data model impact
-----------------
There should be no changes to database table definitions, but the
implementation will almost certainly involve adding/changing database queries.

There will also likely be changes to python-side objects representing
meta-objects used to manage information between the database and the REST
layer. However, the data models for the JSON payloads in the REST layer itself
will be unaffected.

Performance Impact
------------------
The work for ``same_subtree`` will probably (at least initially) be done on the
python side as additional filtering under ``_merge_candidates``. This could
have some performance impact especially on large data sets. Again, we should
optimize requests without ``same_subtree``, where ``same_subtree`` refers to
only one group, where no nested providers exist in the database, etc.

Resourceless request groups may add a small additional burden to
database queries, but it should be negligible. It should be relatively
rare in the wild for a resourceless request group to be satisfied by a
provider that actually provides no resource to the request, though there
are_ cases_ where a resourceless request group would be useful even
though the provider *does* provide resources to the request.

.. _are: https://review.opendev.org/#/c/645316/
.. _cases: https://review.opendev.org/#/c/656885/

Documentation Impact
--------------------
The new query parameters will be documented in the API reference.

Microversion paperwork will be done.

:doc:`/user/provider-tree` will be updated (and/or split off of).

Security impact
---------------
None

Other end user impact
---------------------
None

Other deployer impact
---------------------
None

Developer impact
----------------
None

Upgrade impact
--------------
None

Implementation
==============

Assignee(s)
-----------
* cdent
* tetsuro
* efried
* others

Dependencies
============
None

Testing
=======
Code for a gabbi fixture with some complex and interesting characteristics is
merged here: https://review.opendev.org/#/c/657463/

Lots of functional testing, primarily via gabbi, will be included.

It wouldn't be insane to write some PoC consuming code on the nova side to
validate assumptions and use cases.

References
==========
...are inline

History
=======

.. list-table:: Revisions
   :header-rows: 1

   * - Release Name
     - Description
   * - Train
     - Introduced

.. _can_split: https://review.opendev.org/658510
