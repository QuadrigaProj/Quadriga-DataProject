"""
체력나이 API 서버

frontend/ 화면이 붙는 지점. 정적 파일도 이 서버가 함께 내보낸다.
backend/fitness_age.py, backend/prescription.py 를 HTTP 로 감쌌다.

실행:
    pip install -r requirements.txt
    uvicorn backend.main:app --reload
화면:
    http://localhost:8000
API 문서:
    http://localhost:8000/docs
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from typing import Literal

import httpx
from fastapi import Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:                                        # 저장소 루트에서 실행할 때
    from backend import auth, daily, fitness_age as fa, prescription as pr, paths
    from backend import routine_player as rp
except ImportError:                         # backend/ 안에서 직접 실행할 때
    import auth                             # noqa: E402
    import daily                            # noqa: E402
    import routine_player as rp             # noqa: E402
    import fitness_age as fa                # noqa: E402
    import paths                            # noqa: E402
    import prescription as pr               # noqa: E402

app = FastAPI(
    title="체력나이 API",
    description="국민체력100 공공데이터 기반 체력나이 산출·운동 처방",
    version="0.2.0",
)

# 개발 중에는 프론트 로컬 서버를 허용한다. 배포 시 도메인으로 좁힐 것.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

AgeGroup = Literal["성인", "어르신", "성장기"]
Sex = Literal["M", "F"]
Purpose = Literal[
    "다이어트", "기초 체력 증진", "특정 운동을 위한 체력 증진",
    "낙상 예방", "수험생 체력 증진", "유연성 강화",
]

# 한 번만 로드해 캐시한다 (요청마다 CSV 를 읽지 않는다)
_dist = None
_freq = None


def _load() -> None:
    """지연 로드. 데이터가 없어도 서버는 뜨고 /health 로 상태를 알린다."""
    global _dist, _freq
    if _dist is None:
        try:
            _dist = fa.load()
        except FileNotFoundError as e:
            print(f"[warn] 분포 미로드: {e}")
    if _freq is None:
        try:
            _freq = pr.load_freq()
        except FileNotFoundError as e:
            print(f"[warn] 처방 미로드: {e}")


@app.get("/health")
def health() -> dict:
    """프론트가 데이터 준비 여부를 확인하는 용도."""
    _load()
    return {
        "ok": True,
        "분포_로드됨": _dist is not None,
        "처방_로드됨": _freq is not None,
        "안내": None if _dist is not None else
               "python backend/collect_measurements.py --sample 450 후 "
               "python backend/build_distribution.py 를 실행하세요. "
               "(data/sample/ 이 있으면 자동으로 그쪽을 씁니다)",
    }


# ---------- 1. 체력나이 ----------

class MeasureIn(BaseModel):
    age_gbn: AgeGroup = Field(..., description="연령군 (성장기 = 만 11~18세)")
    sex: Sex
    age: float | None = Field(None, ge=5, le=110,
                              description="만 나이. 주면 또래 백분위를 함께 계산한다")
    flexibility: float | None = Field(None, description="앉아윗몸앞으로굽히기 (cm). 음수 가능")
    strength: float | None = Field(
        None,
        description="연령군별 항목: 성인=교차윗몸일으키기(회), "
                    "어르신=의자앉았다일어서기(회), 성장기=제자리멀리뛰기(cm)")
    height_cm: float | None = Field(None, gt=0)
    weight_kg: float | None = Field(None, gt=0)
    bmi: float | None = Field(None, gt=0, description="직접 주거나 키·몸무게로 계산")


class MeasureOut(BaseModel):
    체력나이: float | None
    신뢰구간: float | None
    항목별: dict[str, float]
    약점: dict | None
    또래비교: dict = {}
    해석: str = ""


@app.post("/fitness-age", response_model=MeasureOut)
def post_fitness_age(body: MeasureIn) -> MeasureOut:
    """측정값 → 체력나이 + 가장 효율적인 약점.

    자가 측정 오차를 고려해 신뢰구간을 함께 반환한다.
    화면에는 "27세 (±2세)" 형태로 표시할 것.
    """
    _load()
    if _dist is None:
        raise HTTPException(503, "분포 데이터가 없습니다. /health 참고")

    bmi = body.bmi
    if bmi is None and body.height_cm and body.weight_kg:
        bmi = body.weight_kg / (body.height_cm / 100) ** 2

    if body.flexibility is None and body.strength is None and bmi is None:
        raise HTTPException(400, "측정값을 최소 하나는 보내주세요.")

    result = fa.fitness_age(
        _dist, body.age_gbn, body.sex,
        flexibility=body.flexibility, strength=body.strength, bmi=bmi,
    )
    if result["체력나이"] is None:
        raise HTTPException(422, "해당 연령군·성별의 분포가 부족해 산출할 수 없습니다.")

    peers = {}
    if body.age is not None:
        peers = fa.peer_report(_dist, body.age_gbn, body.sex, body.age,
                               flexibility=body.flexibility, strength=body.strength,
                               bmi=bmi)

    약점 = fa.weakest_link(result)

    # 성장기는 나이가 들수록 기록이 좋아지므로 "체력나이가 높다 = 나쁘다" 가 아니다.
    # 연령 폭도 11~18세로 좁아 개선효과(세) 차이가 거의 안 난다.
    # 그래서 약점을 "또래 백분위가 가장 낮은 항목" 으로 바꿔서 고른다.
    if body.age_gbn == fa.GROWTH and peers and any("백분위" in v for v in peers.values()):
        후보 = {k: v for k, v in peers.items() if "백분위" in v}
        낮은순 = sorted(후보.items(), key=lambda kv: kv[1]["백분위"])
        약점 = {
            "약점": 낮은순[0][0],
            "백분위": 낮은순[0][1]["백분위"],
            "기준": "또래 백분위",
            "전체": {k: v["백분위"] for k, v in 후보.items()},
        }

    해석 = ("발달 수준입니다. 숫자가 실제 나이보다 높을수록 또래보다 앞서 있다는 뜻이에요."
            if body.age_gbn == fa.GROWTH else
            "체력나이입니다. 숫자가 실제 나이보다 낮을수록 좋아요.")

    return MeasureOut(**result, 약점=약점, 또래비교=peers, 해석=해석)


# ---------- 2. 루틴 ----------

class RoutineStep(BaseModel):
    단계: str
    운동명: str
    체력요인: str


@app.get("/routine", response_model=list[RoutineStep])
def get_routine(
    age_gbn: AgeGroup,
    sex: Sex,
    purpose: Purpose | None = None,
    weak_factor: str | None = None,
    home_only: bool = True,
) -> list[RoutineStep]:
    """준비운동 2 → 본운동 3 → 정리운동 2 순서의 루틴 한 벌.

    weak_factor 는 /fitness-age 응답의 약점.약점 을 그대로 넘기면 된다.
    """
    _load()
    if _freq is None:
        raise HTTPException(503, "처방 데이터가 없습니다. /health 참고")

    rec = pr.recommend(
        _freq, age_gbn=age_gbn, sex=sex,
        purpose=purpose, weak_factor=weak_factor, home_only=home_only,
    )
    steps = pr.build_routine(rec)
    if not steps:
        raise HTTPException(404, "조건에 맞는 처방 기록이 없습니다.")
    return [RoutineStep(**s) for s in steps]


# ---------- 3. 목적 목록 ----------

@app.get("/purposes")
def get_purposes() -> list[dict]:
    """목적 선택 화면(화면 2)이 쓰는 목록."""
    return [
        {"목적": k, "우선요인": v}
        for k, v in pr.PURPOSE_FACTORS.items()
    ]


# ---------- 4. 재점검 ----------

class RecheckIn(BaseModel):
    이전: MeasureIn
    현재: MeasureIn


@app.post("/recheck")
def post_recheck(body: RecheckIn) -> dict:
    """3개월 재점검 — 두 실측값의 차이만 계산한다. 예측이 아니다.

    자가 측정은 오차가 크다. 그렇다고 변화 폭을 인위적으로 깎으면
    "지금 45세인데 근력을 고치면 53세" 같은 모순이 생긴다.
    (실제로 그런 결함이 있었다: 걷어낸 website/server.js 의 ±5세 캡.
     캡은 체력나이에만 걸리고 약점 계산은 캡 전 값으로 해서 개선효과가 음수로 나왔다.)

    그래서 값은 그대로 두고, 변화가 측정 편차 안인지 밖인지를 함께 알려준다.
    """
    before = post_fitness_age(body.이전)
    after = post_fitness_age(body.현재)
    delta = round((after.체력나이 or 0) - (before.체력나이 or 0), 1)

    # 두 측정의 편차를 합쳐 "이 정도 차이는 오차일 수 있다" 는 문턱을 만든다
    노이즈 = round(((before.신뢰구간 or 0) ** 2 + (after.신뢰구간 or 0) ** 2) ** 0.5, 1)
    유의미 = abs(delta) > 노이즈

    성장 = body.현재.age_gbn == fa.GROWTH
    좋아짐 = delta > 0 if 성장 else delta < 0      # 성장기는 숫자가 오르는 게 좋다

    if delta == 0:
        메시지 = "변화 없음"
    elif not 유의미:
        메시지 = (f"{abs(delta)}세 움직였지만 측정 편차(±{노이즈}세) 안이라 "
                "아직 변화라고 보긴 일러요")
    elif 성장:
        메시지 = f"발달 수준이 {abs(delta)}세 {'앞당겨졌습니다' if 좋아짐 else '뒤처졌습니다'}"
    else:
        메시지 = f"체력나이가 {abs(delta)}세 {'어려졌습니다' if 좋아짐 else '늘었습니다'}"

    return {
        "이전": before.체력나이,
        "현재": after.체력나이,
        "변화": delta,
        "측정편차": 노이즈,
        "유의미한변화": 유의미,
        "메시지": 메시지,
        "항목별_이전": before.항목별,
        "항목별_현재": after.항목별,
    }


# ---------- 5. 일상 처방 ----------

@app.get("/daily")
def get_daily(
    strength_stars: int = Query(3, ge=1, le=5, description="근력 별점 1~5"),
    walk_minutes: float | None = Query(None, ge=0, description="목적지까지 도보 분"),
    days_since_start: int = Query(0, ge=0, description="시작 후 경과일"),
) -> dict:
    """운동 시간을 따로 내지 않아도 되는 일상 제안 (화면 3).

    교통 데이터는 쓰지 않는다. 사용자가 알려준 값만으로 판단한다.
    """
    return {
        "계단": daily.stairs(strength_stars),
        "도보": daily.walk(walk_minutes),
        "강도": daily.intensity(days_since_start),
    }


# ---------- 6. 동영상 ----------

@app.get("/videos")
def get_videos(
    factor: str | None = None,
    se: str | None = Query(None, description="준비운동 / 본운동 / 정리운동"),
    place: str | None = None,
    level: str | None = None,
    max_sec: int | None = None,
    exclude_parts: str | None = Query(None, description="쉼표로 구분. 예: 무릎,허리"),
) -> dict:
    """루틴 플레이어(화면 4)가 쓰는 동영상 목록.

    지금은 data/sample/videos.json 기반이다. 실제 동영상 API 응답을 같은
    필드명으로 채워 넣으면 화면은 그대로 둔 채 데이터만 교체된다.
    """
    parts = [p.strip() for p in (exclude_parts or "").split(",") if p.strip()]
    items = daily.videos(factor=factor, se=se, place=place, level=level,
                         max_sec=max_sec, exclude_parts=parts)
    return {"출처": "sample", "개수": len(items), "items": items}


# ---------- 7. 영상 루틴 (준비 → 본 → 정리) ----------

@app.get("/video-routine")
def get_video_routine(
    factor: str | None = Query(None, description="체력요인. 예: 근력·근지구력"),
    place: str | None = None,
    exclude_parts: str | None = Query(None, description="쉼표로 구분. 예: 무릎,허리"),
    main_count: int = Query(2, ge=1, le=5, description="본운동 개수"),
) -> dict:
    """backend/routine_player.py 로 만든 영상 루틴.

    /routine 은 공단의 실제 처방 기록(pres_note)에서 뽑은 **운동명** 목록이고,
    이쪽은 동영상 API 레코드에서 고른 **영상** 목록이다. 둘은 용도가 다르다.
    지금은 샘플을 API 스키마로 변환해 넘긴다. 서비스키가 나오면
    backend/nfa_video_api.py 가 받아온 레코드를 그대로 넣으면 된다.
    """
    parts = frozenset(p.strip() for p in (exclude_parts or "").split(",") if p.strip())
    # 부위 제외·장소는 전 단계 공통, 체력요인은 본운동에만 건다.
    # 공통으로 걸면 준비운동(유연성)까지 걸러져 루틴이 미완성이 된다.
    공통 = rp.VideoFilter(excluded_parts=parts,
                         places=frozenset([place]) if place else None)
    본운동 = rp.VideoFilter(factors=frozenset([factor])) if factor else rp.VideoFilter()
    result = rp.build_video_routine(
        daily.sample_records(),
        criteria=공통,
        phase_filters={"본운동": 본운동},
        counts={"준비운동": 1, "본운동": main_count, "정리운동": 1},
    )
    return {
        "출처": "sample",
        "상태": result.status,
        "부족한단계": result.missing,
        "총시간초": result.total_seconds,
        "steps": [
            {"순서": s["order"], "단계": s["phase"],
             "영상명": s["video"].get("vdo_ttl_nm"),
             "체력요인": s["video"].get("ftns_fctr_nm"),
             "초": s.get("duration_seconds"),
             "재생주소": s.get("file_url")}
            for s in result.steps
        ],
    }


# ---------- 8. 인증센터 ----------

@app.get("/centers")
def get_centers(lat: float | None = None, lon: float | None = None,
                limit: int = Query(5, ge=1, le=50)) -> dict:
    """가까운 체력인증센터. 좌표를 주면 거리순으로 정렬한다."""
    return {"출처": "sample", "items": daily.centers(lat, lon, limit)}


# ===========================================================================
# 계정
#
# 저장하는 건 로그인 수단·닉네임·체력 측정값뿐이다.
# 휴대폰 번호나 주소는 입력받지도, 소셜 응답에서 받아 두지도 않는다.
# (backend/auth.py 의 KEEP_FIELDS 에서 걸러진다)
# ===========================================================================

class SignupIn(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=200)
    display_name: str | None = Field(None, max_length=40)


class LoginIn(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=200)


def _set_session(response: Response, user_id: int) -> None:
    response.set_cookie(
        auth.SESSION_COOKIE, auth.create_session(user_id),
        max_age=auth.SESSION_DAYS * 86400,
        httponly=True,          # 자바스크립트가 못 읽는다
        samesite="lax",         # 다른 사이트에서 실려 나가지 않는다
        secure=bool(os.getenv("HTTPS")),
    )


def _require_user(token: str | None) -> dict:
    user = auth.user_for_token(token)
    if not user:
        raise HTTPException(401, "로그인이 필요합니다.")
    return user


@app.get("/auth/providers")
def auth_providers() -> dict:
    """화면이 어떤 소셜 버튼을 살릴지 결정하는 데 쓴다."""
    return {"소셜": auth.enabled_providers(), "비밀번호": True}


@app.post("/auth/signup")
def auth_signup(body: SignupIn, response: Response) -> dict:
    auth.init_db()
    email = body.email.strip().lower()
    if "@" not in email or len(email) < 5:
        raise HTTPException(400, "이메일 형식을 확인해주세요.")
    problem = auth.password_problem(body.password)
    if problem:
        raise HTTPException(400, problem)
    if auth.find_password_user(email):
        raise HTTPException(409, "이미 가입된 이메일입니다.")

    salt, pw_hash = auth.hash_password(body.password)
    uid = auth.upsert_user("password", email, email=email,
                           name=body.display_name or email.split("@")[0],
                           salt=salt, pw_hash=pw_hash)
    _set_session(response, uid)
    return {"ok": True, "이름": body.display_name or email.split("@")[0]}


@app.post("/auth/login")
def auth_login(body: LoginIn, response: Response) -> dict:
    auth.init_db()
    row = auth.find_password_user(body.email)
    # 이메일이 없을 때와 비밀번호가 틀렸을 때의 응답을 같게 둔다.
    # 다르게 두면 어떤 이메일이 가입돼 있는지 알아낼 수 있다.
    if not row or not auth.verify_password(body.password, row["password_salt"],
                                           row["password_hash"]):
        raise HTTPException(401, "이메일 또는 비밀번호가 맞지 않습니다.")
    _set_session(response, row["id"])
    return {"ok": True, "이름": row["display_name"]}


@app.post("/auth/logout")
def auth_logout(response: Response,
                quadriga_session: str | None = Cookie(None)) -> dict:
    auth.drop_session(quadriga_session)
    response.delete_cookie(auth.SESSION_COOKIE)
    return {"ok": True}


@app.get("/auth/me")
def auth_me(quadriga_session: str | None = Cookie(None)) -> dict:
    auth.init_db()
    user = auth.user_for_token(quadriga_session)
    return {"로그인": bool(user), "이름": user["display_name"] if user else None,
            "수단": user["provider"] if user else None}


@app.delete("/auth/me")
def auth_delete_me(response: Response,
                   quadriga_session: str | None = Cookie(None)) -> dict:
    """계정과 측정 기록을 모두 지운다. 되돌릴 수 없다."""
    user = _require_user(quadriga_session)
    auth.delete_account(user["id"])
    response.delete_cookie(auth.SESSION_COOKIE)
    return {"ok": True}


# ---------- 소셜 로그인 ----------

@app.get("/auth/{provider}/start")
def auth_start(provider: str, request: Request) -> RedirectResponse:
    if provider not in auth.PROVIDERS:
        raise HTTPException(404, "지원하지 않는 로그인 수단입니다.")
    client_id, _ = auth.client_config(provider)
    if not client_id:
        raise HTTPException(503,
            f"{provider} 로그인이 아직 설정되지 않았습니다. "
            f".env 에 {provider.upper()}_CLIENT_ID 와 _CLIENT_SECRET 를 넣어주세요.")
    auth.init_db()
    conf = auth.PROVIDERS[provider]
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": str(request.url_for("auth_callback", provider=provider)),
        "state": auth.new_state(provider),
    }
    if conf["scope"]:
        params["scope"] = conf["scope"]
    return RedirectResponse(conf["authorize"] + "?" + urlencode(params))


@app.get("/auth/{provider}/callback", name="auth_callback")
async def auth_callback(provider: str, request: Request,
                        code: str | None = None, state: str | None = None
                        ) -> RedirectResponse:
    if provider not in auth.PROVIDERS:
        raise HTTPException(404, "지원하지 않는 로그인 수단입니다.")
    if not code or not state or auth.take_state(state) != provider:
        # state 가 안 맞으면 남이 만든 요청이다. 진행하지 않는다.
        return RedirectResponse("/?login=failed")

    client_id, client_secret = auth.client_config(provider)
    conf = auth.PROVIDERS[provider]
    async with httpx.AsyncClient(timeout=10) as http:
        tok = await http.post(conf["token"], data={
            "grant_type": "authorization_code", "code": code,
            "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": str(request.url_for("auth_callback", provider=provider)),
            "state": state,
        }, headers={"Accept": "application/json"})
        access = (tok.json() or {}).get("access_token")
        if not access:
            return RedirectResponse("/?login=failed")
        me = await http.get(conf["profile"],
                            headers={"Authorization": f"Bearer {access}"})
        profile = auth.normalize_profile(provider, me.json() or {})

    if not profile.get("uid"):
        return RedirectResponse("/?login=failed")

    uid = auth.upsert_user(provider, profile["uid"],
                           email=profile.get("email"), name=profile.get("name"))
    res = RedirectResponse("/?login=ok")
    _set_session(res, uid)
    return res


# ---------- 측정 기록 (기기 간 이어보기) ----------

@app.get("/me/measurements")
def get_my_measurements(quadriga_session: str | None = Cookie(None)) -> dict:
    user = _require_user(quadriga_session)
    return {"이름": user["display_name"], "기록": auth.list_measurements(user["id"])}


@app.post("/me/measurements")
def post_my_measurement(payload: dict,
                        quadriga_session: str | None = Cookie(None)) -> dict:
    """측정값과 산출 결과를 저장한다. 다른 기기에서 로그인하면 그대로 이어진다."""
    user = _require_user(quadriga_session)
    auth.save_measurement(user["id"], payload)
    return {"ok": True}


# ---------- 정적 프론트엔드 ----------
# 모든 API 라우트를 정의한 뒤 마운트해야 "/" 가 API 를 가리지 않는다.

if paths.FRONTEND.exists():
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(paths.FRONTEND / "index.html")

    app.mount("/", StaticFiles(directory=paths.FRONTEND), name="frontend")
