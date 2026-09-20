"""Postgres 연결을 다시 쓰는 장치(backend/auth.py 의 db()).

배포 서버(Render 무료 · 0.1 CPU)에서 연결을 새로 여는 값이 비싸다 — 2026-09-20 실측으로 db() 한 번에 +18ms,
두 번째부터는 CPU 제한에 걸려 +104ms. 그래서 쓰고 난 연결을 몇 개 들고 있다가 다시 쓴다.

여기서는 가짜 연결로 '보관함' 의 규칙만 본다. 진짜 Postgres 에서 도는지는 CI 의 pytest-postgres 작업이 본다
(거기서는 다른 테스트 전부가 이 장치를 거쳐 간다).
"""
from __future__ import annotations

import sys
import threading
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import auth  # noqa: E402


class 가짜커서:
    def __init__(self, con):
        self.con = con

    def execute(self, sql, params=()):
        if self.con.고장:
            raise RuntimeError("connection lost")
        self.con.상태 = "INTRANS"
        self.con.기록.append(sql)
        return self

    def fetchone(self):
        return {"id": 1}

    def fetchall(self):
        return []

    def close(self):
        self.con.기록.append("커서 닫음")


class 가짜연결:
    """psycopg 연결에서 db() 가 쓰는 만큼만 흉내 낸다."""

    def __init__(self):
        self.closed = False
        self.상태 = "IDLE"           # IDLE · INTRANS · INERROR
        self.고장 = False            # True 면 무엇을 시켜도 터진다 (저쪽에서 끊긴 연결)
        self.쓰는중 = False
        self.겹침 = False            # 두 곳에서 한꺼번에 집어 든 적이 있으면 True
        self.기록 = []

    @property
    def info(self):
        return SimpleNamespace(transaction_status=SimpleNamespace(name=self.상태))

    def cursor(self):
        if self.쓰는중:
            self.겹침 = True
        self.쓰는중 = True
        return 가짜커서(self)

    def execute(self, sql, params=()):
        return 가짜커서(self).execute(sql, params)

    def commit(self):
        if self.고장:
            raise RuntimeError("connection lost")
        self.상태 = "IDLE"
        self.기록.append("COMMIT")
        self.쓰는중 = False

    def rollback(self):
        if self.고장:
            raise RuntimeError("connection lost")
        self.상태 = "IDLE"
        self.기록.append("ROLLBACK")
        self.쓰는중 = False

    def close(self):
        self.closed = True


@pytest.fixture
def 연결들(monkeypatch):
    """Postgres 인 척한다. 새로 연 연결이 차례로 쌓이는 목록을 준다."""
    만든 = []

    def 새로():
        만든.append(가짜연결())
        return 만든[-1]

    auth.close_idle()
    monkeypatch.setattr(auth, "is_postgres", lambda: True)
    monkeypatch.setattr(auth, "_pg_connect", 새로)
    yield 만든
    auth.close_idle()


def test_쓰고_난_연결을_다시_쓴다(연결들):
    for _ in range(3):
        with auth.db() as con:
            con.execute("SELECT * FROM users WHERE id=?", (1,))
    assert len(연결들) == 1                                           # 세 번 불렀지만 연 것은 한 번
    assert 연결들[0].기록.count("COMMIT") == 3 and not 연결들[0].closed
    assert 연결들[0].기록[0] == "SELECT * FROM users WHERE id=%s"      # 자리표시자 변환은 그대로다
    assert 연결들[0].기록.count("커서 닫음") == 3                       # 커서는 그때그때 닫는다


def test_안에서_또_부르면_기다리지_않고_새로_연다(연결들):
    """db() 안에서 db() 를 부르는 코드가 있어도 막히지 않는다 — 보관함이 비면 새로 연다."""
    with auth.db() as 밖:
        밖.execute("SELECT 1")
        with auth.db() as 안:
            안.execute("SELECT 2")
    assert len(연결들) == 2 and len(auth._idle) == 2


