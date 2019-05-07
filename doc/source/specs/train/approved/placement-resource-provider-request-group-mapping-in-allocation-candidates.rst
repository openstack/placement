..
 This work is licensed under a Creative Commons Attribution 3.0 Unported
 License.

 http://creativecommons.org/licenses/by/3.0/legalcode

==========================================================================
Provide resource provider - request group mapping in allocation candidates
==========================================================================

https://blueprints.launchpad.net/nova/+spec/placement-resource-provider-request-group-mapping-in-allocation-candidates

To support QoS minimum bandwidth policy during server scheduling Neutron needs
to know which resource provider provides the bandwidth resource for each port
in the server create request. Similar needs arise in case of handling VGPUs
and accelerator devices.

Problem description
===================

Placement supports granular request groups in the ``GET allocation_candidates``
query but the returned allocation candidates do not contain explicit
information about which granular request group is fulfilled by which RP in the
candidate. For example the resource request of a Neutron port is mapped to a
granular request group by Nova towards Placement during scheduling. After
scheduling Neutron needs the information about which port got allocation from
which RP to set up the proper port binding towards those network device RPs.
Similar examples can be created with VGPU and accelerator devices.

Doing this mapping in Nova is possible (see the `current implementation`_) but
scales pretty badly even for small amount of ports in a single server create
request. See the `Non-scalable Nova based solution`_ section with detailed
examples and analysis.

On the other hand when Placement builds an allocation candidate it does that by
`building allocations for each granular request group`_. Therefore Placement
could include the necessary mapping information in the response with
significantly less effort.

So doing the mapping in Nova also duplicates logic that is already implemented
in Placement.

Use Cases
---------

The use case of the `bandwidth resource provider spec`_ applies here because to
fulfill that use case in a scalable way we need to consider the change proposed
in this spec. Similarly handling VGPUs and accelerator devices requires this
mapping information as well.

Proposed change
===============

Extend the response of the ``GET /allocation_candidates`` API with
an extra field ``mapping`` for each candidate. This field contains a mapping
between resource request group names and RP UUIDs for each candidate to
express which RP provides the resource for which request groups.

Alternatives
------------
For API alternatives about the proposed REST API change see the REST API
section.

Non-scalable Nova based solution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Given a single compute with the following inventories::

  Compute RP (name=compute1, uuid=compute_uuid)
   +    CPU = 1
   |    MEMORY = 1024
   |    DISK = 10
   |
   +--+Network agent RP (for SRIOV agent),
          +    uuid=sriov_agent_uuid
          |
          |
          +--+Physical network interface RP
          |    uuid = uuid5(compute1:eth0)
          |    resources:
          |        NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND=2000
          |        NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND=2000
          |    traits:
          |        CUSTOM_PHYSNET_1
          |        CUSTOM_VNIC_TYPE_DIRECT
          |
          +--+Physical network interface RP
               uuid = uuid5(compute1:eth1)
               resources:
                   NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND=2000
                   NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND=2000
               traits:
                   CUSTOM_PHYSNET_1
                   CUSTOM_VNIC_TYPE_DIRECT


Example 1 - boot with a single port having bandwidth request
............................................................

Neutron port::

  {
      'id': 'da941911-a70d-4aac-8be0-c3b263e6fd4f',
      'resource_request': {
          "resources": {
              "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND": 1000,
              "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND": 1000},
          "required": ["CUSTOM_PHYSNET_1",
                       "CUSTOM_VNIC_TYPE_DIRECT"]
      }
  }


Placement request during scheduling::

  GET /placement/allocation_candidates?
      limit=1000&
      resources=DISK_GB=1,MEMORY_MB=512,VCPU=1&
      required1=CUSTOM_PHYSNET_1,CUSTOM_VNIC_TYPE_DIRECT&
      resources1=NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND=1000,
                 NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND=1000


Placement response::

  {
     "allocation_requests":[
        {
           "allocations":{
              uuid5(compute1:eth0):{
                "resources":{
                    "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":1000,
                    "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000
                 }
              },
              compute_uuid:{
                 "resources":{
                    "MEMORY_MB":512,
                    "DISK_GB":1,
                    "VCPU":1
                 }
              }
           }
        },
        // ... another similar allocations with uuid5(compute1:eth1)
     ],
     "provider_summaries":{
         // ...
     }
  }

Filter scheduler selects the first candidate that points to
uuid5(compute1:eth0)

The nova-compute needs to pass RP UUID which provides resource for each port
to Neutron in the port binding. To be able to do that nova (in the `current
implementation`_ the nova-conductor) needs to find the RP in the selected
allocation candidate which provides the resources the Neutron port is
requested. The `current implementation`_ does this by checking which RP
provides the matching resource classes and resource amounts.

During port binding nova updates the port with that network device RP::

  {
    "id":"da941911-a70d-4aac-8be0-c3b263e6fd4f",
    "resource_request":{
        "resources":{
           "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":1000,
           "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000
        },
        "required":[
           "CUSTOM_PHYSNET_1",
           "CUSTOM_VNIC_TYPE_DIRECT"
        ]
     },
     "binding:host_id":"compute1",
     "binding:profile":{
        "allocation": uuid5(compute1:eth0)
     },
  }

