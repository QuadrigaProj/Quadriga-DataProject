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
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode
from typing import Literal

import httpx
from fastapi import Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:                                        # 저장소 루트에서 실행할 때
    from backend import auth, daily, fitness_age as fa, prescription as pr, paths
    from backend import routine_player as rp
    from backend import routines as rt, bodycomp as bc, hometest as ht, geo
    from backend import sports as sp
    from backend import route
except ImportError:                         # backend/ 안에서 직접 실행할 때
    import auth                             # noqa: E402
    import daily                            # noqa: E402
    import routine_player as rp             # noqa: E402
    import routines as rt                   # noqa: E402
    import bodycomp as bc                   # noqa: E402
    import hometest as ht                   # noqa: E402
    import geo                              # noqa: E402
    import sports as sp                     # noqa: E402
    import fitness_age as fa                # noqa: E402
    import paths                            # noqa: E402
    import prescription as pr               # noqa: E402
    import route                            # noqa: E402

@asynccontextmanager
async def lifespan(_: FastAPI):
    """배포 직후 첫 요청에서 테이블이 없어 500 이 나지 않도록 미리 만든다."""
    try:
        auth.init_db()
    except Exception as e:                       # DB 가 아직 안 붙어도 서버는 뜬다
        print(f"[warn] DB 초기화 실패: {type(e).__name__}")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="체력나이 API",
    description="국민체력100 공공데이터 기반 체력나이 산출·운동 처방",
    version="0.2.0",
)

# 개발 중에는 프론트 로컬 서버를 허용한다. 배포 시 도메인으로 좁힐 것.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ["http://localhost:3000", "http://localhost:5173",
                               os.getenv("PUBLIC_BASE_URL", "").rstrip("/")] if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROVIDER_CONSOLE = {
    "google": "https://console.cloud.google.com/apis/credentials",
    "naver": "https://developers.naver.com/apps/#/register",
    "kakao": "https://developers.kakao.com/console/app",
}

