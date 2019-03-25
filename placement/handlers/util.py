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

from oslo_log import log as logging
import webob

from placement import errors
from placement import exception
from placement.objects import consumer as consumer_obj
from placement.objects import project as project_obj
from placement.objects import user as user_obj


LOG = logging.getLogger(__name__)


def ensure_consumer(ctx, consumer_uuid, project_id, user_id,
                    consumer_generation, want_version):
    """Ensures there are records in the consumers, projects and users table for
    the supplied external identifiers.

    Returns a tuple containing the populated Consumer object containing Project
    and User sub-objects and a boolean indicating whether a new Consumer object
    was created (as opposed to an existing consumer record retrieved)

    :note: If the supplied project or user external identifiers do not match an
           existing consumer's project and user identifiers, the existing
           consumer's project and user IDs are updated to reflect the supplied
           ones.

    :param ctx: The request context.
    :param consumer_uuid: The uuid of the consumer of the resources.
    :param project_id: The external ID of the project consuming the resources.
    :param user_id: The external ID of the user consuming the resources.
    :param consumer_generation: The generation provided by the user for this
        consumer.
    :param want_version: the microversion matcher.
    :raises webob.exc.HTTPConflict if consumer generation is required and there
            was a mismatch
    """
    created_new_consumer = False
    requires_consumer_generation = want_version.matches((1, 28))
    if project_id is None:
        project_id = ctx.config.placement.incomplete_consumer_project_id
        user_id = ctx.config.placement.incomplete_consumer_user_id
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
        # we will end up deleting the auto-created consumer but we MAY not undo
        # the changes to the second consumer's project and user ID. I say MAY
        # and not WILL NOT because I'm not sure that the exception that gets
        # raised from AllocationList.replace_all() will cause the context
        # manager's transaction to rollback automatically. I believe that the
        # same transaction context is used for both util.ensure_consumer() and
        # AllocationList.replace_all() within the same HTTP request, but need
        # to test this to be 100% certain...
        if (project_id != consumer.project.external_id or
                user_id != consumer.user.external_id):
            LOG.debug("Supplied project or user ID for consumer %s was "
                      "different than existing record. Updating consumer "
                      "record.", consumer_uuid)
            consumer.project = proj
            consumer.user = user
            consumer.update()
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
        # No such consumer. This is common for new allocations. Create the
        # consumer record
        try:
            consumer = consumer_obj.Consumer(
                ctx, uuid=consumer_uuid, project=proj, user=user)
            consumer.create()
            created_new_consumer = True
        except exception.ConsumerExists:
            # No worries, another thread created this user already
            consumer = consumer_obj.Consumer.get_by_uuid(ctx, consumer_uuid)
    return consumer, created_new_consumer
