..
 This work is licensed under a Creative Commons Attribution 3.0 Unported
 License.

 http://creativecommons.org/licenses/by/3.0/legalcode

===========================
Policy Defaults Improvement
===========================

https://blueprints.launchpad.net/placement/+spec/policy-defaults-improvement

This spec is to improve the placement APIs policy as the directions
decided in `RBAC community-wide goal
<https://governance.openstack.org/tc/goals/selected/consistent-and-secure-rbac.html>`_

Problem description
===================

While discussing the new RBAC (scope_type and project admin vs
system admin things) with operators in berlin ops meetup and
via emails, and policy popup meetings, we got the feedback that
we need to keep the legacy admin behaviour same as it is otherwise
it is going to be a big breaking change for many of the operators.
Same feedback for scope_type.

- https://etherpad.opendev.org/p/BER-2022-OPS-SRBAC
- https://etherpad.opendev.org/p/rbac-operator-feedback

By considering the feedback, we decided to make all the policy
to be project scoped, release project reader role, and not to
change the legacy admin behaviour.

Use Cases
---------

Ideally most operators should be able to run without modifying policy, as
such we need to have defaults closure to the usage.

Proposed change
===============

The `RBAC community-wide goal
<https://governance.openstack.org/tc/goals/selected/consistent-and-secure-rbac.html>`_
defines all the direction and implementation usage of policy. This proposal
is to implement the phase 1 and phase 2 of the `RBAC community-wide goal
<https://governance.openstack.org/tc/goals/selected/consistent-and-secure-rbac.html>`_

Alternatives
------------

Keep the policy defaults same as it is and expect operators to override
them to behave as per their usage.

Data model impact
-----------------

None

REST API impact
---------------

The placement APIs policy will modified to add reader roles, scoped to
projects, and keep legacy behaviour same as it is. Most of the policies
will be default to 'admin-or-service' role but we will review every
policy rule default while doing the code change.

Security impact
---------------

Easier to understand policy defaults will help keep the system secure.

Notifications impact
--------------------

None

Other end user impact
---------------------

None

Performance Impact
------------------

None

Other deployer impact
---------------------

None

Developer impact
----------------

New APIs must add policies that follow the new pattern.

Upgrade impact
--------------

The scope_type of all the policy rules will be ``project`` if any
deployement is running with enforce_scope enabled and with system
scope token then they need to use the project scope token.

Also, if any API policy defaults have been modified to ``service``
role only (most of the policies will be default to admin-or-service)
then the deployment using such APIs need to override them in policy.yaml
to continue working for them.

Implementation
==============

Assignee(s)
-----------

Primary assignee:
  gmann

Feature Liaison
---------------

Feature liaison:
  dansmith

Work Items
----------

* Scope all policy to project
* Add project reader role in policy
* Modify policy rule unit tests

Dependencies
============

None

Testing
=======

Modify or add the policy unit tests.

Documentation Impact
====================

API Reference should be kept consistent with any policy changes, in particular
around the default reader role.

References
==========

History
=======

.. list-table:: Revisions
   :header-rows: 1

   * - Release Name
     - Description
   * - 2023.1
     - Introduced
