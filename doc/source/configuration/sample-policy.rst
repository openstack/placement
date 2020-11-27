============================
Sample Placement Policy File
============================

.. warning::

   JSON formatted policy file is deprecated since Placement 5.0.0 (Wallaby).
   The `oslopolicy-convert-json-to-yaml`__ tool will migrate your existing
   JSON-formatted policy file to YAML in a backward-compatible way.

.. __: https://docs.openstack.org/oslo.policy/latest/cli/oslopolicy-convert-json-to-yaml.html

The following is a sample placement policy file for adaptation and use.

The sample policy can also be viewed in :download:`file form
</_static/placement.policy.yaml.sample>`.

.. important::

   The sample policy file is auto-generated from placement when this
   documentation is built. You must ensure your version of placement matches
   the version of this documentation.

.. literalinclude:: /_static/placement.policy.yaml.sample
