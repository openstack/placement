..
 This work is licensed under a Creative Commons Attribution 3.0 Unported
 License.

 http://creativecommons.org/licenses/by/3.0/legalcode

========================
Example Spec - The title
========================

Include the URL of your story from StoryBoard:

https://storyboard.openstack.org/#!/story/XXXXXXX

Introduction paragraph -- why are we doing anything? A single paragraph of
prose that operators can understand. The title and this first paragraph
should be used as the subject line and body of the commit message
respectively.

Some notes about the spec process:

* Not all blueprints need a spec, start with a story.

* The aim of this document is first to define the problem we need to solve,
  and second agree the overall approach to solve that problem.

* This is not intended to be extensive documentation for a new feature.
  For example, there is no need to specify the exact configuration changes,
  nor the exact details of any DB model changes. But you should still define
  that such changes are required, and be clear on how that will affect
  upgrades.

* You should aim to get your spec approved before writing your code.
  While you are free to write prototypes and code before getting your spec
  approved, its possible that the outcome of the spec review process leads
  you towards a fundamentally different solution than you first envisaged.

* But API changes are held to a much higher level of scrutiny.
  As soon as an API change merges, we must assume it could be in production
  somewhere, and as such, we then need to support that API change forever.
  To avoid getting that wrong, we do want lots of details about API changes
  up front.

Some notes about using this template:

* Your spec should be in ReSTructured text, like this template.

* Please wrap text at 79 columns.

* The filename in the git repository should start with the StoryBoard story
  number. For example: ``2005171-allocation-partitioning.rst``.

* Please do not delete any of the sections in this template. If you have
  nothing to say for a whole section, just write: None

* For help with syntax, see http://sphinx-doc.org/rest.html

* To test out your formatting, build the docs using ``tox -e docs`` and see the
  generated HTML file in doc/build/html/specs/<path_of_your_file>. The
  generated file will have an ``.html`` extension where the original has
  ``.rst``.

* If you would like to provide a diagram with your spec, ascii diagrams are
  often the best choice. http://asciiflow.com/ is a useful tool. If ascii
  is insufficient, you have the option to use seqdiag_ or actdiag_.

.. _seqdiag: http://blockdiag.com/en/seqdiag/index.html
.. _actdiag: http://blockdiag.com/en/actdiag/index.html

Problem description
===================

A detailed description of the problem. What problem is this feature
addressing?

Use Cases
---------

What use cases does this address? What impact on actors does this change have?
Ensure you are clear about the actors in each use case: Developer, End User,
Deployer etc.

Proposed change
===============

Here is where you cover the change you propose to make in detail. How do you
propose to solve this problem?

If this is one part of a larger effort make it clear where this piece ends. In
other words, what's the scope of this effort?

At this point, if you would like to get feedback on if the problem and proposed
change fit in placement, you can stop here and post this for review saying:
Posting to get preliminary feedback on the scope of this spec.

Alternatives
------------

What other ways could we do this thing? Why aren't we using those? This doesn't
have to be a full literature review, but it should demonstrate that thought has
been put into why the proposed solution is an appropriate one.

Data model impact
-----------------

Changes which require modifications to the data model often have a wider impact
on the system. The community often has strong opinions on how the data model
should be evolved, from both a functional and performance perspective. It is
therefore important to capture and gain agreement as early as possible on any
proposed changes to the data model.

Questions which need to be addressed by this section include:

* What new data objects and/or database schema changes is this going to
  require?

* What database migrations will accompany this change?

* How will the initial set of new data objects be generated? For example if you
  need to take into account existing instances, or modify other existing data,
  describe how that will work.

API impact
----------

Each API method which is either added or changed should have the following

* Specification for the method

  * A description of what the method does suitable for use in user
    documentation

  * Method type (POST/PUT/GET/DELETE)

  * Normal http response code(s)

  * Expected error http response code(s)

    * A description for each possible error code should be included
      describing semantic errors which can cause it such as
      inconsistent parameters supplied to the method, or when a
      resource is not in an appropriate state for the request to
      succeed. Errors caused by syntactic problems covered by the JSON
      schema definition do not need to be included.

  * URL for the resource

    * URL should not include underscores; use hyphens instead.

  * Parameters which can be passed via the url

  * JSON schema definition for the request body data if allowed

    * Field names should use snake_case style, not camelCase or MixedCase
      style.

  * JSON schema definition for the response body data if any

    * Field names should use snake_case style, not camelCase or MixedCase
      style.

