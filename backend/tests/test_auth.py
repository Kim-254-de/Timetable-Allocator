from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuthSession, utcnow
from tests.conftest import sign_in
from tests.fake_smarttt import COD_ACCOUNT


def test_login_sets_httponly_session_and_csrf_cookie(client, smarttt):
    response = client.post("/api/auth/login", json={"identifier": "stf/0100", "password": "right-password"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["departments"][0]["role"] == "cod"
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("ta_session="))
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    csrf_cookie = next(c for c in cookies if c.startswith("XSRF-TOKEN="))
    assert "HttpOnly" not in csrf_cookie


def test_wrong_password(client, smarttt):
    response = client.post("/api/auth/login", json={"identifier": "STF/0100", "password": "nope"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_lecturer_without_department_role_is_refused(client, smarttt):
    response = client.post("/api/auth/login", json={"identifier": "STF/0001", "password": "right-password"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NO_ALLOCATION_ACCESS"


def test_rate_limited_after_repeated_failures(client, smarttt):
    for _ in range(10):
        client.post("/api/auth/login", json={"identifier": "STF/0100", "password": "nope"})
    response = client.post("/api/auth/login", json={"identifier": "STF/0100", "password": "right-password"})
    assert response.status_code == 429


def test_me_requires_session(client, smarttt):
    assert client.get("/api/auth/me").status_code == 401
    sign_in(client, "STF/0100")
    assert client.get("/api/auth/me").json()["data"]["full_name"] == "Ann Cod"


def test_logout_revokes(client, smarttt):
    sign_in(client, "STF/0100")
    token = client.cookies["ta_session"]
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set("ta_session", token)
    assert client.get("/api/auth/me").status_code == 401


def test_writes_need_csrf_header(client, smarttt):
    sign_in(client, "STF/0100")
    del client.headers["X-XSRF-TOKEN"]
    response = client.put(
        "/api/sessions/412-GRA/allocation", json={"lecturer_id": None, "expected_lecturer_id": None}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"


def test_idle_session_expires(client, smarttt, db: Session):
    sign_in(client, "STF/0100")
    db.execute(update(AuthSession).values(last_seen_at=utcnow() - timedelta(hours=3)))
    db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_roles_refreshed_from_smarttt(client, smarttt, db: Session):
    sign_in(client, "STF/0100")
    smarttt.identities[COD_ACCOUNT]["departments"] = []
    db.execute(update(AuthSession).values(identity_checked_at=utcnow() - timedelta(hours=1)))
    db.commit()
    assert client.get("/api/auth/me").json()["data"]["departments"] == []


def test_deactivated_account_loses_session(client, smarttt, db: Session):
    sign_in(client, "STF/0100")
    del smarttt.identities[COD_ACCOUNT]
    db.execute(update(AuthSession).values(identity_checked_at=utcnow() - timedelta(hours=1)))
    db.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert db.scalar(select(AuthSession.revoked_at)) is not None


def test_smarttt_down_keeps_cached_roles(client, smarttt, db: Session):
    sign_in(client, "STF/0100")
    smarttt.down = True
    db.execute(update(AuthSession).values(identity_checked_at=utcnow() - timedelta(hours=1)))
    db.commit()
    assert client.get("/api/auth/me").status_code == 200


def test_session_token_stored_hashed(client, smarttt, db: Session):
    sign_in(client, "STF/0100")
    token = client.cookies["ta_session"]
    assert db.scalar(select(AuthSession.token_hash)) != token
