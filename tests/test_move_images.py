"""측정 동작 썸네일(C5)과 GIF 시트(C6) — 화면 문자열과 정적 자산이 서빙되는지 확인한다.

GIF 파일은 아직 저장소에 없다(저작권이 불분명한 외부 파일은 받지 않기로 함).
그래서 GIF 는 '경로가 코드에 잡혀 있고 placeholder 문구가 있다' 까지만 본다.
"""
from fastapi.testclient import TestClient

from backend.main import app

c = TestClient(app)

SLUGS = ["sit-reach", "situp", "jump", "knee-pushup", "high-knee"]


def _index():
    r = c.get("/")
    assert r.status_code == 200
    return r.text


def test_측정_카드_5개에_썸네일이_있다():
    html = _index()
    for slug in SLUGS:
        assert f'data-move="{slug}"' in html, slug
        assert f"/img/moves/{slug}.svg" in html, slug
    assert html.count('class="move-thumb"') == 5


def test_썸네일_svg_가_서빙된다():
    for slug in SLUGS:
        r = c.get(f"/img/moves/{slug}.svg")
        assert r.status_code == 200, slug
        assert "image/svg+xml" in r.headers["content-type"], slug
        assert 'viewBox="0 0 64 64"' in r.text, slug
        assert 'stroke="currentColor"' in r.text, slug


def test_시트와_gif_경로가_있다():
    html = _index()
    assert 'id="sheet"' in html and 'id="sheetBackdrop"' in html
    assert "function openSheet(" in html and "function closeSheet(" in html
    assert "const MOVE_MEDIA" in html
    for slug in SLUGS:
        assert f"/img/moves/{slug}.gif" in html, slug
    assert "동작 GIF 준비 중" in html


def test_시트는_보이는_뷰포트에_뜨고_닫으면_스크롤이_복원된다():
    """.device 는 내용만큼 자라 페이지 전체가 스크롤되므로, 시트 top 은 열 때 계산하고 닫을 때 스크롤을 되돌린다."""
    html = _index()
    assert "function placeSheet(" in html
    assert "sheetScrollY = window.scrollY" in html
    assert "window.scrollTo(0, sheetScrollY)" in html


def test_gif_는_있으면_그대로_서빙된다():
    """파일을 넣으면 200(image/gif), 없으면 404 — 어느 쪽이든 서버 오류(5xx)는 아니어야 한다."""
    for slug in SLUGS:
        r = c.get(f"/img/moves/{slug}.gif")
        assert r.status_code in (200, 404), slug
        if r.status_code == 200:
            assert "image/gif" in r.headers["content-type"], slug
