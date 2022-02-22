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
"""Microversion handling."""

# NOTE(cdent): This code is taken from enamel:
# https://github.com/jaypipes/enamel and was the original source of
# the code now used in microversion_parse library.

import collections
import inspect

import microversion_parse
import webob


SERVICE_TYPE = 'placement'
MICROVERSION_ENVIRON = '%s.microversion' % SERVICE_TYPE
VERSIONED_METHODS = collections.defaultdict(list)

# The Canonical Version List
VERSIONS = [
    '1.0',
    '1.1',  # initial support for aggregate.get_aggregates and set_aggregates
    '1.2',  # Adds /resource_classes resource endpoint
    '1.3',  # Adds 'member_of' query parameter to get resource providers
            # that are members of any of the listed aggregates
    '1.4',  # Adds resources query string parameter in GET /resource_providers
    '1.5',  # Adds DELETE /resource_providers/{uuid}/inventories
    '1.6',  # Adds /traits and /resource_providers{uuid}/traits resource
            # endpoints
    '1.7',  # PUT /resource_classes/{name} is bodiless create or update
    '1.8',  # Adds 'project_id' and 'user_id' required request parameters to
            # PUT /allocations
    '1.9',  # Adds GET /usages
    '1.10',  # Adds GET /allocation_candidates resource endpoint
    '1.11',  # Adds 'allocations' link to the GET /resource_providers response
    '1.12',  # Add project_id and user_id to GET /allocations/{consumer_uuid}
             # and PUT to /allocations/{consumer_uuid} in the same dict form
             # as GET. The 'allocation_requests' format in GET
             # /allocation_candidates is updated to be the same as well.
    '1.13',  # Adds POST /allocations to set allocations for multiple consumers
    '1.14',  # Adds parent and root provider UUID on resource provider
             # representation and 'in_tree' filter on GET /resource_providers
    '1.15',  # Include last-modified and cache-control headers
    '1.16',  # Add 'limit' query parameter to GET /allocation_candidates
    '1.17',  # Add 'required' query parameter to GET /allocation_candidates and
             # return traits in the provider summary.
    '1.18',  # Support ?required=<traits> queryparam on GET /resource_providers
    '1.19',  # Include generation and conflict detection in provider aggregates
             # APIs
    '1.20',  # Return 200 with provider payload from POST /resource_providers
    '1.21',  # Support ?member_of=in:<agg UUIDs> queryparam on
             # GET /allocation_candidates
    '1.22',  # Support forbidden traits in the required parameter of
             # GET /resource_providers and GET /allocation_candidates
    '1.23',  # Add support for error codes in error response JSON
    '1.24',  # Support multiple ?member_of=<agg UUIDs> queryparams on
             # GET /resource_providers
    '1.25',  # Adds support for granular resource requests via numbered
             # querystring groups in GET /allocation_candidates
    '1.26',  # Add ability to specify inventory with reserved value equal to
             # total.
    '1.27',  # Include all resource class inventories in `provider_summaries`
             # field in response of `GET /allocation_candidates` API even if
             # the resource class is not in the requested resources.
    '1.28',  # Add support for consumer generation
    '1.29',  # Support nested providers in GET /allocation_candidates API.
    '1.30',  # Add POST /reshaper for atomically migrating resource provider
             # inventories and allocations.
    '1.31',  # Add in_tree and in_tree<N> queryparam on
             # `GET /allocation_candidates` API
    '1.32',  # Support negative member_of queryparams on
             # `GET /resource_providers` and `GET /allocation_candidates`
    '1.33',  # Support granular resource requests with suffixes that match
             # [A-Za-z0-9_-]{1,64}.
    '1.34',  # Include a mappings key in allocation requests that shows which
             # resource providers satisfied which request group suffix.
    '1.35',  # Add a `root_required` queryparam on `GET /allocation_candidates`
    '1.36',  # Add a `same_subtree` parameter on GET /allocation_candidates
             # and allow resourceless requests for groups in `same_subtree`.
    '1.37',  # Allow re-parenting and un-parenting resource providers
    '1.38',  # Adds ``consumer_type`` (required) key in the request body of
             # ``POST /allocations``, ``PUT /allocations/{consumer_uuid}``
             # and in the response of ``GET /allocations/{consumer_uuid}``.
             # ``GET /usages`` request will also gain ``consumer_type`` key as
             # an optional queryparam to filter usages based on consumer_types.
             # ``GET /usages`` response will group results based on the
             # consumer type and will include a new ``consumer_count`` key per
             # type irrespective of whether the ``consumer_type`` was specified
             # in the request. The corresponding changes to ``/reshaper`` are
             # included.
    '1.39',  # Adds support for the ``in:`` syntax in the ``required`` query
             # parameter in the ``GET /resource_providers`` API as well as to
             # the ``required`` and ``requiredN`` query params of the
             # ``GET /allocation_candidates`` API.
]


def max_version_string():
    return VERSIONS[-1]


def min_version_string():
    return VERSIONS[0]


# Based on code in twisted
# https://github.com/twisted/twisted/blob/trunk/twisted/python/deprecate.py
def _fully_qualified_name(handler):
    """Return the name of a function used as an HTTP API handler, qualified by
    module name.
    """
    if inspect.isfunction(handler):
        module_name = handler.__module__
        return "%s.%s" % (module_name, handler.__name__)

    # We got a class, object method, or module. This is a coding error.
    raise TypeError("_fully_qualified_name received bad handler type. "
                    "Module-level function required.")


def _find_method(qualified_name, version, status_code):
    """Look in VERSIONED_METHODS for method with right name matching version.

    If no match is found a HTTPError corresponding to status_code will
    be returned.
    """
    # A KeyError shouldn't be possible here, but let's be robust
    # just in case.
    method_list = VERSIONED_METHODS.get(qualified_name, [])
    for min_version, max_version, func in method_list:
        if min_version <= version <= max_version:
            return func

    raise webob.exc.status_map[status_code]


def version_handler(min_ver, max_ver=None, status_code=404):
    """Decorator for versioning API methods.

    Add as a decorator to a placement API handler to constrain
    the microversions at which it will run. Add after the
    ``wsgify`` decorator.

    This does not check for version intersections. That's the
    domain of tests.

    :param min_ver: A string of two numerals, X.Y indicating the
                    minimum version allowed for the decorated method.
    :param max_ver: A string of two numerals, X.Y, indicating the
                    maximum version allowed for the decorated method.
    :param status_code: A status code to indicate error, 404 by default
    """
    def decorator(f):
        min_version = microversion_parse.parse_version_string(min_ver)
        if max_ver:
            max_version = microversion_parse.parse_version_string(max_ver)
        else:
            max_version = microversion_parse.parse_version_string(
                max_version_string())
        qualified_name = _fully_qualified_name(f)
        VERSIONED_METHODS[qualified_name].append(
            (min_version, max_version, f))

        def decorated_func(req, *args, **kwargs):
            version = req.environ[MICROVERSION_ENVIRON]
            return _find_method(
                qualified_name, version, status_code)(req, *args, **kwargs)

        # Sort highest min version to beginning of list.
        VERSIONED_METHODS[qualified_name].sort(key=lambda x: x[0],
                                               reverse=True)
        return decorated_func
    return decorator