This scenario is easy as only one port is requesting bandwidth
resources so there will be only one RP in the each allocation
candidate that provides such resources.

Example 2 - boot with two ports having bandwidth request
........................................................

Neutron port1::

  {
      'id': 'da941911-a70d-4aac-8be0-c3b263e6fd4f',
      'resource_request': {
          "resources": {
              "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND": 1000,
              "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND": 1000},
          "required": ["CUSTOM_PHYSNET_1",
                       "CUSTOM_VNIC_TYPE_DIRECT"]
      }
  }

Neutron port2::

  {
      'id': '2f2613ce-95a9-490a-b3c4-5f1c28c1f886',
      'resource_request': {
          "resources": {
              "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND": 1000,
              "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND": 2000},
          "required": ["CUSTOM_PHYSNET_1",
                       "CUSTOM_VNIC_TYPE_DIRECT"]
      }
  }


Placement request during scheduling::

  GET /placement/allocation_candidates?
      group_policy=isolate&
      limit=1000&
      resources=DISK_GB=1,MEMORY_MB=512,VCPU=1&
      required1=CUSTOM_PHYSNET_1,CUSTOM_VNIC_TYPE_DIRECT&
      resources1=NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND=1000,
                 NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND=1000&
      required2=CUSTOM_PHYSNET_1,CUSTOM_VNIC_TYPE_DIRECT&
      resources2=NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND=1000,
                 NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND=2000

In the above request the granular request group1 is generated from
port1 and granular request group2 is generated from port2.

Placement response::

  {
     "allocation_requests":[
        {
           "allocations":{
              uuid5(compute1:eth0):{
                "resources":{
                    "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000,
                    "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":1000
                 }
              },
              uuid5(compute1:eth1):{
                "resources":{
                    "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000,
                    "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":2000
                 }
              },
              compute_uuid:{
                 "resources":{
                    "MEMORY_MB":512,
                    "DISK_GB":1,
                    "VCPU":1
                 }
              }
           }
        },
        // ... another similar allocation_request where the allocated
        // amounts are reversed between uuid5(compute1:eth0) and
        // uuid5(compute1:eth1)
     ],
     "provider_summaries":{
         // ...
     }
  }

Filter scheduler selects the first candidate.

Nova needs to find the RP in the selected allocation candidate which
provides the resources for each Neutron port request.

For the selected allocation candidate there are two possible port - RP
mappings but only one valid mapping if we consider the bandwidth
amounts:

* port1 - uuid5(compute1:eth0)
* port2 - uuid5(compute1:eth1)

When Nova tries to map the first port, port1, then both
uuid5(compute1:eth0) and uuid5(compute1:eth1) still has enough
resources in the allocation request to match with the request of port1. So at
that point Nova can map port1 to uuid5(compute1:eth1). However this means
that Nova will not find any viable mapping later for port2 and therefore Nova
has to go back an retry to create the  mapping with port1 mapped to the other
alternative. This means that Nova needs to implement a full backtracking
algorithm to find the proper mapping.

Scaling considerations
......................

With 4 RPs and 4 ports, in worst case, we have 4! (24) possible
mappings and each mappings needs 4 steps to be generated (assuming
that in the worst case the mapping of the 4th port is the one that
fails). So this backtrack makes 96 steps. So I think this code will
scale pretty badly.

Note that our example uses the group_policy=isolate query param
so the RPs in the allocation candidate cannot overlap. If we set
group_policy=none and therefore allow RP overlapping then the necessary
calculation step could grow even more.

Note that even if having more than 4 ports for an server considered
unrealistic, additional granular request groups can appear in the
allocation candidate request from other sources than Neutron, e.g. from flavor
extra_spec due to VGPUs or from Cyborg due to accelerators.

Data model impact
-----------------
None

REST API impact
---------------
Extend the response of the ``GET /allocation_candidates`` API with
an extra field ``mappings`` for each candidate in a new microversion. This
field contains a mapping between resource request group names and RP UUIDs for
each candidate to express which RP provides the resource for which request
groups.

For the request::

  GET /placement/allocation_candidates?
      resources=DISK_GB=1,MEMORY_MB=512,VCPU=1&
      required1=CUSTOM_PHYSNET_1,CUSTOM_VNIC_TYPE_DIRECT&
      resources1=NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND=1000,
                 NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND=1000&
      required2=CUSTOM_PHYSNET_1,CUSTOM_VNIC_TYPE_DIRECT&
      resources2=NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND=1000,
                 NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND=2000

