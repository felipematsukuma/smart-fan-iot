"""Auth boundaries exercised over HTTP with real PostgreSQL service grants."""
# ruff: noqa: F811

import hashlib
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from smartfan_common.reliability.database import engine_for, migrate
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_reliability_integration import database, reset_disposable_rows  # noqa: F401

from services.api.auth import AuthService, seed_users
from services.api.errors import Problem
from services.api.main import create_app
from services.api.security import BCRYPT_COST, check_password, hash_password

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/postgres_bootstrap").exists(),
    reason="Requires isolated real PostgreSQL integration environment",
)


@pytest.fixture
def api(database):
    admin, engines = database
    passwords = {
        name: secrets.token_urlsafe(18)
        for name in ("admin", "operador", "visualizador")
    }
    with admin.begin() as conn:
        conn.execute(
            text("TRUNCATE app.audit,app.ws_tickets,app.login_attempts,app.sessions")
        )
        # Test database only: keep device metadata while replacing disposable actors.
        conn.execute(text("UPDATE app.device_configurations SET actor_user_id=NULL"))
        conn.execute(text("DELETE FROM app.users"))
        for username, role in [
            ("admin", "administrador"),
            ("operador", "operador"),
            ("visualizador", "visualizador"),
        ]:
            conn.execute(
                text(
                    "INSERT INTO app.users(id,username,password_hash,role) VALUES(:id,:name,:hash,:role)"
                ),
                {
                    "id": str(uuid4()),
                    "name": username,
                    "hash": hash_password(passwords[username], 4),
                    "role": role,
                },
            )
    key = secrets.token_bytes(32)
    auth = AuthService(engines["api"], key, cost=4, progressive_delay=False)
    app = create_app(engines["api"], key, auth=auth, origins=("http://localhost:8080",))
    with TestClient(app) as client:
        yield client, auth, passwords, key


def login(api, name="admin"):
    client, _, passwords, _ = api
    response = client.post(
        "/api/v1/auth/login", json={"username": name, "password": passwords[name]}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token):
    return {"Authorization": "Bearer " + token}


def test_three_roles_are_checked_on_server_and_secrets_do_not_leak(api, capsys):
    client, _, passwords, _ = api
    assert client.get("/api/v1/auth/me").status_code == 401
    for name, role in [
        ("admin", "administrador"),
        ("operador", "operador"),
        ("visualizador", "visualizador"),
    ]:
        token = login(api, name)
        assert (
            client.get("/api/v1/auth/me", headers=headers(token)).json()["role"] == role
        )
        expected = 200 if name == "admin" else 403
        assert (
            client.get("/api/v1/users", headers=headers(token)).status_code == expected
        )
        assert (
            client.get("/api/v1/audit", headers=headers(token)).status_code == expected
        )
        if name != "admin":
            own = client.get("/api/v1/auth/me", headers=headers(token)).json()["id"]
            assert (
                client.patch(
                    "/api/v1/users/" + own,
                    headers=headers(token),
                    json={"role": "administrador"},
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/v1/users",
                    headers=headers(token),
                    json={
                        "username": "forbidden",
                        "password": "test-only-valid-password",
                        "role": "administrador",
                    },
                ).status_code
                == 403
            )
        output = capsys.readouterr().out
        assert token not in output and passwords[name] not in output


def test_logout_and_expired_database_session_revoke_access(api, database):
    client, auth, _, _ = api
    token = login(api)
    principal = auth.authenticate(token)
    assert client.post("/api/v1/auth/logout", headers=headers(token)).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers(token)).status_code == 401
    token = login(api)
    principal = auth.authenticate(token)
    with database[0].begin() as conn:
        conn.execute(
            text(
                "UPDATE app.sessions SET expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"
            ),
            {"id": principal.session_id},
        )
    assert client.get("/api/v1/auth/me", headers=headers(token)).status_code == 401


