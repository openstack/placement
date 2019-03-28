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


Writing Code
------------


New Features
------------


.. _Project Team Guide: https://docs.openstack.org/project-team-guide/
.. _Developer's Guide: https://docs.openstack.org/infra/manual/developers.html
.. _openstack-discuss: http://lists.openstack.org/cgi-bin/mailman/listinfo/openstack-discuss
.. _StoryBoard: https://storyboard.openstack.org/#!/project/openstack/placement
.. _new bug: https://storyboard.openstack.org/#!/worklist/580
.. _gerrit: http://review.openstack.org/
