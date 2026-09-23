"""AI 관문 — 값표 · 시연 기간의 하루 무료 횟수 · 관리자 · 사용량 기록 (backend/main.py ai_allow · ai_settle · billing.ai_usage).

실결제가 안 되는 동안(카카오페이 키가 없거나 테스트 가맹점) 테스트 결제로 누구나 이용권을 공짜로 채울 수 있어서,
값으로 막는 건 막는 게 아니다. 그래서 시연 기간에는 값 대신 하루 횟수로 제한한다
(예현, 2026-09-22 "AI추천은 실제 결제가 안되는 동안은 3회, 약봉지 2회제한").
"""
import sys
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import ai_recommend as air  # noqa: E402
from backend import auth, billing, community  # noqa: E402
from backend import main as m  # noqa: E402
from backend.main import app  # noqa: E402
from test_ai_recommend import _fake_sdk, _지은응답, _네계절  # noqa: E402

루틴 = {"루틴명": "전신 HIIT", "목적": "다이어트", "steps": [{"동작": "버피", "단계": "본운동", "수행량": "10회"}]}
사진 = "data:image/png;base64," + "A" * 400


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.delenv("AI_BILLING_MODE", raising=False)      # 카카오페이 키가 없으니 시연 모드
    monkeypatch.delenv("KAKAOPAY_SECRET_KEY", raising=False)
    monkeypatch.delenv("ADMIN_USERS", raising=False)
    if auth.is_postgres():
        from pg_reset import reset_postgres
        reset_postgres()
    else:
        monkeypatch.setattr(auth, "DB_PATH", Path(tempfile.mkdtemp()) / "t.db")
        auth.init_db(); community.init_db(); billing.init_db()
    yield


def _user(email: str = "a@x.com", ip: str = "10.1.1.1") -> TestClient:
    c = TestClient(app)
    c.headers["X-Forwarded-For"] = ip
    c.post("/auth/signup", json={"email": email, "password": "pw12345678"})
    return c


def _ai(c, **params) -> dict:
    return c.post("/recommend/routines", json={"ai": True, "age_gbn": "성인", "limit": 3, **params}).json()


def test_시연_모드는_카카오페이_설정으로_정해진다(monkeypatch):
    assert m.billing_mode() == "demo"                             # 키가 없다
    monkeypatch.setenv("KAKAOPAY_SECRET_KEY", "k")
    monkeypatch.setenv("KAKAOPAY_CID", "TC0ONETIME")
    assert m.billing_mode() == "demo"                             # 테스트 가맹점
    monkeypatch.setenv("KAKAOPAY_CID", "C1234567")
    assert m.billing_mode() == "real"
    monkeypatch.setenv("AI_BILLING_MODE", "demo")
    assert m.billing_mode() == "demo"                             # 환경변수가 이긴다


def test_시연에는_루틴을_하루_세_번_무료로(monkeypatch):
    _fake_sdk(monkeypatch, _지은응답())
    a = _user()
    for i in range(3):
        d = _ai(a)
        assert d["출처"] == "ai" and d["잔액"] == 0, i               # 이용권 없이 된다
        assert d["오늘남음"]["루틴"] == 2 - i
    d = _ai(a)
    assert d["출처"] == "점수" and "다 썼어요" in d["안내"] and len(d["추천"]) == 3
    s = a.get("/recommend/ai-status").json()
    assert s["시연"] is True and s["오늘남음"] == {"루틴": 0, "구간": 3, "사진": 2}
    # 조정도 루틴 횟수에 든다
    d = _ai(a, 조정="더 어렵게", 이전루틴={"루틴명": "x", "steps": []})
    assert d["출처"] == "점수" and "다 썼어요" in d["안내"]


def test_시연에는_사진을_하루_두_번_구간_계획은_세_번(monkeypatch):
    _fake_sdk(monkeypatch, '{"건강상태":["당뇨"],"메모":"","바쁜시간":{}}')
    a = _user()
    assert a.post("/health/photo", json={"사진": 사진}).json()["오늘남음"]["사진"] == 1
    assert a.post("/schedule/photo", json={"사진": 사진}).json()["오늘남음"]["사진"] == 0   # 약봉지 · 시간표를 합쳐 센다
    r = a.post("/health/photo", json={"사진": 사진})
    assert r.status_code == 429 and "다 썼어요" in r.json()["detail"]
    assert a.post("/schedule/photo", json={"사진": 사진}).status_code == 429
    assert a.post("/ai/detail").status_code == 400                # 시연 기간에는 살 것이 없다

    _fake_sdk(monkeypatch, _네계절())
    for _ in range(3):
        assert a.post("/recommend/seasons", json={"age_gbn": "성인", "루틴": 루틴}).status_code == 200
    r = a.post("/recommend/seasons", json={"age_gbn": "성인", "루틴": 루틴})
    assert r.status_code == 429 and "다 썼어요" in r.json()["detail"]


