======
Errors
======

When there is an error interacting with the placement API, the response will
include a few different signals of what went wrong, include the status header
and information in the response body. The structure of the ``JSON`` body of an
error response is defined by the OpenStack errors_ guideline.

**HTTP Status Code**
    The ``Status`` header of the response will include a code, defined by
    :rfc:`7231#section-6` that gives a general overview of the problem.
    This value also shows up in a ``status`` attribute in the body of the
    response.

**Detail Message**
    A textual description of the error condition, in a ``detail`` attribute.
    The value is usually the message associated with whatever exception
    happened within the service.

**Error Code**
    When the microversion is ``>=1.23`` responses will also include a ``code``
    attribute in the ``JSON`` body. These are documented below. Where a
    response does not use a specific code ``placement.undefined_code`` is
    present.

.. note:: In some cases, for example when keystone is being used and no
          authentication information is provided in a request (causing a
          ``401`` response), the structure of the error response will not match
          the above because the error is produced by code other than the
          placement service.

.. _`error_codes`:

Error Codes
===========

The defined errors are:

.. list-table::
   :header-rows: 1

   * - Code
     - Meaning
   * - ``placement.undefined_code``
     - The default code used when a specific code has not been defined or is
       not required.
   * - ``placement.inventory.inuse``
     - An attempt has been made to remove or shrink inventory that has capacity
       in use.
   * - ``placement.concurrent_update``
     - Another operation has concurrently made a request that involves one or
       more of the same resources referenced in this request, changing state.
       The current state should be retrieved to determine if the desired
       operation should be retried.
   * - ``placement.duplicate_name``
     - A resource of this type already exists with the same name, and duplicate
       names are not allowed.
   * - ``placement.resource_provider.inuse``
     - An attempt was made to remove a resource provider, but there are
       allocations against its inventory.
   * - ``placement.resource_provider.cannot_delete_parent``
     - An attempt was made to remove a resource provider, but it has one or
       more child providers. They must be removed first in order to remove this
       provider.
   * - ``placement.resource_provider.not_found``
     - A resource provider mentioned in an operation involving multiple
       resource providers, such as :ref:`reshaper`, does not exist.
   * - ``placement.query.duplicate_key``
     - A request included multiple instances of a query parameter that may only
       be specified once.
   * - ``placement.query.bad_value``
     - A value in a request conformed to the schema, but failed semantic
       validation.
   * - ``placement.query.missing_value``
     - A required query parameter is not present in a request.

.. _errors: https://specs.openstack.org/openstack/api-wg/guidelines/errors.html