AgeGroup = Literal["성인", "어르신", "성장기"]
Sex = Literal["M", "F"]
Purpose = Literal[
    "다이어트", "기초 체력 증진",
    "재활 및 기능 회복", "수험생 체력 증진", "유연성 강화",
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
    집중개선영역: list[str] = []
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
        age=body.age,
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


# ---------- 7b. 3개월 프로그램 루틴 (250 고정 루틴) ----------

ProgramAge = Literal["유아기", "유소년", "청소년", "성인", "어르신"]
ProgramPurpose = Literal[
    "다이어트", "기초 체력 증진", "재활 및 기능 회복", "수험생 체력 증진", "유연성 강화",
]


@app.get("/program/routine")
def get_program_routine(
    age_gbn: ProgramAge,
    purpose: ProgramPurpose,
    day: int = Query(0, ge=0, description="0-based 경과일. Day1 = 0. 10일마다 순환"),
    week: int = Query(1, ge=1, le=13, description="프로그램 주차 (강도 구간용)"),
    exclude_parts: str | None = Query(None, description="쉼표 구분. 예: 무릎,허리"),
    heavy: bool = Query(False, description="몸이 무거운 날"),
    fitness_age: float | None = Query(None, description="추정 체력나이 — 시작 강도 보정용"),
    real_age: float | None = Query(None, description="실제 만 나이"),
    sports: str | None = Query(None, description="쉼표 구분 종목 id. 예: running,tennis"),
) -> dict:
    """연령대 × 목적 의 고정 루틴 10개 중 오늘 것 한 벌.

    루틴을 새로 만들지 않는다. data/sample/routines_250.json 을 그대로 순환시킨다.
    수행량은 12주 3구간 규칙 + 현재 체력 보정(offset)으로 붙인다.
    안전·제외 부위 조건은 후보가 없어도 완화하지 않는다.
    """
    parts = [p.strip() for p in (exclude_parts or "").split(",") if p.strip()]

    # 고른 운동 종목 → 그 종목이 많이 쓰는 체력요인 상위 2개만 본다.
    # 너무 많이 넣으면 원래 커리큘럼이 흐려진다.
    # 안 고른 사람에게는 종목 데이터를 아예 읽지 않는다. 종목은 곁가지라
    # sports.json 이 없다고 해서 루틴 자체가 안 나오면 안 된다.
    picked = [i.strip() for i in (sports or "").split(",") if i.strip()]

    try:
        prefer = list(sp.factor_weights(picked))[:2] if picked else []
        routine = rt.build_program_routine(
            age_gbn, purpose, day=day, exclude_parts=parts, heavy=heavy,
            prefer_factors=prefer)
    except (KeyError, FileNotFoundError) as e:
        raise HTTPException(404, str(e))

    offset = rt.start_offset(fitness_age, real_age)
    intensity = rt.intensity_for(age_gbn, week, offset=offset, heavy=heavy)
    routine["강도"] = intensity
    if picked:
        routine["고른종목"] = [s["이름"] for s in sp.resolve(picked)]
        routine["참고요인"] = prefer
        routine["조심할부위"] = sp.care_parts(picked)
    routine["시작보정"] = {"offset": offset,
                        "설명": {-1: "현재 체력을 반영해 한 단계 낮게 시작",
                               0: "기본 수행량", 1: "여유가 있어 한 단계 높게"}[offset]}
    return routine


@app.get("/sports")
def get_sports() -> dict:
    """배우고 싶은 운동 종목 목록. 화면이 그대로 그린다."""
    try:
        return sp.catalog()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/sports/summary")
def get_sports_summary(ids: str = Query("", description="쉼표로 구분한 종목 id")) -> dict:
    """선택한 종목이 어떤 체력요인을 요구하는지, 어디를 조심해야 하는지."""
    picked = [i.strip() for i in ids.split(",") if i.strip()]
    try:
        return {"선택": sp.resolve(picked),
                "체력요인": sp.factor_weights(picked),
                "조심할부위": sp.care_parts(picked)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/program/purposes")
def get_program_purposes(age_gbn: ProgramAge | None = None) -> list[dict]:
    """목적 5종 + (연령대를 주면) 그 연령대 재프레이밍 라벨."""
    d = rt.load()["config"]
    out = []
    for p in rt.PURPOSES:
        item = {"목적": p, "우선요인": d["purpose_factors"].get(p, [])}
        if age_gbn:
            item["표시명"] = d["reframe"].get(age_gbn, {}).get(p, p)
        out.append(item)
    return out


# ---------- 7c. InBody · 홈 체력측정 ----------

class InBodyIn(BaseModel):
    sex: Sex
    age: float = Field(..., ge=4, le=110)
    height_cm: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)
    skeletal_muscle_kg: float | None = Field(None, gt=0, description="골격근량")
    body_fat_pct: float | None = Field(None, ge=0, le=70, description="체지방률 %")
    waist_cm: float | None = Field(None, gt=0, description="허리둘레")
    body_water_pct: float | None = Field(None, ge=0, le=90, description="체수분 % (선택)")


@app.post("/bodycomp")
def post_bodycomp(body: InBodyIn) -> dict:
    """InBody 결과 → 체성분 분석 + (근거가 있으면) 추정 체력나이."""
    _load()
    return bc.analyze(
        sex=body.sex, age=body.age, height_cm=body.height_cm, weight_kg=body.weight_kg,
        skeletal_muscle_kg=body.skeletal_muscle_kg, body_fat_pct=body.body_fat_pct,
        waist_cm=body.waist_cm, body_water_pct=body.body_water_pct, dist=_dist,
    )


class HomeTestIn(BaseModel):
    sex: Sex
    age: float = Field(..., ge=4, le=110)
    height_cm: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)
    waist_cm: float | None = Field(None, gt=0)
    jump_30s: float | None = Field(None, ge=0, description="30초 제자리 점프 (회)")
    curlup_30s: float | None = Field(None, ge=0, description="30초 컬업 (회)")
    knee_pushup_30s: float | None = Field(None, ge=0, description="30초 무릎 푸시업 (회)")
    high_knee_2min: float | None = Field(None, ge=0, description="2분 하이니 (회)")


@app.post("/hometest")
def post_hometest(body: HomeTestIn) -> dict:
    """홈 체력측정(약 4분) → 추정 체력나이 + 항목별 홈 등급 + 가장 부족한 요인."""
    _load()
    if _dist is None:
        raise HTTPException(503, "분포 데이터가 없습니다. /health 참고")
    return ht.evaluate(
        _dist, sex=body.sex, age=body.age, height_cm=body.height_cm,
        weight_kg=body.weight_kg, jump_30s=body.jump_30s, curlup_30s=body.curlup_30s,
        knee_pushup_30s=body.knee_pushup_30s, high_knee_2min=body.high_knee_2min,
        waist_cm=body.waist_cm,
    )


# ---------- 8. 인증센터 ----------

BOOKING_URL = "https://nfa.kspo.or.kr/reserve/main.kspo"    # 국민체력100 공식 예약


