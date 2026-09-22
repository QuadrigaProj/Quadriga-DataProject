"""서버가 스스로를 지키는 장치.

한 요청이 멈추면 그 스레드가 영구히 잠긴다. 서버가 한 대뿐이라 그런 요청
몇 개면 남는 자리가 없다 — 추천의 무한 루프 때 실제로 그랬다.
"""
from __future__ import annotations

import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import main as m  # noqa: E402

client = TestClient(m.app)


def test_시간_제한이_걸려_있다():
    assert m.REQUEST_TIMEOUT_SEC > 0
    assert m.REQUEST_TIMEOUT_SEC <= 60, "이보다 길면 지키는 뜻이 없다"


def test_끊을_때_까닭을_알려_준다():
    """503 만 던지면 쓰는 쪽이 무엇을 해야 할지 모른다."""
    src = __import__("inspect").getsource(m.시간_제한)
    assert "status_code=503" in src
    assert "다시 시도해주세요" in src
    assert "[timeout]" in src            # 무엇이 오래 걸렸는지 로그에 남긴다


def test_로그에_쿼리는_적지_않는다():
    """쿼리에는 개인 정보가 실릴 수 있다."""
    src = __import__("inspect").getsource(m.시간_제한)
    assert "request.url.path" in src
    assert "request.url}" not in src and "str(request.url)" not in src


def test_끌_수_있다(monkeypatch):
    """디버깅할 때 붙잡아 두고 봐야 할 때가 있다. 끄면 AI 경로까지 다 꺼진다."""
    monkeypatch.setattr(m, "REQUEST_TIMEOUT_SEC", 0.0)
    assert m.request_limit_sec("GET", "/health") == 0
    assert m.request_limit_sec("POST", "/recommend/routines") == 0
    assert "if 제한 <= 0:" in __import__("inspect").getsource(m.시간_제한)


def test_압축해서_내려보낸다():
    """index.html 이 380KB 다. 배포는 CDN 이 하지만 로컬 개발 서버는 아니다."""
    r = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_작은_응답까지_압축하지는_않는다():
    """작은 것은 압축해도 이득이 없고 CPU 만 쓴다."""
    import inspect
    src = inspect.getsource(m)
    assert "GZipMiddleware, minimum_size=" in src


def test_평소_요청은_그대로_지나간다():
    assert client.get("/health").status_code == 200


def test_화면_파일은_늘_다시_확인하게_한다():
    """배포해도 사람마다 옛 화면이 남아 "고쳤다는데 안 바뀌었다" 가 되풀이됐다.
    no-cache 는 쓰기 전에 물어보라는 뜻이다 — ETag 가 있으니 안 바뀌었으면 304 다."""
    for 경로 in ("/", "/js/api.js"):
        r = client.get(경로)
        assert r.status_code == 200, 경로
        assert r.headers.get("cache-control") == "no-cache, must-revalidate", 경로
        assert r.headers.get("etag"), 경로
        # 안 바뀌었으면 304 한 줄 — no-cache 가 "매번 다시 받기" 가 되지 않는다
        assert client.get(경로, headers={"If-None-Match": r.headers["etag"]}).status_code == 304, 경로


def test_API_응답에는_붙이지_않는다():
    r = client.get("/health")
    assert "cache-control" not in {k.lower() for k in r.headers.keys()}


# ---------- AI 를 부르는 경로 ----------
#
# AI 는 루틴 하나를 짓는 데 30~60초가 걸린다. 요청 제한(25초)이 그보다 짧아서 화면에는 "너무 오래 걸려 멈췄어요" 가
# 나가고, 멈추지 못하는 스레드는 끝까지 지은 다음 이용권을 깎았다 — 값은 치렀는데 루틴은 못 받는다(2026-09-20 재현).

가짜_루틴 = {"루틴": {"루틴명": "가짜 루틴", "목적": "기초",
                  "steps": [{"단계": "본운동", "동작": "걷기", "수행량": "10분"}]}}


