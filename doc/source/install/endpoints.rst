
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

   .. note:: Depending on your environment, the URL for the endpoint will vary
             by port (possibly 8780 instead of 8778, or no port at all) and
             hostname. You are responsible for determining the correct URL.

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
