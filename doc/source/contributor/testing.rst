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

===================
 Testing Placement
===================

Most of the handler code in the placement API is tested using `gabbi`_. Some
utility code is tested with unit tests found in ``placement/tests/unit``. The
back-end objects are tested with a combination of unit and functional tests
found in ``placement/tests/unit/objects`` and
``placement/tests/functional/db``.

When writing tests for handler code (that is, the code found in
``placement/handlers``) a good rule of thumb is that if you feel like there
needs to be a unit test for some of the code in the handler, that is a good
sign that the piece of code should be extracted to a separate method. That
method should be independent of the handler method itself (the one decorated by
the ``wsgify`` method) and testable as a unit, without mocks if possible. If
the extracted method is useful for multiple resources consider putting it in
the ``util`` package.

As a general guide, handler code should be relatively short and where there are
conditionals and branching, they should be reachable via the gabbi functional
tests. This is merely a design goal, not a strict constraint.

Using Gabbi
-----------

Gabbi was developed in the `telemetry`_ project to provide a declarative way to
test HTTP APIs that preserves visibility of both the request and response of
the HTTP interaction. Tests are written in YAML files where each file is an
ordered suite of tests. Fixtures (such as a database) are set up and torn down
at the beginning and end of each file, not each test. JSON response bodies can
be evaluated with `JSONPath`_. The placement WSGI application is run via
`wsgi-intercept`_, meaning that real HTTP requests are being made over a file
handle that appears to Python to be a socket.

In the placement API the YAML files (aka "gabbits") can be found in
``placement/tests/functional/gabbits``. Fixture definitions are in
``placement/tests/functional/fixtures/gabbits.py``. Tests are frequently
grouped by handler name (e.g., ``resource-provider.yaml`` and
``inventory.yaml``). This is not a requirement and as we increase the number of
tests it makes sense to have more YAML files with fewer tests, divided up by
the arc of API interaction that they test.

The gabbi tests are integrated into the functional tox target, loaded via
``placement/tests/functional/test_api.py``. If you
want to run just the gabbi tests one way to do so is::

    tox -efunctional test_api

If you want to run just one yaml file (in this example ``inventory.yaml``)::

    tox -efunctional api.inventory

It is also possible to run just one test from within one file. When you do this
every test prior to the one you asked for will also be run. This is because
the YAML represents a sequence of dependent requests. Select the test by using
the name in the yaml file, replacing space with ``_``::

    tox -efunctional api.inventory_post_new_ipv4_address_inventory

.. note:: ``tox.ini`` in the placement repository is configured by a
          ``group_regex`` so that each gabbi YAML is considered a group. Thus,
          all tests in the file will be run in the same process when running
          stestr concurrently (the default).

Writing More Gabbi Tests
------------------------

The docs for `gabbi`_ try to be complete and explain the `syntax`_ in some
depth. Where something is missing or confusing, please log a `bug`_.

While it is possible to test all aspects of a response (all the response
headers, the status code, every attribute in a JSON structure) in one single
test, doing so will likely make the test harder to read and will certainly make
debugging more challenging. If there are multiple things that need to be
asserted, making multiple requests is reasonable. Since database set up is only
happening once per file (instead of once per test) and since there is no TCP
overhead, the tests run quickly.

While `fixtures`_ can be used to establish entities that are required for
tests, creating those entities via the HTTP API results in tests which are more
descriptive. For example the ``inventory.yaml`` file creates the resource
provider to which it will then add inventory. This makes it easy to explore a
sequence of interactions and a variety of responses with the tests:

* create a resource provider
* confirm it has empty inventory
* add inventory to the resource provider (in a few different ways)
* confirm the resource provider now has inventory
* modify the inventory
* delete the inventory
* confirm the resource provider now has empty inventory

Nothing special is required to add a new set of tests: create a YAML file with
a unique name in the same directory as the others. The other files can provide
examples. Gabbi can provide a useful way of doing test driven development of a
new handler: create a YAML file that describes the desired URLs and behavior
and write the code to make it pass.

It's also possible to use gabbi against a running placement service, for
example in devstack. See `gabbi-run`_ to get started. If you don't want to
go to the trouble of using devstack, but do want a live server see
:doc:`quick-dev`.

Profiling
---------

If you wish to profile requests to the placement service, to get an idea of
which methods are consuming the most CPU or are being used repeatedly, it is
possible to enable a ProfilerMiddleware_ to output per-request python profiling
dumps. The environment (:doc:`quick-dev` is a good place to start) in which
the service is running will need to have Werkzeug_ added.

* If the service is already running, stop it.
* Install Werkzeug.
* Set an environment variable, ``OS_WSGI_PROFILER``, to a directory where
  profile results will be written.
* Make sure the directory exists.
* Start the service, ensuring the environment variable is passed to it.
* Make an HTTP request that exercises the code you wish to profile.

The profiling results will be in the directory named by ``OS_WSGI_PROFILER``.
There are many ways to analyze the files. See `Profiling WSGI Apps`_ for an
example.

Profiling with OSProfiler
-------------------------

To use `OSProfiler`_ with placement:

* Add a [profiler] section to the placement.conf:

  .. code-block:: ini

    [profiler]
    connection_string = mysql+pymysql://root:admin@127.0.0.1/osprofiler?charset=utf8
    hmac_keys = my-secret-key
    enabled = True

* Include the hmac_keys in your API request:

  .. code-block:: console

    $ openstack resource provider list --os-profile my-secret-key

  The openstack client will return the trace id:

  .. code-block:: console

    Trace ID: 67428cdd-bfaa-496f-b430-507165729246

* Extract the trace in html format:

  .. code-block:: console

    $ osprofiler trace show --html 67428cdd-bfaa-496f-b430-507165729246 \
      --connection-string mysql+pymysql://root:admin@127.0.0.1/osprofiler?charset=utf8


.. _bug: https://github.com/cdent/gabbi/issues
.. _fixtures: http://gabbi.readthedocs.io/en/latest/fixtures.html
.. _gabbi: https://gabbi.readthedocs.io/
.. _gabbi-run: http://gabbi.readthedocs.io/en/latest/runner.html
.. _JSONPath: http://goessner.net/articles/JsonPath/
.. _ProfilerMiddleware: https://werkzeug.palletsprojects.com/en/master/middleware/profiler/
.. _Profiling WSGI Apps: https://anticdent.org/profiling-wsgi-apps.html
.. _syntax: https://gabbi.readthedocs.io/en/latest/format.html
.. _telemetry: http://specs.openstack.org/openstack/telemetry-specs/specs/kilo/declarative-http-tests.html
.. _Werkzeug: https://palletsprojects.com/p/werkzeug/
.. _wsgi-intercept: http://wsgi-intercept.readthedocs.io/
.. _OSProfiler: https://docs.openstack.org/osprofiler/latest/
