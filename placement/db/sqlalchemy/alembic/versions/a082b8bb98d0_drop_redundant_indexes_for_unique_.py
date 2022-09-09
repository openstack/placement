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

"""Drop redundant indexes for unique constraints

Revision ID: a082b8bb98d0
Revises: 422ece571366
Create Date: 2022-09-09 15:52:21.644040

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a082b8bb98d0'
down_revision = '422ece571366'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index('inventories_resource_provider_id_idx',
                  table_name='inventories')
    op.drop_index('inventories_resource_provider_resource_class_idx',
                  table_name='inventories')
    op.drop_index('ix_placement_aggregates_uuid',
                  table_name='placement_aggregates')
    op.drop_index('resource_providers_name_idx',
                  table_name='resource_providers')
    op.drop_index('resource_providers_uuid_idx',
                  table_name='resource_providers')
