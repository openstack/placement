Install and configure Placement from PyPI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The section describes how to install and configure the placement service using
packages from PyPI_. Placement works with Python version 2.7, but version 3.6
or higher is recommended.

This document assumes you have a working MySQL server and a working Python
environment, including the :ref:`about-pip` package installer. Depending on
your environment, you may wish to install placement in a virtualenv_.

This document describes how to run placement with uwsgi_ as its web server.
This is but one of many different ways to host the service. Placement is a
well-behaved WSGI_ application so should be straightforward to host with any
WSGI server.

If using placement in an OpenStack environment, you will need to ensure it is
up and running before starting services that use it but after services it uses.
That means after Keystone_, but before anything else.

Prerequisites
-------------

Before installing the service, you will need to create the database, service
credentials, and API endpoints, as described in the following sections.

.. _about-pip:

pip
^^^
Install `pip <https://pypi.org/project/pip/>`_ from PyPI_.

.. note:: Examples throughout this reference material use the ``pip`` command.
          This may need to be pathed or spelled differently (e.g. ``pip3``)
          depending on your installation and Python version.

python-openstackclient
^^^^^^^^^^^^^^^^^^^^^^
If not already installed, install the ``openstack`` command line tool:

.. code-block:: console

   # pip install python-openstackclient

.. _create-database-pypi:

Create Database
^^^^^^^^^^^^^^^

Placement is primarily tested with MySQL/MariaDB so that is what is described
here. It also works well with PostgreSQL and likely with many other databases
supported by sqlalchemy_.

To create the database, complete these steps:

.. TODO(cdent): Extract this to a shared document for all the install docs.

#. Use the database access client to connect to the database server as the
   ``root`` user or by using ``sudo`` as appropriate:

   .. code-block:: console

      # mysql

#. Create the ``placement`` database:

   .. code-block:: console

      MariaDB [(none)]> CREATE DATABASE placement;

#. Grant proper access to the database:

   .. code-block:: console

      MariaDB [(none)]> GRANT ALL PRIVILEGES ON placement.* TO 'placement'@'localhost' \
        IDENTIFIED BY 'PLACEMENT_DBPASS';
      MariaDB [(none)]> GRANT ALL PRIVILEGES ON placement.* TO 'placement'@'%' \
        IDENTIFIED BY 'PLACEMENT_DBPASS';

   Replace ``PLACEMENT_DBPASS`` with a suitable password.

#. Exit the database access client.

.. _configure-endpoints-pypi:

Configure User and Endpoints
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. note:: If you are not using Keystone, you can skip the steps below but will
          need to configure the :oslo.config:option:`api.auth_strategy` setting
          with a value of ``noauth2``. See also :doc:`/contributor/quick-dev`.

.. note:: You will need to authenticate to Keystone as an ``admin`` before
          making these calls. There are many different ways to do this,
          depending on how your system was set up. If you do not have an
          ``admin-openrc`` file, you will have something similar.

.. important:: These documents use an endpoint URL of
               ``http://controller:8778/`` as an example only. You should
               configure placement to use whatever hostname and port works best
               for your environment. Using SSL on the default port, with either
               a domain or path specific to placement, is recommended. For
               example: ``https://mygreatcloud.com/placement`` or
               ``https://placement.mygreatcloud.com/``.

.. include:: shared/endpoints.rst

.. _configure-conf-pypi:

Install and configure components
--------------------------------

The default location of the placement configuration file is
``/etc/placement/placement.conf``. A different directory may be chosen by
setting ``OS_PLACEMENT_CONFIG_DIR`` in the environment. It is also possible to
run the service with a partial or no configuration file and set some options
in `the environment`_. See :doc:`/configuration/index` for additional
configuration settings not mentioned here.

.. note:: In the steps below, ``controller`` is used as a stand in for the
          hostname of the hosts where keystone, mysql, and placement are
          running. These may be distinct. The keystone host (used for
          ``auth_url`` and ``www_authenticate_uri``) should be the unversioned
          public endpoint for the Identity service.

.. TODO(cdent): Some of these database steps could be extracted to a shared
                document used by all the install docs.

#. Install placement and required database libraries:

   .. code-block:: console

      # pip install openstack-placement pymysql

#. Create the ``/etc/placement/placement.conf`` file and complete the following
   actions:

   * Create a ``[placement_database]`` section and configure database access:

     .. path /etc/placement/placement.conf
     .. code-block:: ini

        [placement_database]
        connection = mysql+pymysql://placement:PLACEMENT_DBPASS@controller/placement

     Replace ``PLACEMENT_DBPASS`` with the password you chose for the placement
     database.

   * Create ``[api]`` and ``[keystone_authtoken]`` sections, configure Identity
     service access:

     .. path /etc/placement/placement.conf
     .. code-block:: ini

        [api]
        auth_strategy = keystone  # use noauth2 if not using keystone

        [keystone_authtoken]
        www_authenticate_uri = http://controller:5000/
        auth_url = http://controller:5000/
        memcached_servers = controller:11211
        auth_type = password
        project_domain_name = Default
        user_domain_name = Default
        project_name = service
        username = placement
        password = PLACEMENT_PASS

     Replace ``PLACEMENT_PASS`` with the password you chose for the
     ``placement`` user in the Identity service.

     .. note::

        The value of ``user_name``, ``password``, ``project_domain_name`` and
        ``user_domain_name`` need to be in sync with your keystone config.

   * You may wish to set the :oslo.config:option:`debug` option to ``True`` to
     produce more verbose log output.

#. Populate the ``placement`` database:

   .. code-block:: console

      $ placement-manage db sync

   .. note:: An alternative is to use the
             :oslo.config:option:`placement_database.sync_on_startup` option.


Finalize installation
---------------------

Now that placement itself has been installed we need to launch the service in a
web server. What follows provides a very basic web server that, while
relatively performant, is not set up to be easy to manage. Since there are many
web servers and many ways to manage them, such things are outside the scope of
this document.

Install and run the web server:

#. Install the ``uwsgi`` package (these instructions are against version
   2.0.18):

   .. code-block:: console

      # pip install uwsgi

#. Run the server with the placement WSGI application in a terminal window:

   .. warning:: Make sure you are using the correct ``uwsgi`` binary. It may
                be in multiple places in your path. The wrong version will
                fail and complain about bad arguments.

   .. code-block:: console

      # uwsgi -M --http :8778 --wsgi-file /usr/local/bin/placement-api \
              --processes 2 --threads 10

#. In another terminal confirm the server is running using ``curl``. The URL
   should match the public endpoint set in :ref:`configure-endpoints-pypi`.

   .. code-block:: console

      $ curl http://controller:8778/

   The output will look something like this:

   .. code-block:: json

      {
         "versions" : [
            {
               "id" : "v1.0",
               "max_version" : "1.31",
               "links" : [
                  {
                     "href" : "",
                     "rel" : "self"
                  }
               ],
               "min_version" : "1.0",
               "status" : "CURRENT"
            }
         ]
      }

   Further interactions with the system can be made with osc-placement_.

.. _PyPI: https://pypi.org
.. _virtualenv: https://pypi.org/project/virtualenv/
.. _uwsgi: https://uwsgi-docs.readthedocs.io/en/latest/WSGIquickstart.html
.. _WSGI: https://www.python.org/dev/peps/pep-3333/
.. _Keystone: https://docs.openstack.org/keystone/latest/
.. _sqlalchemy: https://www.sqlalchemy.org
.. _the environment: https://docs.openstack.org/oslo.config/latest/reference/drivers.html#module-oslo_config.sources._environment
.. _osc-placement: https://docs.openstack.org/osc-placement/latest/