Placement would return the response::

  {
     "allocation_requests":[
        {
           "allocations":{
              uuid5(compute1:eth0):{
                "resources":{
                    "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000,
                    "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":1000
                 },
              },
              uuid5(compute1:eth1):{
                "resources":{
                    "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000,
                    "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":2000
                 },
              },
              compute_uuid:{
                 "resources":{
                    "MEMORY_MB":512,
                    "DISK_GB":1,
                    "VCPU":1
                  },
              }
           },
           "mappings": {
               "1": [uuid5(compute1:eth0)],
               "2": [uuid5(compute1:eth1)],
               "": [compute_uuid],
           },
        },
        {
           "allocations":{
              uuid5(compute1:eth1):{
                "resources":{
                    "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000,
                    "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":1000
                 },
              },
              uuid5(compute1:eth0):{
                "resources":{
                    "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000,
                    "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":2000
                 },
              },
              compute_uuid:{
                 "resources":{
                    "MEMORY_MB":512,
                    "DISK_GB":1,
                    "VCPU":1
                  },
              }
           },
           "mappings": {
               "1": [uuid5(compute1:eth1)],
               "2": [uuid5(compute1:eth0)],
               "": [compute_uuid],
           },
        },
     ],
     "provider_summaries":{
         // unchanged
     }
  }



The numbered groups are always satisfied by a single RP so the length of the
mapping value will be always 1. However the unnumbered group might be satisfied
by more than one RPs so the length of the mapping value there can be bigger
than 1.

This new field will be added to the schema for ``POST /allocations``, ``PUT
/allocations/{consumer_uuid}``, and ``POST /reshaper`` so the client does not
need to strip it from the candidate before posting that back to Placement to
make the allocation. The contents of the field will be ignored by these
operations.

*Alternatively* the mapping can be added as a separate top level key to the
response.

Response::

  {
     "allocation_requests":[
        {
           "allocations":{
              uuid5(compute1:eth0):{
                "resources":{
                    "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000,
                    "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":1000
                 },
              },
              uuid5(compute1:eth1):{
                "resources":{
                    "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000,
                    "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":2000
                 },
              },
              compute_uuid:{
                 "resources":{
                    "MEMORY_MB":512,
                    "DISK_GB":1,
                    "VCPU":1
                  },
              }
           }
        },
        {
           "allocations":{
              uuid5(compute1:eth0):{
                "resources":{
                    "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000,
                    "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":2000
                 },
              },
              uuid5(compute1:eth1):{
                "resources":{
                    "NET_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND":1000,
                    "NET_BANDWIDTH_INGRESS_KILOBITS_PER_SECOND":1000
                 },
              },
              compute_uuid:{
                 "resources":{
                    "MEMORY_MB":512,
                    "DISK_GB":1,
                    "VCPU":1
                  },
              }
           }
        },
     ],
     "provider_summaries":{
         // unchanged
     }

     "resource_provider-request_group-mappings":[
         {
             "1": [uuid5(compute1:eth0)],
             "2": [uuid5(compute1:eth1)],
             "": [compute_uuid],
         },
         {
             "1": [uuid5(compute1:eth1)],
             "2": [uuid5(compute1:eth0)],
             "": [compute_uuid],
         }
     ]
  }


This has the advantage that the allocation requests are unchanged and
therefore still can be transparently sent back to placement
to do the allocation.

This has the disadvantage that one mapping in the
``resource_provider-request_group-mappings`` connected to one candidate
in the allocation_requests list by the list index only.

We decided to go with the primary proposal.

Security impact
---------------
None

Notifications impact
--------------------
None

Other end user impact
---------------------
None

Performance Impact
------------------
None

Other deployer impact
---------------------
None

Developer impact
----------------
None

Upgrade impact
--------------
None

Implementation
==============

Assignee(s)
-----------

Primary assignee:
   None


Work Items
----------

* Extend the `placement allocation candidate generation algorithm`_ to return
  the mapping that is internally calculated.
* Extend the API with a new microversion to return the mapping to the API
  client as well
* Within the same microverison extend the JSON schema for ``POST
  /allocations``, ``PUT /allocations/{uuid}``, and ``POST /reshaper`` to accept
  (and ignore) the mappings key.


Dependencies
============
None

Testing
=======

New gabbi tests for the new API microversion and unit test to cover the
unhappy path.

Documentation Impact
====================

Placement API ref needs to be updated with the new microversion.

References
==========

.. _`building allocations for each granular request group`: https://github.com/openstack/nova/blob/6522ea3ecfe99cca3fb33258b11e5a1f34e6e8f0/nova/api/openstack/placement/objects/resource_provider.py#L4113
.. _`bandwidth resource provider spec`: https://specs.openstack.org/openstack/nova-specs/specs/rocky/approved/bandwidth-resource-provider.html
.. _`current implementation`: https://github.com/openstack/nova/blob/58a1fcc7851930febdb4c1c7ed49357337151f0c/nova/objects/request_spec.py#L761
.. _`placement allocation candidate generation algorithm`: https://github.com/openstack/placement/blob/57026255615679122e6f305dfa3520c012f57ca7/placement/objects/allocation_candidate.py#L207
.. _`Proposed in nova spec repo`: https://review.opendev.org/#/c/597601

History
=======

.. list-table:: Revisions
   :header-rows: 1

   * - Release Name
     - Description
   * - Stein
     - `Proposed in nova spec repo`_ but was not approved
   * - Train
     - Re-proposed in the placement repo
