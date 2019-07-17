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

from sqlalchemy import func
from sqlalchemy import sql

from placement.db.sqlalchemy import models
from placement import db_api


class Usage(object):

    def __init__(self, resource_class=None, usage=0):
        self.resource_class = resource_class
        self.usage = int(usage)


def get_all_by_resource_provider_uuid(context, rp_uuid):
    """Get a list of Usage objects filtered by one resource provider."""
    usage_list = _get_all_by_resource_provider_uuid(context, rp_uuid)
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
def _get_all_by_project_user(context, project_id, user_id=None):
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
    result = [dict(resource_class=context.rc_cache.string_from_id(item[0]),
                   usage=item[1])
              for item in query.all()]
    return result
