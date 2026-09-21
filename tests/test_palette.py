"""앱의 바탕색 — 아이보리. 색을 바꿔도 글씨가 읽히는지(명암 대비)를 같이 잰다.

예현(2026-09-21): "앱 전체 바탕색이 흰색에 가까운 것 같은데 좀 더 아이보리나 베이지 컬러감이 보였으면 좋겠어".
전엔 화면 #FAFAF4 · 바깥 #EDEFE6 (흰색에 가까운 회녹색) 이었다.
"""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _vars(css: str) -> dict:
    return dict(re.findall(r"(--[a-z-]+)\s*:\s*(#[0-9A-Fa-f]{6})", css))


def _root() -> dict:
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    return _vars(html.split(":root{")[1].split("}")[0])


def _rgb(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _lum(h: str) -> float:
    def f(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    """WCAG 명암 대비 (1 ~ 21)."""
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_바탕은_아이보리다():
    v = _root()
    for 이름 in ("--paper", "--bg"):
        r, g, b = _rgb(v[이름])
        assert r > g > b and r - b >= 20, (이름, v[이름])          # 누런 기가 눈에 보인다 — 회색 · 회녹색이 아니다
        assert _lum(v[이름]) >= 0.72, (이름, v[이름])               # 그래도 밝은 바탕이다
    assert _lum(v["--paper"]) > _lum(v["--bg"])                     # 화면(기기 안)이 바깥보다 밝다
    assert v["--paper"].upper() not in ("#FAFAF4", "#FFFFFF") and v["--bg"].upper() != "#EDEFE6"
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert f'<meta name="theme-color" content="{v["--bg"]}" />' in html        # 휴대폰 주소창 색도 같은 바탕
    assert html.count(f"c('--paper', '{v['--paper']}')") == 2                  # 공유 카드(캔버스)의 예비 색도 같은 값


def test_바탕을_바꿔도_글씨는_읽힌다():
    """흐린 글씨(--muted)는 화면 · 바깥 · 연초록 칸 · 연호박 칸 어디에 놓여도 4.5:1 (WCAG AA) 을 지킨다."""
    v = _root()
    for 바탕 in ("--paper", "--bg", "--pine-tint", "--amber-tint"):
        assert contrast(v["--muted"], v[바탕]) >= 4.5, (바탕, round(contrast(v["--muted"], v[바탕]), 2))
    assert contrast(v["--ink"], v["--paper"]) >= 12                  # 본문
    assert contrast(v["--pine"], v["--paper"]) >= 6                  # 초록 글씨 · 버튼 테두리
    assert contrast("#FFFFFF", v["--pine"]) >= 6                      # 초록 버튼 위 흰 글씨


def test_약관과_쉬운_모드도_같은_바탕이다():
    v = _root()
    정책 = _vars((FRONT / "_policy.css").read_text(encoding="utf-8").split(":root{")[1].split("}")[0])
    for 이름 in ("--bg", "--paper", "--muted", "--line"):
        assert 정책[이름] == v[이름], 이름                              # 개인정보처리방침 · 이용약관
    쉬운 = (FRONT / "easy-mode.css").read_text(encoding="utf-8").split("#easyRoot{")[1].split("}")[0]
    쉬운색 = _vars(쉬운)
    assert 쉬운색["--paper"] == v["--paper"] and f"background:{v['--bg']};" in 쉬운
    assert contrast(쉬운색["--soft"], 쉬운색["--paper"]) >= 7 and contrast(쉬운색["--ink"], 쉬운색["--paper"]) >= 7   # 쉬운 모드는 7:1 (AAA)
