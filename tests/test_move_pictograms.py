"""F5 운동종목 픽토그램 — 정적 자산과 index.html 참조가 함께 있는지 본다.

JS 매핑(moveCategory)은 브라우저에서만 돌아가므로 여기서는
"파일이 있고, 서버가 서빙하며, 화면이 그 경로를 참조한다" 까지만 잡는다.

매핑 규칙은 DevTools 콘솔에서 아래 8건으로 확인한다(routines_250.json 의 실제 체력요인 값):
    moveCategory({단계:'준비운동', 체력요인:'심폐지구력'})          === 'stretch'   # 단계 우선
    moveCategory({단계:'본운동',   체력요인:'근력·근지구력(상체)'})  === 'strength'
    moveCategory({단계:'본운동',   체력요인:'심폐지구력'})          === 'cardio'
    moveCategory({단계:'본운동',   체력요인:'평형성'})              === 'balance'
    moveCategory({단계:'본운동',   체력요인:'민첩성·순발력'})       === 'power'
    moveCategory({단계:'정리운동', 체력요인:'이완'})                === 'stretch'   # 단계 우선(본운동이면 breath)
    moveCategory({단계:'본운동',   체력요인:'유연성'})              === 'stretch'
    moveCategory({단계:'본운동',   체력요인:'전신'})                === 'strength'  # 기본값
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import paths  # noqa: E402
from backend.main import app  # noqa: E402

client = TestClient(app)
CATEGORIES = ("stretch", "strength", "cardio", "balance", "power", "breath")
MOVES_DIR = paths.FRONTEND / "img" / "moves"


def test_범주_svg_6개가_있다():
    """conventions 3절 규격: viewBox 64, currentColor, 배경 없음."""
    for c in CATEGORIES:
        p = MOVES_DIR / f"{c}.svg"
        assert p.exists(), p
        text = p.read_text(encoding="utf-8")
        assert 'viewBox="0 0 64 64"' in text, c
        assert 'stroke="currentColor"' in text, c
        assert '<rect width="64"' not in text, c   # 배경 사각형 금지


def test_범주_svg가_서빙된다():
    """frontend/ 전체가 StaticFiles 로 마운트되므로 /img/moves/… 로 바로 열려야 한다."""
    for c in CATEGORIES:
        r = client.get(f"/img/moves/{c}.svg")
        assert r.status_code == 200, c
        assert "image/svg+xml" in r.headers["content-type"], c


def test_index가_픽토그램을_참조한다():
    html = client.get("/").text
    assert "MOVE_CATEGORY_MEDIA" in html
    assert "function moveCategory" in html
    assert 'id="playerPicto"' in html
    assert "openMovePicto()" in html
    for c in CATEGORIES:
        assert f"img/moves/{c}.svg" in html, c
        assert f"img/moves/{c}.gif" in html, c   # GIF 는 경로만 두고 파일은 넣지 않는다(C6)


def test_gif_placeholder_문구가_있다():
    """C6 원문: 저작권 불분명한 파일을 임의로 넣지 않고 placeholder 까지만 구현."""
    html = client.get("/").text
    assert "동작 GIF 준비 중" in html
