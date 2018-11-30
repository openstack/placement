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

=====
Goals
=====

Like many OpenStack projects, placement uses blueprints and specifications to
plan and design upcoming work. Sometimes, however, certain types of work fit
more in the category of wishlist, or when-we-get-around-to-it. These types of
work are often not driven by user or operator feature requests, but are instead
related to architectural, maintenance, and technical debt management goals that
will make the lives of contributors to the project easier over time. In those
cases a specification is too formal and detailed but it is still worthwhile to
remember the idea and put it somewhere. That's what this document is for: a
place to find and put goals for placement that are related to making
contribution more pleasant and keep the project and product healthy, yet are
too general to be considered feature requests.

This document can also operate as one of several sources of guidance on how not
to stray too far from the long term vision of placement.

Don't Global Config
-------------------

Placement uses `oslo.config`_ to manage configuration. From nova, it inherits
using a global ``CONF`` as the way to interact with the configuration options.
This isn't necessary. If changed, it would make tests less likely to leak
configuration settings amongst themselves and will also ease use of the
``PlacementFixture`` by other projects which wish to use placement in their
functional tests. Once we fix this we should ensure that we avoid regressing to
using global configuration.


.. _oslo.config: https://docs.openstack.org/oslo.config
