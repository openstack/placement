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

============================
So You Want to Contribute...
============================

For general information on contributing to OpenStack, please check out the
`contributor guide <https://docs.openstack.org/contributors/>`_ to get started.
It covers all the basics that are common to all OpenStack projects: the accounts
you need, the basics of interacting with our Gerrit review system, how we
communicate as a community, etc.

Below will cover the more project specific information you need to get started
with placement.

Communication
-------------

As an official OpenStack project, Placement follows the overarching processes
outlined in the `Project Team Guide`_. Contribution is welcomed from any
interested parties and takes many different forms.

To make sure everything gets the attention it deserves and work is not
duplicated there are some guidelines, stated here.

If in doubt, ask someone, either by sending a message to the
`openstack-discuss`_ mailing list with a ``[placement]`` subject tag, or by
visiting the ``#openstack-nova`` IRC channel on ``webchat.oftc.net``.

Submitting and Managing Bugs
----------------------------

Bugs found in  placement should be reported in `Launchpad`_ by creating a new
bug in the ``placement`` project.

.. _new_bug:

New Bugs
~~~~~~~~

If you are submitting a `new bug`_, explain the problem, the steps taken that led
to the bad results, and the expected results. Please also add as much of the
following information as possible:

* Relevant lines from the ``placement-api`` log.
* The OpenStack release (e.g., ``Stein``).
* The method used to install or deploy placement.
* The operating system(s) on which the placement is running.
* The version(s) of Python being used.

Tag the bug with ``tags``, like doc, api, etcetera.
Learn more about launchpad from `openstack launchpad doc`_.

.. _triage:

Triaging Bugs
~~~~~~~~~~~~~

Triaging newly submitted bugs to confirm they really are bugs, gather missing
information, and to suggest possible solutions is one of the most important
contributions that can be made to any open source project.

If a new bug doesn't have tags, add the relevant tag as per the area of
affected code.

Leave comments on the bug if you have questions or ideas. If you are
relatively certain about a solution, add the steps of that solution as tasks
on the bug.

While triaging, only if you are sure, update the status of the bug from new
to others.

If submitting a change related to a bug, the `gerrit`_ system will
automatically link to launchpad bug if you include ``bug_id:`` identifiers in
your commit message, like this::

    Related-Bug: 2005189
    Partial-Bug: 2005190
    Closes-Bug: 2005190

Reviewing Code
--------------

Like other OpenStack projects, Placement uses `gerrit`_ to facilitate peer code
review. It is hoped and expected that anyone who would like to commit code to
the Placement project will also spend time reviewing code for the sake of the
common good. The more people reviewing, the more code that will eventually
merge.

See `How to Review Changes the OpenStack Way`_ for an overview of the review
and voting process.

There is a small group of people within the Placement team called `core
reviewers`_. These are people who are empowered to signal (via the ``+2`` vote)
that code is of a suitable standard to be merged and is aligned with the
current goals of the project. Core reviewers are regularly selected from all
active reviewers based on the quantity and quality of their reviews and
demonstrated understanding of the Placement code and goals of the project.

The point of review is to evolve potentially useful code to merged working code
that is aligned with the standards of style, testing, and correctness that we
share as group. It is not for creating perfect code. Review should always be
`constructive`_, encouraging, and friendly. People who contribute code are
doing the project a favor, make it feel that way.

Some guidelines that reviewers and patch submitters should be aware of:

* It is very important that a new patch set gets some form of review as soon as
  possible, even if only to say "we've seen this". Latency in the review
  process has been identified as hugely discouraging for new and experienced
  contributors alike.
* Follow up changes, to fix minor problems identified during review, are
  encouraged. We want to keep things moving.
* As a reviewer, remember that not all patch submitters will know these
  guidelines. If it seems they don't, point them here and be patient in the
  meantime.
* Gerrit can be good for code review, but is often not a great environment for
  having a discussion that is struggling to resolve to a decision. Move
  discussion to the mailing list sooner rather than later. Add a link to the
  thread in the `list archive`_ to the review.
* If the CI system is throwing up random failures in test runs, you should
  endeavor whenever possible to investigate, not simply ``recheck``. A flakey
  gate is an indication that OpenStack is not robust and at the root of all
  this, making OpenStack work well is what we are doing.

  See here for `How to Recheck`_

Special Considerations For Core Reviewers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Core reviewers have special powers. With great power comes great responsibility
and thus being held to a standard. As a core reviewer, your job is to enable
other people to contribute good code. Under ideal conditions it is more
important to be reviewing other people's code and bugs and fixing bugs than it
is to be writing your own features. Frequently conditions will not be ideal,
but strive to enable others.

When there are open questions that need to be resolved, try to prefer the
`openstack-discuss`_ list over IRC so that anyone can be involved according
to their own schedules and input from unexpected sources can be available.


Writing Code
------------

This document cannot enumerate all the many ways to write good Python code.
Instead it lists some guidelines that, if followed, will help make sure your
code is reviewed promptly and merges quickly. As with everything else in this
document, these guidelines will evolve over time and may be violated for
special circumstances. If you have questions, ask.

See :doc:`/contributor/index` for an overview of Placement and how the various
pieces fit together.

* Divide your change into a series of commits each of which encapsulates a
  single unit of functionality but still results in a working service. Smaller
  changes are easier to review.

