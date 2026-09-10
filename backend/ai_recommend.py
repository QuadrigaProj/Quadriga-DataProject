"""AI 루틴 추천 — 그 사람의 데이터를 전부 읽고 Claude 가 루틴 하나를 직접 짓는다.

무료 추천(backend/recommend.py, 점수 순)은 맞춤이 아니다. AI 추천은 항목별
체력나이·고른 종목·최근 기록·일정·하루의 모습을 읽고 짠다. 다만 **재료는
검증된 것뿐**이다 — 국민체력100 공식 동작, 배우고 싶다고 고른 종목, 당일
기록에 적을 수 있는 운동. 영상이 있느냐는 조건이 아니다. 응답의 코드·id 를
재료 목록에 대조해 없는 줄은 버린다(이름을 지어낼 수 없다).

키가 없거나, SDK 가 없거나, 호출이 실패하거나, 응답 모양이 다르면 조용히
None 을 돌려준다. 부르는 쪽은 점수 결과를 그대로 쓰면 된다 — 화면은 어떤
경우에도 빈 채로 남지 않는다.

설정
    1. pip install -r requirements.txt   (anthropic 이 들어 있다)
    2. .env 에 ANTHROPIC_API_KEY=sk-ant-...
    3. 서버 재시작. 키가 없으면 지금까지와 똑같이 점수만으로 추천한다.
"""
from __future__ import annotations

import json
import os

MODEL = "claude-opus-5"
TIMEOUT_SEC = 20.0
MAX_TOKENS = 8000

def available() -> bool:
    """지금 AI 를 부를 수 있는지. 키와 SDK 가 모두 있어야 한다."""
    return why_unavailable() is None


def why_unavailable() -> str | None:
    """못 쓰는 까닭 한 줄. 쓸 수 있으면 None.

    "지금 쓸 수 없어요" 만 보여 주면 붙이는 사람이 무엇을 해야 할지 모른다.
    키 값은 절대 담지 않는다 — 있는지 없는지만 말한다.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        return "서버에 ANTHROPIC_API_KEY 가 없어요. 관리자가 넣으면 켜집니다."
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return "서버에 anthropic 패키지가 없어요. 관리자가 설치하면 켜집니다."
    return None


def _text(message) -> str:
    """응답에서 사람이 읽는 글자만 모은다 (thinking 블록은 건너뛴다)."""
    parts = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts).strip()


def _json_only(s: str) -> dict | None:
    """앞뒤에 군말이 붙어도 첫 JSON 덩어리만 꺼낸다."""
    if not s:
        return None
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(s[i:j + 1])
    except (ValueError, TypeError):
        return None
    return d if isinstance(d, dict) else None


def _clean_slots(고른것, 일정: dict | None) -> dict:
    """AI 가 고른 짬시간 계획에서, 실제로 있는 칸과 있는 이름만 남긴다.

    칸 번호가 없거나 그 칸에 못 넣는 것을 골랐으면 그 줄만 버린다.
    통째로 버리지 않는 까닭은, 한 줄이 틀렸다고 나머지 요일까지 잃을
    필요는 없어서다.
    """
    칸들 = (일정 or {}).get("요일별") or {}
    if not isinstance(고른것, dict) or not 칸들:
        return {}
    out = {}
    for 요일, 목록 in 고른것.items():
        원본 = 칸들.get(요일)
        if not 원본 or not isinstance(목록, list):
            continue
        줄 = []
        for x in 목록:
            if not isinstance(x, dict):
                continue
            try:
                i = int(x.get("칸"))
            except (TypeError, ValueError):
                continue
            if not (0 <= i < len(원본)):
                continue
            할것 = str(x.get("할것") or "").strip()
            있는것 = {y["이름"] for y in (원본[i].get("추천") or [])}
            if 할것 not in 있는것:
                continue                       # 그 칸에 없는 것을 골랐다 → 그 줄만 버린다
            c = 원본[i]
            줄.append({"시작": c["시작"], "끝": c["끝"], "분": c["분"],
                      "할것": 할것,
                      "한줄": str(x.get("한줄") or "").strip()[:80]})
        if 줄:
            out[요일] = 줄
    return out

# ---------- 계절별로 자세히 도전하기 ----------

SEASONS = ("봄", "여름", "가을", "겨울")

SEASON_SYSTEM = """당신은 국민체력100 데이터로 운동을 처방하는 서비스의 코치입니다.

