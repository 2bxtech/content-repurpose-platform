"""Enforce row-level security: unprivileged app role, stricter policies.

Until now every policy existed but none applied: the app connected as the table
owner (a superuser in local dev), and both skip RLS. This migration

- creates the role the app switches to on connect (settings.DB_APP_ROLE),
  with DML rights only;
- recreates the workspace policies so an unset or reset `app.workspace_id`
  matches nothing (NULLIF avoids ''::uuid errors), explicit cross-tenant
  operations can opt out via `app.rls_bypass`, and writes are checked too.

Needs a migration user that can CREATE ROLE (true for the Postgres superuser
Railway and the compose stack provide). The app is expected to log in as that
same user and SET ROLE down; `GRANT role TO CURRENT_USER` is what allows it.

Revision ID: b7e1c9d2a4f0
Revises: a1b2c3d4e5f6
Create Date: 2026-09-25
"""
from alembic import op

from app.core.config import settings
from app.core.tenancy import ROLE_NAME

revision = "b7e1c9d2a4f0"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

ROLE = settings.DB_APP_ROLE or "content_repurpose_app"
if not ROLE_NAME.match(ROLE):  # interpolated into DDL below
    raise ValueError(f"Invalid DB_APP_ROLE: {ROLE!r}")

# (table, policy name, column holding the workspace id)
POLICIES = [
    ("users", "workspace_isolation_users", "workspace_id"),
    ("documents", "workspace_isolation_documents", "workspace_id"),
    ("transformations", "workspace_isolation_transformations", "workspace_id"),
    ("transformation_presets", "workspace_isolation_transformation_presets", "workspace_id"),
    ("workspaces", "workspace_isolation_workspaces", "id"),
]


def _rule(column: str) -> str:
    return (
        f"({column} = NULLIF(current_setting('app.workspace_id', true), '')::uuid"
        " OR current_setting('app.rls_bypass', true) = 'on')"
    )


def upgrade() -> None:
    op.execute(
        f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOLOGIN;
            END IF;
        END $$
        """
    )
    # Lets a non-superuser migration/app login switch to the role with SET ROLE.
    op.execute(f"GRANT {ROLE} TO CURRENT_USER")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")
    op.execute(f"REVOKE ALL ON alembic_version FROM {ROLE}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ROLE}"
    )
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {ROLE}")

    for table, name, column in POLICIES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
        op.execute(f"CREATE POLICY {name} ON {table} USING {_rule(column)} WITH CHECK {_rule(column)}")


def downgrade() -> None:
    for table, name, column in POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
        op.execute(
            f"CREATE POLICY {name} ON {table} "
            f"USING ({column} = current_setting('app.workspace_id', true)::uuid)"
        )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {ROLE}"
    )
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {ROLE}")
