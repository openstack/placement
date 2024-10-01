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

==============
 Architecture
==============

The placement service is straightforward: It is a `WSGI`_ application that
sends and receives JSON, using an RDBMS (usually MySQL) for persistence.
As state is managed solely in the DB, scaling the placement service is done by
increasing the number of WSGI application instances and scaling the RDBMS using
traditional database scaling techniques.

For sake of consistency and because there was initially intent to make the
entities in the placement service available over RPC,
:oslo.versionedobjects-doc:`versioned objects <>` were used to provide the
interface between the HTTP application layer and the SQLAlchemy-driven
persistence layer. In the Stein release, that interface was refactored to
remove the use of versioned objects and split functionality into smaller
modules.

Though the placement service does not aspire to be a *microservice* it does
aspire to continue to be small and minimally complex. This means a relatively
small amount of middleware that is not configurable, and a limited number of
exposed resources where any given resource is represented by one (and only
one) URL that expresses a noun that is a member of the system. Adding
additional resources should be considered a significant change requiring robust
review from many stakeholders.

The set of HTTP resources represents a concise and constrained grammar for
expressing the management of resource providers, inventories, resource classes,
traits, and allocations. If a solution is initially designed to need more
resources or a more complex grammar that may be a sign that we need to give our
goals greater scrutiny. Is there a way to do what we want with what we have
already?  Can some other service help? Is a new collaborating service required?

Minimal Framework
=================

The API is set up to use a minimal framework that tries to keep the structure
of the application as discoverable as possible and keeps the HTTP interaction
near the surface. The goal of this is to make things easy to trace when
debugging or adding functionality.

Functionality which is required for every request is handled in raw WSGI
middleware that is composed in the ``placement.deploy`` module. Dispatch or
routing is handled declaratively via the ``ROUTE_DECLARATIONS`` map defined in
the ``placement.handler`` module.

Mapping is by URL plus request method. The destination is a complete WSGI
application, using a subclass of the `wsgify`_  method from `WebOb`_ to provide
a `Request`_ object that provides convenience methods for accessing request
headers, bodies, and query parameters and for generating responses. In the
placement API these mini-applications are called *handlers*. The ``wsgify``
subclass is provided in ``placement.wsgi_wrapper`` as ``PlacementWsgify``. It is
used to make sure that JSON formatted error responses are structured according
to the API-SIG `errors`_ guideline.

This division between middleware, dispatch and handlers is supposed to
provide clues on where a particular behavior or functionality should be
implemented. Like most such systems, this does not always work but is a useful
tool.

.. _microversion process:

Microversions
=============

The placement API makes use of `microversions`_ to allow the release of new
features on an opt in basis. See :doc:`/index` for an up to date
history of the available microversions.

The rules around when a microversion is needed are modeled after those of the
:nova-doc:`compute API <contributor/microversions>`. When adding a new
microversion there are a few bits of required housekeeping that must be done in
the code:

* Update the ``VERSIONS`` list in ``placement/microversion.py`` to indicate the
  new microversion and give a very brief summary of the added feature.
* Update ``placement/rest_api_version_history.rst`` to add a more detailed
  section describing the new microversion.
* Add a :reno-doc:`release note <>` with a ``features`` section announcing the
  new or changed feature and the microversion.
* If the ``version_handler`` decorator (see below) has been used, increment
  ``TOTAL_VERSIONED_METHODS`` in ``placement/tests/unit/test_microversion.py``.
  This provides a confirmatory check just to make sure you are paying attention
  and as a helpful reminder to do the other things in this list.
* Include functional gabbi tests as appropriate (see :doc:`testing`). At the
  least, update the ``latest microversion`` test in
  ``placement/tests/functional/gabbits/microversion.yaml``.
* Update the `API Reference`_ documentation as appropriate.  The source is
  located under ``api-ref/source/``.
* If a new error code has been added in ``placement/errors.py``, it should
  be added to the `API Reference`_.

In the placement API, microversions only use the modern form of the
version header::

    OpenStack-API-Version: placement 1.2

If a valid microversion is present in a request it will be placed,
as a ``Version`` object, into the WSGI environment with the
``placement.microversion`` key. Often, accessing this in handler
code directly (to control branching) is the most explicit and
granular way to have different behavior per microversion. A
``Version`` instance can be treated as a tuple of two ints and
compared as such or there is a ``matches`` method.

A ``version_handler`` decorator is also available. It makes it possible to have
multiple different handler methods of the same (fully-qualified by package)
name, each available for a different microversion window.  If a request wants a
microversion that is not available, a defined status code is returned (usually
``404`` or ``405``). There is a unit test in place which will fail if there are
version intersections.

Adding a New Handler
====================

