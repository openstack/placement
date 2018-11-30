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

===============
 Placement API
===============

Overview
========

The placement API service was introduced in the 14.0.0 Newton release within
the nova repository and extracted to the placement repository in the 19.0.0
Stein release. This is a REST API stack and data model used to track resource
provider inventories and usages, along with different classes of resources.
For example, a resource provider can be a compute node, a shared storage pool,
or an IP allocation pool. The placement service tracks the inventory and usage
of each provider. For example, an instance created on a compute node may be a
consumer of resources such as RAM and CPU from a compute node resource
provider, disk from an external shared storage pool resource provider and IP
addresses from an external IP pool resource provider.

The types of resources consumed are tracked as **classes**. The service
provides a set of standard resource classes (for example ``DISK_GB``,
``MEMORY_MB``, and ``VCPU``) and provides the ability to define custom
resource classes as needed.

Each resource provider may also have a set of traits which describe qualitative
aspects of the resource provider. Traits describe an aspect of a resource
provider that cannot itself be consumed but a workload may wish to specify. For
example, available disk may be solid state drives (SSD).

References
~~~~~~~~~~

For an overview of some of the features provided by placement, see
:doc:`Placement Usage <usage/index>`.

For a command line reference, see :doc:`cli/index`.

See the :doc:`Configuration Guide <configuration/index>` for information on
configuring the system, including role-based access control policy rules.

See the :doc:`Contributor Guide <contributor/index>` for information on how to
contribute to the placement project and development processes and guidelines.

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

Deployment
==========

.. note:: Before the Stein release the placement code was in Nova alongside
          the compute REST API code (nova-api). Make sure that the release
          version of this document matches the release version you want to
          deploy.

Steps
~~~~~

**1. Deploy the API service**

Placement provides a ``placement-api`` WSGI script for running the service with
Apache, nginx or other WSGI-capable web servers. Depending on what packaging
solution is used to deploy OpenStack, the WSGI script may be in ``/usr/bin``
or ``/usr/local/bin``.

``placement-api``, as a standard WSGI script, provides a module level
``application`` attribute that most WSGI servers expect to find. This means it
is possible to run it with lots of different servers, providing flexibility in
the face of different deployment scenarios. Common scenarios include:

* apache2_ with mod_wsgi_
* apache2 with mod_proxy_uwsgi_
* nginx_ with uwsgi_
* nginx with gunicorn_

In all of these scenarios the host, port and mounting path (or prefix) of the
application is controlled in the web server's configuration, not in the
configuration (``placement.conf``) of the placement application.

When placement was `first added to DevStack`_ it used the ``mod_wsgi`` style.
Later it `was updated`_ to use mod_proxy_uwsgi_. Looking at those changes can
be useful for understanding the relevant options.

DevStack is configured to host placement at ``/placement`` on either the
default port for http or for https (``80`` or ``443``) depending on whether TLS
is being used. Using a default port is desirable.

By default, the placement application will get its configuration for settings
such as the database connection URL from ``/etc/placement/placement.conf``.
The directory the configuration file will be found in can be changed by setting
``OS_PLACEMENT_CONFIG_DIR`` in the environment of the process that starts the
application. With recent releases of ``oslo.config``, configuration options may
also be set in the environment_.

.. note:: When using uwsgi with a front end (e.g., apache2 or nginx) something
    needs to ensure that the uwsgi process is running. In DevStack this is done
    with systemd_. This is one of many different ways to manage uwsgi.

This document refrains from declaring a set of installation instructions for
the placement service. This is because a major point of having a WSGI
application is to make the deployment as flexible as possible. Because the
placement API service is itself stateless (all state is in the database), it is
possible to deploy as many servers as desired behind a load balancing solution
for robust and simple scaling. If you familiarize yourself with installing
generic WSGI applications (using the links in the common scenarios list,
above), those techniques will be applicable here.

