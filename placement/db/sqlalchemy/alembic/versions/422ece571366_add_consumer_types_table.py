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

"""Add consumer_types table

Revision ID: 422ece571366
Revises: b5c396305c25
Create Date: 2019-07-02 13:47:04.165692

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '422ece571366'
down_revision = 'b5c396305c25'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'consumer_types',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.Unicode(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uniq_consumer_types0name'),
    )

    with op.batch_alter_table('consumers') as batch_op:
        batch_op.add_column(
            sa.Column(
                'consumer_type_id', sa.Integer(),
                sa.ForeignKey('consumer_types.id',
                              name='consumers_consumer_type_id_fkey'),
                nullable=True
            )
        )

    op.create_index(
        'consumers_consumer_type_id_idx',
        'consumers',
        ['consumer_type_id'],
        unique=False
    )
