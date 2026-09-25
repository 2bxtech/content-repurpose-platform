"""initial_multitenancy_rls_schema

Revision ID: 6295f93177b8
Revises:
Create Date: 2025-08-31 15:46:29.324251

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "6295f93177b8"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create workspaces table first (as it's referenced by foreign keys)
    op.create_table(
        "workspaces",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("plan", sa.String(length=50), nullable=False, server_default="free"),
        sa.Column("settings", JSONB, nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_workspace_slug_active",
        "workspaces",
        ["slug"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_workspaces_active",
        "workspaces",
        ["is_active"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(op.f("ix_workspaces_slug"), "workspaces", ["slug"], unique=True)

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("is_verified", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.Enum("OWNER", "ADMIN", "MEMBER", "VIEWER", name="userrole"),
            nullable=True,
            server_default="MEMBER",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_users_email_active",
        "users",
        ["email"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_users_workspace_active",
        "users",
        ["workspace_id"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # Create documents table
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUID(as_uuid=True), nullable=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("doc_metadata", JSONB, nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "PROCESSING", "COMPLETED", "FAILED", name="documentstatus"
            ),
            nullable=True,
            server_default="PENDING",
        ),
        sa.Column("version", sa.Integer(), nullable=True, server_default="1"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_documents_status", "documents", ["status"], unique=False)
    op.create_index(
        "idx_documents_workspace_active",
        "documents",
        ["workspace_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_documents_workspace_user_created",
        "documents",
        ["workspace_id", "user_id", "created_at"],
        unique=False,
    )

    # Create transformations table
    op.create_table(
        "transformations",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUID(as_uuid=True), nullable=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "transformation_type",
            sa.Enum(
                "BLOG_POST",
                "SOCIAL_MEDIA",
                "EMAIL_SEQUENCE",
                "NEWSLETTER",
                "SUMMARY",
                "CUSTOM",
                name="transformationtype",
            ),
            nullable=False,
        ),
        sa.Column("parameters", JSONB, nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PROCESSING",
                "COMPLETED",
                "FAILED",
                name="transformationstatus",
            ),
            nullable=True,
            server_default="PENDING",
        ),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("ai_provider", sa.String(length=50), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("processing_time_seconds", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_transformations_document", "transformations", ["document_id"], unique=False
    )
    op.create_index(
        "idx_transformations_status_created",
        "transformations",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_transformations_workspace_active",
        "transformations",
        ["workspace_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_transformations_workspace_user",
        "transformations",
        ["workspace_id", "user_id"],
        unique=False,
    )

    # Enable Row-Level Security (RLS) on all multi-tenant tables
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE transformations ENABLE ROW LEVEL SECURITY")

    # Create RLS policies for workspace isolation
    # Users can only see users in their workspace
    op.execute("""
        CREATE POLICY workspace_isolation_users ON users
        USING (workspace_id = current_setting('app.workspace_id')::UUID)
    """)

    # Documents are isolated by workspace
    op.execute("""
        CREATE POLICY workspace_isolation_documents ON documents
        USING (workspace_id = current_setting('app.workspace_id')::UUID)
    """)

    # Transformations are isolated by workspace
    op.execute("""
        CREATE POLICY workspace_isolation_transformations ON transformations
        USING (workspace_id = current_setting('app.workspace_id')::UUID)
    """)

    # Create default workspace for migration
    op.execute("""
        INSERT INTO workspaces (id, name, slug, plan, settings, description, is_active)
        VALUES (
            gen_random_uuid(),
            'Default Workspace',
            'default',
            'free',
            '{"max_users": 10, "max_documents": 100, "max_storage_mb": 1000, "ai_requests_per_month": 1000, "features_enabled": ["basic_transformations"]}',
            'Default workspace for existing users',
            true
        )
    """)


def downgrade() -> None:
    # Drop RLS policies
    op.execute(
        "DROP POLICY IF EXISTS workspace_isolation_transformations ON transformations"
    )
    op.execute("DROP POLICY IF EXISTS workspace_isolation_documents ON documents")
    op.execute("DROP POLICY IF EXISTS workspace_isolation_users ON users")

    # Disable RLS
    op.execute("ALTER TABLE transformations DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE documents DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")

    # Drop tables
    op.drop_table("transformations")
    op.drop_table("documents")
    op.drop_table("users")
    op.drop_table("workspaces")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS transformationstatus")
    op.execute("DROP TYPE IF EXISTS transformationtype")
    op.execute("DROP TYPE IF EXISTS documentstatus")
    op.execute("DROP TYPE IF EXISTS userrole")
