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


"""Initial

Revision ID: b4ed3a175331
Revises:
Create Date: 2018-10-19 18:27:55.950383

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4ed3a175331'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'allocations',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('resource_provider_id', sa.Integer(), nullable=False),
        sa.Column('consumer_id', sa.String(length=36), nullable=False),
        sa.Column('resource_class_id', sa.Integer(), nullable=False),
        sa.Column('used', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'allocations_resource_provider_class_used_idx', 'allocations',
        ['resource_provider_id', 'resource_class_id', 'used'], unique=False)
    op.create_index(
        'allocations_resource_class_id_idx', 'allocations',
        ['resource_class_id'], unique=False)
    op.create_index(
        'allocations_consumer_id_idx', 'allocations', ['consumer_id'],
        unique=False)

    op.create_table(
        'consumers',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('generation', sa.Integer(), server_default=sa.text('0'),
                  nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid', name='uniq_consumers0uuid'),
    )
    op.create_index(
        'consumers_project_id_user_id_uuid_idx', 'consumers',
        ['project_id', 'user_id', 'uuid'], unique=False)
    op.create_index(
        'consumers_project_id_uuid_idx', 'consumers',
        ['project_id', 'uuid'], unique=False)

    op.create_table(
        'inventories',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('resource_provider_id', sa.Integer(), nullable=False),
        sa.Column('resource_class_id', sa.Integer(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('reserved', sa.Integer(), nullable=False),
        sa.Column('min_unit', sa.Integer(), nullable=False),
        sa.Column('max_unit', sa.Integer(), nullable=False),
        sa.Column('step_size', sa.Integer(), nullable=False),
        sa.Column('allocation_ratio', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'resource_provider_id', 'resource_class_id',
            name='uniq_inventories0resource_provider_resource_class'),
    )
    op.create_index(
        'inventories_resource_class_id_idx', 'inventories',
        ['resource_class_id'], unique=False)
    op.create_index(
        'inventories_resource_provider_id_idx', 'inventories',
        ['resource_provider_id'], unique=False)
    op.create_index(
        'inventories_resource_provider_resource_class_idx',
        'inventories', ['resource_provider_id', 'resource_class_id'],
        unique=False)

    op.create_table(
        'placement_aggregates',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid', name='uniq_placement_aggregates0uuid')
    )
    op.create_index(op.f('ix_placement_aggregates_uuid'),
                    'placement_aggregates', ['uuid'], unique=False)

    op.create_table(
        'projects',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id', name='uniq_projects0external_id'),
    )

    op.create_table(
        'resource_classes',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uniq_resource_classes0name'),
    )

    op.create_table(
        'resource_provider_aggregates',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('resource_provider_id', sa.Integer(), nullable=False),
        sa.Column('aggregate_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('resource_provider_id', 'aggregate_id'),
    )
    op.create_index(
        'resource_provider_aggregates_aggregate_id_idx',
        'resource_provider_aggregates', ['aggregate_id'], unique=False)

    op.create_table(
        'resource_providers',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('name', sa.Unicode(length=200), nullable=True),
        sa.Column('generation', sa.Integer(), nullable=True),
        sa.Column('root_provider_id', sa.Integer(), nullable=True),
        sa.Column('parent_provider_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['parent_provider_id'],
                                ['resource_providers.id']),
        sa.ForeignKeyConstraint(['root_provider_id'],
                                ['resource_providers.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uniq_resource_providers0name'),
        sa.UniqueConstraint('uuid', name='uniq_resource_providers0uuid'),
    )
    op.create_index(
        'resource_providers_name_idx', 'resource_providers', ['name'],
        unique=False)
    op.create_index(
        'resource_providers_parent_provider_id_idx', 'resource_providers',
        ['parent_provider_id'], unique=False)
    op.create_index(
        'resource_providers_root_provider_id_idx',
        'resource_providers', ['root_provider_id'], unique=False)
    op.create_index(
        'resource_providers_uuid_idx', 'resource_providers', ['uuid'],
        unique=False)

    op.create_table(
        'traits',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.Unicode(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uniq_traits0name'),
    )

    op.create_table(
        'users',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id', name='uniq_users0external_id'),
    )

    op.create_table(
        'resource_provider_traits',
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('trait_id', sa.Integer(), nullable=False),
        sa.Column('resource_provider_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['resource_provider_id'],
                                ['resource_providers.id'], ),
        sa.ForeignKeyConstraint(['trait_id'], ['traits.id'], ),
        sa.PrimaryKeyConstraint('trait_id', 'resource_provider_id'),
    )
    op.create_index(
        'resource_provider_traits_resource_provider_trait_idx',
        'resource_provider_traits', ['resource_provider_id', 'trait_id'],
        unique=False)