def test_AI_경로의_제한은_AI_가_스스로_포기하는_시간보다_길다():
    """늦을 때는 AI 쪽이 먼저 포기해야 한다 — 그러면 값을 안 받고 무료 추천으로 넘어간다."""
    from backend import ai_recommend as air
    # 루틴 짓기는 재시도가 없다(두 번 내는 일을 막으려고) — 제한 시간 × (처음 + 재시도) 가운데 가장 긴 것
    assert air.longest_wait_sec() == max(air.TIMEOUT_SEC * 2 * (air.SDK_RETRIES + 1),
                                         air.COMPOSE_TIMEOUT_SEC * (air.COMPOSE_RETRIES + 1),
                                         air.PERIOD_TIMEOUT_SEC * 1.5 * (air.SDK_RETRIES + 1))
    assert m.AI_REQUEST_TIMEOUT_SEC > air.longest_wait_sec()
    for 경로 in ("/recommend/routines", "/recommend/periods", "/recommend/seasons", "/health/photo", "/schedule/photo"):
        assert m.request_limit_sec("POST", 경로) == m.AI_REQUEST_TIMEOUT_SEC, 경로
    # 무료 추천(GET)과 나머지는 그대로 짧다 — 이 제한이 생긴 까닭(추천의 무한 루프)이 그쪽이다
    assert m.request_limit_sec("GET", "/recommend/routines") == m.REQUEST_TIMEOUT_SEC
    assert m.request_limit_sec("POST", "/fitness-age") == m.REQUEST_TIMEOUT_SEC
    # AI 모듈이 실제로 그 재시도 횟수를 쓴다 — 숫자를 따로 적으면 위의 계산이 거짓이 된다
    src = Path(air.__file__).read_text(encoding="utf-8")
    assert src.count("max_retries=SDK_RETRIES)") == 3 and src.count("max_retries=COMPOSE_RETRIES)") == 1 and "max_retries=1" not in src


@pytest.fixture
def 이용권_있는_사람(monkeypatch):
    """가입시키고 이용권 1,000원을 넣는다(실결제 모드). AI 는 '쓸 수 있다' 로만 둔다 — 실제로 부르지 않는다."""
    from backend import auth, billing, community
    monkeypatch.setenv("AI_BILLING_MODE", "real")
    if not auth.is_postgres():
        monkeypatch.setattr(auth, "DB_PATH", Path(tempfile.mkdtemp()) / "t.db")
    auth.init_db(); community.init_db(); billing.init_db()
    c = TestClient(m.app)
    email = f"limit-{uuid.uuid4().hex[:10]}@x.com"
    assert c.post("/auth/signup", json={"email": email, "password": "pw12345678", "display_name": "가"}).status_code == 200
    with auth.db() as con:
        uid = con.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]
    billing.charge(uid, 1000, 1000, f"order-{uuid.uuid4().hex[:10]}")
    monkeypatch.setattr(m.air, "available", lambda: True)
    monkeypatch.setattr(m.air, "why_unavailable", lambda: None)
    return c, uid


def test_제한_안에_지어지면_루틴을_주고_값을_받는다(이용권_있는_사람, monkeypatch):
    from backend import billing
    c, uid = 이용권_있는_사람
    monkeypatch.setattr(m.air, "compose", lambda *a, **k: 가짜_루틴)
    r = c.post("/recommend/routines", json={"age_gbn": "성인", "ai": True})
    assert r.status_code == 200 and r.json()["출처"] == "ai" and r.json()["잔액"] == 1000 - m.AI_PRICE
    assert billing.balance(uid) == 1000 - m.AI_PRICE


