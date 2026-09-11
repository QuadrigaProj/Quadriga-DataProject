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
    # 교차윗몸일으키기는 근력이 아니라 근지구력이다 (G6 에서 라벨 정정)
    assert {"유연성", "근지구력", "체성분"} <= set(b["항목별"])
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


def test_daily_일상처방은_경과일마다_순환한다():
    p = {"age_gbn": "성인", "purpose": "다이어트"}
    d0 = client.get("/daily", params={**p, "days_since_start": 0}).json()
    d1 = client.get("/daily", params={**p, "days_since_start": 1}).json()
    d30 = client.get("/daily", params={**p, "days_since_start": 30}).json()
    assert d0["일상처방"]["문구"] != d1["일상처방"]["문구"]     # 매일 바뀐다
    assert d0["일상처방"]["문구"] == d30["일상처방"]["문구"]    # 30일 주기로 되돌아온다
    assert d0["일상처방"]["총일수"] == 30


def test_daily_age_purpose_없으면_일상처방_생략():
    assert "일상처방" not in client.get("/daily").json()


def test_daily_어르신_수험생은_기초체력_문구로_대체():
    노인 = client.get("/daily", params={
        "age_gbn": "어르신", "purpose": "수험생 체력 증진", "days_since_start": 0}).json()
    기초 = client.get("/daily", params={
        "age_gbn": "어르신", "purpose": "기초 체력 증진", "days_since_start": 0}).json()
    assert 노인["일상처방"]["문구"] == 기초["일상처방"]["문구"]


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
    p = b["또래비교"]["근지구력"]
    assert 0 <= p["백분위"] <= 100
    assert p["표본수"] > 30
    assert "백분위" not in b["또래비교"]["체성분"]     # BMI 는 U자형이라 백분위를 내지 않는다


@needs_data
def test_안_잰_항목은_또래비교도_항목별에도_안_나온다():
    """유연성만 보내면 유연성만 나와야 한다 — placeholder 예시값이 실제 값처럼
    쓰여 근력·체성분까지 '분석'되는 일이 없어야 한다."""
    b = client.post("/fitness-age", json={
        "age_gbn": "성인", "sex": "M", "age": 45, "flexibility": 8}).json()
    assert set(b["또래비교"]) == {"유연성"}
    assert set(b["항목별"]) == {"유연성"}


@needs_data
def test_나이를_안_주면_또래비교_자체가_없다():
    """또래비교는 나이가 있어야 성립한다 — 측정값이 있어도 나이가 없으면 비워 둔다."""
    b = client.post("/fitness-age", json={
        "age_gbn": "성인", "sex": "M", "flexibility": 8, "strength": 25}).json()
    assert b["또래비교"] == {}


@needs_data
def test_빈_문자열이나_NaN은_422로_막혀_계산에_안_들어간다():
    """프런트가 빈 입력칸을 실수로 빈 문자열("")로 보내는 경우를 흉내 낸다.
    숫자 타입 필드에 문자열이 오면 Pydantic 이 요청 자체를 거절해야 하고,
    이게 조용히 0 이나 다른 값으로 둔갑해 계산에 들어가면 안 된다."""
    r = client.post("/fitness-age", json={
        "age_gbn": "성인", "sex": "M", "age": 45, "flexibility": ""})
    assert r.status_code == 422


def test_NaN값은_측정_안한_것으로_취급한다():
    """혹시라도 NaN 이 함수까지 들어오면(예: 다른 호출 경로) '안 잰 것'으로 본다 —
    None 과 똑같이 취급해서 보간 계산이 NaN 을 퍼뜨리지 않게 막는 마지막 방어선."""
    from backend import fitness_age as fa
    assert fa._given(None) is False
    assert fa._given(float("nan")) is False
    assert fa._given(0) is True          # 0 은 '안 잰 것'이 아니라 실제로 0을 잰 것이다
    assert fa._given(12.0) is True


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


def test_별명은_재로그인해도_유지된다():
    """rename_user() 로 정한 별명이 다음 로그인 때 provider 실명으로 덮이면 안 된다."""
    from backend import auth
    uid = auth.upsert_user("kakao", "9999", name="본명")
    auth.rename_user(uid, "내가정한별명")
    # 다른 기기에서 다시 로그인 — provider 는 여전히 본명을 준다
    again = auth.upsert_user("kakao", "9999", name="본명")
    assert again == uid
    with auth.db() as con:
        row = con.execute("SELECT display_name FROM users WHERE id=?", (uid,)).fetchone()
    assert row["display_name"] == "내가정한별명"


# ---------- 약관 · 로고 (소셜 로그인 콘솔이 공개 URL 을 요구한다) ----------

def test_개인정보처리방침이_열린다():
    c = _fresh()
    r = c.get("/privacy")
    assert r.status_code == 200
    assert "개인정보처리방침" in r.text


