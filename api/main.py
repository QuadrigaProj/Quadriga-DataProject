"""
체력나이 API 서버 — 담당 D

프론트(담당 C)와 영상 화면(담당 B)이 붙는 지점.
src/fitness_age.py, src/prescription.py 를 HTTP 로 감쌌다.

실행:
    pip install fastapi uvicorn
    uvicorn api.main:app --reload
문서:
    http://localhost:8000/docs
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import fitness_age as fa          # noqa: E402
from src import prescription as pr         # noqa: E402

app = FastAPI(
    title="체력나이 API",
    description="국민체력100 공공데이터 기반 체력나이 산출·운동 처방",
    version="0.1.0",
)

# 개발 중에는 프론트 로컬 서버를 허용한다. 배포 시 도메인으로 좁힐 것.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

AgeGroup = Literal["성인", "어르신", "청소년"]
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
               "python scripts/collect_measurements.py --sample 450 후 "
               "python src/build_distribution.py 를 실행하세요.",
    }


# ---------- 1. 체력나이 ----------

class MeasureIn(BaseModel):
    age_gbn: AgeGroup = Field(..., description="연령군")
    sex: Sex
    flexibility: float | None = Field(None, description="앉아윗몸앞으로굽히기 (cm). 음수 가능")
    strength: int | None = Field(None, description="교차윗몸일으키기(성인) 또는 의자앉았다일어서기(어르신) 회수")
    height_cm: float | None = Field(None, gt=0)
    weight_kg: float | None = Field(None, gt=0)
    bmi: float | None = Field(None, gt=0, description="직접 주거나 키·몸무게로 계산")


class MeasureOut(BaseModel):
    체력나이: float | None
    신뢰구간: float | None
    항목별: dict[str, float]
    약점: dict | None


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

    return MeasureOut(**result, 약점=fa.weakest_link(result))


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
    """3개월 재점검 — 변화량을 반환한다.

    예측이 아니라 두 실측값의 차이만 계산한다.
    """
    before = post_fitness_age(body.이전)
    after = post_fitness_age(body.현재)
    delta = round((after.체력나이 or 0) - (before.체력나이 or 0), 1)
    return {
        "이전": before.체력나이,
        "현재": after.체력나이,
        "변화": delta,
        "메시지": f"체력나이가 {abs(delta)}세 {'어려졌습니다' if delta < 0 else '늘었습니다'}"
                  if delta else "변화 없음",
        "항목별_이전": before.항목별,
        "항목별_현재": after.항목별,
    }
