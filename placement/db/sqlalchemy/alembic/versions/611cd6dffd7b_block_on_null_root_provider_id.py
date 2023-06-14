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

"""Block on null root_provider_id

Revision ID: 611cd6dffd7b
Revises: b4ed3a175331
Create Date: 2019-05-09 13:57:04.874293

"""
from alembic import context
import sqlalchemy as sa
from sqlalchemy import func as sqlfunc
from sqlalchemy import MetaData, Table, select

# revision identifiers, used by Alembic.
revision = '611cd6dffd7b'
down_revision = 'b4ed3a175331'
branch_labels = None
depends_on = None


def upgrade():
    connection = context.get_bind()

    meta = MetaData()
    meta.reflect(bind=connection)
    resource_providers = Table(
        'resource_providers',
        meta,
        autoload_with=connection,
    )

    query = select(
        sqlfunc.count(),
    ).select_from(
        resource_providers,
    ).where(
        resource_providers.c.root_provider_id == sa.null()
    )

    if connection.scalar(query):
        raise Exception('There is at least one resource provider table '
                        'record which is missing its root provider id. '
                        'Run the "placement-manage db '
                        'online_data_migrations" command.')
