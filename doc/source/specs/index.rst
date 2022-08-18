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

=========================
 Placement Specifications
=========================

Significant feature developments are tracked in documents called specifications.
From the Train cycle onward, those documents are kept in this section.
Prior to that, Placement specifications were a part of the `Nova Specs`_.

The following specifications represent the stages of design and development of
resource providers and the Placement service. Implementation details may have
changed or be partially complete at this time.

* `Generic Resource Pools <https://specs.openstack.org/openstack/nova-specs/specs/newton/implemented/generic-resource-pools.html>`_
* `Compute Node Inventory <https://specs.openstack.org/openstack/nova-specs/specs/newton/implemented/compute-node-inventory-newton.html>`_
* `Resource Provider Allocations <https://specs.openstack.org/openstack/nova-specs/specs/newton/implemented/resource-providers-allocations.html>`_
* `Resource Provider Base Models <https://specs.openstack.org/openstack/nova-specs/specs/newton/implemented/resource-providers.html>`_
* `Nested Resource Providers`_
* `Custom Resource Classes <http://specs.openstack.org/openstack/nova-specs/specs/ocata/implemented/custom-resource-classes.html>`_
* `Scheduler Filters in DB <http://specs.openstack.org/openstack/nova-specs/specs/ocata/implemented/resource-providers-scheduler-db-filters.html>`_
* `Scheduler claiming resources to the Placement API <http://specs.openstack.org/openstack/nova-specs/specs/pike/approved/placement-claims.html>`_
* `The Traits API - Manage Traits with ResourceProvider <http://specs.openstack.org/openstack/nova-specs/specs/pike/approved/resource-provider-traits.html>`_
* `Request Traits During Scheduling`_
* `filter allocation candidates by aggregate membership`_
* `perform granular allocation candidate requests`_
* `inventory and allocation data migration`_ (reshaping provider trees)
* `handle allocation updates in a safe way`_

.. _Nested Resource Providers: http://specs.openstack.org/openstack/nova-specs/specs/queens/approved/nested-resource-providers.html
.. _Request Traits During Scheduling: https://specs.openstack.org/openstack/nova-specs/specs/queens/approved/request-traits-in-nova.html
.. _filter allocation candidates by aggregate membership: https://specs.openstack.org/openstack/nova-specs/specs/rocky/approved/alloc-candidates-member-of.html
.. _perform granular allocation candidate requests: http://specs.openstack.org/openstack/nova-specs/specs/rocky/approved/granular-resource-requests.html
.. _inventory and allocation data migration: http://specs.openstack.org/openstack/nova-specs/specs/rocky/approved/reshape-provider-tree.html
.. _handle allocation updates in a safe way: https://specs.openstack.org/openstack/nova-specs/specs/rocky/approved/add-consumer-generation.html
.. _Nova Specs: http://specs.openstack.org/openstack/nova-specs

Train
-----

Implemented
~~~~~~~~~~~

.. toctree::
   :maxdepth: 1
   :glob:

   train/implemented/*

In Progress
~~~~~~~~~~~

.. toctree::
   :maxdepth: 1
   :glob:

   train/approved/*


Xena
----

Implemented
~~~~~~~~~~~

.. toctree::
   :maxdepth: 1
   :glob:

   xena/implemented/*

In Progress
~~~~~~~~~~~


Yoga
----

Implemented
~~~~~~~~~~~

.. toctree::
   :maxdepth: 1
   :glob:

   yoga/implemented/*

In Progress
~~~~~~~~~~~


Zed
---

Implemented
~~~~~~~~~~~


In Progress
~~~~~~~~~~~

.. toctree::
   :maxdepth: 1
   :glob:

   zed/approved/*

2023.1
------

Implemented
~~~~~~~~~~~


In Progress
~~~~~~~~~~~

.. toctree::
   :maxdepth: 1
   :glob:

   2023.1/approved/*

.. toctree::
   :hidden:

   template.rst

