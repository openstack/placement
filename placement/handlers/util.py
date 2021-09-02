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
"""DB Utility methods for placement."""

import collections

from oslo_log import log as logging
import webob

from placement import errors
from placement import exception
from placement.objects import consumer as consumer_obj
from placement.objects import consumer_type as consumer_type_obj
from placement.objects import project as project_obj
from placement.objects import user as user_obj


LOG = logging.getLogger(__name__)

RequestAttr = collections.namedtuple('RequestAttr',
                                     ['project', 'user', 'consumer_type_id'])


def get_or_create_consumer_type_id(ctx, name):
    """Tries to fetch the provided consumer_type and creates a new one if it
    does not exist.

    :param ctx: The request context.
    :param name: The name of the consumer type.
    :returns: The id of the ConsumerType object.
    """
    try:
        return ctx.ct_cache.id_from_string(name)
    except exception.ConsumerTypeNotFound:
        cons_type = consumer_type_obj.ConsumerType(ctx, name=name)
        try:
            cons_type.create()
            return cons_type.id
        except exception.ConsumerTypeExists:
            # another thread created concurrently, so try again
            return get_or_create_consumer_type_id(ctx, name)


def _get_or_create_project(ctx, project_id):
    try:
        proj = project_obj.Project.get_by_external_id(ctx, project_id)
    except exception.NotFound:
        # Auto-create the project if we found no record of it...
        try:
            proj = project_obj.Project(ctx, external_id=project_id)
            proj.create()
        except exception.ProjectExists:
            # No worries, another thread created this project already
            proj = project_obj.Project.get_by_external_id(ctx, project_id)
    return proj


def _get_or_create_user(ctx, user_id):
    try:
        user = user_obj.User.get_by_external_id(ctx, user_id)
    except exception.NotFound:
        # Auto-create the user if we found no record of it...
        try:
            user = user_obj.User(ctx, external_id=user_id)
            user.create()
        except exception.UserExists:
            # No worries, another thread created this user already
            user = user_obj.User.get_by_external_id(ctx, user_id)
    return user


def _create_consumer(ctx, consumer_uuid, project, user, consumer_type_id):
    created_new_consumer = False
    try:
        consumer = consumer_obj.Consumer(
            ctx, uuid=consumer_uuid, project=project, user=user,
            consumer_type_id=consumer_type_id)
        consumer.create()
        created_new_consumer = True
    except exception.ConsumerExists:
        # Another thread created this consumer already, verify whether
        # the consumer type matches
        consumer = consumer_obj.Consumer.get_by_uuid(ctx, consumer_uuid)
        # If the types don't match, update the consumer record
        if consumer_type_id != consumer.consumer_type_id:
            LOG.debug("Supplied consumer type for consumer %s was "
                      "different than existing record. Updating "
                      "consumer record.", consumer_uuid)
            consumer.consumer_type_id = consumer_type_id
            consumer.update()
    return consumer, created_new_consumer


