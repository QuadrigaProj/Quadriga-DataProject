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

import hmac
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode
from typing import Literal

import asyncio

import anyio
import httpx
from fastapi import Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:                                        # 저장소 루트에서 실행할 때
    from backend import auth, daily, fitness_age as fa, prescription as pr, paths
    from backend import daily_prescription as dp
    from backend import routine_player as rp
    from backend import routines as rt, bodycomp as bc, hometest as ht, geo
    from backend import sports as sp
    from backend import style_test as st
    from backend import workout_items as wi
    from backend import recommend as rc
    from backend import ai_recommend as air
    from backend import projection as pj
    from backend import route
    from backend import kakaopay as kp
    from backend import billing
    from backend import community
    from backend import centers_api
    from backend import spare_time as spare
    from backend import season as ssn
    from backend import outdoor
except ImportError:                         # backend/ 안에서 직접 실행할 때
    import auth                             # noqa: E402
    import daily                            # noqa: E402
    import daily_prescription as dp         # noqa: E402
    import routine_player as rp             # noqa: E402
    import routines as rt                   # noqa: E402
    import bodycomp as bc                   # noqa: E402
    import hometest as ht                   # noqa: E402
    import geo                              # noqa: E402
    import sports as sp                     # noqa: E402
    import style_test as st                 # noqa: E402
    import workout_items as wi              # noqa: E402
    import recommend as rc                  # noqa: E402
    import ai_recommend as air              # noqa: E402
    import fitness_age as fa                # noqa: E402
    import paths                            # noqa: E402
    import prescription as pr               # noqa: E402
    import route                            # noqa: E402
    import kakaopay as kp                   # noqa: E402
    import billing                          # noqa: E402
    import centers_api                      # noqa: E402
    import community                        # noqa: E402
    import spare_time as spare              # noqa: E402
    import season as ssn  # type: ignore
    import outdoor  # type: ignore

# 서버가 잠들지 않게 스스로를 두드린다.
#
# Render 무료 요금제는 15분 동안 들어오는 요청이 없으면 서버를 끄고, 다음 첫 접속은 30초가 넘게 걸린다.
# 깃허브 예약 실행(.github/workflows/keep-warm.yml, 5분마다)에 맡겼더니 첫 실행까지 3시간 23분이 걸렸고
# 그 뒤로도 5분 간격을 지켜 주지 않아 서버가 다시 잠들어 있었다(2026-09-21 실측: /health 32초).
# 그래서 서버가 직접 10분마다 자기 바깥 주소의 /health 를 부른다 — 밖으로 나갔다가 들어오는 요청이라
# Render 가 '접속' 으로 센다. 한 번 깨어난 뒤로는 잠들지 않고, 배포로 다시 떠도 그때부터 다시 돈다.
# 깃허브 쪽은 그대로 둔다: 어쩌다 잠들었을 때 깨우는 것은 바깥에서만 할 수 있다.
# 바깥 주소를 모르면(로컬 · 테스트) 아무 일도 하지 않는다. KEEP_AWAKE_EVERY_SEC=0 으로 끈다.
KEEP_AWAKE_EVERY_SEC = float(os.getenv("KEEP_AWAKE_EVERY_SEC", "600"))


def keep_awake_url() -> str | None:
    """스스로를 두드릴 주소. PUBLIC_BASE_URL 이 없으면 Render 가 넣어 주는 RENDER_EXTERNAL_URL 을 쓴다."""
    base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if not base.startswith("https://") or KEEP_AWAKE_EVERY_SEC <= 0:
        return None
    return base + "/health"


async def _keep_awake(url: str) -> None:
    async with httpx.AsyncClient(timeout=20) as http:
        while True:
            await asyncio.sleep(KEEP_AWAKE_EVERY_SEC)
            try:
                await http.get(url)
            except Exception:                    # 한 번 못 불러도 다음에 다시 — 서버를 멈출 일은 아니다
                pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    """배포 직후 첫 요청에서 테이블이 없어 500 이 나지 않도록 미리 만든다."""
    try:
        auth.init_db()
        community.init_db()
        billing.init_db()
    except Exception as e:                       # DB 가 아직 안 붙어도 서버는 뜬다
        print(f"[warn] DB 초기화 실패: {type(e).__name__}")
    url = keep_awake_url()
    깨우기 = asyncio.create_task(_keep_awake(url)) if url else None
    # 체력인증센터 목록은 공단 오픈API 에서 받아 둔다 — 첫 검색이 기다리지 않게 뒤에서 미리
    asyncio.get_running_loop().run_in_executor(None, centers_api.items)
    yield
    if 깨우기:
        깨우기.cancel()
    auth.close_idle()                            # 들고 있던 DB 연결을 닫고 내려간다


app = FastAPI(
    lifespan=lifespan,
    title="체력나이 API",
    description="국민체력100 공공데이터 기반 체력나이 산출·운동 처방",
    version="0.2.0",
)

# 한 요청이 이만큼을 넘기면 끊는다.
#
# 무한 루프 하나가 스레드를 영구 점유해 앱 전체를 멈춰 세운 적이 있다
# (추천의 limit=12). 서버가 한 대뿐이라 그런 요청 몇 개면 남는 자리가 없다.
# 오래 걸릴 일이 없는 서비스라, 넘긴 요청은 답을 못 낸 것으로 본다.
REQUEST_TIMEOUT_SEC = float(os.getenv("REQUEST_TIMEOUT_SEC", "25"))

# AI 를 부르는 경로만 제한을 따로 길게 둔다.
#
# 사진 읽기 · 구간 계획은 요청 안에서 AI 를 기다린다(20~90초). 그 안에 못 끝내면 AI 쪽이 스스로 포기해 폴백으로 넘어간다
# (ai_recommend 의 제한 시간). 위의 25초가 그보다 짧으면 화면에는 "너무 오래 걸려 멈췄어요" 가 나가고 서버의 스레드는
# 끝까지 지은 다음 이용권을 깎는다 — 값은 치렀는데 결과는 못 받는다(2026-09-20 재현). 그래서 이 경로들의 제한은
# AI 가 스스로 포기하는 시간보다 길게 둔다: 늦을 때는 AI 쪽이 먼저 끝나야 한다.
# 루틴 짓기(POST /recommend/routines)는 다르다 — 요청은 작업만 걸어 두고 JOB_WAIT_SEC 만 기다린 뒤 돌아오고,
# 짓는 일은 백그라운드 스레드가 끝까지 한다(_ai_job_run). 화면은 작업 번호로 결과를 가져간다.
# 무료 추천(GET)은 그대로 25초다 — 이 제한이 생긴 까닭(추천의 무한 루프)이 그쪽이다.
AI_ROUTES = {("POST", "/recommend/routines"), ("POST", "/recommend/periods"), ("POST", "/recommend/seasons"),
             ("POST", "/health/photo"), ("POST", "/schedule/photo")}
AI_REQUEST_TIMEOUT_SEC = float(os.getenv("AI_REQUEST_TIMEOUT_SEC", "0")) or air.longest_wait_sec() + 15


def request_limit_sec(method: str, path: str) -> float:
    """이 요청을 몇 초에서 끊는가. 0 이하면 끊지 않는다."""
    if REQUEST_TIMEOUT_SEC <= 0:
        return 0.0
    if (method.upper(), path) in AI_ROUTES:
        return max(REQUEST_TIMEOUT_SEC, AI_REQUEST_TIMEOUT_SEC)
    return REQUEST_TIMEOUT_SEC


def 아직_받을_수_있다(시작: float, method: str, path: str) -> bool:
    """값을 받기 직전에 묻는다 — 이 요청이 아직 끊기지 않았는가(끊겼으면 화면에는 이미 실패가 나갔다).

    끊는 쪽(시간_제한)은 답만 먼저 보낼 뿐 일하던 스레드를 멈추지 못한다. 그 스레드가 뒤늦게 값을 받지 않게 한다.
    1초의 여유를 둔다: 아슬아슬할 때는 받지 않는 쪽으로 틀린다.
    """
    제한 = request_limit_sec(method, path)
    return 제한 <= 0 or time.monotonic() - 시작 < 제한 - 1.0


@app.middleware("http")
async def 시간_제한(request: Request, call_next):
    """오래 끄는 요청을 끊는다. 0 이하로 두면 끄지 않는다(디버깅용)."""
    제한 = request_limit_sec(request.method, request.url.path)
    if 제한 <= 0:
        return await call_next(request)
    try:
        with anyio.fail_after(제한):
            return await call_next(request)
    except TimeoutError:
        # 무엇이 오래 걸렸는지 로그에 남긴다. 경로만 적는다 — 쿼리에는
        # 개인 정보가 실릴 수 있다.
        print(f"[timeout] {request.method} {request.url.path} "
              f"> {제한}s", flush=True)
        return JSONResponse(
            {"detail": "처리가 너무 오래 걸려 멈췄어요. 잠시 뒤 다시 시도해주세요."},
            status_code=503)


# 화면 파일(index.html · js · css)은 받을 때마다 서버에 "바뀌었나" 를 묻게 한다.
#
# 여태 Cache-Control 이 없어서 브라우저가 알아서 오래 들고 있었다. 배포를 해도
# 사람마다 옛 화면이 남아 "고쳤다는데 안 바뀌었다" 가 되풀이됐고, 그때마다
# 강력 새로고침을 부탁했다. no-cache 는 "쓰지 말라" 가 아니라 "쓰기 전에
# 물어보라" 다 — ETag 가 있으니 안 바뀌었으면 304 한 줄로 끝난다.
NO_CACHE_SUFFIXES = (".html", ".js", ".css")


@app.middleware("http")
async def 화면은_늘_다시_확인(request: Request, call_next):
    response = await call_next(request)
    경로 = request.url.path
    if 경로 == "/" or 경로.endswith(NO_CACHE_SUFFIXES):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


