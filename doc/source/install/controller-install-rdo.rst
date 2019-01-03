Install and configure controller node for Red Hat Enterprise Linux and CentOS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This section describes how to install and configure the placement service on
the controller node.

Prerequisites
-------------

Before you install and configure the placement service, you must create
a database, service credentials, and API endpoints.

#. To create the databases, complete these steps:

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

#. Source the ``admin`` credentials to gain access to admin-only CLI commands:

   .. code-block:: console

      $ . admin-openrc

#. Create a Placement service user using your chosen ``PLACEMENT_PASS``:

   .. code-block:: console

      $ openstack user create --domain default --password-prompt placement

      User Password:
      Repeat User Password:
      +---------------------+----------------------------------+
      | Field               | Value                            |
      +---------------------+----------------------------------+
      | domain_id           | default                          |
      | enabled             | True                             |
      | id                  | fa742015a6494a949f67629884fc7ec8 |
      | name                | placement                        |
      | options             | {}                               |
      | password_expires_at | None                             |
      +---------------------+----------------------------------+

#. Add the Placement user to the service project with the admin role:

   .. code-block:: console

      $ openstack role add --project service --user placement admin

   .. note::

      This command provides no output.

#. Create the Placement API entry in the service catalog:

   .. code-block:: console

      $ openstack service create --name placement \
        --description "Placement API" placement

      +-------------+----------------------------------+
      | Field       | Value                            |
      +-------------+----------------------------------+
      | description | Placement API                    |
      | enabled     | True                             |
      | id          | 2d1a27022e6e4185b86adac4444c495f |
      | name        | placement                        |
      | type        | placement                        |
      +-------------+----------------------------------+

#. Create the Placement API service endpoints:

   .. code-block:: console

      $ openstack endpoint create --region RegionOne \
        placement public http://controller:8778

      +--------------+----------------------------------+
      | Field        | Value                            |
      +--------------+----------------------------------+
      | enabled      | True                             |
      | id           | 2b1b2637908b4137a9c2e0470487cbc0 |
      | interface    | public                           |
      | region       | RegionOne                        |
      | region_id    | RegionOne                        |
      | service_id   | 2d1a27022e6e4185b86adac4444c495f |
      | service_name | placement                        |
      | service_type | placement                        |
      | url          | http://controller:8778           |
      +--------------+----------------------------------+

      $ openstack endpoint create --region RegionOne \
        placement internal http://controller:8778

      +--------------+----------------------------------+
      | Field        | Value                            |
      +--------------+----------------------------------+
      | enabled      | True                             |
      | id           | 02bcda9a150a4bd7993ff4879df971ab |
      | interface    | internal                         |
      | region       | RegionOne                        |
      | region_id    | RegionOne                        |
      | service_id   | 2d1a27022e6e4185b86adac4444c495f |
      | service_name | placement                        |
      | service_type | placement                        |
      | url          | http://controller:8778           |
      +--------------+----------------------------------+

      $ openstack endpoint create --region RegionOne \
        placement admin http://controller:8778

      +--------------+----------------------------------+
      | Field        | Value                            |
      +--------------+----------------------------------+
      | enabled      | True                             |
      | id           | 3d71177b9e0f406f98cbff198d74b182 |
      | interface    | admin                            |
      | region       | RegionOne                        |
      | region_id    | RegionOne                        |
      | service_id   | 2d1a27022e6e4185b86adac4444c495f |
      | service_name | placement                        |
      | service_type | placement                        |
      | url          | http://controller:8778           |
      +--------------+----------------------------------+

Install and configure components
--------------------------------

.. include:: note_configuration_vary_by_distribution.rst

#. Install the packages:

   .. code-block:: console

      # yum install openstack-placement-api

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
        project_domain_name = default
        user_domain_name = default
        project_name = service
        username = placement
        password = PLACEMENT_PASS

     Replace ``PLACEMENT_PASS`` with the password you chose for the
     ``placement`` user in the Identity service.

     .. note::

        Comment out or remove any other options in the ``[keystone_authtoken]``
        section.

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