* Example use case including typical API samples for both data supplied
  by the caller and the response

* Discuss any policy changes, and discuss what things a deployer needs to
  think about when defining their policy.

Note that the schema should be defined as restrictively as
possible. Parameters which are required should be marked as such and
only under exceptional circumstances should additional parameters
which are not defined in the schema be permitted (eg
additionalProperties should be False).

Reuse of existing predefined parameter types such as regexps for
passwords and user defined names is highly encouraged.

Security impact
---------------

Describe any potential security impact on the system. Some of the items to
consider include:

* Does this change touch sensitive data such as tokens, keys, or user data?

* Does this change alter the API in a way that may impact security, such as
  a new way to access sensitive information or a new way to log in?

* Does this change involve cryptography or hashing?

* Does this change require the use of sudo or any elevated privileges?

* Does this change involve using or parsing user-provided data? This could
  be directly at the API level or indirectly such as changes to a cache layer.

* Can this change enable a resource exhaustion attack, such as allowing a
  single API interaction to consume significant server resources? Some examples
  of this include launching subprocesses for each connection, or entity
  expansion attacks in XML.

For more detailed guidance, please see the OpenStack Security Guidelines as
a reference (https://wiki.openstack.org/wiki/Security/Guidelines). These
guidelines are a work in progress and are designed to help you identify
security best practices. For further information, feel free to reach out
to the OpenStack Security Group at openstack-security@lists.openstack.org.

Other end user impact
---------------------

Aside from the API, are there other ways a user will interact with this
feature?

* Does this change have an impact on osc-placement? What does the user
  interface there look like?

Performance Impact
------------------

Describe any potential performance impact on the system, for example
how often will new code be called, and is there a major change to the calling
pattern of existing code.

Examples of things to consider here include:

* A small change in a utility function or a commonly used decorator can have a
  large impacts on performance.

* Calls which result in a database queries can have a profound impact on
  performance when called in critical sections of the code.

* Will the change include any locking, and if so what considerations are there
  on holding the lock?

Other deployer impact
---------------------

Discuss things that will affect how you deploy and configure OpenStack
that have not already been mentioned, such as:

* What config options are being added? Should they be more generic than
  proposed? Are the default values ones which will work well in real
  deployments?

* Is this a change that takes immediate effect after its merged, or is it
  something that has to be explicitly enabled?

* If this change is a new binary, how would it be deployed?

* Please state anything that those doing continuous deployment, or those
  upgrading from the previous release, need to be aware of. Also describe
  any plans to deprecate configuration values or features.

Developer impact
----------------

Discuss things that will affect other developers working on OpenStack.

Upgrade impact
--------------

Describe any potential upgrade impact on the system.


Implementation
==============

Assignee(s)
-----------

Who is leading the writing of the code? Or is this a blueprint where you're
throwing it out there to see who picks it up?

If more than one person is working on the implementation, please designate the
primary author and contact.

Primary assignee:
  <IRC nick or None>

Other contributors:
  <IRC nick or None>

Work Items
----------

Work items or tasks -- break the feature up into the things that need to be
done to implement it. Those parts might end up being done by different people,
but we're mostly trying to understand the timeline for implementation.


Dependencies
============

* Include specific references to other specs or stories that this one either
  depends on or is related to.

* If this requires new functionality in another project that is not yet used
  document that fact.

* Does this feature require any new library dependencies or code otherwise not
  included in OpenStack? Or does it depend on a specific version of a library?


Testing
=======

Please discuss the important scenarios that need to be tested, as well as
specific edge cases we should be ensuring work correctly.


Documentation Impact
====================

Which audiences are affected most by this change, and which documentation
titles on docs.openstack.org should be updated because of this change? Don't
repeat details discussed above, but reference them here in the context of
documentation for multiple audiences.

References
==========

Please add any useful references here. You are not required to have any
references. Moreover, this specification should still make sense when your
references are unavailable. Examples of what you could include are:

* Links to mailing list or IRC discussions

* Links to notes from a summit session

* Links to relevant research, if appropriate

* Anything else you feel it is worthwhile to refer to


History
=======

Optional section intended to be used each time the spec is updated to describe
new design, API or any database schema updated. Useful to let the reader
understand how the spec has changed over time.

.. list-table:: Revisions
   :header-rows: 1

   * - Release Name
     - Description
   * - <Replace With Current Release>
     - Introduced