사용자가 루틴 하나를 골라 "이 루틴으로 자세히 도전하기" 를 눌렀습니다.
그 루틴을 **1년 동안 어떻게 이어갈지** 계절마다 한 덩이씩 써 주세요.

지켜야 할 것
  - 루틴을 바꾸지 마세요. 같은 루틴을 계절에 맞게 **어떻게** 할지만 씁니다.
    (실내로 옮긴다, 준비운동을 늘린다, 물을 더 마신다, 횟수를 조금 올린다 …)
  - 하루의 모습(고등학생·직장인·알바생 등)이 있으면 그 사람 생활에 맞게 씁니다.
    시험 기간, 교대 근무, 방학처럼 그 사람에게 실제로 있는 일로요.
    **여럿이면 다 겹쳐 놓고 봅니다** — 대학생이면서 알바생이면 둘 다 맞아야 합니다.
  - 계절은 봄·여름·가을·겨울 네 개를 모두, 이 순서로 씁니다.
  - 측정하지 않은 값을 아는 척하지 마세요.
  - 한국어 존댓말. 한줄은 40자 안팎, 할것은 각 25자 안팎으로 셋까지.
  - 의학적 진단이나 치료를 말하지 마세요. 아프면 쉬라고 안내합니다.
  - 더위·추위로 위험할 수 있는 날은 무리하지 말라고 한마디 넣습니다.

JSON 만 출력하세요. 다른 말은 쓰지 마세요.
{"계절": [{"계절": "봄", "한줄": "문장", "할것": ["문장", ...], "조심": "문장"}, ...]}"""


def _season_prompt(루틴: dict, 참고: dict, 연령대: str, 상태) -> str:
    사용자 = {
        "연령대": 연령대,
        "하루의 모습": 상태,
        "뒤처지는 체력요인": 참고.get("약점") or [],
        "고른 종목": 참고.get("고른종목") or [],
        "조심할 부위": 참고.get("조심할부위") or [],
    }
    골른것 = {
        "목적": 루틴.get("목적"),
        "루틴명": 루틴.get("루틴명"),
        "동작수": 루틴.get("동작수"),
        "체력요인": (루틴.get("체력요인") or [])[:4],
        "난이도": 루틴.get("난이도"),
    }
    return ("사용자\n" + json.dumps(사용자, ensure_ascii=False, indent=1)
            + "\n\n고른 루틴\n" + json.dumps(골른것, ensure_ascii=False, indent=1))


def seasons(루틴: dict, 참고: dict, 연령대: str,
            상태: list[str] | str | None = None) -> list[dict] | None:
    """고른 루틴을 계절마다 어떻게 이어갈지. 못 하면 None.

    네 계절이 다 나오지 않으면 통째로 버린다. 봄·여름만 있는 1년 계획은
    받아 든 사람이 나머지를 알아서 채워야 해서, 없느니만 못하다.
    """
    if not 루틴 or not available():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(timeout=TIMEOUT_SEC, max_retries=1)
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SEASON_SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user",
                       "content": _season_prompt(루틴, 참고, 연령대, 상태)}],
        )
        if getattr(message, "stop_reason", None) == "refusal":
            return None
        d = _json_only(_text(message))
    except Exception:                          # 무엇이 잘못돼도 폴백
        return None

    if not d or not isinstance(d.get("계절"), list):
        return None
    본것, out = set(), []
    for x in d["계절"]:
        if not isinstance(x, dict):
            return None
        이름 = str(x.get("계절") or "").strip()
        if 이름 not in SEASONS or 이름 in 본것:
            return None                        # 없는 계절이거나 중복 → 지어낸 응답
        본것.add(이름)
        할것 = [str(y).strip()[:40] for y in (x.get("할것") or [])
              if isinstance(y, (str, int, float)) and str(y).strip()]
        out.append({"계절": 이름,
                    "한줄": str(x.get("한줄") or "").strip()[:80],
                    "할것": 할것[:3],
                    "조심": str(x.get("조심") or "").strip()[:80]})
    if 본것 != set(SEASONS):
        return None                            # 네 계절이 다 있어야 1년이 된다
    순서 = {이름: i for i, 이름 in enumerate(SEASONS)}
    out.sort(key=lambda x: 순서[x["계절"]])
    return out

# ---------- 사진으로 시간표 읽기 ----------

PHOTO_MAX_BYTES = 4 * 1024 * 1024          # 4MB. 그 이상은 부르기 전에 막는다
PHOTO_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")

PHOTO_SYSTEM = """당신은 사진 속 시간표를 읽어 주는 도우미입니다.