def test_user_change_revokes_sessions_and_last_admin_is_preserved(api):
    client, auth, _, _ = api
    admin_token = login(api)
    user_token = login(api, "operador")
    user = auth.authenticate(user_token)
    response = client.patch(
        "/api/v1/users/" + user.id,
        headers=headers(admin_token),
        json={"enabled": False},
    )
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers(user_token)).status_code == 401
    _, _, passwords, _ = api
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "operador", "password": passwords["operador"]},
        ).status_code
        == 401
    )
    administrator = auth.authenticate(admin_token)
    assert (
        client.patch(
            "/api/v1/users/" + administrator.id,
            headers=headers(admin_token),
            json={"role": "visualizador"},
        ).status_code
        == 409
    )


def test_jwt_signed_role_change_does_not_override_database(api):
    client, _, _, key = api
    token = login(api, "visualizador")
    claims = jwt.decode(
        token,
        key,
        algorithms=["HS256"],
        audience="smartfan-web",
        issuer="smartfan-aiot",
    )
    claims["role"] = "administrador"
    forged = jwt.encode(claims, key, algorithm="HS256")
    assert client.get("/api/v1/users", headers=headers(forged)).status_code == 401


def test_login_rate_limits_identity_and_untrusted_forwarded_header(api):
    client, _, passwords, _ = api
    for _ in range(5):
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "test-only-wrong-password"},
            ).status_code
            == 401
        )
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": passwords["admin"]},
        headers={"X-Forwarded-For": "203.0.113.99"},
    )
    assert response.status_code == 429 and response.headers["retry-after"] == "900"
    for index in range(25):
        assert (
            client.post(
                "/api/v1/auth/login",
                json={
                    "username": "unknown_" + str(index),
                    "password": "test-only-wrong-password",
                },
                headers={"X-Forwarded-For": "203.0.113." + str(index)},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "another", "password": "test-only-wrong-password"},
        ).status_code
        == 429
    )


def test_ticket_is_short_single_use_origin_bound_and_revoked_with_session(
    api, database
):
    client, auth, _, _ = api
    token = login(api)
    authorization = {**headers(token), "Origin": "http://localhost:8080"}
    response = client.post("/api/v1/auth/ws-ticket", headers=authorization)
    assert response.status_code == 200 and response.json()["expires_in"] == 30
    ticket = response.json()["ticket"]
    with database[0].connect() as conn:
        stored = conn.execute(
            text("SELECT token_hash FROM app.ws_tickets")
        ).scalar_one()
    assert stored != ticket and stored == hashlib.sha256(ticket.encode()).hexdigest()
    with pytest.raises(Problem):
        auth.consume_ticket(ticket, "http://not-permitted.test")

    def consume(_):
        try:
            auth.consume_ticket(ticket, "http://localhost:8080")
            return True
        except Problem:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(consume, range(2))) == [False, True]
    another = client.post("/api/v1/auth/ws-ticket", headers=authorization).json()[
        "ticket"
    ]
    client.post("/api/v1/auth/logout", headers=headers(token))
    with pytest.raises(Problem):
        auth.consume_ticket(another, "http://localhost:8080")


def test_audit_is_append_only_and_users_do_not_return_hashes(api, database):
    client, _, _, _ = api
    token = login(api)
    password = secrets.token_urlsafe(18)
    response = client.post(
        "/api/v1/users",
        headers=headers(token),
        json={"username": "created", "password": password, "role": "visualizador"},
    )
    assert (
        response.status_code == 201
        and password not in response.text
        and "password_hash" not in response.text
    )
    page = client.get("/api/v1/users?limit=2", headers=headers(token)).json()
    assert len(page["items"]) == 2 and page["next_cursor"] is not None
    next_page = client.get(
        "/api/v1/users",
        params={"limit": 2, "cursor": page["next_cursor"]},
        headers=headers(token),
    ).json()
    assert not {item["id"] for item in page["items"]} & {
        item["id"] for item in next_page["items"]
    }
    audit = client.get("/api/v1/audit", headers=headers(token))
    assert (
        audit.status_code == 200
        and password not in audit.text
        and "password_hash" not in audit.text
    )
    with pytest.raises(DBAPIError), database[1]["api"].begin() as conn:
        conn.execute(text("DELETE FROM app.audit"))
    with pytest.raises(DBAPIError), database[1]["writer"].connect() as conn:
        conn.execute(text("SELECT password_hash FROM app.users"))