Adding a new URL or a new method (e.g, ``PATCH``) to an existing URL
requires adding a new handler function. In either case a new microversion and
release note is required. When adding an entirely new route a request for a
lower microversion should return a ``404``. When adding a new method to an
existing URL a request for a lower microversion should return a ``405``.

In either case, the ``ROUTE_DECLARATIONS`` dictionary in the
``placement.handler`` module should be updated to point to a
function within a module that contains handlers for the type of entity
identified by the URL. Collection and individual entity handlers of the same
type should be in the same module.

As mentioned above, the handler function should be decorated with
``@wsgi_wrapper.PlacementWsgify``, take a single argument ``req`` which is a
WebOb `Request`_ object, and return a WebOb `Response`_.

For ``PUT`` and ``POST`` methods, request bodies are expected to be JSON
based on a content-type of ``application/json``. This may be enforced by using
a decorator: ``@util.require_content('application/json')``. If the body is not
JSON, a ``415`` response status is returned.

Response bodies are usually JSON. A handler can check the ``Accept`` header
provided in a request using another decorator:
``@util.check_accept('application/json')``. If the header does not allow
JSON, a ``406`` response status is returned.

If a handler returns a response body, a ``Last-Modified`` header should be
included with the response. If the entity or entities in the response body
are directly associated with an object (or objects, in the case of a
collection response) that has an ``updated_at`` (or ``created_at``)
field, that field's value can be used as the value of the header (WebOb will
take care of turning the datetime object into a string timestamp). A
``util.pick_last_modified`` is available to help choose the most recent
last-modified when traversing a collection of entities.

If there is no directly associated object (for example, the output is the
composite of several objects) then the ``Last-Modified`` time should be
``timeutils.utcnow(with_timezone=True)`` (the timezone must be set in order
to be a valid HTTP timestamp). For example, the response__ to
``GET /allocation_candidates`` should have a last-modified header of now
because it is composed from queries against many different database entities,
presents a mixture of result types (allocation requests and provider
summaries), and has a view of the system that is only meaningful *now*.

__ https://docs.openstack.org/api-ref/placement/#list-allocation-candidates

If a ``Last-Modified`` header is set, then a ``Cache-Control`` header with a
value of ``no-cache`` must be set as well. This is to avoid user-agents
inadvertently caching the responses.

JSON sent in a request should be validated against a JSON Schema. A
``util.extract_json`` method is available. This takes a request body and a
schema. If multiple schema are used for different microversions of the same
request, the caller is responsible for selecting the right one before calling
``extract_json``.

When a handler needs to read or write the data store it should use methods on
the objects found in the ``placement.objects`` package. Doing so requires a
context which is provided to the handler method via the WSGI environment. It
can be retrieved as follows::

    context = req.environ['placement.context']

.. note:: If your change requires new methods or new objects in the
          ``placement.objects`` package, after you have made sure that you really
          do need those new methods or objects (you may not!) make those
          changes in a patch that is separate from and prior to the HTTP API
          change.

If a handler needs to return an error response, with the advent of `Placement
API Error Handling`_, it is possible to include a code in the JSON error
response.  This can be used to distinguish different errors with the same HTTP
response status code (a common case is a generation conflict versus an
inventory in use conflict). Error codes are simple namespaced strings (e.g.,
``placement.inventory.inuse``) for which symbols are maintained in
``placement.errors``. Adding a symbol to a response is done
by using the ``comment`` kwarg to a WebOb exception, like this::

    except exception.InventoryInUse as exc:
        raise webob.exc.HTTPConflict(
            _('update conflict: %(error)s') % {'error': exc},
            comment=errors.INVENTORY_INUSE)

Code that adds newly raised exceptions should include an error code. Find
additional guidelines on use in the docs for ``placement.errors``. When a
new error code is added, also document it in the `API Reference`_.

Testing of handler code is described in :doc:`testing`.

Database Schema Changes
=======================

At some point in every application's life it becomes necessary to change the
structure of its database. Modifying the SQLAlchemy models (in
placement/db/sqlachemy/models.py) is necessary for the application to
understand the new structure, but that will not change the actual underlying
database. To do that, Placement uses ``alembic`` to run database migrations.

Alembic calls each change a **revision**. To create a migration with alembic,
run the ``alembic revision`` command. Alembic will then generate a new revision
file with a unique file name, and place it in the ``alembic/versions/``
directory:

.. code-block:: console

  ed@devenv:~/projects/placement$ alembic -c placement/db/sqlalchemy/alembic.ini revision -m "Add column foo to bar table"
  Generating /home/ed/projects/placement/placement/db/sqlalchemy/alembic/versions/dfb006498ad2_add_column_foo_to_bar_table.py ... done

