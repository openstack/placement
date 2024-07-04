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

from placement import errors
from placement import microversion
from placement.schemas import common
from placement import util


# Querystring-related constants
_QS_RESOURCES = 'resources'
_QS_REQUIRED = 'required'
_QS_MEMBER_OF = 'member_of'
_QS_IN_TREE = 'in_tree'
_QS_KEY_PATTERN = re.compile(
    r"^(%s)(%s)?$" % ('|'.join(
        (_QS_RESOURCES, _QS_REQUIRED, _QS_MEMBER_OF, _QS_IN_TREE)),
        common.GROUP_PAT))
_QS_KEY_PATTERN_1_33 = re.compile(
    r"^(%s)(%s)?$" % ('|'.join(
        (_QS_RESOURCES, _QS_REQUIRED, _QS_MEMBER_OF, _QS_IN_TREE)),
        common.GROUP_PAT_1_33))

# In newer microversion we no longer check for orphaned member_of
# and required because "providers providing no inventory to this
# request" are now legit with `same_subtree` queryparam accompanied.
SAME_SUBTREE_VERSION = (1, 36)


def _fix_one_forbidden(traits):
    forbidden = [trait for trait in traits if trait.startswith('!')]
    required = traits - set(forbidden)
    forbidden = set(trait.lstrip('!') for trait in forbidden)
    conflicts = forbidden & required
    return required, forbidden, conflicts


