=================
Vision Reflection
=================

In late-2018, the OpenStack Technical Committee composed a
`technical vision <https://governance.openstack.org/tc/reference/technical-vision.html>`_
of what OpenStack clouds should look like. This document compares the state of
placement relative to that vision to provide some guidance on broad stroke ways
in which placement may need to change to match the vision.

Since placement is primarily a back-end and admin-only system (at least for
now), many aspects of the vision document do not apply, but it is still a
useful exercise.

Note that there is also a placement :doc:`goals` document.

The vision document is divided into three sections, which this document
mirrors. This should be a living document which evolves as placement itself
evolves.

The Pillars of Cloud
====================

The sole interface to the placement service is an HTTP API, meaning that in
theory, anything can talk to it, enabling the self-service and application
control that define a cloud. However, at the moment the data managed by
placement is considered for administrators only. This policy could be changed,
but doing so would be a dramatic adjustment in the scope of who placement is
for and what it does. Since placement has not yet fully satisfied its original
vision to clarify and ease cloud resource allocation such a change should be
considered secondary to completing the original goals.

OpenStack-specific Considerations
=================================

Placement uses microversions to help manage interoperability and bi-directional
compatibility. Because placement has used microversions from the very start a
great deal of the valuable functionality is only available in an opt-in
fashion. In fact, it would be accurate to say that a placement service at the
default microversion is incapable of being a placement service. We may wish to
evaluate (and publish) if there is a minimum microversion at which placement is
useful. To some extent this is already done with the way nova requires specific
placement microversions, and for placement to be upgraded in advance of nova.

As yet, placement provides no dedicated mechanism for partitioning its resource
providers amongst regions. Aggregates can be used for this purpose but this is
potentially cumbersome in the face of multi-region use cases where a single
placement service is used to manage resources in several clouds. This is an
area that is already under consideration, and would bring placement closer to
matching the "partitioning" aspect of the vision document.

Design Goals
============

Placement already maps well to several of the design goals in the vision
document, adhering to fairly standard methods for scalability, reliability,
customization, and flexible utilization models. It does this by being a simple
web app over a database and not much more. We should strive to keep this.
Details of how we plan to do so should be maintained in the :doc:`goals`
document.
