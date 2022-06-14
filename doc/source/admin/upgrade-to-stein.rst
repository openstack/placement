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

================================
Upgrading from Nova to Placement
================================

This document is for people who are upgrading from an existing Rocky-based
installation of OpenStack, where Placement is a part of Nova, to a Stein-based
system, using the independently packaged placement service. It is also for
people who have already upgraded to Stein but are using the version of the
placement service included in Nova in the Stein release.

Upgrading to the extracted placement is not a requirement when upgrading the
rest of OpenStack to Stein. The version of the placement service in the
Nova Stein release may be used. It is possible to upgrade to Stein and then
deploy and switch to the extracted placement at a later time.

The placement code in Nova will be removed in Train so the switch to using
extracted placement must happen before upgrading to Train.

.. note:: The extracted placement code has features and performance and bug
          fixes that are not present in the placement code in Nova, but no code
          that is required by Nova. See the `release notes`_ for more detail.

If you are installing a new OpenStack, you will want the
:doc:`installation docs </install/index>`.

Upgrading to use the extracted placement service requires migrating several
database tables from the ``nova_api`` database to a placement database.
Depending on the number of compute hosts in your system and the number of
active virtual machines, the amount of data to copy can vary widely. You can
get an idea by counting rows in the ``resource_providers`` and ``consumers``
tables.

To avoid losing data while performing the copy it is important that writing to
the placement database (on either side of the upgrade) is stopped. You may shut
down solely the placement service but this will result in errors attempting to
use the service from Nova. It is potentially less disruptive to shut down the
entire control plane to avoid confusing errors. What strategy is best will
vary. This document describes the simple way.

.. note:: In some installations of nova and placement, data may already be in
          a database named ``placement`` and not ``nova_api``. If that is the
          case, you will not need to copy data. Make sure that there are tables
          and rows in that database and that it is of expected quantity and
          recently modified (many tables have ``created_at`` and ``updated_at``
          columns). In some cases the ``placement`` database will be present
          *but empty*.

There are database migrations scripts in the placement code repository which
may be used to copy the data or as models for your own tooling:
`mysql-migrate-db.sh`_ and `postgresql-migrate-db.sh`_.

.. note:: Starting in the Train release, these migration scripts are also
          packaged with the `openstack-placement`_ package on PyPI. Their
          filenames may be discovered using ``pkg_resources`` to look in the
          ``placement_db_tools`` package::

              pkg_resources.resource_filename('placement_db_tools', 'mysql-migrate-db.sh')

For best results run the database migration on your database host. If you are
unable to do this, you will need to take some additional steps below.

This document assumes that the same HTTP endpoint will be used before and after
the upgrade. If you need to change that see :ref:`configure-endpoints-pypi` for
guidance.

Initial Steps
-------------

#. Install the new placement code on a controller node. This can be
   `openstack-placement`_ from PyPI or you can use packages from a Linux
   distribution. If you are using the latter be aware that:

   * The name of the package can be found in the :doc:`installation docs
     </install/index>`.

   * You need to install the packages on a different host from the old nova,
     to avoid accidentally upgrading before you are ready.

#. Create a ``placement`` database with appropriate access controls. If you
   need details on how to do this, see :ref:`create-database-pypi`.

#. Create and configure the ``placement.conf`` file.

   * The default location is ``/etc/placement``.

   * Set :oslo.config:option:`placement_database.connection` to point to the
     new database. For example (replacing ``PLACEMENT_DBPASS`` and
     ``controller`` with the appropriate password and host):

     .. path /etc/placement/placement.conf
     .. code-block:: ini

        [placement_database]
        connection = mysql+pymysql://placement:PLACEMENT_DBPASS@controller/placement

   * Configure the :oslo.config:group:`keystone_authtoken` section as described
     in :ref:`configure-conf-pypi`.

   * If the following configuration settings are set in the ``[placement]``
     section of ``/etc/nova/nova.conf``, move them to a ``[placement]``
     section in ``/etc/placement/placement.conf``:

     * :oslo.config:option:`placement.randomize_allocation_candidates`
     * :oslo.config:option:`placement.incomplete_consumer_project_id`
     * :oslo.config:option:`placement.incomplete_consumer_user_id`

