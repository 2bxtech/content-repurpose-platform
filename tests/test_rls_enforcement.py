"""Postgres itself enforces tenant isolation, independently of the app's filters.

Connects to the integration stack's database as the unprivileged app role and
checks the policies directly, the way a query with a forgotten WHERE clause
would hit them. Runs under `make test-integration` (needs TEST_API_URL and
TEST_DATABASE_URL); skipped otherwise.
"""

import base64
import json
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

APP_ROLE = os.getenv("DB_APP_ROLE", "content_repurpose_app")


@pytest.fixture(scope="module")
def db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Needs TEST_DATABASE_URL (make test-integration)")
    engine = create_engine(url)
    yield engine
    engine.dispose()


async def _tenant_with_document(api_client) -> dict:
    suffix = uuid.uuid4().hex[:8]
    # Throwaway user on a disposable stack; generated so no credential literal is committed.
    creds = {"email": f"rls_{suffix}@example.com", "username": f"rls_{suffix}", "password": f"Rls-{uuid.uuid4().hex}-A1"}
    assert (await api_client.post("/api/auth/register", json=creds)).status_code == 201
    r = await api_client.post(
        "/api/auth/token", data={"username": creds["email"], "password": creds["password"]}
    )
    token = r.json()["access_token"]
    payload = token.split(".")[1]
    workspace_id = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["workspace_id"]
    r = await api_client.post(
        "/api/documents/text",
        data={"title": f"doc {suffix}", "content": "Tenant-private text for the RLS check."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return {"workspace_id": workspace_id, "document_id": r.json()["id"]}


def _as_app(conn, workspace_id=None, bypass=False):
    # Transaction-scoped, so pooled test connections go back unchanged.
    conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
    conn.execute(
        text("SELECT set_config('app.workspace_id', :ws, true), set_config('app.rls_bypass', :b, true)"),
        {"ws": workspace_id or "", "b": "on" if bypass else ""},
    )


def _count(conn, sql, **params):
    return conn.execute(text(sql), params).scalar_one()


async def test_database_enforces_workspace_isolation(api_client, db):
    a = await _tenant_with_document(api_client)
    b = await _tenant_with_document(api_client)
    b_doc = "SELECT count(*) FROM documents WHERE id = :id"

    with db.connect() as conn, conn.begin():
        _as_app(conn)  # no workspace set: nothing is visible
        assert _count(conn, "SELECT count(*) FROM documents") == 0
        assert _count(conn, "SELECT count(*) FROM users") == 0

    with db.connect() as conn, conn.begin():
        _as_app(conn, a["workspace_id"])
        assert _count(conn, b_doc, id=b["document_id"]) == 0
        assert _count(conn, "SELECT count(*) FROM documents WHERE workspace_id <> :ws", ws=a["workspace_id"]) == 0
        updated = conn.execute(
            text("UPDATE documents SET title = 'hijacked' WHERE id = :id"), {"id": b["document_id"]}
        )
        assert updated.rowcount == 0

    with db.connect() as conn, conn.begin():
        _as_app(conn, a["workspace_id"])
        with pytest.raises(DBAPIError, match="row-level security"):
            conn.execute(
                text("UPDATE documents SET workspace_id = :b WHERE id = :id"),
                {"b": b["workspace_id"], "id": a["document_id"]},
            )

    with db.connect() as conn, conn.begin():
        _as_app(conn, a["workspace_id"])
        with pytest.raises(DBAPIError, match="row-level security"):
            # Copy A's document into B's workspace: rejected by the policy's WITH CHECK.
            conn.execute(
                text(
                    "INSERT INTO documents SELECT (jsonb_populate_record(NULL::documents,"
                    " to_jsonb(d) || jsonb_build_object('id', gen_random_uuid(), 'workspace_id', :b))).*"
                    " FROM documents d WHERE d.id = :id"
                ),
                {"b": b["workspace_id"], "id": a["document_id"]},
            )

    with db.connect() as conn, conn.begin():
        _as_app(conn, bypass=True)  # explicit, auditable opt-out
        assert _count(conn, b_doc, id=b["document_id"]) == 1


def test_app_role_cannot_bypass_rls_or_alter_schema(db):
    with db.connect() as conn, conn.begin():
        role = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :r"), {"r": APP_ROLE}
        ).one()
        assert role == (False, False)
        conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        with pytest.raises(DBAPIError):
            conn.execute(text("ALTER TABLE documents DISABLE ROW LEVEL SECURITY"))


def test_every_tenant_table_has_rls_and_a_policy(db):
    """A new table with a workspace_id but no policy would be readable across tenants."""
    with db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname, c.relrowsecurity,"
                "       (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid)"
                " FROM pg_class c JOIN information_schema.columns col"
                "   ON col.table_name = c.relname AND col.column_name = 'workspace_id'"
                " WHERE c.relkind = 'r' AND col.table_schema = 'public'"
            )
        ).all()
    assert rows, "expected tenant tables"
    unprotected = [name for name, rls_on, policies in rows if not rls_on or policies == 0]
    assert unprotected == []


async def test_running_api_queries_as_the_unprivileged_role(api_client):
    """The policies only matter if the app itself is subject to them."""
    health = (await api_client.get("/api/health")).json()
    assert health["checks"]["database"]["row_level_security"] == "enforced"
