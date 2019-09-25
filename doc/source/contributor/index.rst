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

===========================
 Placement Developer Notes
===========================

The Nova project introduced the placement service as part of the Newton
release, and it was extracted to its own repository in the Stein release. The
service provides an HTTP API to manage inventories of different classes of
resources, such as disk or virtual cpus, made available by entities called
resource providers. Information provided through the placement API is intended
to enable more effective accounting of resources in an OpenStack deployment and
better scheduling of various entities in the cloud.

The document serves to explain the architecture of the system and to provide
some guidance on how to maintain and extend the code. For more detail on why
the system was created and how it does its job see :doc:`/index`. For some
insight into the longer term goals of the system see :doc:`goals` and
:doc:`vision-reflection`.

.. toctree::
   :maxdepth: 2

   contributing
   architecture
   api-ref-guideline
   goals
   quick-dev
   testing
   vision-reflection
