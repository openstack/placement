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

"""Block on null consumer

Revision ID: b5c396305c25
Revises: 611cd6dffd7b
Create Date: 2019-06-11 16:30:04.114287

"""
from alembic import context
import sqlalchemy as sa
from sqlalchemy import func as sqlfunc


# revision identifiers, used by Alembic.
revision = 'b5c396305c25'
down_revision = '611cd6dffd7b'
branch_labels = None
depends_on = None


def upgrade():
    connection = context.get_bind()

    meta = sa.MetaData()
    meta.reflect(bind=connection)
    consumers = sa.Table('consumers', meta, autoload_with=connection)
    allocations = sa.Table('allocations', meta, autoload_with=connection)

    alloc_to_consumer = sa.outerjoin(
        allocations, consumers,
        allocations.c.consumer_id == consumers.c.uuid,
    )
    sel = sa.select(sqlfunc.count())
    sel = sel.select_from(alloc_to_consumer)
    sel = sel.where(consumers.c.id.is_(None))

    if connection.scalar(sel):
        raise Exception('There is at least one allocation record which is '
                        'missing a consumer record. Run the "placement-manage '
                        'db online_data_migrations" command.')
