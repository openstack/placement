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