def test_problem_json_has_correlation_and_never_echoes_invalid_password(api):
    client, _, _, _ = api
    supplied = secrets.token_urlsafe(18)
    invalid = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": {"private": supplied}},
    )
    assert invalid.status_code == 422 and supplied not in invalid.text
    correlation = str(uuid4())
    response = client.get("/api/v1/auth/me", headers={"X-Correlation-ID": correlation})
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["correlation_id"] == correlation
    assert response.headers["x-correlation-id"] == correlation
    oversized = client.post(
        "/api/v1/auth/login",
        content=b"x" * 16385,
        headers={"Content-Type": "application/json"},
    )
    assert oversized.status_code == 413
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": supplied},
            headers={"Origin": "http://evil.test"},
        ).status_code
        == 403
    )


def test_openapi_describes_problem_errors_and_docs_are_local(api):
    client, _, _, _ = api
    schema = client.get("/api/v1/openapi.json").json()
    assert (
        "application/problem+json"
        in schema["paths"]["/api/v1/auth/login"]["post"]["responses"]["422"]["content"]
    )
    docs = client.get("/api/v1/docs")
    assert docs.status_code == 200 and "<script" not in docs.text


def test_migration_preserves_legacy_public_tables(database):
    administrator = engine_for("bootstrap", Path("/run/secrets/postgres_bootstrap"))
    name = "test_legacy_" + uuid4().hex
    with administrator.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    copied = engine_for(
        "bootstrap", Path("/run/secrets/postgres_bootstrap"), database=name
    )
    try:
        with copied.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE public.users(id integer PRIMARY KEY,note text NOT NULL)"
                )
            )
            conn.execute(text("INSERT INTO public.users VALUES(1,'legacy-sentinel')"))
        migrate(copied)
        migrate(copied)
        with copied.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT note FROM public.users WHERE id=1")
                ).scalar_one()
                == "legacy-sentinel"
            )
            assert conn.execute(
                text("SELECT to_regclass('app.users') IS NOT NULL")
            ).scalar_one()
    finally:
        copied.dispose()
        with administrator.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            conn.execute(text(f'DROP DATABASE "{name}"'))
        administrator.dispose()


def test_seed_policy_preserves_ids_credentials_and_user_changes(
    api, database, tmp_path
):
    _, _, passwords, _ = api
    for name, filename in [
        ("admin", "initial_admin_password"),
        ("operador", "initial_operator_password"),
        ("visualizador", "initial_viewer_password"),
    ]:
        (tmp_path / filename).write_text(passwords[name])
    admin, _ = database
    seed_users(admin, tmp_path)
    with admin.connect() as conn:
        before = {
            row["username"]: (row["id"], bytes(row["password_hash"]))
            for row in conn.execute(text("SELECT * FROM app.users")).mappings()
        }
    seed_users(admin, tmp_path)
    with admin.connect() as conn:
        rows = conn.execute(text("SELECT * FROM app.users")).mappings().all()
    assert all(
        row["id"] == before[row["username"]][0]
        and bytes(row["password_hash"]) == before[row["username"]][1]
        for row in rows
    )
    assert all(
        int(bytes(row["password_hash"]).split(b"$")[2]) == BCRYPT_COST for row in rows
    )
    changed = secrets.token_urlsafe(18)
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE app.users SET password_hash=:hash WHERE username='operador'"),
            {"hash": hash_password(changed, 4)},
        )
    seed_users(admin, tmp_path)
    with admin.connect() as conn:
        preserved = bytes(
            conn.execute(
                text("SELECT password_hash FROM app.users WHERE username='operador'")
            ).scalar_one()
        )
    assert check_password(changed, preserved) and not check_password(
        passwords["operador"], preserved
    )
