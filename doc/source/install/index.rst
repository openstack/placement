============
Installation
============

.. note:: Before the Stein release the placement code was in Nova alongside
          the compute REST API code (nova-api). Make sure that the release
          version of this document matches the release version you want to
          deploy.

Steps Overview
--------------

This subsection gives an overview of the process without going into detail
on the methods used.

**1. Deploy the API service**

Placement provides a ``placement-api`` WSGI script for running the service with
Apache, nginx or other WSGI-capable web servers. Depending on what packaging
solution is used to deploy OpenStack, the WSGI script may be in ``/usr/bin``
or ``/usr/local/bin``.

``placement-api``, as a standard WSGI script, provides a module level
``application`` attribute that most WSGI servers expect to find. This means it
is possible to run it with lots of different servers, providing flexibility in
the face of different deployment scenarios. Common scenarios include:

* apache2_ with mod_wsgi_
* apache2 with mod_proxy_uwsgi_
* nginx_ with uwsgi_
* nginx with gunicorn_

In all of these scenarios the host, port and mounting path (or prefix) of the
application is controlled in the web server's configuration, not in the
configuration (``placement.conf``) of the placement application.

When placement was `first added to DevStack`_ it used the ``mod_wsgi`` style.
Later it `was updated`_ to use mod_proxy_uwsgi_. Looking at those changes can
be useful for understanding the relevant options.

DevStack is configured to host placement at ``/placement`` on either the
default port for http or for https (``80`` or ``443``) depending on whether TLS
is being used. Using a default port is desirable.

By default, the placement application will get its configuration for settings
such as the database connection URL from ``/etc/placement/placement.conf``.
The directory the configuration file will be found in can be changed by setting
``OS_PLACEMENT_CONFIG_DIR`` in the environment of the process that starts the
application. With recent releases of ``oslo.config``, configuration options may
also be set in the environment_.

.. note:: When using uwsgi with a front end (e.g., apache2 or nginx) something
    needs to ensure that the uwsgi process is running. In DevStack this is done
    with systemd_. This is one of many different ways to manage uwsgi.

This document refrains from declaring a set of installation instructions for
the placement service. This is because a major point of having a WSGI
application is to make the deployment as flexible as possible. Because the
placement API service is itself stateless (all state is in the database), it is
possible to deploy as many servers as desired behind a load balancing solution
for robust and simple scaling. If you familiarize yourself with installing
generic WSGI applications (using the links in the common scenarios list,
above), those techniques will be applicable here.

.. _apache2: http://httpd.apache.org/
.. _mod_wsgi: https://modwsgi.readthedocs.io/
.. _mod_proxy_uwsgi: http://uwsgi-docs.readthedocs.io/en/latest/Apache.html
.. _nginx: http://nginx.org/
.. _uwsgi: http://uwsgi-docs.readthedocs.io/en/latest/Nginx.html
.. _gunicorn: http://gunicorn.org/
.. _first added to DevStack: https://review.opendev.org/#/c/342362/
.. _was updated: https://review.opendev.org/#/c/456717/
.. _systemd: https://review.opendev.org/#/c/448323/
.. _environment: https://docs.openstack.org/oslo.config/latest/reference/drivers.html#environment

**2. Synchronize the database**

The placement service uses its own database, defined in the
:oslo.config:group:`placement_database` section of configuration. The
:oslo.config:option:`placement_database.connection` option **must** be set or
the service will not start. The command line tool :doc:`/cli/placement-manage`
can be used to migrate the database tables to their correct form, including
creating them. The database described by the ``connection`` option must
already exist and have appropriate access controls defined.

Another option for synchronization is to set
:oslo.config:option:`placement_database.sync_on_startup` to ``True`` in
configuration. This will perform any missing database migrations as the
placement web service starts. Whether you choose to sync automaticaly or use
the command line tool depends on the constraints of your environment and
deployment tooling.

**3. Create accounts and update the service catalog**

Create a **placement** service user with an **admin** role in Keystone.

The placement API is a separate service and thus should be registered under
a **placement** service type in the service catalog. Clients of placement, such
as the resource tracker in the nova-compute node, will use the service catalog
to find the placement endpoint.

See :ref:`configure-endpoints-pypi` for examples of creating the service user
and catalog entries.

Devstack sets up the placement service on the default HTTP port (80) with a
``/placement`` prefix instead of using an independent port.


Installation Packages
---------------------

This section provides instructions on installing placement from Linux
distribution packages.

.. warning:: These installation documents are a work in progress. Some of the
             distribution packages mentioned are not yet available so the
             instructions **will not work**.

The placement service provides an `HTTP API`_ used to track resource provider
inventories and usages. More detail can be found at the :doc:`placement
overview </index>`.

Placement operates as a web service over a data model. Installation involves
creating the necessary database and installing and configuring the web service.
This is a straightforward process, but there are quite a few steps to integrate
placement with the rest of an OpenStack cloud.

.. note:: Placement is required by some of the other OpenStack services,
          notably nova, therefore it should be installed before those other
          services but after Identity (keystone).

.. toctree::
   :maxdepth: 1

   from-pypi.rst
   install-obs.rst
   install-rdo.rst
   install-ubuntu.rst
   verify.rst

.. _HTTP API: https://docs.openstack.org/api-ref/placement/
