Install and configure Placement for Red Hat Enterprise Linux and CentOS Stream
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This section describes how to install and configure the placement service
when using Red Hat Enterprise Linux or CentOS Stream packages.

Prerequisites
-------------

Before you install and configure the placement service, you must create
a database, service credentials, and API endpoints.

Create Database
^^^^^^^^^^^^^^^

#. To create the database, complete these steps:

   * Use the database access client to connect to the database server
     as the ``root`` user:

     .. code-block:: console

        $ mysql -u root -p

   * Create the ``placement`` database:

     .. code-block:: console

        MariaDB [(none)]> CREATE DATABASE placement;

   * Grant proper access to the database:

     .. code-block:: console

        MariaDB [(none)]> GRANT ALL PRIVILEGES ON placement.* TO 'placement'@'localhost' \
          IDENTIFIED BY 'PLACEMENT_DBPASS';
        MariaDB [(none)]> GRANT ALL PRIVILEGES ON placement.* TO 'placement'@'%' \
          IDENTIFIED BY 'PLACEMENT_DBPASS';

     Replace ``PLACEMENT_DBPASS`` with a suitable password.

   * Exit the database access client.

Configure User and Endpoints
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: shared/endpoints.rst

Install and configure components
--------------------------------

.. include:: note_configuration_vary_by_distribution.rst

#. Install the packages:

   .. code-block:: console

      # dnf install openstack-placement-api

#. Edit the ``/etc/placement/placement.conf`` file and complete the following
   actions:

   * In the ``[placement_database]`` section, configure database access:

     .. path /etc/placement/placement.conf
     .. code-block:: ini

        [placement_database]
        # ...
        connection = mysql+pymysql://placement:PLACEMENT_DBPASS@controller/placement

     Replace ``PLACEMENT_DBPASS`` with the password you chose for the placement
     database.

   * In the ``[api]`` and ``[keystone_authtoken]`` sections, configure Identity
     service access:

     .. path /etc/placement/placement.conf
     .. code-block:: ini

        [api]
        # ...
        auth_strategy = keystone

        [keystone_authtoken]
        # ...
        auth_url = http://controller:5000/v3
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

        Comment out or remove any other options in the ``[keystone_authtoken]``
        section.

     .. note::

        The value of ``user_name``, ``password``, ``project_domain_name`` and
        ``user_domain_name`` need to be in sync with your keystone config.

#. Populate the ``placement`` database:

   .. code-block:: console

      # su -s /bin/sh -c "placement-manage db sync" placement

   .. note::

      Ignore any deprecation messages in this output.

Finalize installation
---------------------

* Restart the httpd service:

   .. code-block:: console

      # systemctl restart httpd
