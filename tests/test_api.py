"""API 스모크 테스트.

실행:
    pytest -q

서버를 따로 띄우지 않아도 된다. FastAPI TestClient 가 앱을 직접 호출한다.
화면(frontend/)이 기대하는 응답 모양이 깨지지 않았는지 확인하는 것이 목적이다.
API 응답의 키 이름을 바꾸면 화면이 조용히 깨지므로, 바꿀 때는 이 파일도 함께 고친다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import app  # noqa: E402

client = TestClient(app)

ADULT = {"age_gbn": "성인", "sex": "M", "flexibility": 8.0, "strength": 25,
         "height_cm": 175, "weight_kg": 74}


def data_ready() -> bool:
    h = client.get("/health").json()
    return h["분포_로드됨"] and h["처방_로드됨"]


needs_data = pytest.mark.skipif(
    not data_ready(), reason="분포/처방 데이터 없음 — /health 안내 참고"
)


# ---------- 기본 ----------

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_frontend_served():
    """화면과 API 를 같은 서버가 내보낸다."""
    r = client.get("/")
    assert r.status_code == 200
    assert "체력나이" in r.text
    assert client.get("/js/api.js").status_code == 200


def test_purposes():
    """목적 목록은 데이터 없이도 떠야 한다 (화면 2가 먼저 로드된다)."""
    body = client.get("/purposes").json()
    assert len(body) == 5
    assert {"목적", "우선요인"} <= set(body[0])


# ---------- 체력나이 ----------

@needs_data
def test_fitness_age_성인():
    b = client.post("/fitness-age", json=ADULT).json()
    assert 10 < b["체력나이"] < 100
    assert b["신뢰구간"] > 0
    assert {"유연성", "근력", "체성분"} <= set(b["항목별"])
    assert b["약점"]["약점"] in b["항목별"]


@needs_data
def test_fitness_age_어르신():
    r = client.post("/fitness-age",
                    json={"age_gbn": "어르신", "sex": "F",
                          "flexibility": 10.0, "strength": 18, "bmi": 23.5})
    assert r.status_code == 200
    assert r.json()["체력나이"] > 50


@needs_data
def test_bmi_는_양방향_편차():
    """저체중도 과체중처럼 불리하게 잡혀야 한다 (BMI 는 U 자형)."""
    def 체성분(bmi):
        return client.post("/fitness-age",
                           json={"age_gbn": "성인", "sex": "M", "bmi": bmi}
                           ).json()["항목별"]["체성분"]

    assert 체성분(16.0) > 체성분(22.0)
    assert 체성분(30.0) > 체성분(22.0)


@needs_data
def test_청소년은_구간부족으로_거절():
    """공개 데이터에 연령구간이 2개뿐이라 보간이 무의미하다 → 산출하지 않는다."""
    r = client.post("/fitness-age",
                    json={"age_gbn": "청소년", "sex": "M",
                          "flexibility": 10, "strength": 25, "bmi": 21})
    assert r.status_code == 422


def test_측정값_없으면_400():
    assert client.post("/fitness-age",
                       json={"age_gbn": "성인", "sex": "M"}).status_code == 400


def test_없는_연령군은_422():
    assert client.post("/fitness-age",
                       json={"age_gbn": "유아", "sex": "M", "strength": 25}
                       ).status_code == 422


# ---------- 루틴 ----------

@needs_data
def test_routine_순서():
    steps = client.get("/routine", params={"age_gbn": "성인", "sex": "M",
                                           "purpose": "다이어트",
                                           "weak_factor": "근력"}).json()
    order = ["준비운동", "본운동", "정리운동"]
    assert [s["단계"] for s in steps] == sorted(
        (s["단계"] for s in steps), key=order.index)
    assert steps[0]["단계"] == "준비운동"
    assert steps[-1]["단계"] == "정리운동"


@needs_data
def test_recheck_변화량():
    b = client.post("/recheck", json={
        "이전": ADULT,
        "현재": {**ADULT, "flexibility": 12.0, "strength": 32, "weight_kg": 72},
    }).json()
    assert b["변화"] == round(b["현재"] - b["이전"], 1)
    assert b["변화"] < 0          # 측정값이 좋아졌으니 체력나이는 내려가야 한다


# ---------- 일상 처방 ----------

def test_daily_계단은_근력에_따라_달라진다():
    약 = client.get("/daily", params={"strength_stars": 1}).json()
    강 = client.get("/daily", params={"strength_stars": 5}).json()
    assert 약["계단"]["수준"] == "하위"
    assert 강["계단"]["수준"] == "상위"
    assert 약["계단"]["문구"] != 강["계단"]["문구"]


def test_daily_먼_거리는_걷기를_권하지_않는다():
    assert client.get("/daily", params={"walk_minutes": 12}).json()["도보"]["권장"] is True
    assert client.get("/daily", params={"walk_minutes": 45}).json()["도보"]["권장"] is False
    assert client.get("/daily").json()["도보"] is None


def test_daily_강도는_4주마다_올라간다():
    assert client.get("/daily", params={"days_since_start": 0}).json()["강도"]["세트"] == 2
    assert client.get("/daily", params={"days_since_start": 40}).json()["강도"]["세트"] == 3


# ---------- 동영상 ----------

def test_videos_요인_부분일치():
    """동영상 API 요인명은 '근력·근지구력' 처럼 묶여 있다."""
    assert client.get("/videos", params={"factor": "근력"}).json()["개수"] > 0


def test_videos_부담부위_제외():
    전체 = client.get("/videos", params={"factor": "근력"}).json()["개수"]
    제외 = client.get("/videos", params={"factor": "근력",
                                      "exclude_parts": "무릎"}).json()["개수"]
    assert 제외 < 전체


def test_centers_거리순():
    items = client.get("/centers", params={"lat": 37.55, "lon": 127.0,
                                           "limit": 3}).json()["items"]
    거리 = [c["거리km"] for c in items]
    assert 거리 == sorted(거리)


# ---------- 성장기 (만 11~18세) ----------

@needs_data
def test_성장기_산출된다():
    """5세 단위로 묶으면 구간이 2개뿐이라 계산이 무너진다.
    1세 단위(11~18, 8구간)로 나눠야 보간이 의미를 갖는다."""
    b = client.post("/fitness-age", json={
        "age_gbn": "성장기", "sex": "M", "age": 15,
        "flexibility": 6, "strength": 195, "height_cm": 170, "weight_kg": 61,
    }).json()
    assert 11 <= b["체력나이"] <= 19
    assert "순발력" in b["항목별"]        # 성장기 근력 항목은 제자리멀리뛰기
    assert "발달" in b["해석"]


@needs_data
def test_성장기_잘하면_발달수준이_높게_나온다():
    """성장기는 나이가 들수록 기록이 좋아진다 → 방향이 성인과 반대다."""
    def 산출(flex, jump):
        return client.post("/fitness-age", json={
            "age_gbn": "성장기", "sex": "M", "age": 15,
            "flexibility": flex, "strength": jump, "bmi": 21}).json()["체력나이"]

    assert 산출(14, 225) > 산출(4, 165)


@needs_data
def test_또래백분위():
    b = client.post("/fitness-age", json={
        "age_gbn": "성인", "sex": "M", "age": 45,
        "flexibility": 8, "strength": 25, "bmi": 24.2}).json()
    p = b["또래비교"]["근력"]
    assert 0 <= p["백분위"] <= 100
    assert p["표본수"] > 30
    assert "백분위" not in b["또래비교"]["체성분"]     # BMI 는 U자형이라 백분위를 내지 않는다


@needs_data
def test_환산나이는_절대_음수가_안된다():
    """website/server.js 에 있던 결함: 재점검 캡 때문에 개선효과가 음수로 나왔다."""
    for flex in (-30, -10, 0, 15, 50):
        for st in (0, 5, 40, 200):
            for bmi in (10, 22, 45):
                r = client.post("/fitness-age", json={
                    "age_gbn": "성인", "sex": "M", "age": 45,
                    "flexibility": flex, "strength": st, "bmi": bmi})
                if r.status_code != 200:
                    continue
                b = r.json()
                assert b["체력나이"] > 0
                assert all(v > 0 for v in b["항목별"].values())
                if b["약점"] and "개선효과" in b["약점"]:
                    assert all(g >= 0 for g in b["약점"]["전체"].values())


@needs_data
def test_recheck_는_측정편차와_함께_알려준다():
    """작은 변화를 '좋아졌다' 고 단정하지 않는다."""
    base = {"age_gbn": "성인", "sex": "M", "age": 45,
            "flexibility": 8, "strength": 25, "height_cm": 175, "weight_kg": 74}
    b = client.post("/recheck", json={"이전": base,
                                      "현재": {**base, "flexibility": 9.5}}).json()
    assert b["측정편차"] > 0
    assert b["유의미한변화"] is False
    assert "편차" in b["메시지"]


# ---------- 체력나이 안정화 (기획안 개정 4절) ----------

@needs_data
def test_한_항목이_극단이어도_체력나이가_튀지_않는다():
    """20세 사용자가 유연성 하나만 아주 낮아도 체력나이가 40~50대로 튀면 안 된다."""
    b = client.post("/fitness-age", json={
        "age_gbn": "성인", "sex": "M", "age": 20,
        "flexibility": -25, "strength": 30, "height_cm": 175, "weight_kg": 68,
    }).json()
    assert b["체력나이"] <= 20 + 15          # 실제 나이 ±15세 안
    assert b["체력나이"] >= 20 - 15
    # 극단적으로 부족한 항목은 그대로 삼키지 않고 집중 개선 영역으로 표시한다
    assert "유연성" in b["집중개선영역"]


@needs_data
def test_또래_평균_수준이면_집중개선영역이_비어있다():
    b = client.post("/fitness-age", json={
        "age_gbn": "성인", "sex": "M", "age": 40,
        "flexibility": 12, "strength": 45, "height_cm": 175, "weight_kg": 72,
    }).json()
    assert b["집중개선영역"] == []


@needs_data
def test_안정화_극단값_스윕():
    """나이·측정값을 넓게 훑어도 체력나이가 실제 나이 ±15세를 벗어나지 않는다."""
    for age in (19, 25, 45, 64):
        for flex in (-30, 0, 40):
            for st in (0, 25, 60):
                for bmi in (15, 22, 38):
                    r = client.post("/fitness-age", json={
                        "age_gbn": "성인", "sex": "M", "age": age,
                        "flexibility": flex, "strength": st, "bmi": bmi})
                    if r.status_code != 200:
                        continue
                    ba = r.json()["체력나이"]
                    assert age - 15 <= ba <= age + 15, (age, flex, st, bmi, ba)


# ---------- 영상 루틴 (backend/routine_player.py 연결) ----------

def test_video_routine_준비_본_정리_순서():
    b = client.get("/video-routine",
                   params={"factor": "근력·근지구력", "main_count": 2}).json()
    assert b["상태"] == "complete"
    assert [s["단계"] for s in b["steps"]] == ["준비운동", "본운동", "본운동", "정리운동"]
    assert b["총시간초"] > 0


def test_video_routine_부담부위_제외():
    전체 = client.get("/video-routine", params={"factor": "근력·근지구력"}).json()
    제외 = client.get("/video-routine",
                    params={"factor": "근력·근지구력", "exclude_parts": "허리,무릎"}).json()
    부위 = [s["영상명"] for s in 제외["steps"]]
    assert 부위 != [s["영상명"] for s in 전체["steps"]]


# ---------- 계정 ----------

@pytest.fixture(autouse=True, scope="module")
def _clean_db():
    """테스트용 DB 를 따로 쓴다.

    DATABASE_URL 이 있으면 그 Postgres 로, 없으면 임시 SQLite 파일로 돈다.
    배포(Postgres)와 로컬(SQLite)에서 같은 테스트가 통과해야 한다.
    """
    import os
    import tempfile
    from backend import auth
    old = auth.DB_PATH
    if auth.is_postgres():
        with auth.db() as con:                    # 남은 데이터를 비우고 시작
            auth.init_db()
            for t in ("measurements", "sessions", "oauth_states", "users"):
                con.execute(f"DELETE FROM {t}")
    else:
        auth.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
        auth.init_db()
    yield
    auth.DB_PATH = old


def _fresh():
    return TestClient(app)


def test_가입_로그인_로그아웃():
    c = _fresh()
    assert c.get("/auth/me").json()["로그인"] is False

    r = c.post("/auth/signup", json={"email": "A@Example.com",
                                     "password": "abcd1234", "display_name": "예현"})
    assert r.status_code == 200
    assert c.get("/auth/me").json() == {"로그인": True, "이름": "예현", "수단": "password"}

    c.post("/auth/logout")
    assert c.get("/auth/me").json()["로그인"] is False

    # 이메일 대소문자는 같은 계정으로 본다
    assert c.post("/auth/login", json={"email": "a@example.com",
                                       "password": "abcd1234"}).status_code == 200


def test_약한_비밀번호는_거절():
    c = _fresh()
    for pw in ("short1a", "12345678", "abcdefgh"):
        r = c.post("/auth/signup", json={"email": f"{pw}@ex.com", "password": pw})
        assert r.status_code == 400


def test_비밀번호는_평문으로_저장되지_않는다():
    from backend import auth
    c = _fresh()
    c.post("/auth/signup", json={"email": "hash@ex.com", "password": "abcd1234"})
    row = auth.find_password_user("hash@ex.com")
    assert row["password_hash"] not in (None, b"")
    assert b"abcd1234" not in bytes(row["password_hash"])
    assert auth.verify_password("abcd1234", row["password_salt"], row["password_hash"])
    assert not auth.verify_password("abcd12345", row["password_salt"], row["password_hash"])


def test_없는_계정과_틀린_비밀번호는_같은_응답():
    """다르면 어떤 이메일이 가입돼 있는지 알아낼 수 있다."""
    c = _fresh()
    c.post("/auth/signup", json={"email": "exists@ex.com", "password": "abcd1234"})
    a = c.post("/auth/login", json={"email": "exists@ex.com", "password": "wrong123a"})
    b = c.post("/auth/login", json={"email": "nobody@ex.com", "password": "wrong123a"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_로그인_없이는_기록에_못_들어간다():
    c = _fresh()
    assert c.get("/me/measurements").status_code == 401
    assert c.post("/me/measurements", json={"체력나이": 40}).status_code == 401


def test_기록은_기기_간에_이어진다():
    """같은 계정으로 다른 클라이언트에서 로그인하면 기록이 따라온다."""
    기기A = _fresh()
    기기A.post("/auth/signup", json={"email": "sync@ex.com", "password": "abcd1234"})
    기기A.post("/me/measurements", json={"체력나이": 42.0, "age": 45})

    기기B = _fresh()                      # 쿠키를 공유하지 않는 새 클라이언트
    assert 기기B.get("/me/measurements").status_code == 401
    기기B.post("/auth/login", json={"email": "sync@ex.com", "password": "abcd1234"})
    기록 = 기기B.get("/me/measurements").json()["기록"]
    assert 기록[0]["체력나이"] == 42.0


def test_세션쿠키는_httponly():
    c = _fresh()
    r = c.post("/auth/signup", json={"email": "cookie@ex.com", "password": "abcd1234"})
    setc = r.headers.get("set-cookie", "")
    assert "httponly" in setc.lower()
    assert "samesite=lax" in setc.lower()


def test_소셜은_전화번호_생일을_버린다():
    """제공자가 보내와도 KEEP_FIELDS 밖은 저장되지 않는다."""
    from backend import auth
    kakao = auth.normalize_profile("kakao", {
        "id": 777,
        "kakao_account": {"email": "k@ex.com", "phone_number": "010-1234-5678",
                          "birthday": "0101", "gender": "male",
                          "shipping_addresses": [{"base_address": "서울시"}],
                          "profile": {"nickname": "카카오사용자"}},
    })
    assert kakao == {"uid": "777", "email": "k@ex.com", "name": "카카오사용자"}

    naver = auth.normalize_profile("naver", {"response": {
        "id": "n1", "email": "n@ex.com", "nickname": "네이버사용자",
        "mobile": "010-0000-0000", "birthday": "01-01", "age": "20-29"}})
    assert naver == {"uid": "n1", "email": "n@ex.com", "name": "네이버사용자"}


def test_미설정_소셜은_안내를_준다():
    c = _fresh()
    r = c.get("/auth/google/start", follow_redirects=False)
    assert r.status_code == 503
    assert "CLIENT_ID" in r.json()["detail"]


def test_계정_삭제():
    c = _fresh()
    c.post("/auth/signup", json={"email": "bye@ex.com", "password": "abcd1234"})
    c.post("/me/measurements", json={"체력나이": 50})
    assert c.request("DELETE", "/auth/me").status_code == 200
    assert c.post("/auth/login", json={"email": "bye@ex.com",
                                       "password": "abcd1234"}).status_code == 401


def test_setup_페이지가_리디렉션_URI를_보여준다():
    c = _fresh()
    html = c.get("/auth/setup").text
    for p in ("google", "naver", "kakao"):
        assert f"/auth/{p}/callback" in html


def test_콜백을_직접_열면_설명이_나온다():
    """에러 페이지가 아니라 '원래 이런 주소다' 라고 알려줘야 한다."""
    c = _fresh()
    r = c.get("/auth/google/callback", follow_redirects=False)
    assert r.status_code == 200
    assert "통로" in r.text


# ---------- 배포 ----------

def test_프록시_뒤에서_https로_인식한다():
    """Render 는 앞에 프록시가 있어 request.url.scheme 이 http 로 보인다.
    그대로 쓰면 OAuth 리디렉션 URI 가 콘솔 등록값과 어긋나고 쿠키도 Secure 가 안 붙는다."""
    c = _fresh()
    h = {"x-forwarded-proto": "https", "host": "fitness.example.com"}
    html = c.get("/auth/setup", headers=h).text
    assert "https://fitness.example.com/auth/google/callback" in html

    r = c.post("/auth/signup", json={"email": "proxy@ex.com", "password": "abcd1234"},
               headers=h)
    assert "secure" in r.headers.get("set-cookie", "").lower()


def test_로컬_http에서는_secure를_붙이지_않는다():
    """붙이면 localhost 에서 쿠키가 저장되지 않아 로그인이 안 된다."""
    c = _fresh()
    r = c.post("/auth/signup", json={"email": "local@ex.com", "password": "abcd1234"})
    assert "secure" not in r.headers.get("set-cookie", "").lower()


def test_카카오는_client_secret_없이도_켜진다(monkeypatch):
    """카카오 Client Secret 은 콘솔에서 켜야만 생기는 선택 항목이다.
    없다고 로그인 자체를 막으면 안 된다."""
    from backend import auth
    monkeypatch.setenv("KAKAO_CLIENT_ID", "test-id")
    monkeypatch.delenv("KAKAO_CLIENT_SECRET", raising=False)
    assert "kakao" in auth.enabled_providers()

    c = _fresh()
    assert "kakao" in c.get("/auth/providers").json()["소셜"]
    r = c.get("/auth/kakao/start", follow_redirects=False)
    assert r.status_code in (302, 307)          # 제공자로 넘어간다


def test_구글은_secret이_없으면_켜지지_않는다(monkeypatch):
    from backend import auth
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-id")
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    assert "google" not in auth.enabled_providers()

    c = _fresh()
    r = c.get("/auth/google/start", follow_redirects=False)
    assert r.status_code == 503
    assert "_CLIENT_SECRET" in r.json()["detail"]


def test_카카오는_scope를_보내지_않는다(monkeypatch):
    """필수 동의로 켠 항목은 카카오가 알아서 포함한다.
    그걸 scope 에 또 적으면 KOE206, 안 켠 항목을 적으면 KOE205 로 로그인이 막힌다."""
    from backend import auth
    monkeypatch.delenv("KAKAO_SCOPE", raising=False)
    assert auth.scope_for("kakao") == ""


def test_공백만_있는_scope는_없는_것으로_친다(monkeypatch):
    """환경변수 칸을 완전히 비우기 어려운 콘솔이 있다. 공백도 빈 값으로 본다."""
    from backend import auth
    monkeypatch.setenv("KAKAO_SCOPE", "   ")
    assert auth.scope_for("kakao") == ""


def test_scope는_환경변수로_바꿀_수_있다(monkeypatch):
    """검수를 통과하면 코드 수정 없이 이메일을 다시 넣을 수 있어야 한다."""
    from backend import auth
    monkeypatch.setenv("KAKAO_SCOPE", "profile_nickname account_email")
    assert auth.scope_for("kakao") == "profile_nickname account_email"


def test_start가_카카오에는_scope를_안_붙인다(monkeypatch):
    monkeypatch.setenv("KAKAO_CLIENT_ID", "test-id")
    monkeypatch.delenv("KAKAO_SCOPE", raising=False)
    c = _fresh()
    r = c.get("/auth/kakao/start", follow_redirects=False)
    loc = r.headers["location"]
    assert "scope=" not in loc
    assert "client_id=test-id" in loc


def test_start가_설정된_scope를_보낸다(monkeypatch):
    """검수를 통과해서 환경변수를 채우면 그때는 그대로 실린다."""
    monkeypatch.setenv("KAKAO_CLIENT_ID", "test-id")
    monkeypatch.setenv("KAKAO_SCOPE", "profile_nickname account_email")
    c = _fresh()
    r = c.get("/auth/kakao/start", follow_redirects=False)
    assert "scope=profile_nickname+account_email" in r.headers["location"]


def test_이메일이_없어도_계정이_만들어진다():
    """카카오가 이메일을 안 주는 게 정상 경로다. 회원번호만으로 식별한다."""
    from backend import auth
    p = auth.normalize_profile("kakao", {"id": 4242,
                                         "kakao_account": {"profile": {"nickname": "예현"}}})
    assert p == {"uid": "4242", "email": None, "name": "예현"}
    uid = auth.upsert_user("kakao", p["uid"], email=p["email"], name=p["name"])
    assert uid > 0