def test_이용약관이_열린다():
    c = _fresh()
    r = c.get("/terms")
    assert r.status_code == 200
    assert "이용약관" in r.text


def test_방침에_안_받는_항목이_명시돼_있다():
    """받지 않겠다고 약속한 항목은 방침에도 적혀 있어야 한다."""
    c = _fresh()
    t = c.get("/privacy").text
    for 항목 in ("휴대전화번호", "집 주소", "생년월일"):
        assert 항목 in t


def test_로고_파일이_서빙된다():
    """구글·카카오 콘솔에 올릴 아이콘과 파비콘."""
    c = _fresh()
    for path, ctype in (("/favicon.svg", "image/svg+xml"),
                        ("/img/logo-mark.svg", "image/svg+xml"),
                        ("/img/logo-120.png", "image/png"),
                        ("/img/logo-512.png", "image/png")):
        r = c.get(path)
        assert r.status_code == 200, path
        assert ctype in r.headers["content-type"], path


def test_계정_삭제로_기록까지_사라진다():
    c = _fresh()
    c.post("/auth/signup", json={"email": "gone@example.com", "password": "pw12345678"})
    c.post("/me/measurements", json={"age": 40, "체력나이": 38})
    assert c.get("/me/measurements").json()["기록"]
    assert c.delete("/auth/me").status_code == 200
    # 같은 이메일로 다시 가입하면 빈 상태여야 한다 (기록이 딸려오면 안 된다)
    c2 = _fresh()
    c2.post("/auth/signup", json={"email": "gone@example.com", "password": "pw12345678"})
    assert c2.get("/me/measurements").json()["기록"] == []


# ---------- 별명 바꾸기 (프로필 편집) ----------

def test_별명을_바꿀_수_있다():
    c = _fresh()
    c.post("/auth/signup", json={"email": "rn@example.com", "password": "pw12345678",
                                 "display_name": "예현"})
    assert c.get("/auth/me").json()["이름"] == "예현"
    r = c.patch("/auth/me", json={"이름": "윤서"})
    assert r.status_code == 200 and r.json()["이름"] == "윤서"
    # 다시 로그인해도 바뀐 이름이어야 한다 (서버에 남는다)
    c2 = _fresh()
    c2.post("/auth/login", json={"email": "rn@example.com", "password": "pw12345678"})
    assert c2.get("/auth/me").json()["이름"] == "윤서"


def test_빈_별명은_거부한다():
    c = _fresh()
    c.post("/auth/signup", json={"email": "rn2@example.com", "password": "pw12345678"})
    assert c.patch("/auth/me", json={"이름": "   "}).status_code == 400
    assert c.patch("/auth/me", json={"이름": "가" * 21}).status_code == 400


def test_로그인_없이는_별명을_못_바꾼다():
    c = _fresh()
    assert c.patch("/auth/me", json={"이름": "남"}).status_code == 401


def test_별명을_바꿔도_기록은_그대로다():
    c = _fresh()
    c.post("/auth/signup", json={"email": "rn3@example.com", "password": "pw12345678"})
    c.post("/me/measurements", json={"age": 41, "targetAge": 36, "체력나이": 36})
    c.patch("/auth/me", json={"이름": "새이름"})
    기록 = c.get("/me/measurements").json()
    assert 기록["이름"] == "새이름"
    assert 기록["기록"][0]["targetAge"] == 36


# ---------- G6 체력나이 항목 확대 ----------

@needs_data
def test_선택입력을_주면_근력과_심폐지구력이_늘어난다():
    """악력·왕복오래달리기를 잰 사람만 넣는다. 안 넣으면 지금까지와 같다."""
    기본 = client.post("/fitness-age", json=ADULT).json()
    더함 = client.post("/fitness-age",
                     json={**ADULT, "grip_kg": 42, "endurance": 60}).json()
    assert "근력" not in 기본["항목별"]
    assert "심폐지구력" not in 기본["항목별"]
    assert {"근력", "심폐지구력"} <= set(더함["항목별"])
    # 원래 항목의 값은 그대로 — 더하기만 한다
    for k in ("유연성", "근지구력", "체성분"):
        assert 더함["항목별"][k] == 기본["항목별"][k]


@needs_data
def test_악력은_몸무게로_나눠_상대악력으로_본다():
    """같은 악력이라도 몸무게가 무거우면 상대악력이 낮다."""
    가벼움 = client.post("/fitness-age", json={
        **ADULT, "weight_kg": 60, "grip_kg": 40}).json()["항목별"]["근력"]
    무거움 = client.post("/fitness-age", json={
        **ADULT, "weight_kg": 95, "grip_kg": 40}).json()["항목별"]["근력"]
    assert 가벼움 != 무거움


