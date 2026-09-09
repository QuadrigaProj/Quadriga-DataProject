"""운동 자세 그림이 실제 동작으로 움직인다 (H7).

그림 한 장으로는 어디서 어디까지 가는 동작인지 알 수 없다. 아령만 보고
무엇을 하라는 건지 몰랐다. 자세마다 '반대 끝' 을 하나 더 그려 두고, 누르면
둘을 번갈아 보여 준다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _art() -> str:
    return (ROOT / "frontend" / "js" / "move-art.js").read_text(encoding="utf-8")


def _index() -> str:
    return (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def _ids(kind: str) -> set[str]:
    return set(re.findall(rf'id=.{kind}-([\w-]+).', _art()))


def test_자세마다_두_번째_그림이_있다():
    """하나라도 빠지면 그 운동만 안 움직인다 — 왜 안 되는지 알기 어렵다."""
    a, b = _ids("pose"), _ids("poseb")
    assert a, "자세 그림이 하나도 없다"
    assert a == b, f"짝이 안 맞는다: 없는 두 번째 {sorted(a - b)} / 짝 없는 것 {sorted(b - a)}"


def test_두_그림이_서로_다르다():
    """같은 그림을 두 번 그려 두면 눌러도 아무 일이 없다."""
    art = _art()
    같은것 = []
    for 이름 in _ids("pose"):
        가 = re.search(rf"id='pose-{re.escape(이름)}'.*?>(.*?)</symbol>", art, re.S)
        나 = re.search(rf"id='poseb-{re.escape(이름)}'.*?>(.*?)</symbol>", art, re.S)
        if 가 and 나 and 가.group(1).strip() == 나.group(1).strip():
            같은것.append(이름)
    assert not 같은것, 같은것


def test_두_자세를_겹쳐_그린다():
    art = _art()
    본문 = art.split("function pose(id, cls)")[1].split("\n  }")[0]
    assert 'class="pose-a" href="#pose-${id}"' in 본문
    assert 'class="pose-b"' in 본문 and 'href="#poseb-${id}"' in 본문


def test_눌러서_움직이고_마우스가_아니어도_된다():
    art = _art()
    assert 'role="button"' in art and 'tabindex="0"' in art
    assert 'onclick="MOVE_ART.play(this)"' in art
    assert 'onkeydown="MOVE_ART.onKey(event)"' in art
    키 = art.split("function onKey(ev)")[1].split("\n  }")[0]
    assert "'Enter'" in 키 and "' '" in 키


def test_두_번_눌러도_겹치지_않는다():
    """겹치면 두 배 빨라지거나 끝나는 때를 알 수 없다."""
    본문 = _art().split("function play(el)")[1].split("\n  }")[0]
    assert "classList.contains('playing')" in 본문
    assert "return" in 본문.split("classList.contains('playing')")[1][:40]


def test_다_돌면_원래_그림으로_돌아온다():
    """여러 개가 계속 움직이면 화면이 어지럽다."""
    본문 = _art().split("function play(el)")[1].split("\n  }")[0]
    assert "setTimeout" in 본문
    assert "classList.remove('playing')" in 본문
    assert "CYCLES" in 본문 and "BEAT_MS" in 본문


def test_두_스프라이트를_함께_심는다():
    assert "box.innerHTML = SPRITE + SPRITE_B;" in _art()


def test_평소에는_첫_자세만_보인다():
    html = _index()
    assert ".move-play .pose-b{ opacity:0; }" in html


def test_움직임을_줄여_달라는_사람에게는_움직이지_않는다():
    """대신 두 번째 자세를 그대로 보여 준다 — 무엇이 달라지는지는 알 수 있다."""
    html = _index()
    본문 = html.split("@media (prefers-reduced-motion: reduce){")[1].split("\n  }")[0]
    assert ".move-play.playing .pose-a{ animation:none; opacity:0; }" in 본문
    assert ".move-play.playing .pose-b{ animation:none; opacity:1; }" in 본문