def test_하다가_터지면_되돌리고_멀쩡한_연결은_다시_쓴다(연결들):
    with pytest.raises(ValueError):
        with auth.db() as con:
            con.execute("UPDATE users SET display_name=? WHERE id=?", ("가", 1))
            raise ValueError("일부러")
    assert 연결들[0].기록[-2:] == ["커서 닫음", "ROLLBACK"] and "COMMIT" not in 연결들[0].기록   # 하다 만 것은 남기지 않는다
    with auth.db() as con:
        con.execute("SELECT 1")
    assert len(연결들) == 1                                           # 되돌린 뒤 멀쩡하면 버리지 않는다


def test_고장_난_연결은_보관하지_않는다(연결들):
    with pytest.raises(RuntimeError):
        with auth.db() as con:
            연결들[0].고장 = True                                      # 쓰는 도중에 저쪽에서 끊겼다
            con.execute("SELECT 1")
    assert 연결들[0].closed and auth._idle == []
    # 트랜잭션이 깔끔히 끝나지 않은 연결도 마찬가지다
    with auth.db() as con:
        con.execute("SELECT 1")
        연결들[1].commit = lambda: None                                # 커밋했는데도 상태가 IDLE 로 돌아오지 않는다
    assert 연결들[1].closed and auth._idle == []
    with auth.db() as con:
        con.execute("SELECT 1")
    assert len(연결들) == 3                                           # 다음 사람은 새 연결을 받는다


def test_오래_논_연결은_살아_있는지_물어보고_쓴다(연결들):
    with auth.db() as con:
        con.execute("SELECT 1")
    con0, born, last = auth._idle[0]
    auth._idle[0] = (con0, born, last - auth.POOL_IDLE_CHECK_SEC - 1)
    with auth.db() as con:
        con.execute("SELECT 2")
    assert len(연결들) == 1                                           # 살아 있으면 그대로 쓴다
    # 물어본 것(SELECT 1)은 되돌려서 흔적을 남기지 않고, 그다음에 부른 쪽의 일을 한다
    assert 연결들[0].기록[-5:] == ["SELECT 1", "ROLLBACK", "SELECT 2", "COMMIT", "커서 닫음"]
    # 물어봤더니 죽어 있으면 버리고 새로 연다 — 부른 쪽은 모른다
    con0, born, last = auth._idle[0]
    auth._idle[0] = (con0, born, last - auth.POOL_IDLE_CHECK_SEC - 1)
    con0.고장 = True
    with auth.db() as con:
        con.execute("SELECT 3")
    assert len(연결들) == 2 and 연결들[0].closed and 연결들[1].기록[0] == "SELECT 3"


def test_너무_오래된_연결은_버린다(연결들):
    with auth.db() as con:
        con.execute("SELECT 1")
    con0, born, last = auth._idle[0]
    auth._idle[0] = (con0, born - auth.POOL_MAX_AGE_SEC - 1, last)
    with auth.db() as con:
        con.execute("SELECT 1")
    assert len(연결들) == 2 and 연결들[0].closed


def test_들고_있는_연결_수에는_끝이_있다(연결들):
    with ExitStack() as stack:
        for _ in range(auth.POOL_MAX_IDLE + 2):
            stack.enter_context(auth.db()).execute("SELECT 1")
    assert len(연결들) == auth.POOL_MAX_IDLE + 2
    assert len(auth._idle) == auth.POOL_MAX_IDLE
    assert sum(c.closed for c in 연결들) == 2                          # 넘치는 것은 닫는다
    auth.close_idle()
    assert auth._idle == [] and all(c.closed for c in 연결들)          # 서버가 내려갈 때


