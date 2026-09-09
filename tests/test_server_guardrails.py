"""서버가 스스로를 지키는 장치.

한 요청이 멈추면 그 스레드가 영구히 잠긴다. 서버가 한 대뿐이라 그런 요청
몇 개면 남는 자리가 없다 — 추천의 무한 루프 때 실제로 그랬다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import main as m  # noqa: E402

client = TestClient(m.app)


def test_시간_제한이_걸려_있다():
    assert m.REQUEST_TIMEOUT_SEC > 0
    assert m.REQUEST_TIMEOUT_SEC <= 60, "이보다 길면 지키는 뜻이 없다"


def test_끊을_때_까닭을_알려_준다():
    """503 만 던지면 쓰는 쪽이 무엇을 해야 할지 모른다."""
    src = __import__("inspect").getsource(m.시간_제한)
    assert "status_code=503" in src
    assert "다시 시도해주세요" in src
    assert "[timeout]" in src            # 무엇이 오래 걸렸는지 로그에 남긴다


def test_로그에_쿼리는_적지_않는다():
    """쿼리에는 개인 정보가 실릴 수 있다."""
    src = __import__("inspect").getsource(m.시간_제한)
    assert "request.url.path" in src
    assert "request.url}" not in src and "str(request.url)" not in src


def test_끌_수_있다():
    """디버깅할 때 붙잡아 두고 봐야 할 때가 있다."""
    src = __import__("inspect").getsource(m.시간_제한)
    assert "REQUEST_TIMEOUT_SEC <= 0" in src


def test_압축해서_내려보낸다():
    """index.html 이 380KB 다. 배포는 CDN 이 하지만 로컬 개발 서버는 아니다."""
    r = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_작은_응답까지_압축하지는_않는다():
    """작은 것은 압축해도 이득이 없고 CPU 만 쓴다."""
    import inspect
    src = inspect.getsource(m)
    assert "GZipMiddleware, minimum_size=" in src


def test_평소_요청은_그대로_지나간다():
    assert client.get("/health").status_code == 200