# 배포(Cloudflare)는 알아서 압축하지만 로컬 개발 서버는 아니다.
# index.html 이 380KB 라 켜고 끄고가 눈에 띄게 다르다.
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def 보안_헤더(request: Request, call_next):
    """브라우저가 지켜 주는 것들 — 다른 사이트의 iframe 에 끼워 넣기(클릭 가로채기) · 파일 형식 추측 · 참조 주소 흘리기를 막는다.

    CSP 는 넣지 않는다 — 화면이 인라인 스크립트와 CDN(three.js 등)을 써서 지금은 목록을 만들 수 없다. 2차 점검에서.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(self), payment=()")
    if is_https(request):                            # 브라우저에 "이 주소는 앞으로 https 로만" 을 못 박는다 (1년)
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response

# 개발 중에는 프론트 로컬 서버를 허용한다. 배포 시 도메인으로 좁힐 것.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ["http://localhost:3000", "http://localhost:5173",
                               os.getenv("PUBLIC_BASE_URL", "").rstrip("/")] if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(community.router)     # 커뮤니티(게시글·댓글·반응·채팅)

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
    "벌크업", "근육량 늘리기", "지구력 늘리기",
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

class ServiceAgeIn(BaseModel):
    """입력된 만 나이로 서비스 지원 범위와 측정 연령군을 검사한다."""
    @field_validator("age", check_fields=False)
    @classmethod
    def supported_age(cls, value):
        if value is not None:
            rt.age_group(value)
        return value

    @model_validator(mode="after")
    def align_group(self):
        age = getattr(self, "age", None)
        if age is not None and hasattr(self, "age_gbn"):
            group = rt.age_group(age)
            self.age_gbn = "성장기" if group in ("유소년", "청소년") else group
        return self


class MeasureIn(ServiceAgeIn):
    age_gbn: AgeGroup = Field(..., description="연령군 (성장기 = 만 11~18세)")
    sex: Sex
    age: float | None = Field(None, ge=5, le=110,
                              description="만 나이. 주면 또래 백분위를 함께 계산한다")
    flexibility: float | None = Field(None, description="앉아윗몸앞으로굽히기 (cm). 음수 가능")
    strength: float | None = Field(
        None,
        description="연령군별 항목: 성인=교차윗몸일으키기(1분, 회), "
                    "어르신=의자앉았다일어서기(회), 성장기=제자리멀리뛰기(cm)")
    height_cm: float | None = Field(None, gt=0)
    weight_kg: float | None = Field(None, gt=0)
    bmi: float | None = Field(None, gt=0, description="직접 주거나 키·몸무게로 계산")
    grip_kg: float | None = Field(None, gt=0,
                                  description="악력 (kg). 몸무게와 함께 주면 상대악력으로 근력을 낸다")
    endurance: float | None = Field(
        None, ge=0,
        description="심폐지구력: 성인·성장기=왕복오래달리기(회, 11~12세는 15m · 13세부터 20m), "
                    "어르신=2분제자리걷기(회). 성장기는 나이로 환산하지 않고 또래 백분위만 준다")
    long_jump: float | None = Field(None, gt=0, description="성인 순발력: 제자리 멀리뛰기 (cm)")
    shuttle_10m: float | None = Field(None, gt=0, description="성인 민첩성: 10M 4회 왕복달리기 (초)")
    target_3m: float | None = Field(None, gt=0, description="어르신 평형성: 의자에 앉아 3M 표적 돌아오기 (초)")
    figure8: float | None = Field(None, gt=0, description="어르신 협응력: 8자보행 (초)")
    muscle_endurance: float | None = Field(
        None, ge=0,
        description="성장기 근지구력: 만 11~12세=윗몸말아올리기(회), 만 13~18세=반복점프(30초, 회). "
                    "공식 등급 기준으로 또래 순위를 어림해 또래비교에만 준다. 성인·어르신은 strength 를 쓴다")


class EtaIn(MeasureIn):
    """측정값 + 목표 체력나이 → 언제 닿을지. /fitness-age 와 같은 값을 보낸다."""
    target: float = Field(..., ge=5, le=110, description="목표 체력나이")


class MeasureOut(BaseModel):
    체력나이: float | None
    신뢰구간: float | None
    항목별: dict[str, float]
    약점: dict | None
    또래비교: dict = {}
    집중개선영역: list[str] = []
    해석: str = ""


def _extras(body: "MeasureIn") -> dict:
    """선택 항목(운동체력) — 이 연령군에서 쓰는지는 fitness_age.extra_items 가 가린다."""
    return {k: getattr(body, k) for k in fa.EXTRA_ITEMS}


def _measure_inputs(body: "MeasureIn") -> tuple:
    """BMI 와 상대악력을 만든다 — /fitness-age 와 도달 시점 추정이 같은 값을 쓴다."""
    bmi = body.bmi
    if bmi is None and body.height_cm and body.weight_kg:
        bmi = body.weight_kg / (body.height_cm / 100) ** 2
    grip = None
    if body.grip_kg is not None and body.weight_kg:
        grip = body.grip_kg / body.weight_kg * 100
    return bmi, grip


@app.post("/fitness-age/eta")
def post_fitness_age_eta(body: EtaIn) -> dict:
    """목표 체력나이에 언제 닿을지 — 권장 용량대로 주 3회 할 때의 추정 (backend/projection.py).

    빠르면·늦으면 주로 돌려준다. 못 닿으면 None 과 안내. 성장기는 추정하지 않는다.
    """
    _load()
    if _dist is None:
        raise HTTPException(503, "분포 데이터가 없습니다. /health 참고")
    bmi, grip = _measure_inputs(body)
    if (body.flexibility is None and body.strength is None and bmi is None
            and grip is None and body.endurance is None):
        raise HTTPException(400, "측정값을 최소 하나는 보내주세요.")
    return pj.project(_dist, age_gbn=body.age_gbn, sex=body.sex, age=body.age, target=body.target,
                      flexibility=body.flexibility, strength=body.strength, grip=grip,
                      endurance=body.endurance, bmi=bmi, extras=_extras(body))


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

    # 악력은 몸무게로 나눠 상대악력(%)으로 바꿔야 분포와 견줄 수 있다
    grip = None
    if body.grip_kg is not None and body.weight_kg:
        grip = body.grip_kg / body.weight_kg * 100

    if (body.flexibility is None and body.strength is None and bmi is None
            and grip is None and body.endurance is None):
        raise HTTPException(400, "측정값을 최소 하나는 보내주세요.")

    result = fa.fitness_age(
        _dist, body.age_gbn, body.sex,
        flexibility=body.flexibility, strength=body.strength, bmi=bmi,
        grip=grip, endurance=body.endurance, age=body.age, extras=_extras(body),
    )
    if result["체력나이"] is None:
        raise HTTPException(422, "해당 연령군·성별의 분포가 부족해 산출할 수 없습니다.")

    peers = {}
    if body.age is not None:
        peers = fa.peer_report(_dist, body.age_gbn, body.sex, body.age,
                               flexibility=body.flexibility, strength=body.strength,
                               bmi=bmi, grip=grip, endurance=body.endurance,
                               muscle_endurance=body.muscle_endurance, extras=_extras(body))

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
    age_gbn: str | None = Query(None, description="연령대 — 오늘의 일상 처방 문구 선택용"),
    purpose: str | None = Query(None, description="목적 — 오늘의 일상 처방 문구 선택용"),
) -> dict:
    """운동 시간을 따로 내지 않아도 되는 일상 제안 (화면 3).

    교통 데이터는 쓰지 않는다. 사용자가 알려준 값만으로 판단한다.
    age_gbn·purpose 를 주면 연령대·목적별 일상 처방 문구가 경과일마다 순환한다.
    """
    out = {
        "계단": daily.stairs(strength_stars),
        "도보": daily.walk(walk_minutes),
        "강도": daily.intensity(days_since_start),
    }
    if age_gbn and purpose:
        try:
            today = dp.tip(age_gbn, purpose, days_since_start)
            if today:
                out["일상처방"] = today
        except FileNotFoundError:
            pass                            # 문구 데이터가 없으면 계단·도보만 보여준다
    return out


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


# ---------- 7b. 3개월 프로그램 루틴 (200 KSPO 루틴) ----------

ProgramAge = Literal[ "유소년", "청소년", "성인", "어르신"]
ProgramPurpose = Literal[
    "다이어트", "기초 체력 증진", "재활 및 기능 회복", "수험생 체력 증진", "유연성 강화",
    "벌크업", "근육량 늘리기", "지구력 늘리기",
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

    루틴을 새로 만들지 않는다. data/generated/routines_200_kspo.json 을 순환시킨다.
    수행량은 12주 3구간 규칙 + 현재 체력 보정(offset)으로 붙인다.
    안전·제외 부위 조건은 후보가 없어도 완화하지 않는다.
    """
    if real_age is not None:
        try:
            age_gbn = rt.age_group(real_age)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
    parts = [p.strip() for p in (exclude_parts or "").split(",") if p.strip()]

    # 선택한 모든 스포츠의 체력요소를 본운동 세 번째 교체 후보에 사용한다.
    # 안 고른 사람에게는 종목 데이터를 아예 읽지 않는다. 종목은 곁가지라
    # sports.json 이 없다고 해서 루틴 자체가 안 나오면 안 된다.
    picked = [i.strip() for i in (sports or "").split(",") if i.strip()]

    try:
        prefer = list(sp.factor_weights(picked)) if picked else []
        routine = rt.build_program_routine(
            age_gbn, purpose, day=day, exclude_parts=parts, heavy=heavy,
            prefer_factors=prefer)
    except (KeyError, FileNotFoundError) as e:
        raise HTTPException(404, str(e))

    offset = rt.start_offset(fitness_age, real_age)
    intensity = rt.intensity_for(age_gbn, week, offset=offset, heavy=heavy, purpose=purpose)
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
    """목적 8종 + (연령대를 주면) 그 연령대 재프레이밍 라벨."""
    d = rt.load()["config"]
    out = []
    for p in rt.PURPOSES:
        item = {"목적": p, "우선요인": d["purpose_factors"].get(p, [])}
        if age_gbn:
            item["표시명"] = d["reframe"].get(age_gbn, {}).get(p, p)
        out.append(item)
    return out


# ---------- 7c. InBody · 홈 체력측정 ----------

class InBodyIn(ServiceAgeIn):
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


class HomeTestIn(ServiceAgeIn):
    sex: Sex
    age: float = Field(..., ge=4, le=110)
    height_cm: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)
    waist_cm: float | None = Field(None, gt=0)
    jump_30s: float | None = Field(None, ge=0, description="30초 제자리 점프 (회)")
    curlup_30s: float | None = Field(None, ge=0, description="교차윗몸일으키기 1분 횟수 (필드 이름만 옛것이다)")
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


@app.get("/centers/source")
def get_centers_source() -> dict:
    """센터 목록을 어디서 받았는지 — api · snapshot · sample, 센터 수, 응답에 있던 칸 이름(값은 내지 않는다)."""
    return centers_api.status()


