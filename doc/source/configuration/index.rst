===================
Configuration Guide
===================

The static configuration for Placement lives in two main files: ``placement.conf`` and
``policy.yaml``. These are described below.

Configuration
-------------

* :doc:`Config Reference <config>`: A complete reference of all
  configuration options available in the ``placement.conf`` file.

* :doc:`Sample Config File <sample-config>`: A sample config
  file with inline documentation.

.. TODO(efried):: Get this working
 * :nova-doc:`Configuration Guide </admin/configuration/index>`: Detailed
   configuration guides for various parts of you Nova system. Helpful reference
   for setting up specific hypervisor backends.

Policy
------

Placement, like most OpenStack projects, uses a policy language to restrict
permissions on REST API actions.

* :doc:`Policy Reference <policy>`: A complete
  reference of all policy points in placement and what they impact.

* :doc:`Sample Policy File <sample-policy>`: A sample
  placement policy file with inline documentation.


.. # NOTE(mriedem): This is the section where we hide things that we don't
   # actually want in the table of contents but sphinx build would fail if
   # they aren't in the toctree somewhere.
.. toctree::
   :hidden:

   policy
   sample-policy
   config
   sample-config