def test_한_곳에서_계정을_늘려도_하루_합계가_있다(monkeypatch):
    _fake_sdk(monkeypatch, _지은응답())
    monkeypatch.setattr(m, "DEMO_IP_LIMIT", 4)
    a, b = _user("a@x.com", "10.9.9.9"), _user("b@x.com", "10.9.9.9")
    for _ in range(2):
        assert _ai(a)["출처"] == "ai" and _ai(b)["출처"] == "ai"
    d = _ai(_user("c@x.com", "10.9.9.9"))
    assert d["출처"] == "점수" and "이곳에서" in d["안내"]
    assert _ai(_user("d@x.com", "10.9.9.10"))["출처"] == "ai"     # 다른 곳은 상관없다


def test_관리자는_값도_횟수도_없다(monkeypatch):
    """팀이 직접 써 보는 데 값을 치르지 않게 — 이메일이나 'provider:uid' 로 적는다."""
    _fake_sdk(monkeypatch, _지은응답())
    monkeypatch.setenv("ADMIN_USERS", "password:boss@x.com, kakao:777, social@x.com")
    a = _user("boss@x.com")
    assert a.get("/auth/me").json()["계정"] == "password:boss@x.com"
    for _ in range(5):
        assert _ai(a)["출처"] == "ai"
    s = a.get("/recommend/ai-status").json()
    assert s["관리자"] is True and s["오늘남음"] is None
    # 실결제 모드에서도 이용권이 빠지지 않는다
    monkeypatch.setenv("AI_BILLING_MODE", "real")
    assert _ai(a)["출처"] == "ai" and a.get("/credit").json()["잔액"] == 0
    assert m.is_admin({"email": None, "provider": "kakao", "provider_uid": "777"})
    assert not m.is_admin({"email": "x@x.com", "provider": "kakao", "provider_uid": "778"})
    # 소셜 계정은 이메일로도 되지만, 비밀번호 계정은 이메일을 확인한 적이 없어 이메일만으로는 안 된다
    assert m.is_admin({"email": "social@x.com", "provider": "kakao", "provider_uid": "1"})
    assert not m.is_admin({"email": "social@x.com", "provider": "password", "provider_uid": "social@x.com"})


def test_호출마다_토큰_수를_남긴다(monkeypatch):
    """원가는 청구서가 아니라 여기서 안다 — 관리자만 본다."""
    class _U:
        input_tokens, output_tokens, cache_read_input_tokens = 11000, 4200, 0

    class _Blk:
        type, text = "text", _지은응답()

    class _Msg:
        content, stop_reason, usage, model = [_Blk()], "end_turn", _U(), "claude-opus-5"

    class _Client:
        def __init__(self, **kw): self.messages = self

        def create(self, **kw): return _Msg()

    mod = type(sys)("anthropic")
    mod.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ADMIN_USERS", "password:boss@x.com")
    air.take_usage()                                                # 다른 테스트가 이 스레드에 남긴 것을 비운다 (스레드마다 따로다)
    a = _user("a@x.com")
    assert _ai(a)["출처"] == "ai"
    assert a.get("/ai/usage").status_code == 403
    d = _user("boss@x.com").get("/ai/usage").json()
    assert d["종류별"]["루틴"] == {"호출": 1, "받은값": 0, "입력토큰": 11000, "출력토큰": 4200, "캐시토큰": 0}
    assert air.take_usage() is None                                # 꺼내 갔으니 비어 있다


def test_같은_사람이_동시에_둘을_부르지_못한다():
    with m._ai_turn(7):
        with pytest.raises(Exception) as e:
            with m._ai_turn(7):
                pass
        assert e.value.status_code == 429
        with m._ai_turn(8):                                        # 다른 사람은 된다
            pass
    with m._ai_turn(7):                                            # 끝나면 다시 된다
        pass


def test_루틴_짓기는_다시_부르지_않고_제한도_사실상_없다():
    """제한 시간에 걸린 첫 호출도 저쪽에선 끝까지 돌아 값이 매겨진다 — 한 번 더 부르면 두 번 내고 하나도 못 준다.
    루틴 짓기는 요청과 떼어 백그라운드에서 돌리므로 제한은 SDK 기본(600초)뿐이고, 요청 제한에는 들지 않는다."""
    assert air.COMPOSE_RETRIES == 0 and air.COMPOSE_TIMEOUT_SEC >= 600
    assert m.AI_REQUEST_TIMEOUT_SEC > air.longest_wait_sec() >= air.PERIOD_TIMEOUT_SEC
    assert air.COMPOSE_TIMEOUT_SEC > air.longest_wait_sec()          # 요청 제한과 무관하다


# ---------- 백그라운드 루틴 작업 ----------

