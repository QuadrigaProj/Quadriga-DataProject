"""로그인 시도 제한 — 비밀번호를 5번 틀리면 15분 잠근다 (backend/auth.py login_guard · backend/main.py auth_login).

전에는 제한이 없어서 비밀번호를 끝없이 대입할 수 있었고, 시도 하나마다 scrypt(16MB · 수십 ms)가 돌아
서버를 느리게 만드는 길이기도 했다 (예현, 2026-09-22 "비밀번호는 5회 제한 걸어두고").
"""
import sys
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import auth  # noqa: E402
from backend.main import app  # noqa: E402


@pytest.fixture(autouse=True, scope="module")
def _clean_db():
    """테스트용 DB 를 따로 쓴다 — DATABASE_URL 이 있으면 그 Postgres, 없으면 임시 SQLite."""
    old = auth.DB_PATH
    if auth.is_postgres():
        from pg_reset import reset_postgres
        reset_postgres()
    else:
        auth.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
        auth.init_db()
    yield
    auth.DB_PATH = old


def _fresh(ip: str | None = None) -> TestClient:
    c = TestClient(app)
    if ip:
        c.headers["X-Forwarded-For"] = ip
    return c


def _login(c, email, pw):
    return c.post("/auth/login", json={"email": email, "password": pw})


def test_다섯_번_틀리면_맞는_비밀번호로도_잠긴다():
    c = _fresh("10.0.0.1")
    c.post("/auth/signup", json={"email": "lock@ex.com", "password": "abcd1234"})
    for i in range(3):
        assert _login(c, "lock@ex.com", "wrong123a").status_code == 401
    # 네 번째 · 다섯 번째는 몇 번 남았는지 알려 준다
    r = _login(c, "lock@ex.com", "wrong123a")
    assert r.status_code == 401 and "1번 더 틀리면" in r.json()["detail"]
    r = _login(c, "lock@ex.com", "wrong123a")
    assert r.status_code == 429 and "5번 틀려" in r.json()["detail"] and "15분" in r.json()["detail"]
    # 잠긴 동안은 맞는 비밀번호도 안 받는다 — 대조도 하지 않는다
    r = _login(c, "lock@ex.com", "abcd1234")
    assert r.status_code == 429 and "잠시 잠겼어요" in r.json()["detail"]
    assert "quadriga_session" not in r.headers.get("set-cookie", "")


def test_없는_이메일도_똑같이_잠긴다():
    """있는 이메일만 잠그면 '잠기는지' 로 가입 여부를 알아낼 수 있다."""
    a, b = _fresh("10.0.0.2"), _fresh("10.0.0.3")
    a.post("/auth/signup", json={"email": "real@ex.com", "password": "abcd1234"})
    응답 = []
    for c, email in ((a, "real@ex.com"), (b, "ghost@ex.com")):
        rs = [_login(c, email, "wrong123a") for _ in range(6)]
        응답.append([(r.status_code, r.json()["detail"]) for r in rs])
    assert 응답[0] == 응답[1]
    assert [s for s, _ in 응답[0]] == [401, 401, 401, 401, 429, 429]


def test_제대로_로그인하면_틀린_횟수가_지워진다():
    c = _fresh("10.0.0.4")
    c.post("/auth/signup", json={"email": "reset@ex.com", "password": "abcd1234"})
    for _ in range(4):
        _login(c, "reset@ex.com", "wrong123a")
    assert _login(c, "reset@ex.com", "abcd1234").status_code == 200
    for _ in range(4):
        assert _login(c, "reset@ex.com", "wrong123a").status_code == 401     # 다시 0 부터 센다
    assert _login(c, "reset@ex.com", "abcd1234").status_code == 200


def test_잠금은_시간이_지나면_풀린다():
    now = int(time.time())
    for _ in range(auth.LOGIN_MAX_FAILURES):
        남음 = auth.guard_hit("email:t@ex.com", auth.LOGIN_MAX_FAILURES, now=now)
    assert 남음 == 0 and auth.guard_locked("email:t@ex.com", now=now + 10) > 0
    assert auth.guard_locked("email:t@ex.com", now=now + auth.LOGIN_LOCK_SEC + 1) == 0
    # 세는 기간이 지나면 횟수도 처음부터
    assert auth.guard_hit("email:t@ex.com", auth.LOGIN_MAX_FAILURES,
                          now=now + auth.LOGIN_WINDOW_SEC + 1) == auth.LOGIN_MAX_FAILURES - 1


def test_한_곳에서_이메일을_바꿔_가며_두드려도_잠긴다():
    c = _fresh("10.0.0.5")
    for i in range(auth.IP_MAX_FAILURES):
        r = _login(c, f"u{i}@ex.com", "wrong123a")
        assert r.status_code == 401, i
    assert _login(c, "another@ex.com", "wrong123a").status_code == 429
    # 다른 곳(IP)은 상관없다
    assert _login(_fresh("10.0.0.6"), "another@ex.com", "wrong123a").status_code == 401


def test_프록시_뒤에서는_마지막_전달_주소를_쓴다():
    from backend.main import client_ip
    from starlette.requests import Request

    def req(**headers):
        scope = {"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                 "client": ("127.0.0.1", 1), "method": "GET", "path": "/", "query_string": b""}
        return Request(scope)

    assert client_ip(req()) == "127.0.0.1"
    # 사용자가 앞에 붙인 값은 무시하고 프록시가 뒤에 붙인 값을 쓴다
    assert client_ip(req(**{"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})) == "5.6.7.8"


def test_한_곳에서_계정을_무더기로_만들지_못한다():
    c = _fresh("10.0.0.7")
    for i in range(auth.SIGNUP_MAX_PER_IP):
        assert c.post("/auth/signup", json={"email": f"many{i}@ex.com", "password": "abcd1234"}).status_code == 200
    r = c.post("/auth/signup", json={"email": "onemore@ex.com", "password": "abcd1234"})
    assert r.status_code == 429 and auth.find_password_user("onemore@ex.com") is None
