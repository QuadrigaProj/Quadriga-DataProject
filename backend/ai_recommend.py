"""AI 루틴 추천 — 점수로 고른 후보를 Claude 가 다시 읽고 순서와 설명을 다듬는다.

새 루틴을 만들지 않는다. backend/recommend.py 가 250개 고정 루틴에서 고른
후보 **안에서만** 고르고, 왜 그 순서인지를 사용자 말로 다시 쓴다.
모델이 없는 번호를 내면 그 응답을 통째로 버린다(지어낸 추천을 내보내지 않는다).

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

SYSTEM = """당신은 국민체력100 데이터로 운동을 처방하는 서비스의 코치입니다.

아래 후보는 이미 정해진 250개 고정 루틴에서 규칙으로 골라낸 것입니다.
당신이 할 일은 두 가지입니다.
  1. 이 사용자에게 맞는 순서로 후보를 다시 배열한다
  2. 각 후보를 왜 그 자리에 뒀는지 사용자에게 할 말로 쓴다

일정을 함께 받으면 세 번째 일도 합니다.
  3. 비는 시간(짬시간)마다 무엇을 할지 고르고 한 줄로 설명한다

지켜야 할 것
  - 후보에 없는 루틴을 만들지 마세요. 반드시 주어진 번호만 씁니다.
  - **짬시간에 넣을 것도 그 칸에 주어진 '할 수 있는 것' 에서만 고릅니다.**
    거기 없는 운동·종목을 쓰면 그 줄은 버려집니다.
  - 측정하지 않은 값을 아는 척하지 마세요.
  - 이유는 한국어 존댓말로, 한 줄에 하나씩, 각 40자 안팎으로 씁니다.
  - 하루의 모습(학생·직장인·알바생 등)이 있으면 그에 맞게 말합니다.
    이른 아침 칸에 무거운 운동을 넣지 않는 식으로요.
  - 의학적 진단이나 치료를 말하지 마세요. 아프면 쉬라고 안내합니다.

JSON 만 출력하세요. 다른 말은 쓰지 마세요.
{"순서": [후보번호, ...], "이유": {"후보번호": ["문장", ...], ...}, "한마디": "한 문장",
 "짬시간": {"요일": [{"칸": 칸번호, "할것": "이름", "한줄": "문장"}, ...], ...}}"""


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


def _prompt(후보: list[dict], 참고: dict, 연령대: str,
            일정: dict | None = None) -> str:
    줄 = []
    for i, x in enumerate(후보):
        요인 = " · ".join((x.get("체력요인") or [])[:4])
        줄.append(f"{i}. [{x.get('목적')}] {x.get('루틴명')} — 동작 {x.get('동작수')}개, {요인}")
    사용자 = {
        "연령대": 연령대,
        "뒤처지는 체력요인": 참고.get("약점") or [],
        "고른 종목": 참고.get("고른종목") or [],
        "배우고 싶은 종목이 쓰는 요인": 참고.get("종목요인") or [],
        "운동 스타일 테스트가 고른 목적": 참고.get("스타일목적"),
        "목표 체력나이까지 남은 세": 참고.get("목표격차"),
    }
    if (일정 or {}).get("상태"):
        사용자["하루의 모습"] = 일정["상태"]
    본문 = ("사용자\n" + json.dumps(사용자, ensure_ascii=False, indent=1)
          + "\n\n후보\n" + "\n".join(줄))

    칸들 = (일정 or {}).get("요일별") or {}
    if 칸들:
        본문 += "\n\n비는 시간 (칸번호 · 시각 · 그 칸에서 할 수 있는 것)"
        for 요일, 목록 in 칸들.items():
            for i, c in enumerate(목록):
                이름 = " / ".join(x["이름"] for x in (c.get("추천") or []))
                본문 += f"\n{요일} {i}. {c['시작']}–{c['끝']} ({c['분']}분) — {이름}"
    return 본문


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


def refine(후보: list[dict], 참고: dict, 연령대: str,
           일정: dict | None = None) -> dict | None:
    """후보를 다시 배열하고 이유를 다시 쓴다. 못 하면 None.

    일정을 주면 비는 칸마다 무엇을 할지도 함께 고른다. 그 칸에 주어진
    '할 수 있는 것' 밖의 이름은 버린다 — 지어낸 추천을 내보내지 않는다.
    돌려주는 모양: {"추천": [...], "짬시간": {요일: [...]}}
    """
    if not 후보 or not available():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(timeout=TIMEOUT_SEC, max_retries=1)
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            output_config={"effort": "low"},   # 짧은 정리 작업이라 깊게 생각할 필요가 없다
            messages=[{"role": "user",
                       "content": _prompt(후보, 참고, 연령대, 일정)}],
        )
        if getattr(message, "stop_reason", None) == "refusal":
            return None
        d = _json_only(_text(message))
    except Exception:                          # 키 오류·연결 실패·응답 이상 — 무엇이든 폴백
        return None

    if not d:
        return None
    순서 = d.get("순서")
    if not isinstance(순서, list) or not 순서:
        return None

    이유표 = d.get("이유") if isinstance(d.get("이유"), dict) else {}
    본것, 결과 = set(), []
    for n in 순서:
        try:
            i = int(n)
        except (TypeError, ValueError):
            return None                        # 번호가 아닌 것이 섞였다 → 통째로 버린다
        if not (0 <= i < len(후보)) or i in 본것:
            return None                        # 없는 후보이거나 중복 → 지어낸 응답으로 본다
        본것.add(i)
        x = dict(후보[i])
        새이유 = 이유표.get(str(i)) or 이유표.get(i)
        if isinstance(새이유, list):
            줄 = [str(y).strip() for y in 새이유 if str(y).strip()]
            if 줄:
                x["이유"] = 줄[:5]
        x["출처"] = "ai"
        결과.append(x)

    한마디 = d.get("한마디")
    if 결과 and isinstance(한마디, str) and 한마디.strip():
        결과[0]["한마디"] = 한마디.strip()[:120]
    for i, x in enumerate(결과, 1):
        x["순위"] = i
    return {"추천": 결과, "짬시간": _clean_slots(d.get("짬시간"), 일정)}


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
  - 하루의 모습(학생·직장인·알바생 등)이 있으면 그 사람 생활에 맞게 씁니다.
    시험 기간, 교대 근무, 방학처럼 그 사람에게 실제로 있는 일로요.
  - 계절은 봄·여름·가을·겨울 네 개를 모두, 이 순서로 씁니다.
  - 측정하지 않은 값을 아는 척하지 마세요.
  - 한국어 존댓말. 한줄은 40자 안팎, 할것은 각 25자 안팎으로 셋까지.
  - 의학적 진단이나 치료를 말하지 마세요. 아프면 쉬라고 안내합니다.
  - 더위·추위로 위험할 수 있는 날은 무리하지 말라고 한마디 넣습니다.

JSON 만 출력하세요. 다른 말은 쓰지 마세요.
{"계절": [{"계절": "봄", "한줄": "문장", "할것": ["문장", ...], "조심": "문장"}, ...]}"""


def _season_prompt(루틴: dict, 참고: dict, 연령대: str, 상태: str | None) -> str:
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
            상태: str | None = None) -> list[dict] | None:
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