def test_한_연결을_두_스레드가_한꺼번에_쓰지_않는다(연결들):
    오류 = []

    def 일꾼():
        try:
            for _ in range(200):
                with auth.db() as con:
                    con.execute("SELECT 1")
        except Exception as e:                                         # noqa: BLE001
            오류.append(e)

    스레드들 = [threading.Thread(target=일꾼) for _ in range(8)]
    for t in 스레드들:
        t.start()
    for t in 스레드들:
        t.join()
    assert 오류 == []
    assert not any(c.겹침 for c in 연결들)
    assert len(연결들) <= 8                                            # 1,600번 불렀지만 연 것은 많아야 스레드 수만큼
    assert sum(c.기록.count("COMMIT") for c in 연결들) == 1600


def test_SQLite_는_예전_그대로다(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "is_postgres", lambda: False)
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(auth, "_pg_connect", lambda: (_ for _ in ()).throw(AssertionError("SQLite 인데 Postgres 를 열었다")))
    auth.init_db()
    with auth.db() as con:
        assert con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0
    assert auth._idle == []


def test_서버가_내려갈_때_들고_있던_연결을_닫는다():
    src = (Path(__file__).resolve().parents[1] / "backend" / "main.py").read_text(encoding="utf-8")
    lifespan = src.split("async def lifespan(")[1].split("app = FastAPI(")[0]
    assert lifespan.index("yield") < lifespan.index("auth.close_idle()")


# ---------- 진짜 Postgres 에서만 (CI 의 pytest-postgres 작업) ----------
# 위의 가짜 연결은 규칙만 본다. psycopg 가 실제로 그렇게 구는지 — 끊긴 연결을 어떻게 알리는지,
# 오류 난 트랜잭션이 되돌린 뒤 정말 다시 쓸 수 있는지 — 는 진짜 DB 로만 알 수 있다.

진짜만 = pytest.mark.skipif(not auth.is_postgres(), reason="DATABASE_URL 이 Postgres 일 때만 돈다")


def _pid() -> int:
    with auth.db() as con:
        return con.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]


@진짜만
def test_진짜_DB에서도_같은_연결을_다시_쓴다():
    auth.close_idle()
    assert _pid() == _pid() == _pid()
    assert len(auth._idle) == 1


@진짜만
def test_진짜_DB에서_SQL이_틀려도_되돌린_뒤_다시_쓴다():
    import psycopg
    auth.close_idle()
    처음 = _pid()
    with pytest.raises(psycopg.Error):
        with auth.db() as con:
            con.execute("SELECT * FROM 없는_표")            # 트랜잭션이 오류 상태(INERROR)가 된다
    assert _pid() == 처음                                   # 되돌렸으니 그 연결 그대로 멀쩡하다


def _끊는다(pid: int) -> None:
    """DB 쪽에서 그 연결을 끊는다 — DB 가 다시 뜨거나 놀던 연결을 정리할 때 생기는 일."""
    import psycopg
    with psycopg.connect(auth.DATABASE_URL, autocommit=True) as 관리:
        관리.execute("SELECT pg_terminate_backend(%s)", (pid,))


@진짜만
def test_진짜_DB에서_오래_놀다_끊긴_연결은_부른_쪽이_모르게_바꾼다():
    auth.close_idle()
    처음 = _pid()
    _끊는다(처음)
    con, born, last = auth._idle[0]
    auth._idle[0] = (con, born, last - auth.POOL_IDLE_CHECK_SEC - 1)     # 30초 넘게 논 것으로
    새것 = _pid()                                                        # 오류 없이 된다
    assert 새것 != 처음


@진짜만
def test_진짜_DB에서_방금_끊긴_연결은_한_번_실패하고_버려진다():
    """30초 안에 끊긴 연결은 물어보지 않고 쓰므로 그 요청 하나는 실패한다. 그래도 고장 난 연결이 보관함에 남지는 않는다."""
    import psycopg
    auth.close_idle()
    처음 = _pid()
    _끊는다(처음)
    with pytest.raises(psycopg.Error):
        _pid()
    assert auth._idle == []
    assert _pid() != 처음                                                # 다음 요청은 새 연결로 된다
