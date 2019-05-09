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
placement-status
================

Synopsis
========

::

  placement-status <category> <command> [<args>]

Description
===========

:program:`placement-status` is a tool that provides routines for checking the
status of a Placement deployment.

Options
=======

The standard pattern for executing a :program:`placement-status` command is::

    placement-status <category> <command> [<args>]

Run without arguments to see a list of available command categories::

    placement-status

Categories are:

* ``upgrade``

Detailed descriptions are below.

You can also run with a category argument such as ``upgrade`` to see a list of
all commands in that category::

    placement-status upgrade

These sections describe the available categories and arguments for
:program:`placement-status`.

Upgrade
~~~~~~~

.. _placement-status-checks:

``placement-status upgrade check``
  Performs a release-specific readiness check before restarting services with
  new code. This command expects to have complete configuration and access
  to databases and services.

  **Return Codes**

  .. list-table::
     :widths: 20 80
     :header-rows: 1

     * - Return code
       - Description
     * - 0
       - All upgrade readiness checks passed successfully and there is nothing
         to do.
     * - 1
       - At least one check encountered an issue and requires further
         investigation. This is considered a warning but the upgrade may be OK.
     * - 2
       - There was an upgrade status check failure that needs to be
         investigated. This should be considered something that stops an
         upgrade.
     * - 255
       - An unexpected error occurred.

  **History of Checks**

  **1.0.0 (Stein)**

  * Checks were added for incomplete consumers and missing root provider ids
    both of which can be remedied by running the
    ``placement-manage db online_data_migrations`` command.

  **2.0.0 (Train)**

  * The ``Missing Root Provider IDs`` upgrade check will now result in a
    failure if there are still ``resource_providers`` records with a null
    ``root_provider_id`` value.