def _slow_sdk(monkeypatch, 응답, 초: float):
    """가짜 SDK 가 응답 전에 초 만큼 잔다 — 요청이 기다리는 시간(JOB_WAIT_SEC)보다 길게."""
    import time as _t
    _fake_sdk(monkeypatch, 응답)
    mod = sys.modules["anthropic"]
    원래 = mod.Anthropic

    class 느린:
        def __init__(self, **kw):
            self._c = 원래(**kw)
            self.messages = self

        def create(self, **kw):
            _t.sleep(초)
            return self._c.messages.create(**kw)

    mod.Anthropic = 느린


def _wait_job(a: TestClient, job_id: int, 초: float = 10.0) -> dict:
    import time as _t
    끝 = _t.monotonic() + 초
    while _t.monotonic() < 끝:
        j = a.get(f"/recommend/ai-job/{job_id}").json()
        if j["상태"] != "running":
            return j
        _t.sleep(0.1)
    raise AssertionError("작업이 끝나지 않는다")


def test_루틴_작업은_요청이_돌아온_뒤에도_끝까지_짓고_결과를_남긴다(monkeypatch):
    """요청은 JOB_WAIT_SEC 만 기다리고 작업 번호를 준다. 스레드가 끝까지 짓고 값을 받고, 화면은 작업 번호로 가져간다."""
    monkeypatch.setattr(m, "JOB_WAIT_SEC", 0.2)
    _slow_sdk(monkeypatch, _지은응답(), 1.0)
    a = _user()
    d = _ai(a)
    assert d["출처"] == "점수" and d["작업"]["상태"] == "running" and d["작업"]["종류"] == "루틴"
    assert "짓는 중" in d["안내"] and d["작업"]["예상초"] > 0
    job_id = d["작업"]["id"]
    s = a.get("/recommend/ai-status").json()
    assert s["작업"]["id"] == job_id and s["작업"]["상태"] == "running"           # 새로고침해도 이어서 기다린다
    # 짓는 동안 한 번 더 누르면 429
    r = a.post("/recommend/routines", json={"age_gbn": "성인", "weak": [], "sports": [], "ai": True, "limit": 3})
    assert r.status_code == 429
    j = _wait_job(a, job_id)
    assert j["상태"] == "done" and j["결과"]["출처"] == "ai" and len(j["결과"]["추천"]) == 1
    assert j["결과"]["오늘남음"]["루틴"] == 2                                   # 값(시연 횟수)은 스레드가 받았다
    assert j["지난초"] >= 1.0 and j["예상초"] > 0
    assert a.get("/recommend/ai-status").json()["작업"] is None               # 가져갔으니 더는 알리지 않는다
    assert billing.job_typical_sec("루틴") >= 1.0                               # 다음 사람에게 '보통 이만큼'


def test_루틴_작업이_빨리_끝나면_예전처럼_결과를_바로_준다(monkeypatch):
    _fake_sdk(monkeypatch, _지은응답())
    a = _user()
    d = _ai(a)
    assert d["출처"] == "ai" and "작업" not in d
    assert a.get("/recommend/ai-status").json()["작업"] is None


def test_루틴_작업이_실패하면_값을_받지_않고_다시_받을_수_있다(monkeypatch):
    monkeypatch.setattr(m, "JOB_WAIT_SEC", 0.2)
    _slow_sdk(monkeypatch, "이건 JSON 이 아니다", 0.5)
    a = _user()
    d = _ai(a)
    job_id = d["작업"]["id"]
    j = _wait_job(a, job_id)
    assert j["상태"] == "done" and j["결과"]["출처"] == "점수" and "못 지어" in j["결과"]["안내"]
    assert j["결과"]["오늘남음"]["루틴"] == 3                                   # 폴백은 횟수를 깎지 않는다
    with m._ai_turn(auth.user_for_token(a.cookies.get(auth.SESSION_COOKIE))["id"]):   # 잠금도 풀렸다
        pass


def test_남의_작업은_못_본다(monkeypatch):
    monkeypatch.setattr(m, "JOB_WAIT_SEC", 0.2)
    _slow_sdk(monkeypatch, _지은응답(), 0.5)
    a = _user()
    job_id = _ai(a)["작업"]["id"]
    b = _user("b@x.com", "10.1.1.2")
    assert b.get(f"/recommend/ai-job/{job_id}").status_code == 404
    _wait_job(a, job_id)


def test_서버가_도중에_죽은_작업은_실패로_본다():
    a = _user()
    uid = auth.user_for_token(a.cookies.get(auth.SESSION_COOKIE))["id"]
    job_id = billing.job_start(uid, "루틴", now=time.time() - billing.JOB_STALE_SEC - 5)
    j = a.get(f"/recommend/ai-job/{job_id}").json()
    assert j["상태"] == "failed" and "다시 받아" in j["오류"]
    assert a.get("/recommend/ai-status").json()["작업"] is None


