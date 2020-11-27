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

=============
Upgrade Notes
=============

This section provide notes on upgrading to a given target release.

.. note::

   As a reminder, the
   :ref:`placement-status upgrade check <placement-status-checks>` tool can be
   used to help determine the status of your deployment and how ready it is to
   perform an upgrade.

For releases prior to Stein, please see the `nova upgrade notes`_.

.. _nova upgrade notes: https://docs.openstack.org/nova/rocky/user/placement.html#upgrade-notes

Train (2.0.0)
~~~~~~~~~~~~~

The Train release of placement is the first release where placement is
available solely from its own project and must be installed separately from
nova. If the extracted placement is not already in use, prior to upgrading to
Train, the Stein version of placement must be installed. See the next section
and :doc:`upgrade-to-stein` for details.

There are no database schema changes in the Train release, but there are
checks to confirm that online migrations from Stein have been run. Running
:doc:`/cli/placement-status` *after upgrading code but prior to restarting the
placement service* will notify you of any missing steps and the process to fix
it. Once this is done, :doc:`/cli/placement-manage` should be run to sync the
database::

    $ placement-status upgrade check
    +----------------------------------+
    | Upgrade Check Results            |
    +----------------------------------+
    | Check: Missing Root Provider IDs |
    | Result: Success                  |
    | Details: None                    |
    +----------------------------------+
    | Check: Incomplete Consumers      |
    | Result: Success                  |
    | Details: None                    |
    +----------------------------------+
    $ placement-manage db sync

Then the placement service may be restarted.

Stein (1.0.0)
~~~~~~~~~~~~~

If you are upgrading an existing OpenStack installation from Rocky to Stein,
and wish to use the newly extracted placement, you will need to copy some
data and configuration settings from nova.

* Configuration and policy files are, by default, located in
  ``/etc/placement``.
* The placement server side settings in ``nova.conf`` should be moved to a
  separate placement configuration file ``placement.conf``.
* The default configuration value of ``[placement]/policy_file`` is changed
  from ``placement-policy.yaml`` to ``policy.yaml``. This config option is
  changed to :oslo.config:option:`oslo_policy.policy_file` since Train
  release.
* Several tables in the ``nova_api`` database need to be migrated to a new
  ``placement`` database.

Following these steps will ensure that future changes to placement
configuration and code will not conflict with your setup.

As stated above, using the extracted placement code is not required in Stein,
there is a copy in the Stein release of Nova. However that code will be deleted
in the Train cycle so you must upgrade to external Placement prior to
upgrading to Train.