사진에 있는 **바쁜 시간**(수업·근무·학원·정해진 일정)만 요일별로 옮겨 적으세요.

지켜야 할 것
  - 사진에 **적혀 있는 것만** 옮깁니다. 안 보이는 칸을 채우지 마세요.
  - 요일은 월·화·수·목·금·토·일 만 씁니다. 없는 요일은 아예 빼세요.
  - 시각은 24시간 "HH:MM" 로 씁니다. 09:00 처럼 두 자리로요.
  - 끝나는 시각이 시작보다 빠르면 안 됩니다. 자정을 넘기는 칸은 빼세요.
  - 시간이 안 적혀 있거나 못 읽겠으면 그 칸은 빼세요. 짐작해서 넣지 마세요.
  - 사진이 시간표가 아니면 {"바쁜시간": {}} 만 내세요.

JSON 만 출력하세요. 다른 말은 쓰지 마세요.
{"바쁜시간": {"월": [{"시작": "09:00", "끝": "12:00"}, ...], ...}}"""


def _hhmm(v) -> str | None:
    """"9:5" 같은 것도 "09:05" 로. 시각이 아니면 None."""
    if not isinstance(v, str):
        return None
    부분 = v.strip().split(":")
    if len(부분) != 2:
        return None
    try:
        시, 분 = int(부분[0]), int(부분[1])
    except ValueError:
        return None
    if not (0 <= 시 <= 23 and 0 <= 분 <= 59):
        return None
    return f"{시:02d}:{분:02d}"


def read_schedule_photo(데이터: str, 미디어형: str) -> dict | None:
    """시간표 사진에서 요일별 바쁜 시간을 읽는다. 못 하면 None.

    ``데이터`` 는 base64 문자열이다. 읽어 낸 것은 그대로 쓰지 않고 한 번 더
    거른다 — 자정을 넘기거나 거꾸로 된 칸은 빈 시간을 엉뚱하게 만든다.
    사진이 시간표가 아니면 빈 dict 가 나온다(None 과 다르다. 부른 건 성공했다).
    """
    if not 데이터 or 미디어형 not in PHOTO_TYPES or not available():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(timeout=TIMEOUT_SEC * 2, max_retries=1)
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=PHOTO_SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": 미디어형,
                                             "data": 데이터}},
                {"type": "text", "text": "이 시간표에서 바쁜 시간을 옮겨 적어주세요."},
            ]}],
        )
        if getattr(message, "stop_reason", None) == "refusal":
            return None
        d = _json_only(_text(message))
    except Exception:                          # 무엇이 잘못돼도 폴백
        return None

    if not d or not isinstance(d.get("바쁜시간"), dict):
        return None
    요일들 = ("월", "화", "수", "목", "금", "토", "일")
    out = {}
    for 요일, 목록 in d["바쁜시간"].items():
        if 요일 not in 요일들 or not isinstance(목록, list):
            continue
        줄 = []
        for x in 목록:
            if not isinstance(x, dict):
                continue
            시작, 끝 = _hhmm(x.get("시작")), _hhmm(x.get("끝"))
            # 거꾸로 된 칸은 담지 않는다 — 빈 시간을 엉뚱하게 만든다
            if not 시작 or not 끝 or 시작 >= 끝:
                continue
            줄.append({"시작": 시작, "끝": 끝})
        if 줄:
            out[요일] = sorted(줄, key=lambda c: c["시작"])[:12]
    return out

# ---------- AI 가 검증된 재료로 직접 짓는다 ----------
#
# 무료 추천은 점수 순이라 맞춤이 아니다. AI 추천은 그 사람의 데이터를 전부
# 읽고 루틴 하나를 직접 짠다. 다만 **재료는 검증된 것뿐**이다 — 국민체력100
# 공식 동작, 배우고 싶다고 고른 종목, 당일 기록에 적을 수 있는 운동.
# 영상이 있느냐는 조건이 아니다. 고른 종목은 영상이 없지만 검증된 종목이다.
# 응답의 코드·id 를 재료 목록에 대조해 없는 줄은 버린다. 이름을 지어낼 수 없다.

PHASES = ("준비운동", "본운동", "정리운동")
PURPOSES = ("다이어트", "기초 체력 증진", "재활 및 기능 회복", "수험생 체력 증진", "유연성 강화")
COMPOSE_MIN_STEPS = 3
COMPOSE_MAX_STEPS = 10

COMPOSE_SYSTEM = """당신은 국민체력100 데이터로 운동을 처방하는 서비스의 코치입니다.

