"""계정 · 세션 · 측정 기록 저장.

## 무엇을 저장하고 무엇을 저장하지 않는가

저장한다 — 계정을 식별하고 기기 간에 이어보려면 최소한 필요한 것:
  - 로그인 수단 (소셜 제공자 + 제공자 내부 식별자, 또는 이메일 + 비밀번호 해시)
  - 표시용 이름 (닉네임)
  - 체력 측정값과 그 결과

저장하지 않는다 — 서비스가 굴러가는 데 필요 없는 것:
  - 휴대폰 번호, 집 주소, 생년월일, 성별을 제외한 인적사항
  - 소셜 로그인 응답에 그런 값이 섞여 와도 버린다 (KEEP_FIELDS 참고)

받지 않은 정보는 유출될 수도, 잘못 쓸 수도 없다. 이게 가장 확실한 보호다.

## 비밀번호

평문으로 두지 않는다. 계정마다 다른 소금(salt)을 만들어 scrypt 로 늘려 저장한다.
비교는 상수 시간으로 한다(hmac.compare_digest). 표준 라이브러리만 쓴다.

## 세션

무작위 토큰을 DB 에 두고 쿠키로 주고받는다. 쿠키는 HttpOnly 라 자바스크립트가
읽지 못하고, SameSite=Lax 라 다른 사이트에서 실려 나가지 않는다.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

try:
    from backend.paths import ROOT
except ImportError:
    from paths import ROOT

DB_PATH = ROOT / "data" / "app.db"

SESSION_COOKIE = "quadriga_session"
SESSION_DAYS = 30

# scrypt 파라미터. n 을 키우면 느려지는 대신 대입 공격 비용도 같이 오른다.
SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)
MIN_PASSWORD = 8

# 소셜 응답에서 이것만 남긴다. 나머지(전화번호·생일·성별·주소 등)는 버린다.
KEEP_FIELDS = ("uid", "email", "name")

PROVIDERS = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "profile": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",          # 전화번호 권한은 요청하지 않는다
    },
    "naver": {
        "authorize": "https://nid.naver.com/oauth2.0/authorize",
        "token": "https://nid.naver.com/oauth2.0/token",
        "profile": "https://openapi.naver.com/v1/nid/me",
        "scope": "",
    },
    "kakao": {
        "authorize": "https://kauth.kakao.com/oauth/authorize",
        "token": "https://kauth.kakao.com/oauth/token",
        "profile": "https://kapi.kakao.com/v2/user/me",
        "scope": "profile_nickname account_email",
    },
}


def client_config(provider: str) -> tuple[str | None, str | None]:
    """.env 에서 읽는다. 없으면 그 제공자 버튼은 비활성으로 표시한다."""
    p = provider.upper()
    return os.getenv(f"{p}_CLIENT_ID"), os.getenv(f"{p}_CLIENT_SECRET")


def enabled_providers() -> list[str]:
    return [name for name in PROVIDERS if all(client_config(name))]


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  provider      TEXT NOT NULL,              -- 'password' | 'google' | 'naver' | 'kakao'
  provider_uid  TEXT NOT NULL,              -- 제공자 내부 식별자 (비밀번호 계정은 이메일)
  email         TEXT,
  display_name  TEXT NOT NULL,
  password_salt BLOB,
  password_hash BLOB,
  created_at    INTEGER NOT NULL,
  UNIQUE (provider, provider_uid)
);

CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS measurements (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  measured_at INTEGER NOT NULL,
  payload     TEXT NOT NULL                 -- 측정값 + 산출 결과 (JSON)
);
CREATE INDEX IF NOT EXISTS idx_meas_user ON measurements(user_id, measured_at DESC);

CREATE TABLE IF NOT EXISTS oauth_states (
  state      TEXT PRIMARY KEY,
  provider   TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
"""


@contextmanager
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with db() as con:
        con.executescript(SCHEMA)


# ---------------------------------------------------------------------------
# 비밀번호
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    return salt, hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)


def verify_password(password: str, salt: bytes, expected: bytes) -> bool:
    _, actual = hash_password(password, salt)
    return hmac.compare_digest(actual, expected)


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"비밀번호는 {MIN_PASSWORD}자 이상이어야 합니다."
    if password.isdigit() or password.isalpha():
        return "숫자와 문자를 섞어주세요."
    return None


# ---------------------------------------------------------------------------
# 사용자 · 세션
# ---------------------------------------------------------------------------

