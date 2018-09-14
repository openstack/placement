==========================================
OpenStack Placement Testing Infrastructure
==========================================

This README file attempts to provides some brief guidance for writing tests
when fixing bugs or adding features to placement.

For a lot more information see the `contributor docs`_.

Test Types: Unit vs. Functional vs. Integration
-----------------------------------------------

Placement tests are divided into three types:

* Unit: tests which confirm the behavior of individual pieces of the code
  (individual methods or classes) with minimal dependency on other code or on
  externals like the database.
* Functional: tests which confirm a chunk of behavior, end to end, such as an
  HTTP endpoint accepting a body from a request and returning the expected
  response but without reliance on code or services that are external to
  placement.
* Integration: tests that confirm that things work with other services, such
  as nova.

Placement uses all three, but the majority are functional tests. This is the
result of the fairly direct architecture of placement: It is a WSGI application
that talks to a database.

Writing Unit Tests
------------------

Placement unit tests are based on the ``TestCase`` that comes with the
``testtools`` package. Use mocks only as necessary. If you find that you need
multiple mocks to make a test for the code you are testing may benefit from
being refactored to smaller units.

Writing Functional Tests
------------------------

There are two primary classes of functional test in placement:

* Testing database operations. These are based on
  ``placement.tests.functional.base.TestCase`` which is responsible for
  starting an in-memory database and a reasonable minimal configuration.
* Testing the HTTP API using `gabbi`_.

Writing Integration Tests
-------------------------

Placement configures its gate and check jobs via the ``.zuul.yaml`` file in the
root of the code repository. Some of the entries in that file configure
integration jobs, many of which use `tempest`_.

.. _gabbi: https://gabbi.readthedocs.io/
.. _contributor docs: https://docs.openstack.org/placement/latest/contributor/
.. _tempest: https://docs.openstack.org/tempest/latest/
