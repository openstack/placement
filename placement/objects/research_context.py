#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""Utility methods for getting allocation candidates."""

from oslo_log import log as logging

from placement import exception
from placement.objects import resource_provider as rp_obj
from placement.objects import trait as trait_obj
from placement import resource_class_cache as rc_cache


LOG = logging.getLogger(__name__)


class RequestGroupSearchContext(object):
    """An adapter object that represents the search for allocation candidates
    for a single request group.
    """
    def __init__(self, context, request, has_trees):
        """Initializes the object retrieving and caching matching providers
        for each conditions like resource and aggregates from database.

        :raises placement.exception.ResourceProviderNotFound if there is no
                provider found which satisfies the request.
        """
        # TODO(tetsuro): split this into smaller functions reordering
        self.context = context

        # A dict, keyed by resource class internal ID, of the amounts of that
        # resource class being requested by the group.
        self.resources = {
            rc_cache.RC_CACHE.id_from_string(key): value
            for key, value in request.resources.items()
        }

        # A list of lists of aggregate UUIDs that the providers matching for
        # that request group must be members of
        self.member_of = request.member_of

        # A list of aggregate UUIDs that the providers matching for
        # that request group must not be members of
        self.forbidden_aggs = request.forbidden_aggs

        # If True, this RequestGroup represents requests which must be
        # satisfied by a single resource provider.  If False, represents a
        # request for resources in any resource provider in the same tree,
        # or a sharing provider.
        self.use_same_provider = request.use_same_provider

        # maps the trait name to the trait internal ID
        self.required_trait_map = {}
        self.forbidden_trait_map = {}
        for trait_map, traits in (
                (self.required_trait_map, request.required_traits),
                (self.forbidden_trait_map, request.forbidden_traits)):
            if traits:
                trait_map.update(trait_obj.ids_from_names(context, traits))

        # Internal id of a root provider. If provided, this RequestGroup must
        # be satisfied by resource provider(s) under the root provider.
        self.tree_root_id = None
        if request.in_tree:
            tree_ids = rp_obj.provider_ids_from_uuid(context, request.in_tree)
            if tree_ids is None:
                raise exception.ResourceProviderNotFound()
            self.tree_root_id = tree_ids.root_id
            LOG.debug("getting allocation candidates in the same tree "
                      "with the root provider %s", tree_ids.root_uuid)

        # a dict, keyed by resource class ID, of the set of resource
        # provider IDs that share some inventory for each resource class
        # This is only used for unnumbered request group path where
        # use_same_provider is set to False
        self._sharing_providers = {}
        if not self.use_same_provider:
            for rc_id, amount in self.resources.items():
                # We may want to have a concept of "sharable resource class"
                # so that we can skip this lookup.
                # if not rc_id in (sharable_rc_ids):
                #     continue
                self._sharing_providers[rc_id] = \
                    rp_obj.get_providers_with_shared_capacity(
                        context, rc_id, amount, self.member_of)

        # bool indicating there is some level of nesting in the environment
        self.has_trees = has_trees

    @property
    def exists_sharing(self):
        """bool indicating there is sharing providers in the environment for
        the requested resource class (if there isn't, we take faster, simpler
        code paths)
        """
        return any(self._sharing_providers.values())

    @property
    def exists_nested(self):
        """bool indicating there is some level of nesting in the environment
        (if there isn't, we take faster, simpler code paths)
        """
        # NOTE: This could be refactored to see the requested resources
        return self.has_trees

    def get_rps_with_shared_capacity(self, rc_id):
        return self._sharing_providers.get(rc_id)