@needs_data
def test_성장기는_심폐지구력을_내지_않는다():
    """공개 분포에 성장기 심폐 항목이 없다. 없는 값을 지어내지 않는다."""
    b = client.post("/fitness-age", json={
        "age_gbn": "성장기", "sex": "F", "age": 15, "flexibility": 10,
        "strength": 150, "height_cm": 160, "weight_kg": 50,
        "grip_kg": 25, "endurance": 40}).json()
    assert "심폐지구력" not in b["항목별"]
    assert "근력" in b["항목별"]          # 상대악력은 성장기에도 분포가 있다


@needs_data
def test_선택입력만_보내도_계산된다():
    b = client.post("/fitness-age", json={
        "age_gbn": "성인", "sex": "M", "age": 30,
        "weight_kg": 74, "grip_kg": 42}).json()
    assert b["체력나이"] is not None
    assert set(b["항목별"]) == {"근력"}


def test_AI를_못_쓰면_까닭을_함께_준다(monkeypatch):
    """화면이 '지금 쓸 수 없어요' 만 띄우면 손쓸 방법이 없다."""
    from backend import ai_recommend as air

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert air.available() is False
    까닭 = air.why_unavailable()
    assert 까닭 and "ANTHROPIC_API_KEY" in 까닭

    r = client.get("/recommend/routines", params={"age_gbn": "성인", "limit": 2})
    assert r.status_code == 200
    assert r.json()["ai가능"] is False
    assert "ANTHROPIC_API_KEY" in r.json()["ai이유"]


def test_까닭에_키_값은_담지_않는다(monkeypatch):
    """있는지 없는지만 말한다. 값이 화면에 나가면 그게 곧 유출이다."""
    from backend import ai_recommend as air

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-비밀값123")
    까닭 = air.why_unavailable()
    assert 까닭 is None or "비밀값123" not in 까닭


# ---------- 고른 종목이 추천에 반영되는가 ----------

def _추천(sports, limit=5):
    from backend import recommend as rc
    return rc.for_user("성인", weak=[], sports=sports, limit=limit)


def _종목id(*이름들):
    from backend import sports as sp
    return [s["id"] for s in sp.catalog()["종목"] if s["이름"] in 이름들]


def test_고른_종목이_추천을_바꾼다():
    """예전에는 무엇을 골라도 목적마다 하나씩이라 결과가 거의 같았다."""
    없이 = [x["루틴명"] for x in _추천([])["추천"]]
    러닝 = [x["루틴명"] for x in _추천(_종목id("러닝", "마라톤"))["추천"]]
    요가 = [x["루틴명"] for x in _추천(_종목id("요가", "필라테스"))["추천"]]
    assert 없이 != 러닝
    assert 러닝 != 요가


def test_여러_종목이_같은_요인을_요구하면_더_무겁다():
    """러닝과 마라톤을 함께 골랐으면 심폐지구력이 두 배로 중요하다.
    예전에는 무게를 버리고 요인 이름만 써서 하나로 셌다."""
    한개 = _추천(_종목id("러닝"))
    두개 = _추천(_종목id("러닝", "마라톤"))
    assert 한개["참고"]["종목요인무게"]["심폐지구력"] == 1
    assert 두개["참고"]["종목요인무게"]["심폐지구력"] == 2
    # 무게가 크면 점수도 커진다
    assert 두개["추천"][0]["점수"] > 한개["추천"][0]["점수"]


def test_고른_종목_이름을_이유에_적는다():
    out = _추천(_종목id("수영", "등산"))
    assert out["참고"]["고른종목"] == ["수영", "등산"] or set(out["참고"]["고른종목"]) == {"수영", "등산"}
    이유들 = " ".join(x for r in out["추천"] for x in r["이유"])
    assert "수영" in 이유들 and "등산" in 이유들


def test_근거가_있으면_앞자리는_점수순이다():
    """목적마다 한 줄씩 세우느라 점수가 묻히던 것을 푼다."""
    out = _추천(_종목id("러닝", "마라톤"))
    점수 = [x["점수"] for x in out["추천"]]
    assert 점수[0] >= 점수[1]
    # 앞 두 자리는 같은 목적이 될 수 있다
    assert len({x["목적"] for x in out["추천"][:2]}) <= 2


def test_근거가_없으면_목적을_골고루_보여준다():
    """점수가 고만고만할 때 앞자리를 몰아 줄 이유가 없다."""
    out = _추천([])
    목적들 = [x["목적"] for x in out["추천"]]
    assert len(set(목적들)) == len(목적들)


def test_같은_목적이_셋씩_이어지지_않는다():
    for 종목 in ([], _종목id("러닝", "마라톤"), _종목id("수영", "등산"), _종목id("요가")):
        목적들 = [x["목적"] for x in _추천(종목)["추천"]]
        for m in set(목적들):
            assert 목적들.count(m) <= 2, (종목, 목적들)