사용자 한 사람의 데이터를 전부 읽고, 그 사람을 위한 **오늘의 루틴 하나**를 직접 짭니다.
무료 추천(점수 순)과 다릅니다 — 왜 이 사람에게 이 동작인지가 항목별 체력나이·기록·일정에서 나와야 합니다.

재료는 아래 목록뿐입니다. 세 가지가 있습니다.
  - 동작  국민체력100 공식 동작. 코드로 씁니다. (준비운동 / 본운동 / 정리운동)
  - 종목  배우고 싶은 종목. id 로 씁니다. 영상은 없지만 검증된 종목입니다. ★ 는 사용자가 고른 것입니다.
  - 기록  당일 기록에 적을 수 있는 운동. id 로 씁니다.

지켜야 할 것
  - **목록에 없는 코드·id 를 쓰면 그 줄은 버려집니다.** 이름을 지어내지 마세요.
  - 준비운동 → 본운동 → 정리운동 순서. 본운동은 2~4개. 전체 4~8줄.
  - ★ 고른 종목은 되도록 넣습니다. 그 종목이 쓰는 요인을 본운동이 받쳐 주게 짭니다.
  - 뒤처지는 요인을 먼저 다룹니다. 항목별 체력나이가 실제 나이보다 많이 높은 것이 뒤처진 것입니다.
  - 조심할 부위에 부담을 주는 동작은 피합니다.
  - 수행량은 주어진 강도(세트·반복·시간초)를 기준으로 그 사람에게 맞게 조금 올리거나 내립니다.
    **숫자로 짧게** 씁니다 — "10회 2세트", "20분", "30초 × 2" 처럼 12자 안. 설명은 '왜' 에 씁니다.
  - 최근 기록이 있으면 이어갑니다 — 어제 한 것을 오늘 똑같이 시키지 않습니다.
  - 하루의 모습(고등학생·직장인·알바생 …)과 비는 시간이 있으면 그에 맞춥니다. 여럿이면 다 겹쳐 봅니다.
  - **짬시간에 넣을 것도 그 칸에 주어진 '할 수 있는 것' 에서만 고릅니다.**
  - 측정하지 않은 값을 아는 척하지 마세요. 의학적 진단이나 치료를 말하지 마세요. 아프면 쉬라고 안내합니다.
  - 한국어 존댓말. 한마디는 40자 안팎, 왜 는 각 40자 안팎으로 셋까지.

