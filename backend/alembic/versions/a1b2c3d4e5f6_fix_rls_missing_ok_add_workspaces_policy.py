"""Fix RLS missing_ok flag on all workspace isolation policies and add RLS to workspaces table.

Without missing_ok=true, current_setting('app.workspace_id') raises an exception when the
session variable is not set (e.g. during migrations, background tasks, or an unguarded request).
With missing_ok=true it returns NULL, which correctly blocks all rows instead of erroring.

Revision ID: a1b2c3d4e5f6
Revises: e4f8a9b2c1d3
Create Date: 2026-07-03
"""
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = 'dc46b3a28880'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Drop all existing workspace isolation policies ──────────────────────
    op.execute("DROP POLICY IF EXISTS workspace_isolation_users ON users")
    op.execute("DROP POLICY IF EXISTS workspace_isolation_documents ON documents")
    op.execute("DROP POLICY IF EXISTS workspace_isolation_transformations ON transformations")
    op.execute("DROP POLICY IF EXISTS workspace_isolation_transformation_presets ON transformation_presets")

    # ── Recreate with missing_ok=true (second arg to current_setting) ───────
    # Without the flag, an unset session variable raises an exception.
    # With the flag it returns NULL, which correctly blocks all rows.
    op.execute("""
        CREATE POLICY workspace_isolation_users ON users
        USING (workspace_id = current_setting('app.workspace_id', true)::UUID)
    """)
    op.execute("""
        CREATE POLICY workspace_isolation_documents ON documents
        USING (workspace_id = current_setting('app.workspace_id', true)::UUID)
    """)
    op.execute("""
        CREATE POLICY workspace_isolation_transformations ON transformations
        USING (workspace_id = current_setting('app.workspace_id', true)::UUID)
    """)
    op.execute("""
        CREATE POLICY workspace_isolation_transformation_presets ON transformation_presets
        USING (workspace_id = current_setting('app.workspace_id', true)::UUID)
    """)

    # ── Add RLS to workspaces table (was previously unprotected) ────────────
    # Admins querying their own workspace by ID still work because workspace_service
    # sets app.workspace_id before any RLS-gated query.
    op.execute("ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY workspace_isolation_workspaces ON workspaces
        USING (id = current_setting('app.workspace_id', true)::UUID)
    """)


def downgrade() -> None:
    # Remove workspaces policy
    op.execute("DROP POLICY IF EXISTS workspace_isolation_workspaces ON workspaces")
    op.execute("ALTER TABLE workspaces DISABLE ROW LEVEL SECURITY")

    # Restore original policies without missing_ok
    op.execute("DROP POLICY IF EXISTS workspace_isolation_users ON users")
    op.execute("DROP POLICY IF EXISTS workspace_isolation_documents ON documents")
    op.execute("DROP POLICY IF EXISTS workspace_isolation_transformations ON transformations")
    op.execute("DROP POLICY IF EXISTS workspace_isolation_transformation_presets ON transformation_presets")

    op.execute("""
        CREATE POLICY workspace_isolation_users ON users
        USING (workspace_id = current_setting('app.workspace_id')::UUID)
    """)
    op.execute("""
        CREATE POLICY workspace_isolation_documents ON documents
        USING (workspace_id = current_setting('app.workspace_id')::UUID)
    """)
    op.execute("""
        CREATE POLICY workspace_isolation_transformations ON transformations
        USING (workspace_id = current_setting('app.workspace_id')::UUID)
    """)
    op.execute("""
        CREATE POLICY workspace_isolation_transformation_presets ON transformation_presets
        USING (workspace_id = current_setting('app.workspace_id')::UUID)
    """)