def ensure_consumer(ctx, consumer_uuid, project_id, user_id,
                    consumer_generation, consumer_type, want_version):
    """Ensures there are records in the consumers, projects and users table for
    the supplied external identifiers.

    Returns a 3-tuple containing:
        - the populated Consumer object containing Project and User sub-objects
        - a boolean indicating whether a new Consumer object was created
          (as opposed to an existing consumer record retrieved)
        - a dict of RequestAttr objects by consumer_uuid which contains the
          requested Project, User, and consumer type ID (which may be different
          than what is contained in an existing consumer record retrieved)

    :param ctx: The request context.
    :param consumer_uuid: The uuid of the consumer of the resources.
    :param project_id: The external ID of the project consuming the resources.
    :param user_id: The external ID of the user consuming the resources.
    :param consumer_generation: The generation provided by the user for this
        consumer.
    :param consumer_type: The type of consumer provided by the user.
    :param want_version: the microversion matcher.
    :raises webob.exc.HTTPConflict if consumer generation is required and there
            was a mismatch
    """
    created_new_consumer = False
    requires_consumer_generation = want_version.matches((1, 28))
    requires_consumer_type = want_version.matches((1, 38))
    if project_id is None:
        project_id = ctx.config.placement.incomplete_consumer_project_id
        user_id = ctx.config.placement.incomplete_consumer_user_id
    proj = _get_or_create_project(ctx, project_id)
    user = _get_or_create_user(ctx, user_id)

    cons_type_id = None

    try:
        consumer = consumer_obj.Consumer.get_by_uuid(ctx, consumer_uuid)
        if requires_consumer_generation:
            if consumer.generation != consumer_generation:
                raise webob.exc.HTTPConflict(
                    'consumer generation conflict - '
                    'expected %(expected_gen)s but got %(got_gen)s' %
                    {
                        'expected_gen': consumer.generation,
                        'got_gen': consumer_generation,
                    },
                    comment=errors.CONCURRENT_UPDATE)
        if requires_consumer_type:
            cons_type_id = get_or_create_consumer_type_id(ctx, consumer_type)
    except exception.NotFound:
        # If we are attempting to modify or create allocations after 1.26, we
        # need a consumer generation specified. The user must have specified
        # None for the consumer generation if we get here, since there was no
        # existing consumer with this UUID and therefore the user should be
        # indicating that they expect the consumer did not exist.
        if requires_consumer_generation:
            if consumer_generation is not None:
                raise webob.exc.HTTPConflict(
                    'consumer generation conflict - '
                    'expected null but got %s' % consumer_generation,
                    comment=errors.CONCURRENT_UPDATE)

        if requires_consumer_type:
            cons_type_id = get_or_create_consumer_type_id(ctx, consumer_type)
        # No such consumer. This is common for new allocations. Create the
        # consumer record
        consumer, created_new_consumer = _create_consumer(
            ctx, consumer_uuid, proj, user, cons_type_id)

    # Also return the project, user, and consumer type from the request to use
    # for rollbacks.
    request_attr = RequestAttr(proj, user, cons_type_id)

    return consumer, created_new_consumer, request_attr


def update_consumers(consumers, request_attrs):
    """Update consumers with the requested Project, User, and consumer type ID
    if they are different.

    If the supplied project or user external identifiers do not match an
    existing consumer's project and user identifiers, the existing consumer's
    project and user IDs are updated to reflect the supplied ones.

    If the supplied consumer types do not match an existing consumer's consumer
    type, the existing consumer's consumer types are updated to reflect the
    supplied ones.

    :param consumers: a list of Consumer objects
    :param request_attrs: a dict of RequestAttr objects by consumer_uuid
    """
    for consumer in consumers:
        request_attr = request_attrs[consumer.uuid]
        project = request_attr.project
        user = request_attr.user
        # Note: this can be None if the request microversion is < 1.38.
        consumer_type_id = request_attr.consumer_type_id

        # NOTE(jaypipes): The user may have specified a different project and
        # user external ID than the one that we had for the consumer. If this
        # is the case, go ahead and modify the consumer record with the
        # newly-supplied project/user information, but do not bump the consumer
        # generation (since it will be bumped in the
        # AllocationList.replace_all() method).
        #
        # TODO(jaypipes): This means that there may be a partial update.
        # Imagine a scenario where a user calls POST /allocations, and the
        # payload references two consumers. The first consumer is a new
        # consumer and is auto-created. The second consumer is an existing
        # consumer, but contains a different project or user ID than the
        # existing consumer's record. If the eventual call to
        # AllocationList.replace_all() fails for whatever reason (say, a
        # resource provider generation conflict or out of resources failure),
        # we will end up deleting the auto-created consumer and we will undo
        # the changes to the second consumer's project and user ID.
        #
        # NOTE(melwitt): The aforementioned rollback of changes is predicated
        # on the fact that the same transaction context is used for both
        # util.update_consumers() and AllocationList.replace_all() within the
        # same HTTP request. The @db_api.placement_context_manager.writer
        # decorator on the outermost method will nest to methods called within
        # the outermost method.
        if (project.external_id != consumer.project.external_id or
                user.external_id != consumer.user.external_id):
            LOG.debug("Supplied project or user ID for consumer %s was "
                      "different than existing record. Updating consumer "
                      "record.", consumer.uuid)
            consumer.project = project
            consumer.user = user
            consumer.update()

        # Update the consumer type if it's different than the existing one.
        if consumer_type_id and consumer_type_id != consumer.consumer_type_id:
            LOG.debug("Supplied consumer type for consumer %s was "
                      "different than existing record. Updating "
                      "consumer record.", consumer.uuid)
            consumer.consumer_type_id = consumer_type_id
            consumer.update()