* If your change is to the HTTP API, familiarize yourself with
  :ref:`microversion process`.

* If there is a series of changes leading to an HTTP API change, exposing that
  API change should be the last patch in the series. That patch must update the
  API_ reference and include a `release note`_.

* Changes must include tests. There is a separate document on
  :doc:`/contributor/testing`.

* Run ``tox`` before submitting your code to gerrit_. This will run unit and
  functional tests in both Python 2 and Python 3, and pep8 style checks.
  Placement tests, including functional, are fast, so this should not be too
  much of a hardship. By running the tests locally you avoid wasting scarce
  resources in the CI system.

* Keep the tests fast. Avoid sleeps, network connections, and external
  processes in the tests.

* Keep Placement fast. There is a ``placement-perfload`` job that runs with
  every patch. Within that is a log file, ``/logs/placement-perf.txt[.gz]``
  that gives rough timing information for a common operation. We want those
  numbers to stay small.

* We follow the code formatting guidelines of `PEP 8`_. Check your code with
  ``tox -epep8`` (for all files) or ``tox -efast8`` (for just the files you
  changed). You will not always agree with the advice provided. Follow it.

* Where possible avoid using the visual indent style. Using it can make future
  changes unnecessarily difficult. This guideline is not enforced by pep8 and
  has been used throughout the code in the past. There's no need to fix old
  use. Instead of this

  .. code-block:: python

    return_value = self.some_method(arg1, arg2,
                                    arg3, arg4)

  prefer this

  .. code-block:: python

    return_value = self.some_method(
        arg1, arg2, arg3, arg4)

New Features
------------

New functionality in Placement is developed as needed to meet new use cases or
improve the handling of existing use cases. As a service used by other services
in OpenStack, uses cases often originate in those other services. Considerable
collaboration with other projects is often required to determine if any changes
are needed in the Placement API_ or elsewhere in the project. That interaction
should happen in the usual ways: At Project Team Gatherings, on the
openstack-discuss_ list, and in IRC.

Create a new bug as described in :ref:`new_bug` above.

If a spec is required there are some guidelines for creating one:

* A file should be created in the `placement code`_ in
  ``doc/source/specs/<cycle-name>/approved`` with a filename beginning with the
  identifier of the bug. For example::

     docs/source/specs/train/approved/200056-infinite-resource-classes.rst

  More details on how to write a spec are included in a ``template.rst`` file
  found in the ``doc/source/specs`` directory. This may be copied to use as the
  starting point for a new spec.

* Under normal circumstances specs should be proposed near the beginning of a
  release cycle so there is sufficient time to review the spec and its
  implementation as well as to make any necessary decisions about limiting the
  number of specs being worked in the same cycle. Unless otherwise announced at
  the beginning of a cycle, specs should merge before milestone-2 to be
  considered relevant for that cycle. Exceptions will be reviewed on a case by
  case basis. See the `stein schedule`_ for an example schedule.

* Work items that are described in a spec should be reflected as tasks
  created on the originating launchpad bug. Update the bug with additional
  tasks as they are discovered. Most new tasks will not require updating the
  spec.

* If, when developing a feature, the implementation significantly diverges from
  the spec, the spec should be updated to reflect the new reality. This should
  not be considered exceptional: It is normal for there to be learning during
  the development process which impacts the solution.

* Though specs are presented with the Placement documentation and can usefully
  augment end-user documentation, they are not a substitute. Development of a
  new feature is not complete without documentation.

When a spec was approved in a previous release cycle, but was not finished, it
should be re-proposed (via gerrit) to the current cycle. Include
``Previously-Approved: <cycle>`` in the commit message to highlight that fact.
If there have been no changes, core reviewers should feel free to fast-approve
(only one ``+2`` required) the change.

Project Team Lead Duties
------------------------

PTL duties are enumerated in the `PTL guide`_.

.. _Project Team Guide: https://docs.openstack.org/project-team-guide/
.. _openstack-discuss: http://lists.openstack.org/cgi-bin/mailman/listinfo/openstack-discuss
.. _list archive: http://lists.openstack.org/pipermail/openstack-discuss/
.. _Launchpad: https://bugs.launchpad.net/placement
.. _new bug: https://bugs.launchpad.net/placement/+filebug
.. _gerrit: http://review.opendev.org/
.. _How to Review Changes the OpenStack Way: https://docs.openstack.org/project-team-guide/review-the-openstack-way.html
.. _core reviewers: https://review.opendev.org/#/admin/groups/1936,members
.. _constructive: https://governance.openstack.org/tc/reference/principles.html#we-value-constructive-peer-review
.. _API: https://docs.openstack.org/api-ref/placement/
.. _placement code: https://opendev.org/openstack/placement
.. _stein schedule: https://releases.openstack.org/stein/schedule.html
.. _release note: https://docs.openstack.org/reno/latest/
.. _PEP 8: https://www.python.org/dev/peps/pep-0008/
.. _PTL guide: https://docs.openstack.org/project-team-guide/ptl.html
.. _openstack launchpad doc: https://docs.openstack.org/contributors/common/task-tracking.html#launchpad
.. _How to Recheck: https://docs.openstack.org/project-team-guide/testing.html#how-to-handle-test-failures