#. Move ``placement-policy.yaml``, if required.

   * If it exists, move ``/etc/nova/placement-policy.yaml`` to
     ``/etc/placement/policy.yaml``. If you wish to use a different filename
     adjust config option ``[placement] policy_file``.

#. Configure the database migration tool.

   * Create the configuration file.

     .. note:: The examples in this guide are using MySQL but if you are using
               PostgreSQL it is recommended to use the
               `postgresql-migrate-db.sh`_ script since it handles sequences.
               See `bug 2005478`_ for details.

     .. code-block:: console

        $ mysql-migrate-db.sh --mkconfig /tmp/migrate-db.rc

   * Edit the file to set the values for the ``NOVA_API_USER``,
     ``NOVA_API_PASS``, ``PLACEMENT_USER``, and ``PLACEMENT_PASS`` entries.
     These are the usernames and passwords for accessing the database.

   * If you are unable to run the migration script on the database host you
     will need to set ``NOVA_API_DB_HOST`` and ``PLACEMENT_DB_HOST``.

   * Do not change ``MIGRATE_TABLES`` unless you need to migrate tables
     incrementally.

#. Configure the web server that will host the placement service. The details
   of this are beyond the scope of this document. :doc:`/install/from-pypi`
   may provide some guidance. **Make sure you also disable the previously
   running placement service in the web server configuration.**

Migrate the Data
----------------

#. Shut down or disable your control plane in whatever way works best for you.

#. Run the migration script:

   .. code-block:: console

      $ mysql-migrate-db.sh --migrate /tmp/migrate-db.rc

   The ``--skip-locks`` flag can be used along with ``--migrate`` in
   deployments where table locking operations can't be performed. For example,
   Percona XtraDB Cluster only has experimental support for explicit table
   locking operations and attempts to use locking will result in errors when
   PXC Strict Mode is set to ENFORCING.

   If your controller host (the one where you have been editing
   ``/etc/placement/placement.conf``) and database host are not the same, and
   you have run the migration script on the database host, the final step in
   the process will fail. This step stamps the database with an initial version
   (the hash of the first alembic_ migration) so that future migrations will
   work properly. From the controller host, you may do it manually with:

   .. code-block:: console

      $ placement-manage db stamp b4ed3a175331

#. Sync the placement database to be up to date with all migrations:

   .. code-block:: console

      $ placement-manage db sync

.. note::

   As described in `bug 1978549`_ the ``can_host`` column of the
   ``resource_providers`` table was removed from the DB model but not from the
   DB schema while Placement was still part of Nova. Then when Placement was
   split out its DB schema was altered to not contain ``can_host`` any
   more. This can create a situation when the actual DB schema and the schema
   defined by the alembic code is different. As ``can_host`` is not used any
   more it is safe to manually remove it from the DB to remove the schema
   inconsistency.

Finalize the Upgrade
--------------------

#. Start up the new placement service.

#. Restart your control plane services. If you are upgrading to Stein, continue
   with the upgrade of the rest of the system.

#. Verify the content of the new service by using the osc-placement_ tool to
   list resource providers, allocations and other resources in the service.

#. Verify the integration of placement with the rest of your OpenStack
   installation by creating and deleting a test server.

#. At some point in the future you may remove the tables in the ``nova_api``
   database that were migrated to the ``placement`` database.

.. _openstack-placement: https://pypi.org/p/openstack-placement
.. _mysql-migrate-db.sh: https://opendev.org/openstack/placement/raw/branch/master/placement_db_tools/mysql-migrate-db.sh
.. _postgresql-migrate-db.sh: https://opendev.org/openstack/placement/raw/branch/master/placement_db_tools/postgresql-migrate-db.sh
.. _alembic: https://alembic.sqlalchemy.org/en/latest/
.. _release notes: https://docs.openstack.org/releasenotes/placement/stein.html
.. _osc-placement: https://docs.openstack.org/osc-placement/latest/
.. _bug 2005478: https://storyboard.openstack.org/#!/story/2005478
.. _bug 1978549: https://bugs.launchpad.net/nova/+bug/1978549