@app.get("/centers/all")
def get_centers_all() -> dict:
    """받아 둔 전국 센터 목록 전부 — 저장소 스냅숏(data/sample/centers_kspo.json)을 만들 때 쓴다. 공개된 센터 정보뿐이다."""
    전체, 출처 = centers_api.items()
    return {"출처": 출처, "기준일": time.strftime("%Y-%m-%d"), "데이터": centers_api.SOURCE_PAGE, "items": 전체}


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
    전체, 출처 = centers_api.items()
    matched = daily.centers_by_addr(region, items=전체) if region else []
    by_addr = bool(matched)
    if lat is None and lon is None and region:
        c = geo.geocode(region)
        if c:
            lat, lon, resolved = c[0], c[1], region
    items = daily.centers(lat, lon, limit, items=matched if by_addr else 전체)
    items = [{**it, "예약": BOOKING_URL} for it in items]            # 기억해 둔 목록을 고치지 않는다
    if by_addr:
        note = "입력한 구 주소와 일치하는 센터예요. 예약은 국민체력100 공식 페이지에서 진행합니다."
    elif region and lat is not None:
        note = ("주소가 일치하는 센터가 없어 가까운 순으로 보여드려요. 직선거리 기준이에요. "
                "도보 시간은 지도 앱에서 확인하세요. 예약은 국민체력100 공식 페이지에서 진행합니다.")
    else:
        note = "직선거리 기준이에요. 도보 시간은 지도 앱에서 확인하세요. 예약은 국민체력100 공식 페이지에서 진행합니다."
    return {
        "출처": 출처,                               # api · snapshot(받아 둔 공단 목록) · sample(예시)
        "데이터": "국민체력100 체력인증센터 측정건수 정보(공공데이터포털)" if 출처 != "sample" else "예시 목록",
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


def client_ip(request: Request) -> str:
    """요청한 쪽의 주소. 프록시(Render) 뒤에서는 X-Forwarded-For 의 **마지막** 값 — 프록시가 붙인 것이라 위조하기 어렵다."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd.strip():
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "?"


def _잠금_안내(남은초: int) -> str:
    분 = max(1, -(-남은초 // 60))
    return f"로그인을 여러 번 틀려 잠시 잠겼어요. {분}분 뒤에 다시 해 주세요."


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
    # 한 곳에서 계정을 무더기로 만드는 것을 막는다 — 시연 기간의 무료 AI 횟수를 계정을 늘려 우회하는 길이기도 하다
    가입키 = f"signup:{client_ip(request)}"
    if auth.guard_locked(가입키):
        raise HTTPException(429, "가입 요청이 너무 많아요. 잠시 뒤에 다시 해 주세요.")
    auth.guard_hit(가입키, auth.SIGNUP_MAX_PER_IP)

    salt, pw_hash = auth.hash_password(body.password)
    uid = auth.upsert_user("password", email, email=email,
                           name=body.display_name or email.split("@")[0],
                           salt=salt, pw_hash=pw_hash)
    _set_session(response, uid, request)
    return {"ok": True, "이름": body.display_name or email.split("@")[0]}


@app.post("/auth/login")
def auth_login(body: LoginIn, response: Response, request: Request) -> dict:
    auth.init_db()
    email = body.email.strip().lower()
    ip = client_ip(request)
    # 잠금은 '같은 곳에서 같은 이메일' 기준 — 남이 다른 곳에서 내 이메일을 틀려도 나는 잠기지 않는다.
    이메일키, 주소키 = f"email:{email}@{ip}", f"ip:{ip}"
    # 비밀번호를 5번 틀리면 15분 잠근다 — 잠긴 동안은 비밀번호를 대조하지도 않는다 (scrypt 는 한 번에 16MB · 수십 ms 다).
    # 가입 여부와 상관없이 잠근다: 있는 이메일만 잠그면 잠기는지로 가입 여부를 알아낼 수 있다.
    남은초 = max(auth.guard_locked(이메일키), auth.guard_locked(주소키))
    if 남은초:
        raise HTTPException(429, _잠금_안내(남은초))
    row = auth.find_password_user(email)
    # 이메일이 없을 때와 비밀번호가 틀렸을 때의 응답을 같게 둔다.
    # 다르게 두면 어떤 이메일이 가입돼 있는지 알아낼 수 있다.
    if not row or not auth.verify_password(body.password, row["password_salt"],
                                           row["password_hash"]):
        남은횟수 = auth.guard_hit(이메일키, auth.LOGIN_MAX_FAILURES)
        auth.guard_hit(주소키, auth.IP_MAX_FAILURES)
        if 남은횟수 == 0:
            raise HTTPException(429, f"비밀번호를 {auth.LOGIN_MAX_FAILURES}번 틀려 "
                                     f"{auth.LOGIN_LOCK_SEC // 60}분 동안 잠겼어요. 잠시 뒤에 다시 해 주세요.")
        경고 = f" ({남은횟수}번 더 틀리면 {auth.LOGIN_LOCK_SEC // 60}분 동안 잠겨요)" if 남은횟수 <= 2 else ""
        raise HTTPException(401, "이메일 또는 비밀번호가 맞지 않습니다." + 경고)
    auth.guard_clear(이메일키)
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
            "수단": user["provider"] if user else None,
            # ADMIN_USERS 에 적을 이름 — 'kakao:회원번호' 꼴. 비밀 값이 아니다(제공자 안의 번호일 뿐)
            "계정": f"{user['provider']}:{user['provider_uid']}" if user else None}


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


@app.get("/auth/me/delete-preview")
def auth_delete_preview(quadriga_session: str | None = Cookie(None)) -> dict:
    """지우기 전에 보여 줄 것 — 자동 환불될 충전과 사라질 잔액·구독. 화면이 이걸로 확인 문구를 만든다."""
    user = _require_user(quadriga_session)
    billing.init_db()                                       # 테스트처럼 서버 시작 절차 없이 부를 때도 표가 있게
    p = billing.delete_preview(user["id"])
    return {"환불건수": p["환불건수"], "환불금액": p["환불금액"], "소멸잔액": p["소멸잔액"],
            "구독": {"까지": p["구독"]["ends_at"]} if p["구독"] else None}


async def _refund_unused_before_delete(user_id: int) -> list[str]:
    """안 쓴 충전을 전부 카카오에 취소 요청한다. 하나라도 실패하면 삭제를 막는다 — 돈이 걸린 자리라 조용히 넘기지 않는다."""
    끝난것 = []
    for o in billing.unused_orders(user_id):
        if not billing.set_status(o["order_id"], "refunding", only_from="paid"):
            continue                                              # 다른 요청이 처리 중이면 그쪽에 맡긴다
        ok = await kp.cancel(tid=o["tid"], amount=o["amount"])
        if not ok or ok["canceled"] != o["amount"]:
            billing.set_status(o["order_id"], "paid", only_from="refunding")
            raise HTTPException(502, f"안 쓴 충전({won_text(o['amount'])})의 환불이 되지 않아 삭제하지 않았어요. "
                                     "잠시 뒤 다시 하거나 결제 내역에서 먼저 환불해 주세요.")
        billing.set_status(o["order_id"], "refunded", only_from="refunding")
        billing.refund(user_id, o["credit"], o["order_id"], memo="계정 삭제로 환불")
        끝난것.append(o["order_id"])
    return 끝난것


def won_text(n: int) -> str:
    return f"{int(n):,}원"


@app.delete("/auth/me")
async def auth_delete_me(response: Response,
                         quadriga_session: str | None = Cookie(None)) -> dict:
    """계정과 측정 기록을 모두 지운다. 되돌릴 수 없다.

    지우기 전에 **안 쓴 충전은 자동으로 환불**한다(약관 6조의2 · 예현 2026-09-23). 일부라도 쓴 충전의 남은 잔액과
    구독은 함께 사라진다 — 화면이 /auth/me/delete-preview 로 미리 알리고 확인을 받는다.
    """
    user = _require_user(quadriga_session)
    billing.init_db()
    환불 = await _refund_unused_before_delete(user["id"])
    auth.delete_account(user["id"])
    response.delete_cookie(auth.SESSION_COOKIE)
    return {"ok": True, "환불건수": len(환불)}


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
    res = RedirectResponse(conf["authorize"] + "?" + urlencode(params))
    # 같은 state 를 이 브라우저에도 남긴다. 콜백은 DB 와 쿠키 양쪽을 대조한다 — 남이 시작한 로그인의
    # 콜백 주소를 열어도(로그인 CSRF) 쿠키가 없거나 다르니 진행되지 않는다.
    # SameSite=Lax 라도 제공자에서 돌아오는 최상위 이동(GET)에는 실려 온다.
    res.set_cookie(auth.OAUTH_COOKIE, params["state"], max_age=auth.OAUTH_STATE_SEC,
                   httponly=True, samesite="lax", secure=is_https(request), path="/auth/")
    return res


def _drop_oauth_cookie(res: RedirectResponse) -> RedirectResponse:
    """콜백이 끝나면(성공이든 실패든) state 쿠키는 쓸모가 없다 — 지운다."""
    res.delete_cookie(auth.OAUTH_COOKIE, path="/auth/")
    return res


def _login_failed(provider: str, 단계: str, error=None, desc: str | None = None) -> RedirectResponse:
    """소셜 로그인 실패 — 어디서 · 왜 실패했는지 서버 로그에 한 줄 남기고, 화면에도 단계를 알려 준다.

    전에는 무엇이 잘못돼도 "/?login=failed" 뿐이라, 구글 · 네이버만 안 될 때 까닭을 알 길이 없었다
    (동의 화면에서 막혔는지, Client Secret 이 틀렸는지, 프로필을 못 읽었는지).
    제공자가 준 오류 이름(invalid_client · access_denied …)만 남긴다 — 코드 · 토큰 · 비밀 값은 적지 않는다.
    """
    이름 = str(error or "")[:60]
    print(f"[oauth] {provider} 로그인 실패 · 단계={단계} · {이름} · {(desc or '')[:200]}", flush=True)
    q = {"login": "failed", "why": 단계, "p": provider}
    if 이름:
        q["e"] = 이름
    if desc:
        # 네이버는 무엇이 틀려도 오류 이름이 invalid_request 하나다 — 갈라 주는 것은 설명뿐이다
        # ("wrong client secret" · "no valid data in session" …). 제공자가 쓴 짧은 영어 문장이고 비밀 값은 들어 있지 않다.
        q["d"] = str(desc)[:80]
    return _drop_oauth_cookie(RedirectResponse("/?" + urlencode(q)))


@app.get("/auth/{provider}/callback", name="auth_callback")
async def auth_callback(provider: str, request: Request,
                        code: str | None = None, state: str | None = None,
                        error: str | None = None, error_description: str | None = None,
                        ) -> RedirectResponse:
    if provider not in auth.PROVIDERS:
        raise HTTPException(404, "지원하지 않는 로그인 수단입니다.")
    if error:
        # 제공자가 돌려보냈다 — 동의 화면에서 취소했거나, 아직 허용되지 않은 계정이다
        # (구글 OAuth 동의 화면이 '테스트' 상태면 등록한 테스트 사용자만, 네이버 앱이 '개발 중' 이면 등록한 아이디만 된다)
        if state:
            auth.take_state(state)
        return _login_failed(provider, "denied", error, error_description)
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
    # state 는 DB 에 있어야 하고(우리가 만든 것) **이 브라우저의 쿠키와도 같아야** 한다(이 브라우저가 시작한 것).
    # 쿠키 대조가 없으면 공격자가 제 브라우저로 시작한 로그인의 콜백 주소를 남에게 열게 해서
    # 그 사람의 세션을 공격자 계정으로 묶을 수 있다 — 그 뒤로 그 사람이 적는 기록이 공격자에게 보인다.
    쿠키 = request.cookies.get(auth.OAUTH_COOKIE) or ""
    if not code or not state or not hmac.compare_digest(state.encode(), 쿠키.encode())             or auth.take_state(state) != provider:
        # state 가 안 맞으면 남이 만든 요청이다. 진행하지 않는다. (10분이 지나 만료된 것도 여기로 온다)
        return _login_failed(provider, "state")

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

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            tok = await http.post(conf["token"], data=form,
                                  headers={"Accept": "application/json"})
            try:
                body = tok.json() or {}
            except ValueError:
                body = {}
            access = body.get("access_token") if isinstance(body, dict) else None
            if not access:
                # invalid_client = Client ID/Secret 이 콘솔의 것과 다르다 · redirect_uri_mismatch = 콘솔에 등록한 주소와 다르다
                # · invalid_grant = 코드가 만료됐거나 이미 썼다
                return _login_failed(provider, "token", (body.get("error") if isinstance(body, dict) else None) or tok.status_code,
                                     body.get("error_description") if isinstance(body, dict) else None)
            me = await http.get(conf["profile"],
                                headers={"Authorization": f"Bearer {access}"})
            try:
                raw = me.json() or {}
            except ValueError:
                raw = {}
            profile = auth.normalize_profile(provider, raw if isinstance(raw, dict) else {})
    except httpx.HTTPError as e:
        return _login_failed(provider, "network", type(e).__name__)

    if not profile.get("uid"):
        return _login_failed(provider, "profile", me.status_code)

    uid = auth.upsert_user(provider, profile["uid"],
                           email=profile.get("email"), name=profile.get("name"))
    res = _drop_oauth_cookie(RedirectResponse("/?login=ok"))
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


# ---------- 10. 운동 스타일 테스트 ----------
# 좋아하는 운동·투자하고 싶은 시간이 아직 뚜렷하지 않을 때 쓰는 짧은 테스트(F1).
# 문항·유형·채점 기준은 전부 data/sample/style_test.json 에 있고 서버는 채점만 한다.

class StyleAnswersIn(BaseModel):
    answers: list = Field(..., description="문항 순서대로 고른 선택지 번호(0부터)")


@app.get("/style-test")
def get_style_test() -> dict:
    """운동 스타일 테스트 문항과 결과 유형 목록. 선택지 점수·가중치는 주지 않는다."""
    try:
        return {"문항": st.questions(), "유형": st.result_types()}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/style-test/result")
def post_style_test_result(body: StyleAnswersIn) -> dict:
    """답 목록 → 스타일 유형 + 추천 목적·종목·하루 투자 분. 잘못된 답은 400."""
    try:
        out = st.score(body.answers)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    # 화면이 이름·아이콘을 바로 그리게. 예산 안의 종목을 앞에 — 돈이 드는 종목은 뒤로 보내고 표시한다
    out["종목"] = st.sports_for_budget(sp.resolve(out["유형"]["추천종목"]), out.get("예산"))
    return out


# ---------- 14. 이용권 결제 ----------
#
# 카드번호·CVC·계좌번호는 이 서버가 받지 않는다. 받으면 안 된다.
# 실제 서비스에서 그건 PG사 결제창이 받는다(PCI-DSS). 우리는 금액과
# 주문번호만 다루고, 승인 결과도 PG가 알려준 금액을 그대로 믿는다.

# 값표 (2026-09-22 예현 결정). 기준은 둘 — 우리가 이익을 남기되, 사용자도 적정하다고 느끼게.
# AI 호출 하나의 원가(Opus 5, 1달러 1,400원)는 루틴 짓기 180~240원 · 구간 계획 90~200원 · 사진 읽기 25~60원이다.
# 실제 토큰 수는 ai_usage 표(billing.ai_cost_summary)에 쌓인다 — 값을 다시 정할 때 거기를 본다.
AI_PRICE = 500                          # AI 루틴 추천 1회 — 한 번 받으면 몇 달 이어 쓴다. 화면과 같아야 한다
ADJUST_PRICE = 300                      # '더 쉽게 / 더 어렵게' 조정 — 산 것을 고치는 일이라 새로 받기보다 싸게
DETAIL_PRICE = 500                      # '자세히 보기' — 구간(계절·시간대) 계획 + 시간표 사진 읽기, DETAIL_DAYS 동안
HEALTH_PHOTO_PRICE = 300                # 약봉지·처방전 사진 읽기 (글로 직접 적는 건 무료)
DETAIL_DAYS = 7
DETAIL_LIMITS = {"구간": 5, "시간표사진": 3}    # 자세히 보기 한 번으로 쓸 수 있는 횟수 — 원가가 드는 호출이라 무한정은 아니다
PRICES = {"루틴": AI_PRICE, "조정": ADJUST_PRICE, "자세히": DETAIL_PRICE, "건강사진": HEALTH_PHOTO_PRICE}

# 한 달 구독 — 자동 갱신 없는 30일 이용권(사업자 없이는 정기결제 계약이 안 된다). 매달 직접 결제한다.
# AI 루틴 하루 5회(조정 포함) · 자세히 보기 포함(구간 계획 · 시간표 사진 하루 5회) · 약봉지 사진 하루 5회 ·
# 커뮤니티 쓰기 제한 해제(community.LIMITS["구독"]). 원가: 20~40회 쓰면 4~8천 원 — 하루 5회를 매일 다 쓰면 적자라 사용량을 본다.
SUB_PRICE = 9900
SUB_DAYS = 30
SUB_LIMITS = {"루틴": 5, "구간": 5, "사진": 5}

# 시연 기간 — 실결제가 안 되는 동안(카카오페이 키가 없거나 테스트 가맹점) 값 대신 **하루 무료 횟수**로 제한한다.
# 테스트 결제로는 누구나 이용권을 공짜로 채울 수 있어서, 값으로 막는 건 막는 게 아니다.
DEMO_LIMITS = {"루틴": 3, "구간": 3, "사진": 2}   # 조정은 루틴에, 시간표·약봉지 사진은 '사진' 에 함께 센다
DEMO_IP_LIMIT = 60                                # 한 곳(IP)에서 하루 AI 호출 합계 — 계정을 늘려 우회하는 것을 막되, 같은 와이파이의
                                                  # 여러 사람(심사·시연)이 막히지 않게 (2026-09-23 15→60)
DEMO_KINDS = {"루틴": ("루틴", "조정"), "구간": ("구간",), "사진": ("시간표사진", "건강사진")}


def billing_mode() -> str:
    """'real'(이용권 차감) 또는 'demo'(하루 무료 횟수).

    AI_BILLING_MODE 로 고정할 수 있고, 없으면 카카오페이 설정으로 정한다 — 실제 가맹점 코드(TC 로 시작하지 않는 것)와
    키가 있을 때만 실결제다.
    """
    고정 = (os.getenv("AI_BILLING_MODE") or "").strip().lower()
    if 고정 in ("real", "demo"):
        return 고정
    return "real" if (kp.available() and not kp.is_test()) else "demo"


# 선결제 보너스 (K3).
#   이용권 = 앱 안에서 쓸 수 있는 금액,  결제 = 실제로 내는 금액
# 많이 미리 낼수록 이용권을 더 얹어 준다. 1회만 결제(500원)는 보너스가 없다.
# 보너스는 25%(=값의 20% 할인)까지만 — 한 번 쓸 때마다 원가 200원 안팎이 실제로 나가서 그보다 깊으면 팔수록 손해다.
# **이 표가 기준이다.** 화면이 보낸 결제 금액을 믿지 않고, 여기서 다시 계산한다.
PAY_PACKS = (
    {"이용권": 500,   "결제": 500},     # 1회만
    {"이용권": 1100,  "결제": 1000},    # +10%
    {"이용권": 3450,  "결제": 3000},    # +15%
    {"이용권": 6000,  "결제": 5000},    # +20%
    {"이용권": 12500, "결제": 10000},   # +25%
)


def pack_for(이용권: int) -> dict | None:
    for p in PAY_PACKS:
        if p["이용권"] == 이용권:
            return p
    return None


def pack_view(p: dict) -> dict:
    """화면에 줄 모양 — 보너스율(과 예전 화면이 쓰던 할인율)까지 서버가 계산해서 내려준다."""
    할인 = round((1 - p["결제"] / p["이용권"]) * 100)
    보너스 = round((p["이용권"] / p["결제"] - 1) * 100)
    return {"이용권": p["이용권"], "결제": p["결제"], "할인": 할인, "보너스": 보너스}

@app.get("/pay/methods")
def get_pay_methods() -> dict:
    """화면이 그릴 결제 수단. 카카오페이만 실제로 붙어 있다."""
    return {
        "packs": [pack_view(p) for p in PAY_PACKS],
        "값표": PRICES,
        "시연": billing_mode() == "demo",
        "kakao": {"쓸수있음": kp.available(), "테스트": kp.is_test()},
        "카드": CARD_ISSUERS,
        "은행": BANKS,
    }


@app.post("/pay/refund/{order}")
async def post_pay_refund(order: str,
                          quadriga_session: str | None = Cookie(None)) -> dict:
    """결제 취소(환불). 산 사람이 스스로 부른다.

    전자상거래법상 청약철회를 받아야 하므로 이 길이 필요하다.

    **한 번이라도 쓴 선결제권은 환불하지 않는다.** 쓴 만큼은 이미 제공된
    서비스라 돌려받을 게 없고, 일부만 돌려주려면 얼마를 돌려줄지 규정이
    있어야 한다. 지금은 안 쓴 것만 통째로 취소한다.

    카카오에서 실제로 취소된 뒤에만 이용권을 되돌린다 — 순서가 바뀌면
    돈은 그대로인데 이용권만 사라진다.
    """
    user = _require_user(quadriga_session)
    o = billing.get_order(order)
    if not o or o["user_id"] != user["id"] or o["status"] != "paid":
        raise HTTPException(404, "환불할 결제를 찾을 수 없어요.")
    if o.get("product") == "구독":
        raise HTTPException(409, "구독은 여기서 환불하지 않아요. 문의를 남겨 주세요.")
    if billing.used_after(user["id"], order):
        raise HTTPException(409, "이미 사용한 이용권은 환불할 수 없어요.")

    # 같은 주문을 동시에 두 번 환불하지 못하게 — 먼저 상태를 'refunding' 으로 잡은 요청만 카카오를 부른다.
    if not billing.set_status(order, "refunding", only_from="paid"):
        raise HTTPException(409, "이미 환불 처리 중이에요.")
    ok = await kp.cancel(tid=o["tid"], amount=o["amount"])
    if not ok or ok["canceled"] != o["amount"]:
        billing.set_status(order, "paid", only_from="refunding")      # 카카오가 안 받았다 — 되돌린다
        raise HTTPException(502, "결제 취소에 실패했어요. 잠시 뒤 다시 시도해 주세요.")

    billing.set_status(order, "refunded", only_from="refunding")
    남음 = billing.refund(user["id"], o["credit"], order, memo="결제 취소")
    return {"ok": True, "환불": o["amount"], "잔액": 남음}


CARD_ISSUERS = ["KB국민", "신한", "삼성", "현대", "롯데", "하나", "BC", "NH농협", "우리"]
BANKS = ["KB국민", "신한", "우리", "하나", "NH농협", "IBK기업", "카카오뱅크", "토스뱅크"]


class PayReadyIn(BaseModel):
    amount: int = Field(0, description="충전할 이용권 금액(원). 실제 결제액은 서버가 정한다. 구독이면 무시")
    product: Literal["구독"] | None = Field(None, description="'구독' 이면 한 달 구독(SUB_PRICE)을 산다")


@app.post("/pay/kakao/ready")
async def post_pay_ready(body: PayReadyIn, request: Request,
                         quadriga_session: str | None = Cookie(None)) -> dict:
    """카카오페이 결제 준비 → 결제창 주소를 돌려준다.

    실제 결제는 로그인한 회원만 할 수 있다. 잔액이 서버 원장에 쌓이므로
    붙일 계정이 없으면 돈만 받고 줄 곳이 없다.
    """
    if body.product == "구독":
        pack = {"이용권": 0, "결제": SUB_PRICE}
    else:
        pack = pack_for(body.amount)
    if not pack:
        raise HTTPException(400, "고를 수 없는 금액입니다.")
    if not kp.available():
        raise HTTPException(503, "카카오페이가 아직 설정되지 않았습니다.")
    누구 = auth.user_for_token(quadriga_session)
    if not 누구:
        raise HTTPException(401, "결제하려면 로그인해 주세요.")

    order = kp.new_order_id()
    out = await kp.ready(
        amount=pack["결제"], order_id=order, user_id=f"u{누구['id']}",
        approval_url=public_url(request, f"/pay/kakao/approve?order={order}"),
        cancel_url=public_url(request, f"/pay/kakao/cancel?order={order}"),
        fail_url=public_url(request, f"/pay/kakao/fail?order={order}"),
    )
    if not out or not out.get("tid"):
        # 왜 실패했는지 그대로 알려 준다. "실패했다" 만으로는 손쓸 방법이 없다.
        raise HTTPException(502, kp.hint(out))

    billing.new_order(order, 누구["id"], out["tid"], pack["이용권"], pack["결제"], product=body.product)
    # 접속 환경은 화면이 안다. 셋 다 주고 고르게 한다 — PC 는 QR 화면으로 가야 한다.
    return {"order": order,
            "redirect": out["redirect_mobile"],        # 예전 화면 호환
            "redirect_pc": out["redirect_pc"],
            "redirect_mobile": out["redirect_mobile"],
            "redirect_app": out["redirect_app"],
            "결제": pack["결제"], "이용권": pack["이용권"]}


@app.get("/pay/kakao/approve")
async def get_pay_approve(order: str, pg_token: str = "") -> RedirectResponse:
    """카카오가 사용자를 여기로 돌려보낸다. 여기서 승인해야 돈이 빠진다."""
    o = billing.get_order(order)
    if not o or not pg_token:
        return RedirectResponse("/?pay=fail")
    if o["status"] == "paid":                       # 새로고침으로 다시 들어온 경우
        return RedirectResponse(f"/?pay=ok&order={order}")
    if o["status"] != "ready":
        return RedirectResponse("/?pay=fail")
    # 같은 콜백이 동시에 두 번 오면 하나만 승인으로 간다
    if not billing.set_status(order, "approving", only_from="ready"):
        return RedirectResponse(f"/?pay=ok&order={order}")

    ok = await kp.approve(tid=o["tid"], pg_token=pg_token,
                          order_id=order, user_id=f"u{o['user_id']}")
    if not ok:
        billing.set_status(order, "failed")
        return RedirectResponse("/?pay=fail")

    # 카카오가 실제로 승인한 금액이 우리가 청구한 금액과 다르면 반영하지 않는다.
    if ok["amount"] != o["amount"]:
        billing.set_status(order, "failed")
        return RedirectResponse("/?pay=fail")

    # 이용권은 주문에 적힌 값으로 올린다 — 화면이 보낸 숫자를 믿지 않는다. 구독 주문이면 구독을 연다.
    if o.get("product") == "구독":
        billing.subscribe(o["user_id"], o["amount"], order, SUB_DAYS)
    else:
        billing.charge(o["user_id"], o["credit"], o["amount"], order)
    billing.set_status(order, "paid", ok.get("aid"))
    return RedirectResponse(f"/?pay=ok&order={order}")


@app.get("/pay/kakao/cancel")
def get_pay_cancel(order: str) -> RedirectResponse:
    o = billing.get_order(order)
    if o and o["status"] == "ready":
        billing.set_status(order, "canceled")
    return RedirectResponse("/?pay=cancel")


@app.get("/pay/kakao/fail")
def get_pay_fail(order: str) -> RedirectResponse:
    o = billing.get_order(order)
    if o and o["status"] == "ready":
        billing.set_status(order, "failed")
    return RedirectResponse("/?pay=fail")


@app.get("/pay/result/{order}")
def get_pay_result(order: str, quadriga_session: str | None = Cookie(None)) -> dict:
    """결제가 끝났는지 화면이 확인한다. 충전은 이미 서버에서 끝나 있다."""
    user = _require_user(quadriga_session)
    o = billing.get_order(order)
    if not o or o["user_id"] != user["id"]:
        raise HTTPException(404, "승인된 결제가 아닙니다.")
    if o["status"] != "paid":
        raise HTTPException(404, "승인된 결제가 아닙니다.")
    구독 = subscribed(user) if o.get("product") == "구독" else None
    return {"paid": True, "amount": o["credit"], "결제": o["amount"], "product": o.get("product"),
            "구독": {"까지": 구독["ends_at"]} if 구독 else None,
            "잔액": billing.balance(user["id"])}


# ---------- 이용권 잔액 ----------

@app.get("/credit")
def get_credit(quadriga_session: str | None = Cookie(None)) -> dict:
    """잔액과 내역. 브라우저가 아니라 서버가 기준이다."""
    user = _require_user(quadriga_session)
    return {"잔액": billing.balance(user["id"]),
            "내역": billing.history(user["id"])}


# ---------- 13. 운동 기록 반영 체력나이 ----------

class ActivityIn(ServiceAgeIn):
    age_gbn: AgeGroup
    age: float | None = Field(None, ge=5, le=110)
    sex: Sex | None = None
    항목별: dict[str, float] = Field(..., description="마지막 측정의 항목별 환산나이. 그대로 돌려준다")
    신뢰구간: float | None = Field(None, ge=0, description="그 측정의 편차. 반영 한도가 된다")
    활동: dict[str, int] = Field(default_factory=dict,
                                description="{요인: 그 요인을 운동한 날 수}")
    # 그날 잰 몸 상태가 있으면 체성분만 실제 값으로 갈아 끼운다 (K1·K2)
    키: float | None = Field(None, ge=80, le=250)
    몸무게: float | None = Field(None, ge=20, le=300)
    체지방률: float | None = Field(None, ge=1, le=70)


@app.post("/fitness-age/activity")
def post_activity_age(body: ActivityIn) -> dict:
    """마지막 측정 + 최근 운동 기록 → 반영된 추정 체력나이 (I3).

    운동만으로 체력나이를 새로 산출할 근거는 없다. 그래서 측정값을 기준으로
    두고 측정 편차 안에서만 움직인다. 다시 재면 진짜 값으로 덮인다.
    """
    if not body.항목별:
        raise HTTPException(400, "마지막 측정 결과가 필요합니다.")
    return _activity_one(body)


def _activity_one(body: "ActivityIn") -> dict:
    _load()
    체성분 = None
    if _dist is not None and body.sex and (body.체지방률 is not None or (body.키 and body.몸무게)):
        체성분 = fa.body_part(_dist, body.age_gbn, body.sex,
                            키=body.키, 몸무게=body.몸무게, 체지방률=body.체지방률, age=body.age)
    out = fa.activity_adjusted(body.항목별, body.신뢰구간, body.활동,
                               body.age_gbn, body.age, 체성분)
    if out["체력나이"] is None:
        raise HTTPException(422, "반영할 수 있는 항목이 없습니다.")
    return out


class ActivityDayIn(ActivityIn):
    date: str = Field(..., description="이 결과를 붙일 날짜 (YYYY-MM-DD)")


@app.post("/fitness-age/activity/days")
def post_activity_days(body: list[ActivityDayIn]) -> list[dict]:
    """여러 날을 한 번에 (K1).

    날짜마다 따로 부르면 기록이 쌓일수록 요청이 늘어난다.
    계산할 수 없는 날은 결과에서 빼고, 부르는 쪽이 date 로 짝을 맞춘다.
    """
    if len(body) > 400:
        raise HTTPException(400, "한 번에 400일까지만 됩니다.")
    out = []
    for one in body:
        if not one.항목별:
            continue
        try:
            r = _activity_one(one)
        except HTTPException:
            continue
        r["date"] = one.date
        out.append(r)
    return out


# ---------- 12. 루틴 추천 ----------

# ---------- AI 관문 — 부르기 전에 되는지 보고, 지은 뒤에 받는다 ----------
#
# AI 호출은 종류마다 값이 다르고(PRICES), 시연 기간에는 값 대신 하루 횟수(DEMO_LIMITS)다.
# 어느 쪽이든 순서는 같다: ai_allow → (AI 를 부른다) → ai_settle. 실패하면 settle 을 부르지 않는다 — 한 푼도 안 받는다.
# 관리자(ADMIN_USERS)는 값도 횟수도 없이 쓴다 — 팀이 직접 써 보는 데 값을 치르지 않게. 원가는 그대로 나가니 기록은 남긴다.
_ai_inflight: set[int] = set()          # 지금 AI 를 부르는 중인 사용자 — 한 사람이 동시에 둘을 부르지 못하게(두 번 눌러 두 번 내는 일)
_ai_inflight_lock = threading.Lock()


def is_admin(누구: dict | None) -> bool:
    """ADMIN_USERS 에 적힌 계정인지 — 'provider:uid'(예 kakao:12345 · password:me@x.com) 또는 소셜 계정의 이메일을 쉼표로.

    비밀번호 계정의 이메일은 확인한 적이 없는 값이라 이메일만으로는 관리자가 되지 않는다 — 누군가 관리자 이메일로
    비밀번호 계정을 만들면 그대로 관리자가 되는 구멍이다. 비밀번호 계정은 'password:이메일' 로 적는다.
    """
    if not 누구:
        return False
    허용 = {e.strip().lower() for e in (os.getenv("ADMIN_USERS") or "").split(",") if e.strip()}
    이름들 = {f"{누구.get('provider')}:{누구.get('provider_uid')}".lower()}
    if 누구.get("provider") != "password" and 누구.get("email"):
        이름들.add(str(누구["email"]).lower())
    return bool(허용 & 이름들)


def _demo_group(kind: str) -> str:
    return next(g for g, ks in DEMO_KINDS.items() if kind in ks)


def demo_left(user_id: int, 한도: dict | None = None) -> dict:
    """오늘 남은 횟수 {루틴, 구간, 사진} — 시연 기간(DEMO_LIMITS) 또는 구독(SUB_LIMITS)."""
    한도 = 한도 or DEMO_LIMITS
    return {g: max(0, 한도[g] - billing.ai_uses_today(user_id, ks)) for g, ks in DEMO_KINDS.items()}


def subscribed(누구: dict | None) -> dict | None:
    """살아 있는 구독. 없으면 None."""
    return billing.active_addon(누구["id"], "구독") if 누구 else None


def ai_allow(누구: dict | None, ip: str, kind: str) -> tuple[bool, str | None, int]:
    """(되는지, 안 되면 사용자에게 보일 한 줄, 실결제면 받을 값).

    kind: 루틴 · 조정 · 구간 · 시간표사진 · 건강사진.
    """
    if not 누구:
        return False, "로그인 후 이용할 수 있어요.", 0
    if is_admin(누구):
        return True, None, 0
    if billing_mode() == "demo" and billing.ai_uses_today_ip(ip) >= DEMO_IP_LIMIT:
        return False, "이곳에서 오늘 쓸 수 있는 AI 횟수를 다 썼어요. 내일 다시 쓸 수 있어요.", 0
    if subscribed(누구):                                          # 구독 — 값 없이 하루 횟수
        묶음 = _demo_group(kind)
        if demo_left(누구["id"], SUB_LIMITS)[묶음] <= 0:
            return False, f"구독으로 오늘 쓸 수 있는 {SUB_LIMITS[묶음]}번을 다 썼어요 — 내일 다시 쓸 수 있어요.", 0
        return True, None, 0
    if billing_mode() == "demo":
        묶음 = _demo_group(kind)
        남음 = demo_left(누구["id"])[묶음]
        if 남음 <= 0:
            return False, f"시연 기간이라 무료예요. 오늘 {DEMO_LIMITS[묶음]}번을 다 썼어요 — 내일 다시 쓸 수 있어요.", 0
        return True, None, 0
    if kind in DETAIL_LIMITS:                                   # 구간 계획 · 시간표 사진은 '자세히 보기' 안에서
        상세 = billing.active_addon(누구["id"], "상세")
        if not 상세:
            return False, (f"'자세히 보기'({DETAIL_PRICE}원)를 추가하면 계절·시간대 계획과 시간표 사진 읽기를 "
                           f"{DETAIL_DAYS}일 동안 쓸 수 있어요."), 0
        if billing.ai_uses_since(누구["id"], kind, 상세["starts_at"]) >= DETAIL_LIMITS[kind]:
            return False, "이번 자세히 보기에서 쓸 수 있는 횟수를 다 썼어요.", 0
        return True, None, 0
    값 = PRICES[kind]
    if billing.balance(누구["id"]) < 값:
        return False, "이용권이 모자라요. 먼저 충전해 주세요.", 값
    return True, None, 값


def ai_settle(누구: dict, ip: str, kind: str, 값: int, memo: str) -> int:
    """AI 가 실제로 지었을 때만 부른다 — 값을 받고(실결제) 사용을 기록한다. 돌려주는 값은 잔액."""
    잔액 = billing.spend(누구["id"], 값, memo) if 값 > 0 else billing.balance(누구["id"])
    billing.note_ai_use(누구["id"], ip, kind, 값, air.take_usage())
    return 잔액


JOB_WAIT_SEC = float(os.getenv("AI_JOB_WAIT_SEC", "20"))   # 루틴 작업을 걸고 요청 안에서 이만큼만 기다려 본다 —
                                                             # 그 안에 끝나면(가짜 SDK · 빠른 응답) 예전처럼 결과를 바로 준다


class _ai_turn:
    """with _ai_turn(user_id): — 같은 사람이 이미 AI 를 부르는 중이면 429.

    루틴 작업은 요청이 잡고(__enter__) 백그라운드 스레드가 끝날 때 놓는다(release) — 짓는 동안 한 번 더 누르면 429."""

    def __init__(self, user_id: int | None):
        self.user_id = user_id

    def __enter__(self):
        if self.user_id is None:
            return self
        with _ai_inflight_lock:
            if self.user_id in _ai_inflight:
                raise HTTPException(429, "AI 가 아직 짓는 중이에요. 잠시만 기다려 주세요.")
            _ai_inflight.add(self.user_id)
        return self

    def __exit__(self, *exc):
        self.release()
        return False

    def release(self):
        if self.user_id is not None:
            with _ai_inflight_lock:
                _ai_inflight.discard(self.user_id)


def ai_status_for(누구: dict | None) -> dict:
    """화면이 버튼과 문구를 정하는 데 쓰는 것 — 값표 · 시연 여부 · 오늘 남은 횟수 · 자세히 보기 · 잔액."""
    시연 = billing_mode() == "demo"
    상세 = billing.active_addon(누구["id"], "상세") if 누구 else None
    구독 = subscribed(누구)
    if 누구 and is_admin(누구):
        오늘남음 = None
    elif 구독:
        오늘남음 = demo_left(누구["id"], SUB_LIMITS)
    elif 누구 and 시연:
        오늘남음 = demo_left(누구["id"])
    else:
        오늘남음 = None
    return {"값": AI_PRICE, "값표": PRICES, "시연": 시연, "관리자": is_admin(누구),
            "오늘남음": 오늘남음,
            "시연하루": DEMO_LIMITS if 시연 else None,       # 손님(비로그인)에게 '로그인하면 하루 몇 회' 를 보여 주려고
            "자세히": {"까지": 상세["ends_at"]} if 상세 else None,
            "구독": {"까지": 구독["ends_at"], "하루": SUB_LIMITS} if 구독 else None,
            "구독값": SUB_PRICE, "구독일수": SUB_DAYS,
            "잔액": billing.balance(누구["id"]) if 누구 else 0,
            "로그인": bool(누구),
            # 짓는 중이거나 아직 안 가져간 루틴 작업 — 새로고침해도 화면이 이어서 기다리거나 가져간다
            "작업": billing.job_pending(누구["id"]) if 누구 else None,
            "예상초": billing.job_typical_sec("루틴")}


@app.get("/recommend/ai-status")
def get_ai_status(quadriga_session: str | None = Cookie(None)) -> dict:
    """AI 를 쓸 수 있는지, 이용권이 얼마나 남았는지. 값은 들지 않는다.

    예전에는 이 정보가 추천 응답에만 실려 있었다. 그래서 화면이 AI 를 쓸 수
    있는지 알려면 추천을 한 번 받아야 했고, 받아 둔 추천이 있어 그 호출을
    건너뛰면 **영영 알 수 없었다** — AI 방식 버튼이 '확인하는 중…' 인 채로
    잠겨 있었다. 루틴 점수를 매기지 않으니 가볍다.
    """
    누구 = auth.user_for_token(quadriga_session)
    return {"ai가능": air.available(), "이유": air.why_unavailable(), **ai_status_for(누구)}


@app.post("/ai/detail")
def post_ai_detail(quadriga_session: str | None = Cookie(None)) -> dict:
    """'자세히 보기' 를 산다 — 이용권에서 DETAIL_PRICE 를 빼고 DETAIL_DAYS 동안 구간 계획 · 시간표 사진을 연다.

    시연 기간에는 살 필요가 없다(하루 횟수로 무료) — 그때는 사지 않게 400.
    """
    누구 = _require_user(quadriga_session)
    if billing_mode() == "demo" or is_admin(누구) or subscribed(누구):
        raise HTTPException(400, "지금은 자세히 보기가 무료예요. 따로 살 필요가 없어요.")
    잔액 = billing.spend(누구["id"], DETAIL_PRICE, "자세히 보기 (구간 계획 · 시간표 사진)")
    상세 = billing.add_addon(누구["id"], "상세", DETAIL_DAYS, memo=f"{DETAIL_PRICE}원")
    return {"자세히": {"까지": 상세["까지"]}, "잔액": 잔액}


class DemoResetIn(BaseModel):
    확인: str = Field(..., description="'시연 이용권을 모두 지웁니다' 를 그대로 적어야 한다")


@app.post("/admin/reset-demo-credits")
def post_reset_demo_credits(body: DemoResetIn, quadriga_session: str | None = Cookie(None)) -> dict:
    """실결제로 바꾸는 날 관리자가 한 번 부른다 — 시연 결제로 얻은 이용권 · 구독 · 자세히 보기를 모두 지운다 (약관 6조의2).

    Render 무료 요금제에는 셸이 없어 관리자 화면(프로필)의 버튼으로 부른다. 실결제 모드가 아니면 거절한다 —
    시연 중에 눌러 버리면 시연 결제로 채운 이용권이 사라진다.
    """
    누구 = _require_user(quadriga_session)
    if not is_admin(누구):
        raise HTTPException(403, "관리자만 할 수 있어요.")
    if body.확인 != "시연 이용권을 모두 지웁니다":
        raise HTTPException(400, "확인 문구가 다릅니다.")
    if billing_mode() != "real":
        raise HTTPException(409, "아직 시연 모드예요. Render 의 KAKAOPAY_CID 를 실제 가맹점 코드로 바꾼 뒤에 누르세요.")
    결과 = billing.reset_demo_credits()
    print(f"[admin] 시연 이용권 정리 by {누구.get('email') or 누구.get('provider_uid')}: {결과}", flush=True)
    return 결과


@app.get("/ai/usage")
def get_ai_usage(days: int = Query(30, ge=1, le=365), quadriga_session: str | None = Cookie(None)) -> dict:
    """관리자용 원가 표 — 최근 며칠의 호출 수 · 토큰 합 · 받은 값. ADMIN_USERS 에 적힌 계정만."""
    누구 = _require_user(quadriga_session)
    if not is_admin(누구):
        raise HTTPException(403, "관리자만 볼 수 있어요.")
    return {"일수": days, "종류별": billing.ai_cost_summary(days), "값표": PRICES, "시연": billing_mode() == "demo"}


class RecommendIn(BaseModel):
    """일정까지 함께 보낼 때 쓴다.

    GET 은 쿼리 문자열이라 요일별 시간표를 실을 수 없다. 그래서 같은 추천을
    POST 로도 받는다. 추천 내용은 GET 과 다르지 않다 — 아래 ``_recommend``
    하나를 같이 쓴다.
    """
    age_gbn: ProgramAge
    weak: list[str] = Field(default_factory=list, max_length=10)
    style_purpose: str | None = None
    purpose: str | None = Field(None, description="사용자가 고른 운동 단계(목적) — 권장 용량을 여기에 맞춘다")
    sports: list[str] = Field(default_factory=list, max_length=100)
    areas: list[str] = Field(default_factory=list, max_length=10,
                             description="다이어트에서 고른 관리 부위(팔 · 뱃살 …). 그 부위를 쓰는 동작이 든 루틴을 앞에 세운다")
    target_gap: float | None = None
    limit: int = Field(12, ge=1, le=80)
    week: int = Field(1, ge=1, le=13)
    ai: bool = True
    real_age: float | None = Field(None, ge=5, le=110)
    바쁜시간: dict[str, list[dict]] = Field(default_factory=dict,
                                        description="{요일: [{시작, 끝}, ...]} — 적은 사람만")
    상태: str | list[str] | None = Field(
        None, description="하루의 모습. 여럿 고를 수 있다 — 대학생이면서 알바생인 사람이 흔하다")
    # AI 가 '이 사람' 을 읽는 데 쓰는 것. 무료 추천은 보지 않는다.
    항목별: dict[str, float] = Field(default_factory=dict,
                                   description="마지막 측정의 항목별 환산나이")
    체력나이: float | None = Field(None, ge=5, le=110)
    최근기록: list[dict] = Field(default_factory=list, max_length=30,
                              description="[{date, 이름, 값}] 최근 2주. 화면이 추린다")
    건강상태: list[str] = Field(default_factory=list, max_length=20,
                             description="사용자가 적어 둔 건강 상태. AI 가 해로운 동작을 뺀다")
    시작일: str | None = Field(None, description="루틴을 시작할 날 (YYYY-MM-DD). 그날의 계절·날씨에 맞춘다")
    위도: float | None = Field(None, ge=-90, le=90)
    경도: float | None = Field(None, ge=-180, le=180)
    # 받아 둔 AI 루틴을 바탕으로 방향만 바꿔 다시 짓는다. '다시 받기' 대신 이 둘 중 하나를 고른다.
    조정: Literal["더 쉽게", "더 어렵게"] | None = Field(None, description="이전 루틴보다 더 쉽게/더 어렵게 다시 짓는다")
    예산: int | None = Field(None, ge=0, le=3, description="운동 스타일 테스트의 예산 답 (0 거의 없음 … 3 부담 없음). AI 가 시설·강습 종목을 넣을지 정할 때")
    이전루틴: dict | None = Field(None, description="조정의 바탕 {루틴명, 강도, steps: [{동작, 단계, 수행량}]}")


@app.get("/recommend/routines")
def get_recommend_routines(
    age_gbn: ProgramAge,
    weak: str | None = Query(None, description="쉼표 구분. 체력나이에서 뒤처지는 요인"),
    style_purpose: str | None = Query(None, description="운동 스타일 테스트가 고른 목적"),
    purpose: str | None = Query(None, description="사용자가 고른 운동 단계(목적) — 권장 용량을 여기에 맞춘다"),
    sports: str | None = Query(None, description="쉼표 구분한 종목 id"),
    areas: str | None = Query(None, description="쉼표 구분. 다이어트에서 고른 관리 부위 (팔 · 뱃살 · 옆구리 · 등 · 엉덩이 · 허벅지 · 종아리)"),
    target_gap: float | None = Query(None, description="목표 체력나이까지 남은 세"),
    limit: int = Query(12, ge=1, le=80, description="난이도를 오갈 수 있게 넉넉히 준다. 80이면 전부다 (목적 8 × 10)"),
    week: int = Query(1, ge=1, le=13, description="프로그램 주차 — 수행량 계산용"),
    ai: bool = Query(False, description="예전 화면 호환용 — GET 은 값이 드는 AI 를 부르지 않는다. AI 는 POST 로만"),
    quadriga_session: str | None = Cookie(None),
    real_age: float | None = Query(None),
) -> dict:
    """사용자 데이터로 200개 KSPO 루틴에 점수를 매겨 순위를 낸다.

    루틴을 새로 만들지 않는다. 이미 있는 것 중에서 고르고 왜 골랐는지를 함께 낸다.
    아무 정보가 없어도 안전한 기본 순위를 돌려준다.

    **GET 은 AI 를 부르지 않는다.** 값이 드는 일을 주소 하나로 시킬 수 있으면 남이 만든 링크를 여는 것만으로
    이용권이 빠진다(로그인 쿠키가 실려 가는 최상위 이동). AI 는 POST 로만 — 화면도 늘 POST 로 부른다.
    """
    return _recommend(
        age_gbn=age_gbn,
        weak=[w.strip() for w in (weak or "").split(",") if w.strip()],
        style_purpose=style_purpose, purpose=purpose,
        sports=[s.strip() for s in (sports or "").split(",") if s.strip()],
        areas=[a.strip() for a in (areas or "").split(",") if a.strip()],
        target_gap=target_gap, limit=limit, week=week, ai=False,
        real_age=real_age, token=quadriga_session)


@app.post("/recommend/routines")
def post_recommend_routines(body: RecommendIn, request: Request,
                            quadriga_session: str | None = Cookie(None)) -> dict:
    """GET 과 같은 추천에 일정을 얹는다.

    일정은 선택 사항이다. 적어 보내면 비는 칸을 함께 계산하고, AI 를 쓸 때는
    그 칸에서 무엇을 할지까지 고른다. 안 보내면 GET 과 결과가 같다.
    """
    return _recommend(
        age_gbn=body.age_gbn, weak=body.weak, style_purpose=body.style_purpose,
        purpose=body.purpose, sports=body.sports, areas=body.areas, target_gap=body.target_gap, limit=body.limit,
        week=body.week, ai=body.ai, real_age=body.real_age,
        token=quadriga_session, busy=_short_busy(body.바쁜시간),
        life_kind=_life_kinds(body.상태),
        profile={"항목별": _short_numbers(body.항목별), "체력나이": body.체력나이,
                 "최근기록": _short_records(body.최근기록),
                 "건강상태": _short_list(body.건강상태),
                 "시작": ssn.start_info(body.시작일, body.위도, body.경도),
                 "예산": st.BUDGET_NAMES[body.예산] if body.예산 is not None else None},
        adjust=body.조정, previous=_previous_routine(body.이전루틴) if body.조정 else None,
        method="POST", ip=client_ip(request))


def _recommend(*, age_gbn: str, weak: list[str], style_purpose: str | None,
               sports: list[str], target_gap: float | None, limit: int,
               week: int, ai: bool, real_age: float | None,
               token: str | None, busy: dict | None = None,
               method: str = "GET",
               life_kind: list[str] | str | None = None,
               profile: dict | None = None,
               adjust: str | None = None, previous: dict | None = None,
               purpose: str | None = None, areas: list[str] | None = None,
               ip: str = "?") -> dict:
    """GET·POST 가 함께 쓰는 본체. 두 군데서 따로 굴면 화면이 갈린다.

    method 는 부른 쪽의 HTTP 메서드 — 요청 제한이 경로마다 달라서, 값을 받기 전에 아직 안 끊겼는지 볼 때 쓴다.

    purpose 는 사용자가 고른 운동 단계 — 무료 추천은 그 목적의 루틴 안에서만 고르고,
    AI 는 권장 용량(backend/dose.py)을 거기에 맞춘다.

    adjust 는 '더 쉽게'·'더 어렵게' — previous(받아 둔 AI 루틴)를 바탕으로 그 방향으로만 다시 짓는다.

    profile 은 AI 가 '이 사람' 을 읽는 재료(항목별 체력나이·최근 기록).
    무료 추천은 보지 않는다 — 점수 규칙은 그대로다.
    """
    시작 = time.monotonic()
    if real_age is not None:
        try:
            age_gbn = rt.age_group(real_age)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
    parts = list(weak)
    picked = list(sports)
    try:
        out = rc.for_user(age_gbn, weak=parts, style_purpose=style_purpose,
                          sports=picked, target_gap=target_gap, limit=limit, week=week, areas=areas,
                          purpose=purpose)
    except (KeyError, FileNotFoundError) as e:
        raise HTTPException(404, str(e))

    # AI 가 붙어 있으면 같은 후보 안에서 순서와 설명만 다듬는다.
    # 실패하면 점수 결과를 그대로 쓴다 — 화면이 비지 않는다.
    out["출처"] = "점수"
    out["ai가능"] = air.available()
    # 왜 못 쓰는지도 함께. 화면이 "지금 쓸 수 없어요" 만 띄우면 손쓸 방법이 없다.
    out["ai이유"] = air.why_unavailable()

    # 이용권 차감은 서버에서 한다. 화면에서 빼면 브라우저에서 숫자만 바꿔
    # 공짜로 무제한 쓸 수 있다.
    누구 = auth.user_for_token(token)
    out["잔액"] = billing.balance(누구["id"]) if 누구 else 0
    # 일정을 줬으면 비는 칸도 함께 계산해 둔다. AI 가 그 칸에서 무엇을
    # 할지 고르고, AI 를 안 써도 화면이 그대로 쓸 수 있다.
    일정 = None
    바쁜 = {k: v for k, v in (busy or {}).items() if k in spare.WEEKDAYS}
    if 바쁜:
        일정 = {"상태": life_kind,
              "요일별": spare.plan(바쁜, sports_ids=picked,
                                weak=parts, limit=3)}
        out["짬시간"] = 일정["요일별"]

    if ai and out["ai가능"]:
        종류 = "조정" if adjust else "루틴"
        됨, 안내, 값 = ai_allow(누구, ip, 종류)
        if not 됨:
            out["안내"] = "AI 추천은 로그인 후 이용할 수 있어요." if not 누구 else 안내
        else:
            # 무료 추천은 점수 순이라 맞춤이 아니다. AI 는 이 사람의 데이터를
            # 전부 읽고 루틴 하나를 직접 짓는다 — 검증된 재료(공식 동작·고른
            # 종목·기록 종목) 안에서만. 응답의 코드·id 는 서버가 대조한다.
            참고 = out.get("참고") or {}
            사용자 = {
                "연령대": age_gbn,
                "실제 나이": real_age,
                "체력나이": (profile or {}).get("체력나이"),
                "항목별 체력나이": (profile or {}).get("항목별") or {},
                "뒤처지는 체력요인": parts,
                "고른 종목": 참고.get("고른종목") or [],
                "고른 종목이 쓰는 요인": 참고.get("종목요인") or [],
                "조심할 부위": out.get("조심할부위") or [],
                "운동 스타일 테스트가 고른 목적": style_purpose,
                "고른 운동 단계": purpose,
                "고른 운동 단계가 다루는 요인": (rt.load()["config"]["purpose_factors"].get(purpose) or []) if purpose else [],
                "관리하고 싶은 부위": 참고.get("관리부위") or [],
                "목표 체력나이까지 남은 세": target_gap,
                "프로그램 주차": week,
                "강도": out.get("강도"),
                "하루의 모습": life_kind or [],
                "최근 기록": ((profile or {}).get("최근기록") or [])[:30],
                "건강 상태": (profile or {}).get("건강상태") or [],
                "시작": (profile or {}).get("시작"),   # {시작일, 계절, 날씨(예보)} 또는 None
                "운동 예산": (profile or {}).get("예산"),   # "거의 없음" … "부담 없음" 또는 None
            }
            if adjust:
                사용자["조정"] = {"방향": adjust, "이전 루틴": previous or {}}
            # 여기서부터는 요청과 떼어 놓는다 — 사용자가 '받겠다' 고 한 뒤에는 화면을 옮기거나 새로고침해도,
            # 요청이 끊겨도 끝까지 짓고 값을 받고 결과를 작업 표에 둔다(예현 2026-09-23). 요청은 잠깐만 기다려 본다.
            return _ai_job_begin(누구, ip, 종류, 값, 사용자, age_gbn, picked, 일정, out, adjust, profile)
    if 누구 and not is_admin(누구) and (subscribed(누구) or billing_mode() == "demo"):
        out["오늘남음"] = demo_left(누구["id"], SUB_LIMITS if subscribed(누구) else None)
    return out


def _with_today_left(out: dict, 누구: dict) -> dict:
    if not is_admin(누구) and (subscribed(누구) or billing_mode() == "demo"):
        out["오늘남음"] = demo_left(누구["id"], SUB_LIMITS if subscribed(누구) else None)
    return out


def _ai_job_begin(누구: dict, ip: str, 종류: str, 값: int, 사용자: dict, age_gbn: str, picked: list,
                  일정: dict | None, out: dict, adjust: str | None, profile: dict | None) -> dict:
    """루틴 작업을 걸고 JOB_WAIT_SEC 만 기다려 본다. 그 안에 끝나면 결과를 바로, 아니면 작업 번호를 준다."""
    turn = _ai_turn(누구["id"])
    turn.__enter__()                                                 # 이미 짓는 중이면 여기서 429
    try:
        job_id = billing.job_start(누구["id"], 종류)
        done = threading.Event()
        th = threading.Thread(target=_ai_job_run, name=f"ai-job-{job_id}", daemon=True,
                              args=(job_id, turn, done, 누구, ip, 종류, 값, 사용자, age_gbn, picked, 일정, dict(out), adjust, profile))
        th.start()
    except Exception:
        turn.release()
        raise
    done.wait(JOB_WAIT_SEC)
    job = billing.job_get(job_id, 누구["id"], mark_seen=True)
    if job and job["status"] == "done" and job["result"] is not None:
        return job["result"]
    if job and job["status"] == "failed":
        out["안내"] = job.get("error") or "AI 가 이번엔 못 지어서 무료 추천을 보여 드려요. 값은 받지 않았어요."
        return _with_today_left(out, 누구)
    시작 = int(job["created_at"]) if job else int(time.time())
    예상 = billing.job_typical_sec(종류)
    out["작업"] = {"id": job_id, "종류": 종류, "상태": "running", "시작": 시작, "예상초": 예상}
    out["안내"] = (f"AI 가 짓는 중이에요 — 보통 {int(round(예상))}초쯤 걸려요. 다른 화면을 봐도 되고, "
                 "끝나면 추천 화면에서 보여 드려요.")
    return _with_today_left(out, 누구)


def _ai_job_run(job_id: int, turn: "_ai_turn", done: threading.Event, 누구: dict, ip: str, 종류: str, 값: int,
                사용자: dict, age_gbn: str, picked: list, 일정: dict | None, out: dict,
                adjust: str | None, profile: dict | None) -> None:
    """백그라운드 스레드 — 끝까지 짓고, 실제로 지어졌을 때만 값을 받고, 결과(화면에 줄 응답 전체)를 작업 표에 둔다.

    폴백이면 한 푼도 안 쓴다 — 다만 원가는 나갔으니 '버림' 으로 기록한다. 토큰 기록(take_usage)은 스레드 단위라
    compose 와 같은 스레드에서 읽어야 한다 — 그래서 값 받기도 여기서 한다.
    """
    result, error = None, None
    try:
        지음 = air.compose(사용자, age_gbn, 종목ids=picked, 일정=일정)
        if 지음 and 지음.get("루틴"):
            if (profile or {}).get("시작"):
                지음["루틴"]["시작"] = profile["시작"]
            out["추천"] = [지음["루틴"]]
            out["출처"] = "ai"
            if 지음.get("짬시간"):
                out["짬시간계획"] = 지음["짬시간"]
            out["잔액"] = ai_settle(누구, ip, 종류, 값,
                                  "AI 루틴 추천" if 종류 == "루틴" else f"AI 루틴 조정 ({adjust})")
        else:
            billing.note_ai_use(누구["id"], ip, f"{종류}·버림", 0, air.take_usage())
            out["안내"] = "AI 가 이번엔 못 지어서 무료 추천을 보여 드려요. 값은 받지 않았어요."
        result = _with_today_left(out, 누구)
    except Exception as e:                                           # 무엇이 잘못돼도 작업은 끝난 것으로 남긴다
        error = f"AI 추천을 만들다 문제가 생겼어요 ({type(e).__name__}). 값은 받지 않았어요."
        print(f"[ai-job] {job_id} failed: {type(e).__name__}: {e}", flush=True)
    finally:
        try:
            billing.job_finish(job_id, result, error)
        except Exception as e:
            print(f"[ai-job] {job_id} 기록 실패: {e}", flush=True)
        turn.release()
        done.set()


@app.get("/recommend/ai-job/{job_id}")
def get_ai_job(job_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    """내 루틴 작업 하나 — 짓는 중이면 지난 시간과 예상, 끝났으면 결과(추천 응답 전체). 가져가면 '봤다' 로 표시한다."""
    user = _require_user(quadriga_session)
    job = billing.job_get(job_id, user["id"], mark_seen=True)
    if not job:
        raise HTTPException(404, "그런 작업이 없어요.")
    return {"id": job_id, "종류": job["kind"], "상태": job["status"], "시작": int(job["created_at"]),
            "지난초": job["지난초"], "예상초": billing.job_typical_sec(job["kind"]),
            "결과": job["result"] if job["status"] == "done" else None,
            "오류": job.get("error") if job["status"] == "failed" else None}


def _previous_routine(루틴) -> dict:
    """조정의 바탕이 되는 루틴을 AI 가 읽을 만큼만 남긴다 — 이름·강도·줄(시간대·동작·단계·수행량). 화면이 보낸 것을 그대로 믿지 않는다."""
    if not isinstance(루틴, dict):
        return {}
    글 = lambda v, n: str(v).strip()[:n] if isinstance(v, (str, int, float)) else ""
    줄들 = []
    for s in (루틴.get("steps") or [])[:16]:
        if isinstance(s, dict) and 글(s.get("동작"), 40):
            줄 = {"동작": 글(s.get("동작"), 40), "단계": 글(s.get("단계"), 10), "수행량": 글(s.get("수행량"), 20)}
            if 글(s.get("시간대"), 4) in air.DAYPARTS:
                줄["시간대"] = 글(s.get("시간대"), 4)          # 시간대별로 지은 루틴은 그 나눔째로 조정한다
            줄들.append(줄)
    out = {"루틴명": 글(루틴.get("루틴명"), 40), "동작": 줄들}
    if isinstance(루틴.get("강도"), dict):
        out["강도"] = {k: v for k, v in 루틴["강도"].items() if isinstance(v, (int, float, str))}
    return out


def _short_records(값) -> list[dict]:
    """최근 기록 [{date, 이름, 값}] 을 프롬프트에 실을 만큼만 — 줄 30개, 칸마다 40자. 모르는 칸은 버린다."""
    out = []
    for x in (값 or [])[:30]:
        if isinstance(x, dict):
            줄 = {k: str(x[k]).strip()[:40] for k in ("date", "이름", "값") if isinstance(x.get(k), (str, int, float))}
            if 줄:
                out.append(줄)
    return out


def _short_numbers(값) -> dict:
    """항목별 체력나이 {이름: 숫자} — 이름 20자 · 숫자만 · 20개까지."""
    out = {}
    for k, v in (값 or {}).items():
        if isinstance(v, (int, float)) and isinstance(k, str) and len(out) < 20:
            out[k.strip()[:20]] = round(float(v), 1)
    return out


def _short_busy(값) -> dict:
    """바쁜 시간 {요일: [{시작, 끝}]} — 요일은 아는 것만, 하루 20칸까지, 시각은 8자까지."""
    out = {}
    for 요일, 목록 in (값 or {}).items():
        if 요일 in spare.WEEKDAYS and isinstance(목록, list):
            out[요일] = [{k: str(c.get(k, ""))[:8] for k in ("시작", "끝")} for c in 목록[:20] if isinstance(c, dict)]
    return out


def _short_list(값) -> list[str]:
    """건강 상태처럼 사용자가 적은 짧은 낱말 목록을 다듬는다. 길면 자르고 겹치면 뺀다."""
    out = []
    for x in (값 or []):
        if not isinstance(x, (str, int, float)):
            continue
        한줄 = str(x).strip()[:20]
        if 한줄 and 한줄 not in out:
            out.append(한줄)
    return out[:20]


class HealthPhotoIn(BaseModel):
    """약봉지·처방전 사진 한 장. 저장하지 않는다 — 읽은 후보만 돌려준다."""
    사진: str = Field(..., max_length=7_000_000)
    미디어형: str | None = None


@app.post("/health/photo")
def post_health_photo(body: HealthPhotoIn, request: Request,
                      quadriga_session: str | None = Cookie(None)) -> dict:
    """약봉지·처방전 사진에서 건강 상태 **후보**를 읽는다 (HEALTH_PHOTO_PRICE — 글로 직접 적는 건 무료다).

    읽은 것을 저장하지 않는다. 화면이 사용자에게 보여 주고, 고쳐서 저장할지는
    사용자가 정한다. 사진도 남기지 않는다. 로그인은 있어야 한다.
    값은 읽고 나서 받는다 — 못 읽으면 한 푼도 안 받는다. 사진이 약봉지가 아니어도(빈 목록) 읽은 건 읽은 것이라 받는다.
    """
    시작 = time.monotonic()
    if not air.available():
        raise HTTPException(503, air.why_unavailable() or "지금 쓸 수 없어요.")
    누구 = _require_user(quadriga_session)
    ip = client_ip(request)
    됨, 안내, 값 = ai_allow(누구, ip, "건강사진")
    if not 됨:
        raise HTTPException(402 if 값 else 429, 안내)
    데이터, 형식 = _split_data_url(body.사진, body.미디어형)
    if 형식 not in air.PHOTO_TYPES:
        raise HTTPException(415, "JPG · PNG · WEBP · GIF 사진만 읽을 수 있어요.")
    if len(데이터) * 3 // 4 > air.PHOTO_MAX_BYTES:
        raise HTTPException(413, "사진이 너무 커요. 4MB 아래로 줄여주세요.")
    with _ai_turn(누구["id"]):
        읽은것 = air.read_health_photo(데이터, 형식)
    if 읽은것 is None:
        raise HTTPException(503, "사진을 못 읽었어요. 잠시 뒤 다시 시도해주세요.")
    if not 아직_받을_수_있다(시작, "POST", "/health/photo"):
        raise HTTPException(503, "처리가 너무 오래 걸려 멈췄어요. 잠시 뒤 다시 시도해주세요.")
    if not 읽은것["건강상태"]:
        읽은것["안내"] = "사진에서 건강 상태를 찾지 못했어요. 직접 골라주세요."
    읽은것["잔액"] = ai_settle(누구, ip, "건강사진", 값, "약봉지 사진 읽기")
    if not is_admin(누구) and (subscribed(누구) or billing_mode() == "demo"):
        읽은것["오늘남음"] = demo_left(누구["id"], SUB_LIMITS if subscribed(누구) else None)
    return 읽은것


class SchedulePhotoIn(BaseModel):
    """시간표 사진 한 장. data URL 그대로 받는다 — 화면이 FileReader 로 읽은 모양."""
    사진: str = Field(..., max_length=7_000_000,
                    description="data:image/...;base64,... 또는 base64 그 자체")
    미디어형: str | None = Field(None, description="사진에 형식이 안 붙어 있을 때만")


@app.post("/schedule/photo")
def post_schedule_photo(body: SchedulePhotoIn, request: Request,
                        quadriga_session: str | None = Cookie(None)) -> dict:
    """시간표 사진에서 요일별 바쁜 시간을 읽는다 — '자세히 보기' 안에서(시연 기간에는 하루 횟수).

    읽은 것을 곧바로 저장하지 않는다. 화면이 사용자에게 보여 주고 고치게
    한다 — 사진을 잘못 읽었는데 그대로 저장되면 손댈 곳이 없다.
    """
    시작 = time.monotonic()
    if not air.available():
        raise HTTPException(503, air.why_unavailable() or "지금 쓸 수 없어요.")
    누구 = _require_user(quadriga_session)
    ip = client_ip(request)
    됨, 안내, 값 = ai_allow(누구, ip, "시간표사진")
    if not 됨:
        raise HTTPException(402 if billing_mode() == "real" else 429, 안내)

    데이터, 형식 = _split_data_url(body.사진, body.미디어형)
    if 형식 not in air.PHOTO_TYPES:
        raise HTTPException(415, "JPG · PNG · WEBP · GIF 사진만 읽을 수 있어요.")
    # base64 는 원본보다 4/3 크다. 부르기 전에 막는다 — 부르고 나서 실패하면
    # 우리만 값을 치른다.
    if len(데이터) * 3 // 4 > air.PHOTO_MAX_BYTES:
        raise HTTPException(413, "사진이 너무 커요. 4MB 아래로 줄여주세요.")

    with _ai_turn(누구["id"]):
        읽은것 = air.read_schedule_photo(데이터, 형식)
    if 읽은것 is None:
        raise HTTPException(503, "사진을 못 읽었어요. 잠시 뒤 다시 시도해주세요.")
    if not 아직_받을_수_있다(시작, "POST", "/schedule/photo"):
        # 읽는 동안 요청이 끊겼다 — 화면에는 이미 실패가 나갔으니 값을 받지 않는다.
        raise HTTPException(503, "처리가 너무 오래 걸려 멈췄어요. 잠시 뒤 다시 시도해주세요.")
    잔액 = ai_settle(누구, ip, "시간표사진", 값, "시간표 사진 읽기")
    out = {"바쁜시간": 읽은것 or {}, "잔액": 잔액}
    if not 읽은것:
        # 부르긴 했지만 시간표가 아니었다. 횟수는 세되 왜 비었는지는 알려준다.
        out["안내"] = "사진에서 시간표를 찾지 못했어요. 직접 적어주세요."
    if not is_admin(누구) and (subscribed(누구) or billing_mode() == "demo"):
        out["오늘남음"] = demo_left(누구["id"], SUB_LIMITS if subscribed(누구) else None)
    return out


def _split_data_url(값: str, 기본형: str | None) -> tuple[str, str | None]:
    """data URL 이면 형식과 알맹이로 가른다. 그냥 base64 면 기본형을 쓴다."""
    값 = (값 or "").strip()
    if 값.startswith("data:") and "," in 값:
        머리, _, 몸 = 값.partition(",")
        형식 = 머리[5:].split(";")[0].strip().lower()
        return 몸, (형식 or 기본형)
    return 값, (기본형 or "").strip().lower() or None


def _life_kinds(값) -> list[str]:
    """하루의 모습을 목록 하나로 다듬는다.

    예전에는 하나만 골랐다(문자열). 그때 저장해 둔 것도 그대로 읽힌다.
    직접 적은 것이 섞여 오므로 길이를 자른다 — 프롬프트에 긴 글이 통째로
    실리면 안 된다.
    """
    if 값 is None:
        값 = []
    elif isinstance(값, str):
        값 = [값]
    elif not isinstance(값, list):
        return []
    out = []
    for x in 값:
        if not isinstance(x, (str, int, float)):
            continue
        한줄 = str(x).strip()[:20]
        if 한줄 and 한줄 not in out:
            out.append(한줄)
    return out[:6]


class SeasonIn(BaseModel):
    """고른 루틴 하나를 1년 동안 어떻게 이어갈지 물을 때."""
    age_gbn: ProgramAge
    루틴: dict = Field(..., description="추천에서 고른 그 루틴 (목적·루틴명·체력요인 …)")
    약점: list[str] = Field(default_factory=list, max_length=10)
    고른종목: list[str] = Field(default_factory=list, max_length=100)
    조심할부위: list[str] = Field(default_factory=list, max_length=20)
    상태: str | list[str] | None = Field(
        None, description="하루의 모습. 여럿 고를 수 있다")
    바쁜시간: dict[str, list[dict]] = Field(default_factory=dict,
                                        description="시간대별로 볼 때 비는 시간을 알려면")
    건강상태: list[str] = Field(default_factory=list, max_length=20)
    시작일: str | None = Field(None, description="계절별로 볼 때 첫 계절은 이 날의 계절이다")
    위도: float | None = Field(None, ge=-90, le=90)
    경도: float | None = Field(None, ge=-180, le=180)


class PeriodIn(SeasonIn):
    축: Literal["계절", "시간대"] = "계절"
    시간대포함: bool = Field(False, description="계절 안에 아침·낮·저녁·밤을 함께 (계절 축일 때만)")


def _periods(body: "SeasonIn", 축: str, token: str | None, 시간대포함: bool = False, ip: str = "?") -> dict:
    """'이 루틴 자세히 알아보기' — 구간(계절 | 시간대)마다 어떻게 이어갈지.

    '자세히 보기'(DETAIL_PRICE, DETAIL_DAYS 일) 안에서 쓴다 — 원가가 루틴 짓기에 맞먹는 호출이라 공짜로 둘 수 없었다.
    시연 기간에는 하루 횟수로 무료다. 로그인은 있어야 한다 — 남의 이름으로 AI 를 부를 수는 없다.

    루틴을 바꾸지 않는다. 이미 고른 루틴 하나를 구간에 맞게 어떻게 할지만
    쓴다. 네 구간이 다 나오지 않으면 버린다.
    """
    if not air.available():
        raise HTTPException(503, air.why_unavailable() or "지금 쓸 수 없어요.")
    누구 = _require_user(token)
    됨, 안내, 값 = ai_allow(누구, ip, "구간")
    if not 됨:
        raise HTTPException(402 if billing_mode() == "real" else 429, 안내)

    참고 = {"약점": body.약점, "고른종목": body.고른종목,
          "조심할부위": body.조심할부위, "건강상태": _short_list(body.건강상태)}
    # 계절은 시작일의 계절부터 한 바퀴다. 봄에 받았다고 봄부터가 아니다.
    시작 = ssn.start_info(body.시작일, body.위도, body.경도)
    구간들 = None
    if 시작:
        참고["시작"] = 시작
        if 축 == "계절":
            구간들 = ssn.order_from(시작["계절"])
    일정 = None
    바쁜 = {k: v for k, v in (body.바쁜시간 or {}).items() if k in spare.WEEKDAYS}
    if 바쁜:
        일정 = {"요일별": spare.plan(바쁜, sports_ids=body.고른종목, weak=body.약점, limit=3)}
    with _ai_turn(누구["id"]):
        구간 = air.periods(body.루틴, 참고, body.age_gbn, _life_kinds(body.상태), 축=축, 일정=일정,
                           구간들=구간들, 시간대포함=(시간대포함 and 축 == "계절"))
    if not 구간:
        billing.note_ai_use(누구["id"], ip, "구간·버림", 0, air.take_usage())
        이유 = air.why_last_fail("periods")
        raise HTTPException(503, f"지금은 {축}별 계획을 못 받았어요{' — ' + 이유 if 이유 else ''}. 잠시 뒤 다시 시도해주세요.")
    ai_settle(누구, ip, "구간", 값, f"{축}별 계획")
    out = {"축": 축, 축: 구간, "루틴명": body.루틴.get("루틴명")}
    if 시작:
        out["시작"] = 시작
    return out


@app.post("/recommend/periods")
def post_recommend_periods(body: PeriodIn, request: Request,
                           quadriga_session: str | None = Cookie(None)) -> dict:
    """구간을 골라 본다 — 계절별 또는 시간대별."""
    return _periods(body, body.축, quadriga_session, body.시간대포함, ip=client_ip(request))


@app.post("/recommend/seasons")
def post_recommend_seasons(body: SeasonIn, request: Request,
                           quadriga_session: str | None = Cookie(None)) -> dict:
    """계절 축. /recommend/periods 의 예전 주소다."""
    return _periods(body, "계절", quadriga_session, ip=client_ip(request))


# ---------- 11. 당일 기록 종목 ----------

class WeatherCheckIn(BaseModel):
    """오늘 루틴의 동작들. 밖에서 하는 것만 본다 — 출처(종목·기록)와 id 가 있어야 안다."""
    steps: list[dict] = Field(default_factory=list, max_length=20)
    위도: float | None = Field(None, ge=-90, le=90)
    경도: float | None = Field(None, ge=-180, le=180)


@app.post("/routine/weather-check")
def post_weather_check(body: WeatherCheckIn) -> dict:
    """오늘 날씨에 맞춘 대안 — 밖에서 하는 동작이 있으면 실내·비슷한 것으로 안내.

    AI 를 부르지 않는다. 규칙이다. 값이 들지 않고 로그인도 필요 없다 —
    오늘 날씨와 동작 이름뿐, 누구의 것인지 알 필요가 없다.
    루틴을 바꿔치기하지 않는다. 어떻게 할지는 사용자가 정한다.
    """
    return outdoor.check(body.steps, body.위도, body.경도)


class SpareTimeIn(BaseModel):
    """짬시간 계산에 필요한 것만. 일정은 저장하지 않는다 — 화면이 갖고 있다."""
    바쁜시간: dict[str, list[dict]] = Field(default_factory=dict,
                                        description="{요일: [{시작, 끝}, ...]}")
    sports: list[str] = Field(default_factory=list, max_length=100)
    weak: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(3, ge=1, le=10)


@app.post("/spare-time/plan")
def post_spare_plan(body: SpareTimeIn) -> dict:
    """요일별로 남는 칸과 거기서 할 것.

    적어 두지 않은 요일은 결과에도 없다. 하루가 통째로 빈다고 단정하면
    안 적은 사람에게 온종일 운동하라고 하는 셈이다.
    """
    바쁜 = {k: v for k, v in (body.바쁜시간 or {}).items() if k in spare.WEEKDAYS}
    return {"요일": list(spare.WEEKDAYS),
            "요일별": spare.plan(바쁜, sports_ids=body.sports,
                              weak=body.weak, limit=body.limit)}


@app.get("/workout-items")
def get_workout_items() -> dict:
    """당일 기록 작성 화면이 나열할 운동 종목. 화면이 그대로 그린다."""
    try:
        return wi.catalog()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


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
    # html=True 가 "/" 에 index.html 을 준다. 직접 만든 라우트로 주면 If-None-Match 를
    # 보지 않아 늘 200 이라, no-cache 와 만나면 매번 116KB 를 다시 받게 된다.
    # StaticFiles 는 ETag 로 304 를 낸다 — 안 바뀌었으면 한 줄로 끝난다.
    app.mount("/", StaticFiles(directory=paths.FRONTEND, html=True), name="frontend")
