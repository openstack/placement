..
      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

=================
 Placement Usage
=================

Tracking Resources
==================

The placement service enables other projects to track their own resources.
Those projects can register/delete their own resources to/from placement
via the placement REST API.

The nova resource tracker is responsible for creating the resource provider
record corresponding to the compute host on which the resource tracker runs.
If other projects -- for example, Neutron or Cyborg -- wish to manage resources
on a compute host, they should create resource providers as children of the
compute host provider and register their own managed resources as inventory on
those child providers. For more information, see the
:doc:`Modeling with Provider Trees <provider-tree>`.

.. toctree::
   :hidden:

   provider-tree