def test_AI_추천은_평소_제한보다_오래_걸려도_끊기지_않는다(이용권_있는_사람, monkeypatch):
    """25초 · 60초를 1초 · 6초로 줄여 같은 상황을 만든다 — 짓는 데 1.5초."""
    from backend import billing
    c, uid = 이용권_있는_사람

    def 느린_짓기(*a, **k):
        time.sleep(1.5)
        return 가짜_루틴

    monkeypatch.setattr(m.air, "compose", 느린_짓기)
    monkeypatch.setattr(m, "REQUEST_TIMEOUT_SEC", 1.0)
    monkeypatch.setattr(m, "AI_REQUEST_TIMEOUT_SEC", 6.0)
    r = c.post("/recommend/routines", json={"age_gbn": "성인", "ai": True})
    assert r.status_code == 200 and r.json()["출처"] == "ai"
    assert billing.balance(uid) == 1000 - m.AI_PRICE


def test_끊긴_뒤에_지어진_루틴은_값을_받지_않는다(이용권_있는_사람, monkeypatch):
    """끊는 쪽은 답만 먼저 보낼 뿐 스레드를 멈추지 못한다. 그 스레드가 뒤늦게 값을 받으면 안 된다."""
    from backend import billing
    c, uid = 이용권_있는_사람

    def 느린_짓기(*a, **k):
        time.sleep(2.6)
        return 가짜_루틴

    monkeypatch.setattr(m.air, "compose", 느린_짓기)
    monkeypatch.setattr(m, "REQUEST_TIMEOUT_SEC", 2.0)
    monkeypatch.setattr(m, "AI_REQUEST_TIMEOUT_SEC", 2.0)
    r = c.post("/recommend/routines", json={"age_gbn": "성인", "ai": True})
    assert r.status_code == 503 and "너무 오래 걸려" in r.json()["detail"]
    assert billing.balance(uid) == 1000                     # 화면은 실패를 받았다 — 한 푼도 받지 않는다


def test_끊긴_뒤에_읽힌_시간표_사진도_횟수를_세지_않는다(이용권_있는_사람, monkeypatch):
    """시간표 사진은 '자세히 보기'(500원 · 7일) 안에서 쓴다 — 호출마다 값이 빠지진 않지만 횟수(DETAIL_LIMITS)는 센다.
    끊긴 뒤에 읽힌 것은 세지 않는다."""
    from backend import billing
    c, uid = 이용권_있는_사람
    assert c.post("/ai/detail").json()["잔액"] == 1000 - m.DETAIL_PRICE

    def 느린_읽기(*a, **k):
        time.sleep(2.6)
        return {"월": [{"시작": "09:00", "끝": "18:00"}]}

    monkeypatch.setattr(m.air, "read_schedule_photo", 느린_읽기)
    monkeypatch.setattr(m, "REQUEST_TIMEOUT_SEC", 2.0)
    monkeypatch.setattr(m, "AI_REQUEST_TIMEOUT_SEC", 2.0)
    r = c.post("/schedule/photo", json={"사진": "data:image/png;base64,AAAA"})
    assert r.status_code == 503
    assert billing.ai_uses_since(uid, "시간표사진", 0) == 0
    # 제때 읽히면 센다 — 값은 더 빠지지 않는다
    monkeypatch.setattr(m.air, "read_schedule_photo", lambda *a, **k: {"월": [{"시작": "09:00", "끝": "18:00"}]})
    monkeypatch.setattr(m, "AI_REQUEST_TIMEOUT_SEC", 60.0)
    r = c.post("/schedule/photo", json={"사진": "data:image/png;base64,AAAA"})
    assert r.status_code == 200 and r.json()["잔액"] == 1000 - m.DETAIL_PRICE
    assert billing.ai_uses_since(uid, "시간표사진", 0) == 1


def test_응답에_보안_헤더가_붙는다():
    """다른 사이트의 iframe 에 끼워 넣기(클릭 가로채기) · 파일 형식 추측 · 참조 주소 흘리기를 브라우저가 막게 한다."""
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=(self)" in r.headers["permissions-policy"]      # 날씨에 위치를 쓴다
    assert "camera=()" in r.headers["permissions-policy"]