.. _apache2: http://httpd.apache.org/
.. _mod_wsgi: https://modwsgi.readthedocs.io/
.. _mod_proxy_uwsgi: http://uwsgi-docs.readthedocs.io/en/latest/Apache.html
.. _nginx: http://nginx.org/
.. _uwsgi: http://uwsgi-docs.readthedocs.io/en/latest/Nginx.html
.. _gunicorn: http://gunicorn.org/
.. _first added to DevStack: https://review.openstack.org/#/c/342362/
.. _was updated: https://review.openstack.org/#/c/456717/
.. _systemd: https://review.openstack.org/#/c/448323/
.. _environment: https://docs.openstack.org/oslo.config/latest/reference/drivers.html#environment

**2. Synchronize the database**

The placement service uses its own database, defined in the
``[placement_database]`` section of configuration. The ``connection`` option
**must** be set or the service will not start. The command line tool
:doc:`cli/placement-manage` can be used to migrate the database tables to their
correct form, including creating them. The database described by the
``connection`` option must already exist.

In the Stein release, the placement code was extracted from nova. We have
scripts which can assist with migrating placement data from the nova-api
database to the placement database. You can find them in the `placement
repository`_, ``/tools/mysql-migrate-db.sh`` and
``/tools/postgresql-migrate-db.sh``.

**3. Create accounts and update the service catalog**

Create a **placement** service user with an **admin** role in Keystone.

The placement API is a separate service and thus should be registered under
a **placement** service type in the service catalog. Clients of placement, such
as the resource tracker in the nova-compute node, will use the service catalog
to find the placement endpoint.

Devstack sets up the placement service on the default HTTP port (80) with a
``/placement`` prefix instead of using an independent port.

.. _placement-upgrade-notes:

Upgrade Notes
=============

The following sub-sections provide notes on upgrading to a given target release.

.. note::

   As a reminder, the
   :ref:`placement-status upgrade check <placement-status-checks>` tool can be
   used to help determine the status of your deployment and how ready it is to
   perform an upgrade.

For releases prior to Stein, please see the `nova upgrade notes`_.

.. _nova upgrade notes: https://docs.openstack.org/nova/rocky/user/placement.html#upgrade-notes


Stein (19.0.0)
~~~~~~~~~~~~~~

* The placement code is now available from its own `placement repository`_.
* The placement server side settings in ``nova.conf`` should be moved to a
  separate placement configuration file ``placement.conf``.
* The default configuration value of ``[placement]/policy_file`` is changed
  from ``placement-policy.yaml`` to ``policy.yaml``
* Configuration and policy files are, by default, located in
  ``/etc/placement``.

.. _placement repository: https://git.openstack.org/cgit/openstack/placement


REST API
========

The placement API service provides a `REST API`_ and data model.  One
can get a sample of the REST API via the functional test `gabbits`_.

.. _`REST API`: https://developer.openstack.org/api-ref/placement/
.. _gabbits: http://git.openstack.org/cgit/openstack/nova/tree/nova/tests/functional/api/openstack/placement/gabbits

Microversions
~~~~~~~~~~~~~

The placement API uses microversions for making incremental changes to the
API which client requests must opt into.

It is especially important to keep in mind that nova-compute is a client of
the placement REST API and based on how Nova supports rolling upgrades the
nova-compute service could be Newton level code making requests to an Ocata
placement API, and vice-versa, an Ocata compute service in a cells v2 cell
could be making requests to a Newton placement API.

This history of placement microversions may be found in
:doc:`placement-api-microversion-history`.


.. # NOTE(mriedem): This is the section where we hide things that we don't
   # actually want in the table of contents but sphinx build would fail if
   # they aren't in the toctree somewhere. For example, we hide api/autoindex
   # since that's already covered with modindex below.
.. toctree::
   :hidden:

   cli/index
   configuration/index
   contributor/index
   contributor/api-ref-guideline
   contributor/goals
   contributor/quick-dev
   install/controller-install-obs
   install/controller-install-rdo
   install/controller-install-ubuntu
   placement-api-microversion-history
   usage/index
