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

import sqlalchemy as sa
from sqlalchemy import distinct
from sqlalchemy import func
from sqlalchemy import sql

from placement.db.sqlalchemy import models
from placement import db_api
from placement.objects import consumer_type as consumer_type_obj


class Usage(object):

    def __init__(self, resource_class=None, usage=0, consumer_type=None,
                 consumer_count=0):
        self.resource_class = resource_class
        self.usage = int(usage)
        self.consumer_type = (consumer_type or
                              consumer_type_obj.NULL_CONSUMER_TYPE_ALIAS)
        self.consumer_count = int(consumer_count)


def get_all_by_resource_provider_uuid(context, rp_uuid):
    """Get a list of Usage objects filtered by one resource provider."""
    usage_list = _get_all_by_resource_provider_uuid(context, rp_uuid)
    return [Usage(**db_item) for db_item in usage_list]


def get_by_consumer_type(context, project_id, user_id=None,
                         consumer_type=None):
    """Get a list of Usage objects by consumer type."""
    usage_list = _get_by_consumer_type(context, project_id, user_id=user_id,
                                       consumer_type=consumer_type)
    return [Usage(**db_item) for db_item in usage_list]


def get_all_by_project_user(context, project_id, user_id=None):
    """Get a list of Usage objects filtered by project and (optional) user."""
    usage_list = _get_all_by_project_user(context, project_id,
                                          user_id=user_id)
    return [Usage(**db_item) for db_item in usage_list]


@db_api.placement_context_manager.reader
def _get_all_by_resource_provider_uuid(context, rp_uuid):
    query = (context.session.query(models.Inventory.resource_class_id,
             func.coalesce(func.sum(models.Allocation.used), 0))
             .join(models.ResourceProvider,
                   models.Inventory.resource_provider_id ==
                   models.ResourceProvider.id)
             .outerjoin(models.Allocation,
                        sql.and_(models.Inventory.resource_provider_id ==
                                 models.Allocation.resource_provider_id,
                                 models.Inventory.resource_class_id ==
                                 models.Allocation.resource_class_id))
             .filter(models.ResourceProvider.uuid == rp_uuid)
             .group_by(models.Inventory.resource_class_id))
    result = [dict(resource_class=context.rc_cache.string_from_id(item[0]),
                   usage=item[1])
              for item in query.all()]
    return result


@db_api.placement_context_manager.reader
def _get_all_by_project_user(context, project_id, user_id=None,
                             consumer_type=None):
    """Get usages by project, user, and consumer type.

    When consumer_type is *not* "all" or "unknown", usages will be returned
    without regard to consumer type (behavior prior to microversion 1.38).

    :param context: `placement.context.RequestContext` that
                    contains an oslo_db Session
    :param project_id: The project ID for which to get usages
    :param user_id: The optional user ID for which to get usages
    :param consumer_type: Optionally filter usages by consumer type, "all" or
                          "unknown". If "all" is specified, all results will be
                          grouped under one key, "all". If "unknown" is
                          specified, all results will be grouped under one key,
                          "unknown".
    """
    query = (context.session.query(models.Allocation.resource_class_id,
             func.coalesce(func.sum(models.Allocation.used), 0))
             .join(models.Consumer,
                   models.Allocation.consumer_id == models.Consumer.uuid)
             .join(models.Project,
                   models.Consumer.project_id == models.Project.id)
             .filter(models.Project.external_id == project_id))
    if user_id:
        query = query.join(models.User,
                           models.Consumer.user_id == models.User.id)
        query = query.filter(models.User.external_id == user_id)
    query = query.group_by(models.Allocation.resource_class_id)

    if consumer_type in ('all', 'unknown'):
        # NOTE(melwitt): We have to count the number of consumers in a separate
        # query in order to get a count of unique consumers. If we count in the
        # same query after grouping by resource class, we will count duplicate
        # consumers for any unique consumer that consumes more than one
        # resource class simultaneously (example: an instance consuming both
        # VCPU and MEMORY_MB).
        count_query = (context.session.query(
            func.count(distinct(models.Allocation.consumer_id)))
            .join(models.Consumer,
                  models.Allocation.consumer_id == models.Consumer.uuid)
            .join(models.Project,
                  models.Consumer.project_id == models.Project.id)
            .filter(models.Project.external_id == project_id))
        if user_id:
            count_query = count_query.join(
                models.User, models.Consumer.user_id == models.User.id)
            count_query = count_query.filter(
                models.User.external_id == user_id)
        if consumer_type == 'unknown':
            count_query = count_query.filter(
                models.Consumer.consumer_type_id == sa.null())
        number_of_unique_consumers = count_query.scalar()

        # Filter for unknown consumer type if specified.
        if consumer_type == 'unknown':
            query = query.filter(models.Consumer.consumer_type_id == sa.null())

        result = [dict(resource_class=context.rc_cache.string_from_id(item[0]),
                       usage=item[1],
                       consumer_type=consumer_type,
                       consumer_count=number_of_unique_consumers)
                  for item in query.all()]
    else:
        result = [dict(resource_class=context.rc_cache.string_from_id(item[0]),
                       usage=item[1])
                  for item in query.all()]

    return result


@db_api.placement_context_manager.reader
def _get_by_consumer_type(context, project_id, user_id=None,
                          consumer_type=None):
    if consumer_type in ('all', 'unknown'):
        return _get_all_by_project_user(context, project_id, user_id,
                                        consumer_type=consumer_type)

    query = (context.session.query(
             models.Allocation.resource_class_id,
             func.coalesce(func.sum(models.Allocation.used), 0),
             func.count(distinct(models.Allocation.consumer_id)),
             models.ConsumerType.name)
             .join(models.Consumer,
                   models.Allocation.consumer_id == models.Consumer.uuid)
             .outerjoin(models.ConsumerType,
                        models.Consumer.consumer_type_id ==
                        models.ConsumerType.id)
             .join(models.Project,
                   models.Consumer.project_id == models.Project.id)
             .filter(models.Project.external_id == project_id))
    if user_id:
        query = query.join(models.User,
                           models.Consumer.user_id == models.User.id)
        query = query.filter(models.User.external_id == user_id)
    if consumer_type:
        query = query.filter(models.ConsumerType.name == consumer_type)
    # NOTE(melwitt): We have to count grouped by only consumer type first in
    # order to get a count of unique consumers for a given consumer type. If we
    # only count after grouping by resource class, we will count duplicate
    # consumers for any unique consumer that consumes more than one resource
    # class simultaneously (example: an instance consuming both VCPU and
    # MEMORY_MB).
    unique_consumer_counts = {item[3]: item[2] for item in
                              query.group_by(models.ConsumerType.name).all()}
    query = query.group_by(models.Allocation.resource_class_id,
                           models.Consumer.consumer_type_id)
    result = [dict(resource_class=context.rc_cache.string_from_id(item[0]),
                   usage=item[1],
                   consumer_count=unique_consumer_counts[item[3]],
                   consumer_type=item[3])
              for item in query.all()]
    return result