JSON 만 출력하세요. 다른 말은 쓰지 마세요.
{"목적": "다섯 목적 중 하나", "루틴명": "이 사람을 위한 이름", "한마디": "문장",
 "왜": ["문장", ...],
 "동작": [{"코드": "V…", "단계": "준비운동", "수행량": "…", "왜": "문장"},
          {"종목": "id", "단계": "본운동", "수행량": "…", "왜": "문장"},
          {"기록": "id", "단계": "본운동", "수행량": "…", "왜": "문장"}, ...],
 "주의": ["문장", ...],
 "짬시간": {"요일": [{"칸": 칸번호, "할것": "이름", "한줄": "문장"}, ...], ...}}"""


def _catalogs():
    """재료가 되는 세 카탈로그. 늦게 읽는다 — 서버가 뜰 때 다 읽을 필요는 없다."""
    try:                                        # 저장소 루트에서 실행할 때
        from backend import routines as rt, sports as sp, workout_items as wi
    except ImportError:                         # backend/ 안에서 실행할 때
        import routines as rt, sports as sp, workout_items as wi  # type: ignore
    return rt, sp, wi


def _materials(연령대: str, 종목ids=None) -> tuple[str, dict]:
    """AI 에게 줄 재료 목록(글)과, 응답을 대조할 찾아보기 표.

    재료가 곧 검증의 경계다 — 여기 없는 것은 응답에서 버린다.
    """
    rt, sp, wi = _catalogs()
    고른 = set(종목ids or [])
    줄, 표 = [], {"동작": {}, "종목": {}, "기록": {}}

    줄.append("동작 (코드 | 단계 | 동작 | 요인 | 도구 | 부담부위)")
    pools = rt.load()["pools"].get(연령대, {})
    for 단계 in PHASES:
        for 코드, info in (pools.get(단계) or {}).items():
            if 코드 in 표["동작"]:
                표["동작"][코드]["단계들"].add(단계)   # 같은 동작이 준비·정리 양쪽에 있을 수 있다
                continue
            표["동작"][코드] = {"info": info, "단계들": {단계}}
            줄.append(f"{코드} | {단계} | {info.get('동작')} | "
                      f"{'·'.join(info.get('체력요인') or []) or '-'} | "
                      f"{info.get('도구') or '-'} | {'·'.join(info.get('부담부위') or []) or '-'}")

    줄.append("")
    줄.append("종목 (id | 이름 | 분류 | 요인 | 부담부위)   ★ = 사용자가 고른 것")
    for x in sp.catalog().get("종목", []):
        표["종목"][x["id"]] = x
        별 = "★ " if x["id"] in 고른 else ""
        줄.append(f"{x['id']} | {별}{x['이름']} | {x.get('분류') or '-'} | "
                  f"{'·'.join(x.get('체력요인') or []) or '-'} | {'·'.join(x.get('부담부위') or []) or '-'}")

    줄.append("")
    줄.append("기록 (id | 이름 | 분류 | 요인)")
    for x in wi.catalog().get("종목", []):
        표["기록"][x["id"]] = x
        줄.append(f"{x['id']} | {x['이름']} | {x.get('분류') or '-'} | {x.get('요인') or '-'}")
    return "\n".join(줄), 표


def _compose_prompt(사용자: dict, 재료: str, 일정: dict | None) -> str:
    본문 = "사용자\n" + json.dumps(사용자, ensure_ascii=False, indent=1)
    칸들 = (일정 or {}).get("요일별") or {}
    if 칸들:
        본문 += "\n\n비는 시간 (칸번호 · 시각 · 그 칸에서 할 수 있는 것)"
        for 요일, 목록 in 칸들.items():
            for i, c in enumerate(목록):
                이름 = " / ".join(x["이름"] for x in (c.get("추천") or []))
                본문 += f"\n{요일} {i}. {c['시작']}–{c['끝']} ({c['분']}분) — {이름}"
    return 본문 + "\n\n재료\n" + 재료


def compose(사용자: dict, 연령대: str, 종목ids=None, 일정: dict | None = None) -> dict | None:
    """사용자 데이터 전체로 루틴 하나를 짓는다. 못 하면 None.

    돌려주는 모양: {"루틴": {...화면이 그대로 그리는 루틴...}, "짬시간": {...}}
    재료에 없는 코드·id 는 줄 단위로 버리고, 남은 것이 너무 적으면 통째로
    버린다 — 세 줄도 안 되는 루틴은 루틴이 아니다.
    """
    if not 사용자 or not available():
        return None
    try:
        재료, 표 = _materials(연령대, 종목ids)
    except Exception:                           # 데이터 파일이 없는 환경 — 조용히 폴백
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(timeout=TIMEOUT_SEC * 2, max_retries=1)
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=COMPOSE_SYSTEM,
            output_config={"effort": "medium"},   # 한 사람을 읽고 짓는 일 — 정리 작업보다 깊다
            messages=[{"role": "user",
                       "content": _compose_prompt(사용자, 재료, 일정)}],
        )
        if getattr(message, "stop_reason", None) == "refusal":
            return None
        d = _json_only(_text(message))
    except Exception:                           # 무엇이 잘못돼도 폴백
        return None
    if not d:
        return None
    루틴 = _clean_routine(d, 표, 사용자)
    if not 루틴:
        return None
    return {"루틴": 루틴, "짬시간": _clean_slots(d.get("짬시간"), 일정)}


def _clean_routine(d: dict, 표: dict, 사용자: dict) -> dict | None:
    """응답을 재료 표에 대조해 검증된 줄만 남기고, 화면이 그릴 루틴 모양으로 만든다."""
    from collections import Counter

    줄들 = d.get("동작")
    if not isinstance(줄들, list):
        return None
    steps, 본것 = [], set()
    for x in 줄들:
        if not isinstance(x, dict):
            continue
        step = _resolve_step(x, 표)
        if not step:
            continue                            # 재료에 없다 → 이 줄만 버린다
        열쇠 = (step["출처"], step.get("코드") or step.get("id"))
        if 열쇠 in 본것:
            continue                            # 같은 것을 두 번 넣지 않는다
        본것.add(열쇠)
        steps.append(step)
        if len(steps) >= COMPOSE_MAX_STEPS:
            break
    if len(steps) < COMPOSE_MIN_STEPS or not any(s["단계"] == "본운동" for s in steps):
        return None                             # 루틴이라 부를 수 없다
    차례 = {p: i for i, p in enumerate(PHASES)}
    steps.sort(key=lambda s: 차례[s["단계"]])   # 준비 → 본 → 정리. 안정 정렬이라 그 안 순서는 그대로

    목적 = str(d.get("목적") or "").strip()
    if 목적 not in PURPOSES:
        목적 = "기초 체력 증진"
    요인 = Counter()
    for s in steps:
        요인.update(s.get("체력요인") or [])
    왜 = [str(y).strip()[:80] for y in (d.get("왜") or []) if str(y).strip()][:5]
    주의 = [str(y).strip()[:80] for y in (d.get("주의") or []) if str(y).strip()][:5]
    n = len(steps)
    return {
        "목적": 목적, "표시목적": 목적,
        "루틴명": (str(d.get("루틴명") or "").strip() or "나를 위한 오늘 루틴")[:40],
        "한마디": str(d.get("한마디") or "").strip()[:120],
        "이유": 왜 or ["내 측정값과 기록을 읽고 지었어요"],
        "주의": 주의,
        "steps": steps, "동작수": n,
        "예상시간분": [n * 3, n * 5],
        "체력요인": [f for f, _ in 요인.most_common(4)],
        "강도": 사용자.get("강도"),
        "구성": "ai", "출처": "ai", "순위": 1,
        "루틴번호": None, "점수": None, "난이도": None, "난이도점수": None,
    }


def _resolve_step(x: dict, 표: dict) -> dict | None:
    """응답 한 줄을 재료 표에서 찾아 화면 모양으로. 없으면 None."""
    단계 = str(x.get("단계") or "").strip()
    수행량 = str(x.get("수행량") or "").strip()[:24]     # 길면 설명이다 — 그건 왜 에 들어간다
    왜 = str(x.get("왜") or "").strip()[:80]
    if x.get("코드"):
        항 = 표["동작"].get(str(x["코드"]).strip())
        if not 항:
            return None
        info = 항["info"]
        if 단계 not in 항["단계들"]:
            단계 = sorted(항["단계들"], key=PHASES.index)[0]
        return {"출처": "동작", "단계": 단계, "코드": info["코드"], "동작": info.get("동작"),
                "체력요인": list(info.get("체력요인") or []), "도구": info.get("도구"),
                "유형": info.get("유형"), "부담부위": list(info.get("부담부위") or []),
                "youtube_id": info.get("youtube_id"), "수행량": 수행량, "왜": 왜}
    if x.get("종목"):
        sp = 표["종목"].get(str(x["종목"]).strip())
        if not sp:
            return None
        return {"출처": "종목", "단계": 단계 if 단계 in PHASES else "본운동",
                "id": sp["id"], "동작": sp["이름"], "아이콘": sp.get("아이콘"),
                "체력요인": list(sp.get("체력요인") or []), "도구": sp.get("분류"),
                "유형": "시간", "부담부위": list(sp.get("부담부위") or []),
                "youtube_id": None, "수행량": 수행량, "왜": 왜}
    if x.get("기록"):
        it = 표["기록"].get(str(x["기록"]).strip())
        if not it:
            return None
        기본단계 = "정리운동" if it.get("분류") == "스트레칭" else "본운동"
        return {"출처": "기록", "단계": 단계 if 단계 in PHASES else 기본단계,
                "id": it["id"], "동작": it["이름"],
                "체력요인": [it["요인"]] if it.get("요인") else [], "도구": it.get("분류"),
                "유형": "시간" if "시간" in (it.get("입력") or []) else "횟수",
                "부담부위": [], "youtube_id": None, "수행량": 수행량, "왜": 왜}
    return None
