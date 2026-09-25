"""add_audit_columns_to_transformation_presets

Revision ID: dc46b3a28880
Revises: e4f8a9b2c1d3
Create Date: 2025-10-02 20:05:34.617702

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'dc46b3a28880'
down_revision: Union[str, None] = 'e4f8a9b2c1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add audit columns (created_by, updated_by, deleted_by) to transformation_presets table"""
    
    # Add audit columns to match BaseModel pattern
    op.add_column('transformation_presets', sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('transformation_presets', sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('transformation_presets', sa.Column('deleted_by', postgresql.UUID(as_uuid=True), nullable=True))
    
    # Add foreign key constraints to users table for audit columns
    op.create_foreign_key('fk_transformation_presets_created_by', 'transformation_presets', 'users', ['created_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_transformation_presets_updated_by', 'transformation_presets', 'users', ['updated_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_transformation_presets_deleted_by', 'transformation_presets', 'users', ['deleted_by'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Remove audit columns from transformation_presets table"""
    
    # Drop foreign key constraints first
    op.drop_constraint('fk_transformation_presets_deleted_by', 'transformation_presets', type_='foreignkey')
    op.drop_constraint('fk_transformation_presets_updated_by', 'transformation_presets', type_='foreignkey')
    op.drop_constraint('fk_transformation_presets_created_by', 'transformation_presets', type_='foreignkey')
    
    # Drop audit columns
    op.drop_column('transformation_presets', 'deleted_by')
    op.drop_column('transformation_presets', 'updated_by')
    op.drop_column('transformation_presets', 'created_by')
