===================
Verify Installation
===================

Verify operation of the placement service.

.. note:: You will need to authenticate to the identity service as an
          ``admin`` before making these calls. There are many different ways
          to do this, depending on how your system was set up. If you do not
          have an ``admin-openrc`` file, you will have something similar.

#. Source the ``admin`` credentials to gain access to admin-only CLI commands:

   .. code-block:: console

      $ . admin-openrc

#. Perform status checks to make sure everything is in order:

   .. code-block:: console

      $ placement-status upgrade check
      +----------------------------------+
      | Upgrade Check Results            |
      +----------------------------------+
      | Check: Missing Root Provider IDs |
      | Result: Success                  |
      | Details: None                    |
      +----------------------------------+
      | Check: Incomplete Consumers      |
      | Result: Success                  |
      | Details: None                    |
      +----------------------------------+

   The output of that command will vary by release.
   See :ref:`placement-status upgrade check <placement-status-checks>` for
   details.

#. Run some commands against the placement API:

   * Install the `osc-placement`_ plugin:

     .. note:: This example uses `PyPI`_ and :ref:`about-pip` but if you are
               using distribution packages you can install the package from
               their repository. With the move to python3 you will need to
               specify **pip3** or install **python3-osc-placement** from
               your distribution.

     .. code-block:: console

        $ pip3 install osc-placement

   * List available resource classes and traits:

     .. code-block:: console

        $ openstack --os-placement-api-version 1.2 resource class list --sort-column name
        +----------------------------+
        | name                       |
        +----------------------------+
        | DISK_GB                    |
        | IPV4_ADDRESS               |
        | ...                        |

        $ openstack --os-placement-api-version 1.6 trait list --sort-column name
        +---------------------------------------+
        | name                                  |
        +---------------------------------------+
        | COMPUTE_DEVICE_TAGGING                |
        | COMPUTE_NET_ATTACH_INTERFACE          |
        | ...                                   |

.. _osc-placement: https://docs.openstack.org/osc-placement/latest/
.. _PyPI: https://pypi.org
