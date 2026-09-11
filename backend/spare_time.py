"""짬시간 추천 — 비어 있는 시간에 무엇을 할지 고른다.

사용자가 적어 둔 일정(바쁜 시간)을 하루에서 빼면 남는 칸이 나온다. 그 칸의
길이에 맞는 활동을 고른다. 고른 종목을 되도록 그대로 넣고, 시간이 모자라면
비슷한 류나 그 종목이 쓰는 체력요인을 다루는 짧은 운동으로 바꾼다.

지키는 것
  - **새 활동을 만들지 않는다.** data 의 종목·운동 목록에서만 고른다.
  - **일정을 지어내지 않는다.** 안 적었으면 빈 칸도 없다고 본다.
  - 짧은 칸에 종목(러닝·수영 등)을 넣지 않는다. 오가고 준비하는 시간이 있다.
"""
from __future__ import annotations

try:                                     # 저장소 루트에서 실행할 때
    from backend import sports as sp, workout_items as wi
except ImportError:                      # backend/ 안에서 직접 실행할 때
    import sports as sp                  # noqa: E402
    import workout_items as wi           # noqa: E402

# 화면과 서버가 같은 순서를 쓴다
WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")

# 하루 중 추천을 붙이는 구간. 이 밖은 자는 시간으로 본다.
DAY_START = "07:00"
DAY_END = "22:00"

# 이보다 짧은 칸은 옮겨 다니다 끝난다 — 추천하지 않는다.
MIN_SLOT_MIN = 15
# 종목(러닝·수영 등)은 오가고 준비하는 시간이 있다. 이만큼은 있어야 넣는다.
SPORT_MIN_MIN = 45

# 칸 길이별로 어울리는 운동 분류. 짧을수록 옷을 갈아입지 않아도 되는 것.
BY_MINUTES = (
    (15, ("스트레칭", "균형·코어")),
    (30, ("스트레칭", "균형·코어", "맨몸 근력")),
    (45, ("맨몸 근력", "유산소", "균형·코어")),
    (10 ** 6, ("유산소", "맨몸 근력", "기구 근력")),
)


def _to_min(hhmm: str) -> int:
    """'09:30' → 570. 모양이 아니면 예외를 낸다."""
    시, 분 = str(hhmm).split(":")
    v = int(시) * 60 + int(분)
    if not (0 <= v <= 24 * 60):
        raise ValueError(hhmm)
    return v


def _to_hhmm(v: int) -> str:
    return f"{v // 60:02d}:{v % 60:02d}"


def free_slots(busy, *, day_start: str = DAY_START, day_end: str = DAY_END,
               min_minutes: int = MIN_SLOT_MIN) -> list[dict]:
    """바쁜 시간을 뺀 남는 칸.

    busy 는 [{"시작": "09:00", "끝": "18:00"}, ...]. 순서가 뒤죽박죽이거나
    서로 겹쳐도 된다 — 먼저 합쳐서 정리한다.
    """
    시작, 끝 = _to_min(day_start), _to_min(day_end)
    구간 = []
    for b in busy or []:
        try:
            a, z = _to_min(b["시작"]), _to_min(b["끝"])
        except (KeyError, ValueError, TypeError):
            continue                     # 모양이 틀린 줄은 조용히 건너뛴다
        if z > a:
            구간.append((max(a, 시작), min(z, 끝)))
    구간.sort()

    합침: list[list[int]] = []
    for a, z in 구간:
        if 합침 and a <= 합침[-1][1]:
            합침[-1][1] = max(합침[-1][1], z)
        else:
            합침.append([a, z])

    빈칸, 커서 = [], 시작
    for a, z in 합침 + [[끝, 끝]]:
        if a - 커서 >= min_minutes:
            빈칸.append({"시작": _to_hhmm(커서), "끝": _to_hhmm(a), "분": a - 커서})
        커서 = max(커서, z)
    return 빈칸


def _sport_pool(ids: list[str]) -> list[dict]:
    """고른 종목과, 같은 분류에 있는 이웃 종목."""
    고른것 = sp.resolve(ids or [])
    분류 = {s.get("분류") for s in 고른것}
    이웃 = [s for s in sp.catalog()["종목"]
           if s.get("분류") in 분류 and s not in 고른것]
    return list(고른것), 이웃


def _items_for(minutes: int) -> list[dict]:
    """그 길이에 어울리는 운동 종목."""
    분류들 = next(v for 한도, v in BY_MINUTES if minutes < 한도)
    return [x for x in wi.catalog()["종목"] if x.get("분류") in 분류들]


def suggest_for(minutes: int, *, sports_ids=None, weak=None, limit: int = 3) -> list[dict]:
    """그 칸에 할 것. 고른 종목 → 비슷한 류 → 그 요인을 다루는 운동 차례로 고른다."""
    고른것, 이웃 = _sport_pool(list(sports_ids or []))
    약점 = [w for w in (weak or []) if w]
    필요요인 = {f for s in 고른것 for f in (s.get("체력요인") or [])}

    나온것: list[dict] = []

    def 담기(이름, 갈래, 왜, 아이콘=None):
        if any(x["이름"] == 이름 for x in 나온것):
            return
        나온것.append({"이름": 이름, "갈래": 갈래, "왜": 왜, "아이콘": 아이콘})

    # 1) 시간이 넉넉하면 고른 종목을 그대로
    if minutes >= SPORT_MIN_MIN:
        for s in 고른것:
            담기(s["이름"], "종목", "골라 두신 종목이에요", s.get("아이콘"))
        for s in 이웃:
            담기(s["이름"], "비슷한 종목",
                f"고른 종목과 같은 갈래({s.get('분류')})예요", s.get("아이콘"))

    # 2) 짧으면(또는 자리가 남으면) 그 요인을 다루는 짧은 운동으로
    후보 = _items_for(minutes)
    맞는것 = [x for x in 후보 if x.get("요인") in 약점]
    이어지는것 = [x for x in 후보 if x.get("요인") in 필요요인 and x not in 맞는것]
    나머지 = [x for x in 후보 if x not in 맞는것 and x not in 이어지는것]

    for x in 맞는것:
        담기(x["이름"], x.get("분류") or "운동", f"뒤처지는 {x['요인']}을(를) 다뤄요")
    for x in 이어지는것:
        담기(x["이름"], x.get("분류") or "운동", f"고른 종목에 필요한 {x['요인']}을(를) 써요")
    for x in 나머지:
        담기(x["이름"], x.get("분류") or "운동", f"{minutes}분에 맞는 운동이에요")

    return 나온것[:max(1, limit)]


def plan(busy_by_day: dict, *, sports_ids=None, weak=None,
         limit: int = 3) -> dict:
    """요일별로 남는 칸과 거기서 할 것.

    적어 두지 않은 요일은 결과에도 없다 — 하루가 통째로 빈다고 단정하면
    안 적은 사람에게 온종일 운동하라고 하는 셈이다.
    """
    out = {}
    for 요일 in WEEKDAYS:
        if 요일 not in (busy_by_day or {}):
            continue
        칸들 = free_slots((busy_by_day or {}).get(요일) or [])
        out[요일] = [dict(c, 추천=suggest_for(c["분"], sports_ids=sports_ids,
                                            weak=weak, limit=limit))
                   for c in 칸들]
    return out