Let us break down that command:

- The **-c** parameter tells alembic where to find its configuration file.
- **revision** is the alembic subcommand for creating a new revision file.
- The **-m** parameter specifies a brief comment explaining the change.
- The generated file from alembic will have a name consisting of a random hash
  prefix, followed by an underscore, followed by your **-m** comment, and a
  **.py** extension. So be sure to keep your comment as brief as possible
  while still being descriptive.

The generated file will look something like this:

.. code-block:: python

 """Add column foo to bar table

 Revision ID: dfb006498ad2
 Revises: 0378df171af3
 Create Date: 2018-10-29 20:02:58.290779

 """
 from alembic import op
 import sqlalchemy as sa


 # revision identifiers, used by Alembic.
 revision = 'dfb006498ad2'
 down_revision = '0378df171af3'
 branch_labels = None
 depends_on = None


 def upgrade():
     pass

The top of the file is the docstring that will show when you review your
revision history. If we did not include the **-m** comment when we ran the
``alembic revision`` command, this would just contain "empty message". If you did
not specify the comment when creating the file, be sure to replace "empty
message" with a brief comment describing the reason for the database change.

You then need to define the changes in the ``upgrade()`` method. The code used in
these methods is basic SQLAlchemy code for creating and modifying tables. You
can examine existing migrations in the project to see examples of what this
code looks like, as well as find more in-depth usage of Alembic in the `Alembic
tutorial`_.

One other option when creating the revision is to add the ``--autogenerate``
parameter to the revision command. This assumes that you have already updated
the SQLAlchemy models, and have a connection to the placement database
configured.  When run with this option, the ``upgrade()`` method of the revision
file is filled in for you by alembic as it compares the schema described in
your models.py script and the actual state of the database. You should always
verify the revision script to make sure it does just what you intended, both by
reading the code as well as running the tests, as there are some things that
autogenerate cannot deduce. See `autogenerate limitations`_ for more detailed
information.

Gotchas
=======

This section tries to shed some light on some of the differences between the
placement API and some of the other OpenStack APIs or on situations which may
be surprising or unexpected.

* The placement API is somewhat more strict about ``Content-Type`` and ``Accept``
  headers in an effort to follow the HTTP RFCs.

  If a user-agent sends some JSON in a ``PUT`` or ``POST`` request without a
  ``Content-Type`` of ``application/json`` the request will result in an error.

  If a ``GET`` request is made without an ``Accept`` header, the response will
  default to being ``application/json``.

  If a request is made with an explicit ``Accept`` header that does not include
  ``application/json`` then there will be an error and the error will attempt to
  be in the requested format (for example, ``text/plain``).

* If a URL exists, but a request is made using a method that that URL does not
  support, the API will respond with a ``405`` error. Sometimes in the nova APIs
  this can be a ``404`` (which is wrong, but understandable given the constraints
  of the code).

* Because each handler is individually wrapped by the ``PlacementWsgify``
  decorator any exception that is a subclass of ``webob.exc.WSGIHTTPException``
  that is raised from within the handler, such as ``webob.exc.HTTPBadRequest``,
  will be caught by WebOb and turned into a valid `Response`_ containing
  headers and body set by WebOb based on the information given when the
  exception was raised. It will not be seen as an exception by any of the
  middleware in the placement stack.

  In general this is a good thing, but it can lead to some confusion if, for
  example, you are trying to add some middleware that operates on exceptions.

  Other exceptions that are not from `WebOb`_ will raise outside the handlers
  where they will either be caught in the ``__call__`` method of the
  ``PlacementHandler`` app that is responsible for dispatch, or by the
  ``FaultWrap`` middleware.


.. _WSGI: https://www.python.org/dev/peps/pep-3333/
.. _wsgify: http://docs.webob.org/en/latest/api/dec.html
.. _WebOb: http://docs.webob.org/en/latest/
.. _Request: http://docs.webob.org/en/latest/reference.html#request
.. _Response: http://docs.webob.org/en/latest/#response
.. _microversions: http://specs.openstack.org/openstack/api-wg/guidelines/microversion_specification.html
.. _errors: http://specs.openstack.org/openstack/api-wg/guidelines/errors.html
.. _API Reference: https://docs.openstack.org/api-ref/placement/
.. _Placement API Error Handling: http://specs.openstack.org/openstack/nova-specs/specs/rocky/approved/placement-api-error-handling.html
.. _`Alembic tutorial`: https://alembic.zzzcomputing.com/en/latest/tutorial.html
.. _`autogenerate limitations`: https://alembic.zzzcomputing.com/en/latest/autogenerate.html#what-does-autogenerate-detect-and-what-does-it-not-detect
