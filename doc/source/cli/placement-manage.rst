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

================
placement-manage
================


Synopsis
========

::

    placement-manage <category> <action>

Description
===========

:program:`placement-manage` is used to perform administrative tasks with the
placement service. It is designed for use by operators and deployers.

Options
=======

The standard pattern for executing a ``placement-manage`` command is::

  placement-manage  [-h] [--config-dir DIR] [--config-file PATH]
                    <category> <command> [<args>]

Run without arguments to see a list of available command categories::

  placement-manage

You can also run with a category argument such as ``db`` to see a list of all
commands in that category::

  placement-manage db

Configuration options (for example the ``[placement_database]/connection``
URL) are by default found in a file at ``/etc/placement/placement.conf``. The
``config-dir`` and ``config-file`` arguments may be used to select a different
file.

The following sections describe the available categories and arguments for
placement-manage.

Placement Database
~~~~~~~~~~~~~~~~~~

``placement-manage db version``
    Print the current database version.

``placement-manage db sync``
    Upgrade the database schema to the most recent version.  The local database
    connection is determined by ``[placement_database]/connection`` in the
    configuration file used by placement-manage. If the ``connection`` option
    is not set, the command will fail. The defined database must already exist.

``placement-manage db stamp <version>``
    Stamp the revision table with the given revision; don’t run any migrations.
    This can be used when the database already exists and you want to bring it
    under alembic control.

``placement-manage db online_data_migrations [--max-count]``
   Perform data migration to update all live data.

   ``--max-count`` controls the maximum number of objects to migrate in a given
   call. If not specified, migration will occur in batches of 50 until fully
   complete.

   Returns exit code 0 if no (further) updates are possible, 1 if the
   ``--max-count`` option was used and some updates were completed successfully
   (even if others generated errors), 2 if some updates generated errors and no
   other migrations were able to take effect in the last batch attempted, or
   127 if invalid input is provided (e.g. non-numeric max-count).

   This command should be called after upgrading database schema and placement
   services on all controller nodes. If it exits with partial updates (exit
   status 1) it should be called again, even if some updates initially
   generated errors, because some updates may depend on others having
   completed. If it exits with status 2, intervention is required to resolve
   the issue causing remaining updates to fail. It should be considered
   successfully completed only when the exit status is 0.

   For example::

     $ placement-manage db online_data_migrations
     Running batches of 50 until complete
     2 rows matched query create_incomplete_consumers, 2 migrated
     +---------------------------------------------+-------------+-----------+
     |                  Migration                  | Total Found | Completed |
     +---------------------------------------------+-------------+-----------+
     |            set_root_provider_ids            |      0      |     0     |
     |         create_incomplete_consumers         |      2      |     2     |
     +---------------------------------------------+-------------+-----------+

   In the above example, the ``create_incomplete_consumers`` migration
   found two candidate records which required a data migration. Since
   ``--max-count`` defaults to 50 and only two records were migrated with no
   more candidates remaining, the command completed successfully with exit
   code 0.