class RequestGroup(object):
    def __init__(self, use_same_provider=True, resources=None,
                 required_traits=None, forbidden_traits=None, member_of=None,
                 in_tree=None, forbidden_aggs=None):
        """Create a grouping of resource and trait requests.

        :param use_same_provider:
            If True, (the default) this RequestGroup represents requests for
            resources and traits which must be satisfied by a single resource
            provider.  If False, represents a request for resources and traits
            in any resource provider in the same tree, or a sharing provider.
        :param resources: A dict of { resource_class: amount, ... }
        :param required_traits: A list of set of trait names. E.g.:
            [{T1, T2}, {T3}] means ((T1 or T2) and T3)
        :param forbidden_traits: A set of { trait_name, ... }
        :param member_of: A list of [ [aggregate_UUID],
                                      [aggregate_UUID, aggregate_UUID] ... ]
        :param in_tree: A UUID of a root or a non-root provider from whose
                        tree this RequestGroup must be satisfied.
        """
        self.use_same_provider = use_same_provider
        self.resources = resources or {}
        self.required_traits = required_traits or []
        self.forbidden_traits = forbidden_traits or set()
        self.member_of = member_of or []
        self.in_tree = in_tree
        self.forbidden_aggs = forbidden_aggs or set()

    def __str__(self):
        ret = 'RequestGroup(use_same_provider=%s' % str(self.use_same_provider)
        ret += ', resources={%s}' % ', '.join(
            '%s:%d' % (rc, amount)
            for rc, amount in sorted(list(self.resources.items())))

        all_traits = set()
        fragments = []
        for any_traits in self.required_traits:
            if len(any_traits) == 1:
                all_traits.add(list(any_traits)[0])
            else:
                fragments.append('(' + ' or '.join(sorted(any_traits)) + ')')

        if all_traits:
            fragments.append(', '.join(trait for trait in sorted(all_traits)))
        if self.forbidden_traits:
            fragments.append(
                ', '.join(
                    '!' + trait for trait in sorted(self.forbidden_traits)))

        ret += ', traits=(%s)' % ' and '.join(fragments)

        ret += ', aggregates=[%s]' % ', '.join(
            sorted('[%s]' % ', '.join(sorted(agglist))
                   for agglist in sorted(self.member_of)))
        ret += ')'
        return ret

    @staticmethod
    def _parse_request_items(req, verbose_suffix):
        ret = {}
        pattern = _QS_KEY_PATTERN_1_33 if verbose_suffix else _QS_KEY_PATTERN
        for key, val in req.GET.items():
            match = pattern.match(key)
            if not match:
                continue
            # `prefix` is 'resources', 'required', 'member_of', or 'in_tree'
            # `suffix` is a number in microversion < 1.33, a string 1-64
            # characters long of [a-zA-Z0-9_-] in microversion >= 1.33, or None
            prefix, suffix = match.groups()
            suffix = suffix or ''
            if suffix not in ret:
                ret[suffix] = RequestGroup(use_same_provider=bool(suffix))
            request_group = ret[suffix]
            if prefix == _QS_RESOURCES:
                request_group.resources = util.normalize_resources_qs_param(
                    val)
            elif prefix == _QS_REQUIRED:
                (
                    request_group.required_traits,
                    request_group.forbidden_traits,
                ) = util.normalize_traits_qs_params(req, suffix)
            elif prefix == _QS_MEMBER_OF:
                # special handling of member_of qparam since we allow multiple
                # member_of params at microversion 1.24.
                # NOTE(jaypipes): Yes, this is inefficient to do this when
                # there are multiple member_of query parameters, but we do this
                # so we can error out if someone passes an "orphaned" member_of
                # request group.
                # TODO(jaypipes): Do validation of query parameters using
                # JSONSchema
                request_group.member_of, request_group.forbidden_aggs = (
                    util.normalize_member_of_qs_params(req, suffix))
            elif prefix == _QS_IN_TREE:
                request_group.in_tree = util.normalize_in_tree_qs_params(
                    val)
        return ret

    @staticmethod
    def _check_for_one_resources(by_suffix, resourceless_suffixes):
        if len(resourceless_suffixes) == len(by_suffix):
            msg = ('There must be at least one resources or resources[$S] '
                   'parameter.')
            raise webob.exc.HTTPBadRequest(
                msg, comment=errors.QUERYPARAM_MISSING_VALUE)

    @staticmethod
    def _check_resourceless_suffix(subtree_suffixes, resourceless_suffixes):
        bad_suffixes = [suffix for suffix in resourceless_suffixes
                        if suffix not in subtree_suffixes]
        if bad_suffixes:
            msg = ("Resourceless suffixed group request should be specified "
                   "in `same_subtree` query param: bad group(s) - "
                   "%(suffixes)s.") % {'suffixes': bad_suffixes}
            raise webob.exc.HTTPBadRequest(
                msg, comment=errors.QUERYPARAM_BAD_VALUE)

    @staticmethod
    def _check_actual_suffix(subtree_suffixes, by_suffix):
        bad_suffixes = [suffix for suffix in subtree_suffixes
                        if suffix not in by_suffix]
        if bad_suffixes:
            msg = ("Real suffixes should be specified in `same_subtree`: "
                   "%(bad_suffixes)s not found in %(suffixes)s.") % {
                'bad_suffixes': bad_suffixes,
                'suffixes': list(by_suffix.keys())}
            raise webob.exc.HTTPBadRequest(
                msg, comment=errors.QUERYPARAM_BAD_VALUE)

    @staticmethod
    def _check_for_orphans(by_suffix):
        # Ensure any group with 'required' or 'member_of' also has 'resources'.
        orphans = [('required%s' % suff) for suff, group in by_suffix.items()
                   if group.required_traits and not group.resources]
        if orphans:
            msg = (
                'All traits parameters must be associated with resources.  '
                'Found the following orphaned traits keys: %s')
            raise webob.exc.HTTPBadRequest(msg % ', '.join(orphans))
        orphans = [('member_of%s' % suff) for suff, group in by_suffix.items()
                   if not group.resources and (
                       group.member_of or group.forbidden_aggs)]
        if orphans:
            msg = ('All member_of parameters must be associated with '
                   'resources. Found the following orphaned member_of '
                   'keys: %s')
            raise webob.exc.HTTPBadRequest(msg % ', '.join(orphans))
        # All request groups must have resources (which is almost, but not
        # quite, verified by the orphan checks above).
        if not all(grp.resources for grp in by_suffix.values()):
            msg = "All request groups must specify resources."
            raise webob.exc.HTTPBadRequest(msg)
        # The above would still pass if there were no request groups
        if not by_suffix:
            msg = (
                "At least one request group (`resources` or `resources{$S}`) "
                "is required.")
            raise webob.exc.HTTPBadRequest(msg)

    @staticmethod
    def _check_forbidden(by_suffix):
        conflicting_traits = []
        for suff, group in by_suffix.items():

            for any_traits in group.required_traits:
                if all(
                        trait in group.forbidden_traits
                        for trait in any_traits
                ):
                    conflicting_traits.append(
                        'required%s: (%s)' %
                        (suff, ', '.join(sorted(any_traits))))

        if conflicting_traits:
            msg = (
                'Conflicting required and forbidden traits found in the '
                'following traits keys: %s')
            # TODO(efried): comment=errors.QUERYPARAM_BAD_VALUE
            raise webob.exc.HTTPBadRequest(
                msg % ', '.join(sorted(conflicting_traits)))

    @classmethod
    def dict_from_request(cls, req, rqparams):
        """Parse suffixed resources, traits, and member_of groupings out of a
        querystring dict found in a webob Request.

        The input req contains a query string of the form:

        ?resources=$RESOURCE_CLASS_NAME:$AMOUNT,$RESOURCE_CLASS_NAME:$AMOUNT
        &required=$TRAIT_NAME,$TRAIT_NAME&member_of=in:$AGG1_UUID,$AGG2_UUID
        &in_tree=$RP_UUID
        &resources1=$RESOURCE_CLASS_NAME:$AMOUNT,RESOURCE_CLASS_NAME:$AMOUNT
        &required1=$TRAIT_NAME,$TRAIT_NAME&member_of1=$AGG_UUID
        &resources2=$RESOURCE_CLASS_NAME:$AMOUNT,RESOURCE_CLASS_NAME:$AMOUNT
        &required2=$TRAIT_NAME,$TRAIT_NAME&member_of2=$AGG_UUID
        &required2=in:$TRAIT_NAME,$TRAIT_NAME

        These are parsed in groups according to the arbitrary suffix of the key.
        For each group, a RequestGroup instance is created containing that
        group's resources, required traits, and member_of. For the (single)
        group with no suffix, the RequestGroup.use_same_provider attribute is
        False; for the granular groups it is True.

        If a trait in the required parameter is prefixed with ``!`` this
        indicates that that trait must not be present on the resource
        providers in the group. That is, the trait is forbidden. Forbidden
        traits are processed only if the microversion supports.

        If the value of a `required*` is prefixed with 'in:' then the traits in
        the value are ORred together.

        The return is a dict, keyed by the suffix of these RequestGroup
        instances (or the empty string for the unidentified group).

        As an example, if qsdict represents the query string:

        ?resources=VCPU:2,MEMORY_MB:1024,DISK_GB=50
        &required=HW_CPU_X86_VMX,CUSTOM_STORAGE_RAID
        &member_of=9323b2b1-82c9-4e91-bdff-e95e808ef954
        &member_of=in:8592a199-7d73-4465-8df6-ab00a6243c82,ddbd9226-d6a6-475e-a85f-0609914dd058   # noqa
        &in_tree=b9fc9abb-afc2-44d7-9722-19afc977446a
        &resources1=SRIOV_NET_VF:2
        &required1=CUSTOM_PHYSNET_PUBLIC,CUSTOM_SWITCH_A
        &resources2=SRIOV_NET_VF:1
        &required2=!CUSTOM_PHYSNET_PUBLIC
        &required2=CUSTOM_GOLD
        &required2=in:CUSTOM_FOO,CUSTOM_BAR

        ...the return value will be:

        { '': RequestGroup(
                  use_same_provider=False,
                  resources={
                      "VCPU": 2,
                      "MEMORY_MB": 1024,
                      "DISK_GB" 50,
                  },
                  required_traits=[
                      {"HW_CPU_X86_VMX"},
                      {"CUSTOM_STORAGE_RAID"},
                  ],
                  member_of=[
                    [9323b2b1-82c9-4e91-bdff-e95e808ef954],
                    [8592a199-7d73-4465-8df6-ab00a6243c82,
                     ddbd9226-d6a6-475e-a85f-0609914dd058],
                  ],
                  in_tree=b9fc9abb-afc2-44d7-9722-19afc977446a,
              ),
          '1': RequestGroup(
                  use_same_provider=True,
                  resources={
                      "SRIOV_NET_VF": 2,
                  },
                  required_traits=[
                      {"CUSTOM_PHYSNET_PUBLIC"},
                      {"CUSTOM_SWITCH_A"},
                  ],
               ),
          '2': RequestGroup(
                  use_same_provider=True,
                  resources={
                      "SRIOV_NET_VF": 1,
                  },
                  required_traits=[
                      {"CUSTOM_GOLD"},
                      {"CUSTOM_FOO", "CUSTOM_BAR"},
                  forbidden_traits=[
                      "CUSTOM_PHYSNET_PUBLIC",
                  ],
               ),
        }

        :param req: webob.Request object
        :param rqparams: RequestWideParams object
        :return: A dict, keyed by suffix, of RequestGroup instances.
        :raises `webob.exc.HTTPBadRequest` if any value is malformed, or if
                the suffix of a resourceless request is not in the
                `rqparams.same_subtrees`.
        """
        want_version = req.environ[microversion.MICROVERSION_ENVIRON]
        # Control whether we handle forbidden traits.
        allow_forbidden = want_version.matches((1, 22))
        # Control whether we want verbose suffixes
        verbose_suffix = want_version.matches((1, 33))
        # dict of the form: { suffix: RequestGroup } to be returned
        by_suffix = cls._parse_request_items(req, verbose_suffix)

        if want_version.matches(SAME_SUBTREE_VERSION):
            resourceless_suffixes = set(
                suffix for suffix, grp in by_suffix.items()
                if not grp.resources)
            subtree_suffixes = set().union(*rqparams.same_subtrees)
            cls._check_for_one_resources(by_suffix, resourceless_suffixes)
            cls._check_resourceless_suffix(
                subtree_suffixes, resourceless_suffixes)
            cls._check_actual_suffix(subtree_suffixes, by_suffix)
        else:
            cls._check_for_orphans(by_suffix)

        # check conflicting traits in the request
        if allow_forbidden:
            cls._check_forbidden(by_suffix)

        return by_suffix