@app.get("/centers")
def get_centers(lat: float | None = None, lon: float | None = None,
                region: str | None = Query(None, description="구 단위 지역명 (예: 성북구)"),
                limit: int = Query(3, ge=1, le=50)) -> dict:
    """체력인증센터 검색 — 구 단위 주소 일치 우선.

    1. region 이 센터 주소(addr)에 들어 있으면 그 센터만 먼저 거른다 → 매칭방식 "주소". "성북구" 처럼
       "…구" 로 끝나는 구 이름은 주소의 낱말과 통째로 맞아야 하고(동구 ≠ 남동구), 그 밖("서울")은
       부분 문자열이다(daily.centers_by_addr). 정렬은 기존과 같이 직선거리순이고, 좌표를 못 구하면
       파일 순서 그대로 둔다.
    2. 일치하는 센터가 없으면 기존 geocode 경로로 폴백해 가까운 순으로 돌려준다 → 매칭방식 "거리".
    좌표(lat/lon)만 주면 종전과 같이 직선거리순이다.
    길찾기 API 가 없어 **도보 시간은 계산하지 않으며**, 예약은 공식 예약 페이지로 연결한다.
    """
    resolved = None
    matched = daily.centers_by_addr(region) if region else []
    by_addr = bool(matched)
    if lat is None and lon is None and region:
        c = geo.geocode(region)
        if c:
            lat, lon, resolved = c[0], c[1], region
    items = daily.centers(lat, lon, limit, items=matched if by_addr else None)
    for it in items:
        it["예약"] = BOOKING_URL
    if by_addr:
        note = "입력한 구 주소와 일치하는 센터예요. 예약은 국민체력100 공식 페이지에서 진행합니다."
    elif region and lat is not None:
        note = ("주소가 일치하는 센터가 없어 가까운 순으로 보여드려요. 직선거리 기준이에요. "
                "도보 시간은 지도 앱에서 확인하세요. 예약은 국민체력100 공식 페이지에서 진행합니다.")
    else:
        note = "직선거리 기준이에요. 도보 시간은 지도 앱에서 확인하세요. 예약은 국민체력100 공식 페이지에서 진행합니다."
    return {
        "출처": "sample",
        "매칭방식": "주소" if by_addr else "거리",
        "기준좌표": {"위도": lat, "경도": lon, "입력": resolved} if lat is not None else None,
        "지역인식실패": bool(region) and lat is None and not by_addr,
        "안내": note,
        "items": items,
    }


# ---------- 9. 경로 분석 (출발지→목적지) ----------

@app.get("/route/advice")
async def get_route_advice(
    from_: str = Query(..., alias="from", min_length=1, max_length=80,
                       description="출발지 (구 이름·역 이름·장소명)"),
    to: str = Query(..., min_length=1, max_length=80, description="목적지"),
    strength_stars: int = Query(3, ge=1, le=5, description="근력 별점 1~5"),
) -> dict:
    """출발지→목적지 가는 길의 특성(거리·시간·오르막·계단)을 읽어 걷기/계단을 추천한다 (화면 3).

    카카오 REST 키(KAKAO_CLIENT_ID)가 없거나 호출이 실패하면 geo.geocode + 직선거리 추정으로
    폴백한다(출처: "추정"). 지역을 못 찾으면 404, 출발·목적지가 같으면 400.
    """
    # route 의 전용 예외만 상태코드로 바꾼다. 부모 클래스(LookupError·ValueError)를 잡으면 파싱 중 난
    # KeyError·IndexError·float() 실패까지 404/400 으로 둔갑해 내부 오류 문자열이 화면에 그대로 보인다.
    try:
        return await route.advise(from_, to, strength_stars)
    except route.PlaceNotFoundError as e:
        raise HTTPException(404, str(e))
    except route.SamePointError as e:
        raise HTTPException(400, str(e))


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


PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")


def public_url(request: Request, path: str) -> str:
    """배포된 주소 기준의 절대 URL.

    Render 같은 곳은 앞에 프록시가 있어서 request.url 의 scheme 이 http 로 보인다.
    그대로 쓰면 OAuth 리디렉션 URI 가 콘솔 등록값과 어긋난다.
    PUBLIC_BASE_URL 이 있으면 그걸 쓰고, 없으면 X-Forwarded-Proto 를 본다.
    """
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL + path
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{proto}://{request.headers.get('host', request.url.netloc)}{path}"


