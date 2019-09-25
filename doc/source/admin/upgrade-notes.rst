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


Stein (1.0.0)
~~~~~~~~~~~~~~

If you are upgrading an existing OpenStack installation from Rocky to Stein,
and wish to use the newly extracted placement, you will need to copy some
data and configuration settings from nova.

* Configuration and policy files are, by default, located in
  ``/etc/placement``.
* The placement server side settings in ``nova.conf`` should be moved to a
  separate placement configuration file ``placement.conf``.
* The default configuration value of ``[placement]/policy_file`` is changed
  from ``placement-policy.yaml`` to ``policy.yaml``
* Several tables in the ``nova_api`` database need to be migrated to a new
  ``placement`` database.

Following these steps will ensure that future changes to placement
configuration and code will not conflict with your setup.

As stated above, using the extracted placement code is not required in Stein,
there is a copy in the Stein release of Nova. However that code will be deleted
in the Train cycle so you must upgrade to external Placement prior to
upgrading to Train.
