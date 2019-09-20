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

=================
 Placement Usage
=================

Tracking Resources
==================

The placement service enables other projects to track their own resources.
Those projects can register/delete their own resources to/from placement
via the placement `HTTP API`_.

The placement service originated in the :nova-doc:`Nova project </>`. As a
result much of the functionality in placement was driven by nova's
requirements. However, that functionality was designed to be sufficiently
generic to be used by any service that needs to manage the selection and
consumption of resources.

How Nova Uses Placement
-----------------------

Two processes, ``nova-compute`` and ``nova-scheduler``, host most of nova's
interaction with placement.

The nova resource tracker in ``nova-compute`` is responsible for `creating the
resource provider`_ record corresponding to the compute host on which the
resource tracker runs, `setting the inventory`_ that describes the quantitative
resources that are available for workloads to consume (e.g., ``VCPU``), and
`setting the traits`_ that describe qualitative aspects of the resources (e.g.,
``STORAGE_DISK_SSD``).

If other projects -- for example, Neutron or Cyborg -- wish to manage resources
on a compute host, they should create resource providers as children of the
compute host provider and register their own managed resources as inventory on
those child providers. For more information, see the
:doc:`Modeling with Provider Trees <provider-tree>`.

The ``nova-scheduler`` is responsible for selecting a set of suitable
destination hosts for a workload. It begins by formulating a request to
placement for a list of `allocation candidates`_. That request expresses
quantitative and qualitative requirements, membership in aggregates, and in
more complex cases, the topology of related resources. That list is reduced and
ordered by filters and weighers within the scheduler process. An `allocation`_
is made against a resource provider representing a destination, consuming a
portion of the inventory set by the resource tracker.

.. toctree::
   :hidden:

   provider-tree

.. _HTTP API: https://docs.openstack.org/api-ref/placement/
.. _creating the resource provider: https://docs.openstack.org/api-ref/placement/?expanded=create-resource-provider-detail#create-resource-provider
.. _setting the inventory: https://docs.openstack.org/api-ref/placement/?expanded=update-resource-provider-inventories-detail#update-resource-provider-inventories
.. _setting the traits: https://docs.openstack.org/api-ref/placement/?expanded=update-resource-provider-traits-detail#update-resource-provider-traits
.. _allocation candidates: https://docs.openstack.org/api-ref/placement/?expanded=list-allocation-candidates-detail#list-allocation-candidates
.. _allocation: https://docs.openstack.org/api-ref/placement/?expanded=update-allocations-detail#update-allocations


REST API
========

The placement API service provides a well-documented, JSON-based `HTTP API`_
and data model. It is designed to be easy to use from whatever HTTP client is
suitable. There is a plugin to the openstackclient_ command line tool called
osc-placement_ which is useful for occasional inspection and manipulation of
the resources in the placement service.

.. _HTTP API: https://docs.openstack.org/api-ref/placement/
.. _openstackclient: https://pypi.org/project/openstackclient/
.. _osc-placement: https://pypi.org/project/osc-placement/

Microversions
-------------

The placement API uses microversions for making incremental changes to the
API which client requests must opt into.

It is especially important to keep in mind that nova-compute is a client of
the placement REST API and based on how Nova supports rolling upgrades the
nova-compute service could be Newton level code making requests to an Ocata
placement API, and vice-versa, an Ocata compute service in a cells v2 cell
could be making requests to a Newton placement API.

This history of placement microversions may be found in the following
subsection.

.. toctree::
   :maxdepth: 2

   ../placement-api-microversion-history
