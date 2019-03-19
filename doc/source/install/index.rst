=================
Placement Service
=================

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

.. _HTTP API: https://developer.openstack.org/api-ref/placement/
