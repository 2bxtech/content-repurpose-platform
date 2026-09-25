"""add_transformation_presets_table

Revision ID: e4f8a9b2c1d3
Revises: 3f09ed5cf416
Create Date: 2025-10-02 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e4f8a9b2c1d3'
down_revision: Union[str, None] = '3f09ed5cf416'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create transformation_presets table"""
    
    # Create transformation_presets table
    op.create_table(
        'transformation_presets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('transformation_type', sa.String(length=50), nullable=False),
        sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('is_shared', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "transformation_type IN ('BLOG_POST', 'SOCIAL_MEDIA', 'EMAIL_SEQUENCE', 'NEWSLETTER', 'SUMMARY', 'CUSTOM')",
            name='valid_transformation_type'
        )
    )
    
    # Create indexes
    op.create_index(
        'idx_presets_workspace_active', 
        'transformation_presets', 
        ['workspace_id'],
        postgresql_where=sa.text('deleted_at IS NULL')
    )
    
    op.create_index(
        'idx_presets_user_active', 
        'transformation_presets', 
        ['user_id'],
        postgresql_where=sa.text('deleted_at IS NULL')
    )
    
    op.create_index(
        'idx_presets_type_active', 
        'transformation_presets', 
        ['transformation_type'],
        postgresql_where=sa.text('deleted_at IS NULL')
    )
    
    op.create_index(
        'idx_presets_usage', 
        'transformation_presets', 
        ['usage_count'],
        postgresql_where=sa.text('deleted_at IS NULL')
    )
    
    # Enable RLS
    op.execute('ALTER TABLE transformation_presets ENABLE ROW LEVEL SECURITY')
    
    # Create RLS policy
    op.execute("""
        CREATE POLICY workspace_isolation_transformation_presets ON transformation_presets
        USING (workspace_id = current_setting('app.workspace_id')::UUID)
    """)


def downgrade() -> None:
    """Drop transformation_presets table"""
    
    # Drop RLS policy
    op.execute('DROP POLICY IF EXISTS workspace_isolation_transformation_presets ON transformation_presets')
    
    # Drop indexes
    op.drop_index('idx_presets_usage', table_name='transformation_presets')
    op.drop_index('idx_presets_type_active', table_name='transformation_presets')
    op.drop_index('idx_presets_user_active', table_name='transformation_presets')
    op.drop_index('idx_presets_workspace_active', table_name='transformation_presets')
    
    # Drop table
    op.drop_table('transformation_presets')
