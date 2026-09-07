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

지켜야 할 것
  - 후보에 없는 루틴을 만들지 마세요. 반드시 주어진 번호만 씁니다.
  - 측정하지 않은 값을 아는 척하지 마세요.
  - 이유는 한국어 존댓말로, 한 줄에 하나씩, 각 40자 안팎으로 씁니다.
  - 의학적 진단이나 치료를 말하지 마세요. 아프면 쉬라고 안내합니다.

JSON 만 출력하세요. 다른 말은 쓰지 마세요.
{"순서": [후보번호, ...], "이유": {"후보번호": ["문장", ...], ...}, "한마디": "한 문장"}"""


def available() -> bool:
    """지금 AI 를 부를 수 있는지. 키와 SDK 가 모두 있어야 한다."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _prompt(후보: list[dict], 참고: dict, 연령대: str) -> str:
    줄 = []
    for i, x in enumerate(후보):
        요인 = " · ".join((x.get("체력요인") or [])[:4])
        줄.append(f"{i}. [{x.get('목적')}] {x.get('루틴명')} — 동작 {x.get('동작수')}개, {요인}")
    사용자 = {
        "연령대": 연령대,
        "뒤처지는 체력요인": 참고.get("약점") or [],
        "배우고 싶은 종목이 쓰는 요인": 참고.get("종목요인") or [],
        "운동 스타일 테스트가 고른 목적": 참고.get("스타일목적"),
        "목표 체력나이까지 남은 세": 참고.get("목표격차"),
    }
    return ("사용자\n" + json.dumps(사용자, ensure_ascii=False, indent=1)
            + "\n\n후보\n" + "\n".join(줄))


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


def refine(후보: list[dict], 참고: dict, 연령대: str) -> list[dict] | None:
    """후보를 다시 배열하고 이유를 다시 쓴다. 못 하면 None."""
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
            messages=[{"role": "user", "content": _prompt(후보, 참고, 연령대)}],
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
    return 결과