def test_값표와_선결제_팩():
    assert m.PRICES == {"루틴": 500, "조정": 300, "자세히": 500, "건강사진": 300}
    packs = TestClient(app).get("/pay/methods").json()
    assert packs["시연"] is True and packs["값표"] == m.PRICES
    표 = {p["결제"]: (p["이용권"], p["보너스"]) for p in packs["packs"]}
    assert 표 == {500: (500, 0), 1000: (1100, 10), 3000: (3450, 15), 5000: (6000, 20), 10000: (12500, 25)}
    # 보너스는 25% 까지 — 한 번 쓸 때마다 원가 200원 안팎이 나가서 그보다 깊으면 팔수록 손해다
    assert max(p["보너스"] for p in packs["packs"]) <= 25


def test_구독하면_값_없이_하루_다섯_번(monkeypatch):
    """한 달 구독 — AI 루틴 하루 5회(조정 포함) · 자세히 보기 포함 · 약봉지 사진 5회. 실결제 모드에서도 이용권이 빠지지 않는다."""
    _fake_sdk(monkeypatch, _지은응답())
    monkeypatch.setenv("AI_BILLING_MODE", "real")
    a = _user("sub@x.com")
    uid = auth.user_for_token(a.cookies.get("quadriga_session"))["id"]
    assert _ai(a)["출처"] == "점수"                                    # 이용권도 구독도 없다
    billing.add_addon(uid, "구독", 30, memo="테스트")
    for i in range(5):
        d = _ai(a)
        assert d["출처"] == "ai" and d["잔액"] == 0 and d["오늘남음"]["루틴"] == 4 - i, i
    d = _ai(a)
    assert d["출처"] == "점수" and "구독으로 오늘" in d["안내"]
    s = a.get("/recommend/ai-status").json()
    assert s["구독"]["까지"] > 0 and s["오늘남음"] == {"루틴": 0, "구간": 5, "사진": 5}
    assert a.post("/ai/detail").status_code == 400                    # 자세히 보기는 구독에 들어 있다
    _fake_sdk(monkeypatch, _네계절())
    assert a.post("/recommend/seasons", json={"age_gbn": "성인", "루틴": 루틴}).status_code == 200
    assert a.get("/credit").json()["잔액"] == 0


def test_실결제로_바꿀_때_시연_이용권을_정리한다(monkeypatch):
    """시연 결제로 얻은 이용권 · 구독은 정식 결제가 열릴 때 소멸(약관 6조의2). 관리자만, 실결제 모드에서만, 확인 문구가 맞아야."""
    monkeypatch.setenv("ADMIN_USERS", "password:boss@x.com")
    a, boss = _user("a@x.com"), _user("boss@x.com")
    uid = auth.user_for_token(a.cookies.get("quadriga_session"))["id"]
    billing.charge(uid, 3450, 3000, "demo-order")
    billing.new_order("demo-order", uid, "T1", 3450, 3000)
    billing.set_status("demo-order", "paid")
    billing.spend(uid, 500, "AI 추천")
    billing.add_addon(uid, "구독", 30)
    확인 = {"확인": "시연 이용권을 모두 지웁니다"}
    assert a.post("/admin/reset-demo-credits", json=확인).status_code == 403                 # 관리자만
    assert boss.post("/admin/reset-demo-credits", json=확인).status_code == 409              # 아직 시연 모드
    monkeypatch.setenv("AI_BILLING_MODE", "real")
    assert boss.post("/admin/reset-demo-credits", json={"확인": "지워"}).status_code == 400   # 문구가 달라도 안 됨
    d = boss.post("/admin/reset-demo-credits", json=확인).json()
    assert d == {"지운사람": 1, "지운이용권": 2950, "끝낸구독": 1, "끝낸자세히": 0, "시연주문": 1}
    assert billing.balance(uid) == 0 and billing.active_addon(uid, "구독") is None
    assert billing.get_order("demo-order")["status"] == "demo"                                # 환불 대상에서 빠졌다
    내역 = a.get("/credit").json()["내역"]
    assert 내역[0]["종류"] == "시연 정리" and 내역[0]["금액"] == 2950                          # 내역은 남는다
    assert boss.post("/admin/reset-demo-credits", json=확인).json()["지운사람"] == 0          # 두 번 눌러도 더 지울 게 없다

def test_손님에게도_시연_하루_횟수를_알려준다():
    """비로그인 상태의 ai-status — 오늘남음은 없지만(누구인지 모른다) 시연하루로 '로그인하면 하루 3회' 를 적을 수 있다."""
    s = TestClient(app).get("/recommend/ai-status").json()
    assert s["로그인"] is False and s["시연"] is True and s["오늘남음"] is None
    assert s["시연하루"] == {"루틴": 3, "구간": 3, "사진": 2}