def is_https(request: Request) -> bool:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.startswith("https://")
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _set_session(response: Response, user_id: int, request: Request) -> None:
    response.set_cookie(
        auth.SESSION_COOKIE, auth.create_session(user_id),
        max_age=auth.SESSION_DAYS * 86400,
        httponly=True,          # 자바스크립트가 못 읽는다
        samesite="lax",         # 다른 사이트에서 실려 나가지 않는다
        secure=is_https(request),   # https 로 들어왔으면 https 로만 오간다
    )


def _require_user(token: str | None) -> dict:
    user = auth.user_for_token(token)
    if not user:
        raise HTTPException(401, "로그인이 필요합니다.")
    return user


@app.get("/auth/setup", response_class=HTMLResponse, include_in_schema=False)
def auth_setup(request: Request) -> str:
    """소셜 로그인 설정 도우미.

    각 콘솔에 등록할 리디렉션 URI 를 지금 서버 주소 기준으로 그대로 보여준다.
    콘솔에 넣는 값과 서버가 보내는 값이 한 글자라도 다르면 redirect_uri_mismatch 가 난다.
    """
    rows = []
    for name in PROVIDER_CONSOLE:
        uri = public_url(request, f"/auth/{name}/callback")
        cid, sec = auth.client_config(name)
        if cid and (sec or name in auth.SECRET_OPTIONAL):
            state = "✅ 설정됨" + ("" if sec else " (Client Secret 없이)")
        else:
            state = "⚠️ 키 없음"
        rows.append(f"""<tr><td><b>{name}</b></td><td>{state}</td>
            <td><code>{uri}</code></td>
            <td><a href="{PROVIDER_CONSOLE[name]}" target="_blank" rel="noreferrer">콘솔 열기</a></td></tr>""")
    return f"""<!doctype html><meta charset="utf-8"><title>소셜 로그인 설정</title>
<style>
 body{{font-family:-apple-system,'Malgun Gothic',sans-serif;max-width:760px;margin:40px auto;
       padding:0 20px;line-height:1.6;color:#20261F}}
 table{{border-collapse:collapse;width:100%;margin:18px 0}}
 td,th{{border-bottom:1px solid #DCDCC9;padding:10px 8px;text-align:left;font-size:14px}}
 code{{background:#EDEFE6;padding:3px 6px;border-radius:5px;font-size:13px}}
 .note{{background:#F3E2CC;padding:14px 16px;border-radius:10px;font-size:14px}}
</style>
<h1>소셜 로그인 설정</h1>
<p>아래 <b>리디렉션 URI</b> 를 각 콘솔에 <b>그대로 복사</b>해서 등록하세요.
한 글자라도 다르면 <code>redirect_uri_mismatch</code> 가 납니다.</p>
<table><tr><th>제공자</th><th>상태</th><th>리디렉션 URI</th><th>콘솔</th></tr>
{''.join(rows)}</table>
<div class="note">
 <b>이 주소들은 브라우저로 직접 열어보는 페이지가 아닙니다.</b>
 로그인이 끝난 뒤 제공자가 우리 서버를 부를 때 쓰는 통로예요.
 직접 열면 "정상적인 로그인 요청이 아니다" 라는 안내만 나옵니다. 그게 맞는 동작입니다.
 <br><br>
 키를 넣은 뒤에는 서버를 다시 시작해야 반영됩니다.
 권한(scope)은 <b>이메일·닉네임만</b> 신청하세요.
 <b>카카오</b>는 scope 를 보내지 않고, 콘솔의 [카카오 로그인] &gt; [동의항목] 설정을 그대로 따릅니다.
</div>
<p><a href="/">← 서비스로 돌아가기</a></p>"""


@app.get("/auth/providers")
def auth_providers() -> dict:
    """화면이 어떤 소셜 버튼을 살릴지 결정하는 데 쓴다."""
    return {"소셜": auth.enabled_providers(), "비밀번호": True}


@app.post("/auth/signup")
def auth_signup(body: SignupIn, response: Response, request: Request) -> dict:
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
    _set_session(response, uid, request)
    return {"ok": True, "이름": body.display_name or email.split("@")[0]}


@app.post("/auth/login")
def auth_login(body: LoginIn, response: Response, request: Request) -> dict:
    auth.init_db()
    row = auth.find_password_user(body.email)
    # 이메일이 없을 때와 비밀번호가 틀렸을 때의 응답을 같게 둔다.
    # 다르게 두면 어떤 이메일이 가입돼 있는지 알아낼 수 있다.
    if not row or not auth.verify_password(body.password, row["password_salt"],
                                           row["password_hash"]):
        raise HTTPException(401, "이메일 또는 비밀번호가 맞지 않습니다.")
    _set_session(response, row["id"], request)
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


