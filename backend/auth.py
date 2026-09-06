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

# 로컬은 SQLite 파일, 배포는 Postgres.
# Render 는 DATABASE_URL 을 자동으로 넣어준다. 없으면 SQLite 로 떨어진다.
DB_PATH = ROOT / "data" / "app.db"
DATABASE_URL = os.getenv("DATABASE_URL", "")


def is_postgres() -> bool:
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))

SESSION_COOKIE = "quadriga_session"
SESSION_DAYS = 30

# scrypt 파라미터. n 을 키우면 느려지는 대신 대입 공격 비용도 같이 오른다.
SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)
MIN_PASSWORD = 8

# 소셜 응답에서 이것만 남긴다. 나머지(전화번호·생일·성별·주소 등)는 버린다.
KEEP_FIELDS = ("uid", "email", "name")

# 카카오는 Client Secret 이 선택 기능이다. 콘솔에서 켜지 않으면 값 자체가 없다.
# 없어도 로그인은 되므로, 없을 때는 요청에서 빼고 진행한다.
# (구글·네이버는 필수라 없으면 버튼을 켜지 않는다)
SECRET_OPTIONAL = {"kakao"}

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
        # 카카오는 scope 를 아예 보내지 않는 것이 기본이다.
        #   - 콘솔에서 "필수 동의" 로 켠 항목(우리는 닉네임)은 자동으로 포함된다.
        #     그걸 scope 에 또 적으면 카카오가 거부한다 (KOE206).
        #   - 콘솔에서 설정하지 않은 항목을 적으면 KOE205 가 난다.
        #     (이메일 account_email 은 일반 앱에서는 별도 검수 대상이다)
        # 즉 동의 범위는 콘솔의 [카카오 로그인] > [동의항목] 이 정하고,
        # 코드는 관여하지 않는다. 로그인 식별자는 카카오 회원번호라 닉네임만으로 충분하다.
        # 나중에 선택 동의 항목을 추가로 요청해야 하면 KAKAO_SCOPE 환경변수에만 넣으면 된다.
        "scope": "",
    },
}


def scope_for(provider: str) -> str:
    """콘솔 설정에 맞춰 환경변수로 덮어쓸 수 있다.

    동의항목을 켜지 않았거나 검수를 안 받은 항목을 요청하면 제공자가 거부한다.
    (카카오 KOE205·KOE206 등) 그럴 때 코드를 고치지 않고 환경변수로 줄인다.

    빈 값이거나 공백뿐이면 scope 파라미터 자체를 빼고 보낸다.
    콘솔에 설정해 둔 동의항목이 그대로 적용된다.
    """
    return (os.getenv(f"{provider.upper()}_SCOPE", PROVIDERS[provider]["scope"]) or "").strip()


def client_config(provider: str) -> tuple[str | None, str | None]:
    """.env 에서 읽는다. 없으면 그 제공자 버튼은 비활성으로 표시한다."""
    p = provider.upper()
    return os.getenv(f"{p}_CLIENT_ID"), os.getenv(f"{p}_CLIENT_SECRET")


def enabled_providers() -> list[str]:
    out = []
    for name in PROVIDERS:
        cid, secret = client_config(name)
        if cid and (secret or name in SECRET_OPTIONAL):
            out.append(name)
    return out


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  provider      TEXT NOT NULL,
  provider_uid  TEXT NOT NULL,
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
  payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meas_user ON measurements(user_id, measured_at DESC);
CREATE TABLE IF NOT EXISTS oauth_states (
  state      TEXT PRIMARY KEY,
  provider   TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
"""

# Postgres 는 자동증가·바이너리 타입 표기가 다르다. 나머지는 같다.
SCHEMA_PG = (SCHEMA_SQLITE
             .replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
             .replace("BLOB", "BYTEA"))


class Cur:
    """sqlite3 와 psycopg 의 차이를 여기서만 흡수한다.

    - 자리표시자: 코드에는 항상 ? 로 쓰고, Postgres 일 때만 %s 로 바꾼다
    - 새로 넣은 행의 id: sqlite 는 lastrowid, Postgres 는 RETURNING id
    """

    def __init__(self, raw, pg: bool):
        self._raw, self._pg = raw, pg

    def execute(self, sql: str, params=()):
        self._raw.execute(sql.replace("?", "%s") if self._pg else sql, params)
        return self

    def fetchone(self):
        return self._raw.fetchone()

    def fetchall(self):
        return self._raw.fetchall()

    def insert_id(self, sql: str, params=()) -> int:
        if self._pg:
            self.execute(sql + " RETURNING id", params)
            return self.fetchone()["id"]
        self.execute(sql, params)
        return self._raw.lastrowid


@contextmanager
def db():
    if is_postgres():
        import psycopg
        from psycopg.rows import dict_row
        con = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        try:
            yield Cur(con.cursor(), True)
            con.commit()
        finally:
            con.close()
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield Cur(con.cursor(), False)
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    schema = SCHEMA_PG if is_postgres() else SCHEMA_SQLITE
    with db() as con:
        for stmt in filter(str.strip, schema.split(";")):
            con.execute(stmt)


# ---------------------------------------------------------------------------
# 비밀번호
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    return salt, hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)


def verify_password(password: str, salt, expected) -> bool:
    # Postgres 드라이버는 BYTEA 를 memoryview 로 줄 수 있다
    salt, expected = bytes(salt), bytes(expected)
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
        return con.insert_id(
            "INSERT INTO users (provider, provider_uid, email, display_name,"
            " password_salt, password_hash, created_at) VALUES (?,?,?,?,?,?,?)",
            (provider, uid, email, name or (email or uid).split("@")[0],
             salt, pw_hash, int(time.time())))


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


def rename_user(user_id: int, name: str) -> None:
    """표시 이름(별명)만 바꾼다. 로그인 수단이나 기록은 건드리지 않는다."""
    with db() as con:
        con.execute("UPDATE users SET display_name=? WHERE id=?", (name, user_id))


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
