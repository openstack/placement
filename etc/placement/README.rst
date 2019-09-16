Sample policy and config files
==============================

This directory contains sample ``placement.conf`` and ``policy.yaml`` files.

Sample Config
-------------

To generate the sample ``placement.conf`` file, run the following command from
the top level of the placement directory::

    tox -e genconfig

For a pre-generated example of the latest ``placement.conf``, see:

    https://docs.openstack.org/placement/latest/configuration/sample-config.html

Sample Policy
-------------

To generate the sample ``policy.yaml`` file, run the following command from the
top level of the placement directory::

    tox -e genpolicy

For a pre-generated example of the latest placement ``policy.yaml``, see:

    https://docs.openstack.org/placement/latest/configuration/sample-policy.html