class RenameIn(BaseModel):
    이름: str


@app.patch("/auth/me")
def auth_rename(body: RenameIn, quadriga_session: str | None = Cookie(None)) -> dict:
    """별명만 바꾼다. 다른 기기에서도 같은 별명으로 보이게 서버에 저장한다."""
    user = _require_user(quadriga_session)
    name = body.이름.strip()
    if not name:
        raise HTTPException(400, "별명을 입력해주세요.")
    if len(name) > 20:
        raise HTTPException(400, "별명은 20자까지예요.")
    auth.rename_user(user["id"], name)
    return {"이름": name}


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
    client_id, secret = auth.client_config(provider)
    if not client_id or not (secret or provider in auth.SECRET_OPTIONAL):
        필요 = (f"{provider.upper()}_CLIENT_ID"
              if provider in auth.SECRET_OPTIONAL
              else f"{provider.upper()}_CLIENT_ID 와 _CLIENT_SECRET")
        raise HTTPException(503,
            f"{provider} 로그인이 아직 설정되지 않았습니다. {필요} 를 넣어주세요.")
    auth.init_db()
    conf = auth.PROVIDERS[provider]
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": public_url(request, f"/auth/{provider}/callback"),
        "state": auth.new_state(provider),
    }
    scope = auth.scope_for(provider)
    if scope:
        params["scope"] = scope
    return RedirectResponse(conf["authorize"] + "?" + urlencode(params))


@app.get("/auth/{provider}/callback", name="auth_callback")
async def auth_callback(provider: str, request: Request,
                        code: str | None = None, state: str | None = None
                        ) -> RedirectResponse:
    if provider not in auth.PROVIDERS:
        raise HTTPException(404, "지원하지 않는 로그인 수단입니다.")
    if not code and not state:
        # 주소창에 직접 친 경우다. 에러가 아니라 원래 이렇게 동작한다.
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'>"
            "<div style=\"font-family:sans-serif;max-width:560px;margin:60px auto;line-height:1.7\">"
            f"<h2>{provider} 로그인 통로입니다</h2>"
            "<p>이 주소는 브라우저로 직접 여는 페이지가 아니라, 로그인이 끝난 뒤 "
            f"{provider} 가 우리 서버를 부를 때 쓰는 통로예요. "
            "지금 이 화면이 보이는 건 <b>서버가 정상 동작한다는 뜻</b>입니다.</p>"
            "<p>콘솔에 등록할 주소는 <a href='/auth/setup'>/auth/setup</a> 에서 확인하세요.</p>"
            "<p><a href='/'>← 서비스로 돌아가기</a></p></div>", status_code=200)
    if not code or not state or auth.take_state(state) != provider:
        # state 가 안 맞으면 남이 만든 요청이다. 진행하지 않는다.
        return RedirectResponse("/?login=failed")

    client_id, client_secret = auth.client_config(provider)
    conf = auth.PROVIDERS[provider]
    form = {
        "grant_type": "authorization_code", "code": code,
        "client_id": client_id,
        "redirect_uri": public_url(request, f"/auth/{provider}/callback"),
        "state": state,
    }
    if client_secret:                    # 카카오는 콘솔에서 안 켜면 값이 없다
        form["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=10) as http:
        tok = await http.post(conf["token"], data=form,
                              headers={"Accept": "application/json"})
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
    _set_session(res, uid, request)
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


# ---------- 약관 · 개인정보처리방침 ----------
# 소셜 로그인 콘솔(구글·네이버·카카오)이 공개 URL 을 요구한다.
# frontend/ 아래 정적 파일이지만 확장자 없는 주소로도 열리게 라우트를 둔다.

@app.get("/privacy", include_in_schema=False)
def privacy() -> FileResponse:
    return FileResponse(paths.FRONTEND / "privacy.html")


@app.get("/terms", include_in_schema=False)
def terms() -> FileResponse:
    return FileResponse(paths.FRONTEND / "terms.html")


# ---------- 정적 프론트엔드 ----------
# 모든 API 라우트를 정의한 뒤 마운트해야 "/" 가 API 를 가리지 않는다.

if paths.FRONTEND.exists():
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(paths.FRONTEND / "index.html")

    app.mount("/", StaticFiles(directory=paths.FRONTEND), name="frontend")
