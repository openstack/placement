# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Symbols intended to be imported by both placement code and placement API
consumers.  When placement is separated out, this module should be part of a
common library that both placement and its consumers can require."""
import re

import webob

from placement.i18n import _
from placement import microversion
from placement import util


# Querystring-related constants
_QS_RESOURCES = 'resources'
_QS_REQUIRED = 'required'
_QS_MEMBER_OF = 'member_of'
_QS_KEY_PATTERN = re.compile(
        r"^(%s)([1-9][0-9]*)?$" % '|'.join(
        (_QS_RESOURCES, _QS_REQUIRED, _QS_MEMBER_OF)))


class RequestGroup(object):
    def __init__(self, use_same_provider=True, resources=None,
                 required_traits=None, forbidden_traits=None, member_of=None):
        """Create a grouping of resource and trait requests.

        :param use_same_provider:
            If True, (the default) this RequestGroup represents requests for
            resources and traits which must be satisfied by a single resource
            provider.  If False, represents a request for resources and traits
            in any resource provider in the same tree, or a sharing provider.
        :param resources: A dict of { resource_class: amount, ... }
        :param required_traits: A set of { trait_name, ... }
        :param forbidden_traits: A set of { trait_name, ... }
        :param member_of: A list of [ [aggregate_UUID],
                                      [aggregate_UUID, aggregate_UUID] ... ]
        """
        self.use_same_provider = use_same_provider
        self.resources = resources or {}
        self.required_traits = required_traits or set()
        self.forbidden_traits = forbidden_traits or set()
        self.member_of = member_of or []

    def __str__(self):
        ret = 'RequestGroup(use_same_provider=%s' % str(self.use_same_provider)
        ret += ', resources={%s}' % ', '.join(
            '%s:%d' % (rc, amount)
            for rc, amount in sorted(list(self.resources.items())))
        ret += ', traits=[%s]' % ', '.join(
            sorted(self.required_traits) +
            ['!%s' % ft for ft in self.forbidden_traits])
        ret += ', aggregates=[%s]' % ', '.join(
            sorted('[%s]' % ', '.join(agglist)
                   for agglist in sorted(self.member_of)))
        ret += ')'
        return ret

    @staticmethod
    def _parse_request_items(req, allow_forbidden):
        ret = {}
        for key, val in req.GET.items():
            match = _QS_KEY_PATTERN.match(key)
            if not match:
                continue
            # `prefix` is 'resources', 'required', or 'member_of'
            # `suffix` is an integer string, or None
            prefix, suffix = match.groups()
            suffix = suffix or ''
            if suffix not in ret:
                ret[suffix] = RequestGroup(use_same_provider=bool(suffix))
            request_group = ret[suffix]
            if prefix == _QS_RESOURCES:
                request_group.resources = util.normalize_resources_qs_param(
                    val)
            elif prefix == _QS_REQUIRED:
                request_group.required_traits = util.normalize_traits_qs_param(
                    val, allow_forbidden=allow_forbidden)
            elif prefix == _QS_MEMBER_OF:
                # special handling of member_of qparam since we allow multiple
                # member_of params at microversion 1.24.
                # NOTE(jaypipes): Yes, this is inefficient to do this when
                # there are multiple member_of query parameters, but we do this
                # so we can error out if someone passes an "orphaned" member_of
                # request group.
                # TODO(jaypipes): Do validation of query parameters using
                # JSONSchema
                request_group.member_of = util.normalize_member_of_qs_params(
                    req, suffix)
        return ret

    @staticmethod
    def _check_for_orphans(by_suffix):
        # Ensure any group with 'required' or 'member_of' also has 'resources'.
        orphans = [('required%s' % suff) for suff, group in by_suffix.items()
                   if group.required_traits and not group.resources]
        if orphans:
            msg = _(
                'All traits parameters must be associated with resources.  '
                'Found the following orphaned traits keys: %s')
            raise webob.exc.HTTPBadRequest(msg % ', '.join(orphans))
        orphans = [('member_of%s' % suff) for suff, group in by_suffix.items()
                   if group.member_of and not group.resources]
        if orphans:
            msg = _('All member_of parameters must be associated with '
                    'resources. Found the following orphaned member_of '
                    'keys: %s')
            raise webob.exc.HTTPBadRequest(msg % ', '.join(orphans))
        # All request groups must have resources (which is almost, but not
        # quite, verified by the orphan checks above).
        if not all(grp.resources for grp in by_suffix.values()):
            msg = _("All request groups must specify resources.")
            raise webob.exc.HTTPBadRequest(msg)
        # The above would still pass if there were no request groups
        if not by_suffix:
            msg = _(
                "At least one request group (`resources` or `resources{N}`) "
                "is required.")
            raise webob.exc.HTTPBadRequest(msg)

    @staticmethod
    def _fix_forbidden(by_suffix):
        conflicting_traits = []
        for suff, group in by_suffix.items():
            forbidden = [trait for trait in group.required_traits
                         if trait.startswith('!')]
            group.required_traits = (
                    group.required_traits - set(forbidden))
            group.forbidden_traits = set([trait.lstrip('!') for trait in
                                          forbidden])
            conflicts = group.forbidden_traits & group.required_traits
            if conflicts:
                conflicting_traits.append('required%s: (%s)'
                                          % (suff, ', '.join(conflicts)))
        if conflicting_traits:
            msg = _(
                'Conflicting required and forbidden traits found in the '
                'following traits keys: %s')
            raise webob.exc.HTTPBadRequest(
                msg % ', '.join(conflicting_traits))

    @classmethod
    def dict_from_request(cls, req):
        """Parse numbered resources, traits, and member_of groupings out of a
        querystring dict found in a webob Request.

        The input req contains a query string of the form:

        ?resources=$RESOURCE_CLASS_NAME:$AMOUNT,$RESOURCE_CLASS_NAME:$AMOUNT
        &required=$TRAIT_NAME,$TRAIT_NAME&member_of=in:$AGG1_UUID,$AGG2_UUID
        &resources1=$RESOURCE_CLASS_NAME:$AMOUNT,RESOURCE_CLASS_NAME:$AMOUNT
        &required1=$TRAIT_NAME,$TRAIT_NAME&member_of1=$AGG_UUID
        &resources2=$RESOURCE_CLASS_NAME:$AMOUNT,RESOURCE_CLASS_NAME:$AMOUNT
        &required2=$TRAIT_NAME,$TRAIT_NAME&member_of2=$AGG_UUID

        These are parsed in groups according to the numeric suffix of the key.
        For each group, a RequestGroup instance is created containing that
        group's resources, required traits, and member_of. For the (single)
        group with no suffix, the RequestGroup.use_same_provider attribute is
        False; for the numbered groups it is True.

        If a trait in the required parameter is prefixed with ``!`` this
        indicates that that trait must not be present on the resource
        providers in the group. That is, the trait is forbidden. Forbidden
        traits are only processed  if ``allow_forbidden`` is True. This allows
        the caller to control processing based on microversion handling.

        The return is a dict, keyed by the numeric suffix of these RequestGroup
        instances (or the empty string for the unnumbered group).

        As an example, if qsdict represents the query string:

        ?resources=VCPU:2,MEMORY_MB:1024,DISK_GB=50
        &required=HW_CPU_X86_VMX,CUSTOM_STORAGE_RAID
        &member_of=9323b2b1-82c9-4e91-bdff-e95e808ef954
        &member_of=in:8592a199-7d73-4465-8df6-ab00a6243c82,ddbd9226-d6a6-475e-a85f-0609914dd058   # noqa
        &resources1=SRIOV_NET_VF:2
        &required1=CUSTOM_PHYSNET_PUBLIC,CUSTOM_SWITCH_A
        &resources2=SRIOV_NET_VF:1
        &required2=!CUSTOM_PHYSNET_PUBLIC

        ...the return value will be:

        { '': RequestGroup(
                  use_same_provider=False,
                  resources={
                      "VCPU": 2,
                      "MEMORY_MB": 1024,
                      "DISK_GB" 50,
                  },
                  required_traits=[
                      "HW_CPU_X86_VMX",
                      "CUSTOM_STORAGE_RAID",
                  ],
                  member_of=[
                    [9323b2b1-82c9-4e91-bdff-e95e808ef954],
                    [8592a199-7d73-4465-8df6-ab00a6243c82,
                     ddbd9226-d6a6-475e-a85f-0609914dd058],
                  ],
              ),
          '1': RequestGroup(
                  use_same_provider=True,
                  resources={
                      "SRIOV_NET_VF": 2,
                  },
                  required_traits=[
                      "CUSTOM_PHYSNET_PUBLIC",
                      "CUSTOM_SWITCH_A",
                  ],
               ),
          '2': RequestGroup(
                  use_same_provider=True,
                  resources={
                      "SRIOV_NET_VF": 1,
                  },
                  forbidden_traits=[
                      "CUSTOM_PHYSNET_PUBLIC",
                  ],
               ),
        }

        :param req: webob.Request object
        :return: A dict, keyed by suffix, of RequestGroup instances.
        :raises `webob.exc.HTTPBadRequest` if any value is malformed, or if a
                trait list is given without corresponding resources.
        """
        want_version = req.environ[microversion.MICROVERSION_ENVIRON]
        # Control whether we handle forbidden traits.
        allow_forbidden = want_version.matches((1, 22))
        # dict of the form: { suffix: RequestGroup } to be returned
        by_suffix = cls._parse_request_items(req, allow_forbidden)

        cls._check_for_orphans(by_suffix)

        # Make adjustments for forbidden traits by stripping forbidden out
        # of required.
        if allow_forbidden:
            cls._fix_forbidden(by_suffix)

        return by_suffix
