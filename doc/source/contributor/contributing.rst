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

===========================
 Contributing to Placement
===========================

As an official OpenStack project, Placement follows the overarching processes
outlined in the `Project Team Guide`_ and `Developer's Guide`_. Contribution is
welcomed from any interested parties and takes many different forms.

To make sure everything gets the attention it deserves and work is not
duplicated there are some guidelines, stated here.

If in doubt, ask someone, either by sending a message to the
`openstack-discuss`_ mailing list with a ``[placement]`` subject tag, or by
visiting the ``#openstack-placement`` IRC channel on ``chat.freenode.net``.


Submitting and Managing Bugs
----------------------------

Bugs found in  placement should be reported in `StoryBoard`_ by creating a new
story in the ``openstack/placement`` project.

New Bugs
~~~~~~~~

If you are submitting a new bug, explain the problem, the steps taken that led
to the bad results, and the expected results. Please also add as much of the
following information as possible:

* Relevant lines from the ``placement-api`` log.
* The OpenStack release (e.g., ``Stein``).
* The method used to install or deploy placement.
* The operating system(s) on which the placement is running.
* The version(s) of Python being used.

Tag the story with ``bug``.

Triaging Bugs
~~~~~~~~~~~~~

Triaging newly submitted bugs to confirm they really are bugs, gather missing
information, and to suggest possible solutions is one of the most important
contributions that can be made to any open source project.

If a `new bug`_ doesn't have the ``bug`` tag, add it. If it isn't a functional
problem with existing code, consider adding the ``rfe`` tag for a feature
request, or ``cleanup`` for a suggested refactoring or a reminder for future
work. An error in documentation is a ``bug``.

Leave comments on the story if you have questions or ideas. If you are
relatively certain about a solution, add the steps of that solution as tasks on
the story.

If submitting a change related to a story, the `gerrit`_ system will
automatically link to StoryBoard if you include ``Story:`` and, optionally,
``Task:`` identifiers in your commit message, like this::

    Story: 2005190
    Task: 29938

Using solely ``Story:`` will leave a comment referring back to the commit in
gerrit. Adding ``Task:`` will update the identified task to indicate it is in a
``Progress`` state. When the change merges, the state will be updated to
``Merged``.


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


New Features
------------


.. _Project Team Guide: https://docs.openstack.org/project-team-guide/
.. _Developer's Guide: https://docs.openstack.org/infra/manual/developers.html
.. _openstack-discuss: http://lists.openstack.org/cgi-bin/mailman/listinfo/openstack-discuss
.. _list archive: http://lists.openstack.org/pipermail/openstack-discuss/
.. _StoryBoard: https://storyboard.openstack.org/#!/project/openstack/placement
.. _new bug: https://storyboard.openstack.org/#!/worklist/580
.. _gerrit: http://review.openstack.org/
.. _How to Review Changes the OpenStack Way: https://docs.openstack.org/project-team-guide/review-the-openstack-way.html
.. _core reviewers: https://review.openstack.org/#/admin/groups/1936,members
.. _constructive: https://governance.openstack.org/tc/reference/principles.html#we-value-constructive-peer-review