class RequestWideParams(object):
    """GET /allocation_candidates params that apply to the request as a whole.

    This is in contrast with individual request groups (list of RequestGroup
    above).
    """

    def __init__(self, limit=None, group_policy=None,
                 anchor_required_traits=None, anchor_forbidden_traits=None,
                 same_subtrees=None):
        """Create a RequestWideParams.

        :param limit: An integer, N, representing the maximum number of
                allocation candidates to return. If
                CONF.placement.randomize_allocation_candidates is True this
                will be a random sampling of N of the available results. If
                False then the first N results, in whatever order the database
                picked them, will be returned. In either case if there are
                fewer than N total results, all the results will be returned.
        :param group_policy: String indicating how RequestGroups with
                use_same_provider=True should interact with each other. If the
                value is "isolate", we will filter out allocation requests
                where any such RequestGroups are satisfied by the same RP.
        :param anchor_required_traits: Set of trait names which the anchor of
                each returned allocation candidate must possess, regardless of
                any RequestGroup filters. Note that anchor_required_traits
                does not support the any-trait format the
                RequestGroup.required_traits does.
        :param anchor_forbidden_traits: Set of trait names which the anchor of
                each returned allocation candidate must NOT possess, regardless
                of any RequestGroup filters.
        :param same_subtrees: A list of sets of request group suffix strings
                where each set of strings represents the suffixes from one
                same_subtree query param. If provided, all of the resource
                providers satisfying the specified request groups must be
                rooted at one of the resource providers satisfying the request
                groups.
        """
        self.limit = limit
        self.group_policy = group_policy
        self.anchor_required_traits = anchor_required_traits
        self.anchor_forbidden_traits = anchor_forbidden_traits
        self.same_subtrees = same_subtrees or []

    @classmethod
    def from_request(cls, req):
        # TODO(efried): Make it an error to specify limit more than once -
        #  maybe when we make group_policy optional.
        limit = req.GET.getall('limit')
        # JSONschema has already confirmed that limit has the form
        # of an integer.
        if limit:
            limit = int(limit[0])

        # TODO(efried): Make it an error to specify group_policy more than once
        #  - maybe when we make it optional.
        group_policy = req.GET.getall('group_policy') or None
        # Schema ensures we get either "none" or "isolate"
        if group_policy:
            group_policy = group_policy[0]

        anchor_required_traits = None
        anchor_forbidden_traits = None
        root_required = req.GET.getall('root_required')
        if root_required:
            if len(root_required) > 1:
                raise webob.exc.HTTPBadRequest(
                    "Query parameter 'root_required' may be specified only "
                    "once.", comment=errors.ILLEGAL_DUPLICATE_QUERYPARAM)
            # NOTE(gibi): root_required does not support any-traits so here
            # we continue using the old query parsing function that does not
            # accept the `in:` prefix and that always returns a flat trait
            # list
            anchor_required_traits, anchor_forbidden_traits, conflicts = (
                _fix_one_forbidden(
                    util.normalize_traits_qs_param_to_legacy_value(
                        root_required[0], allow_forbidden=True)))
            if conflicts:
                raise webob.exc.HTTPBadRequest(
                    'Conflicting required and forbidden traits found in '
                    'root_required: %s' % ', '.join(conflicts),
                    comment=errors.QUERYPARAM_BAD_VALUE)

        same_subtree = req.GET.getall('same_subtree')
        # Construct a list of sets of request group suffixes strings.
        same_subtrees = []
        if same_subtree:
            for val in same_subtree:
                suffixes = set(substr.strip() for substr in val.split(','))
                if '' in suffixes:
                    raise webob.exc.HTTPBadRequest(
                        'Empty string (unsuffixed group) can not be specified '
                        'in `same_subtree` ',
                        comment=errors.QUERYPARAM_BAD_VALUE)
                same_subtrees.append(suffixes)

        return cls(
            limit=limit,
            group_policy=group_policy,
            anchor_required_traits=anchor_required_traits,
            anchor_forbidden_traits=anchor_forbidden_traits,
            same_subtrees=same_subtrees)