def upsert_user(provider: str, uid: str, *, email=None, name=None,
                salt=None, pw_hash=None) -> int:
    with db() as con:
        row = con.execute(
            "SELECT id FROM users WHERE provider=? AND provider_uid=?",
            (provider, uid)).fetchone()
        if row:
            if name:
                con.execute("UPDATE users SET display_name=? WHERE id=?", (name, row["id"]))
            return row["id"]
        cur = con.execute(
            "INSERT INTO users (provider, provider_uid, email, display_name,"
            " password_salt, password_hash, created_at) VALUES (?,?,?,?,?,?,?)",
            (provider, uid, email, name or (email or uid).split("@")[0],
             salt, pw_hash, int(time.time())))
        return cur.lastrowid


def find_password_user(email: str) -> sqlite3.Row | None:
    with db() as con:
        return con.execute(
            "SELECT * FROM users WHERE provider='password' AND provider_uid=?",
            (email.strip().lower(),)).fetchone()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with db() as con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        con.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)",
                    (token, user_id, int(time.time()) + SESSION_DAYS * 86400))
    return token


def user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    with db() as con:
        row = con.execute(
            "SELECT u.id, u.display_name, u.email, u.provider FROM sessions s"
            " JOIN users u ON u.id = s.user_id"
            " WHERE s.token=? AND s.expires_at > ?",
            (token, int(time.time()))).fetchone()
    return dict(row) if row else None


def drop_session(token: str | None) -> None:
    if token:
        with db() as con:
            con.execute("DELETE FROM sessions WHERE token=?", (token,))


# ---------------------------------------------------------------------------
# 측정 기록 (기기 간 이어보기)
# ---------------------------------------------------------------------------

def save_measurement(user_id: int, payload: dict) -> None:
    with db() as con:
        con.execute("INSERT INTO measurements (user_id, measured_at, payload) VALUES (?,?,?)",
                    (user_id, int(time.time()), json.dumps(payload, ensure_ascii=False)))


def list_measurements(user_id: int, limit: int = 20) -> list[dict]:
    with db() as con:
        rows = con.execute(
            "SELECT measured_at, payload FROM measurements WHERE user_id=?"
            " ORDER BY measured_at DESC LIMIT ?", (user_id, limit)).fetchall()
    return [{"측정시각": r["measured_at"], **json.loads(r["payload"])} for r in rows]


def delete_account(user_id: int) -> None:
    """계정과 그에 딸린 기록을 모두 지운다. 되돌릴 수 없다."""
    with db() as con:
        con.execute("DELETE FROM measurements WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM users WHERE id=?", (user_id,))


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------

def new_state(provider: str) -> str:
    """CSRF 방지용 1회용 값. 콜백에서 대조하고 바로 버린다."""
    state = secrets.token_urlsafe(24)
    with db() as con:
        con.execute("DELETE FROM oauth_states WHERE created_at < ?", (int(time.time()) - 600,))
        con.execute("INSERT INTO oauth_states (state, provider, created_at) VALUES (?,?,?)",
                    (state, provider, int(time.time())))
    return state


def take_state(state: str) -> str | None:
    with db() as con:
        row = con.execute("SELECT provider FROM oauth_states WHERE state=?", (state,)).fetchone()
        if row:
            con.execute("DELETE FROM oauth_states WHERE state=?", (state,))
    return row["provider"] if row else None


def normalize_profile(provider: str, raw: dict) -> dict:
    """제공자 응답에서 KEEP_FIELDS 만 뽑는다. 나머지는 버린다.

    네이버·카카오는 앱 설정에 따라 전화번호·생일 같은 값이 함께 오기도 한다.
    여기서 걸러내므로 그런 값은 DB 에 닿지 않는다.
    """
    if provider == "google":
        out = {"uid": raw.get("sub"), "email": raw.get("email"), "name": raw.get("name")}
    elif provider == "naver":
        r = raw.get("response") or {}
        out = {"uid": r.get("id"), "email": r.get("email"),
               "name": r.get("nickname") or r.get("name")}
    elif provider == "kakao":
        acc = raw.get("kakao_account") or {}
        out = {"uid": str(raw.get("id")) if raw.get("id") is not None else None,
               "email": acc.get("email"),
               "name": (acc.get("profile") or {}).get("nickname")}
    else:
        out = {}
    return {k: out.get(k) for k in KEEP_FIELDS}
