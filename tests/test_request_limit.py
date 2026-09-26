"""요청 몸통 크기 상한 — 수백 MB 요청 하나로 무료 서버(메모리 512MB)가 죽지 않게 (2026-09-26 점검).

항목마다 길이 제한은 있지만 몸통을 다 읽고 푼 뒤에 본다. 상한은 그 전에, 읽으면서 끊는다.
"""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import main as m  # noqa: E402
from backend.main import app  # noqa: E402

측정 = {"age_gbn": "성인", "sex": "F", "age": 34, "flexibility": 12, "strength": 20, "height_cm": 162, "weight_kg": 56}


def test_길이를_밝힌_몸통이_상한을_넘으면_읽기_전에_413(monkeypatch):
    monkeypatch.setattr(m, "MAX_BODY_BYTES", 1000)
    r = TestClient(app).post("/fitness-age", content=b"x" * 2000, headers={"content-type": "application/json"})
    assert r.status_code == 413 and "너무 커요" in r.json()["detail"]


def test_길이를_안_밝힌_몸통도_읽으면서_세어_끊는다(monkeypatch):
    monkeypatch.setattr(m, "MAX_BODY_BYTES", 1000)

    def 조각():                                          # chunked — Content-Length 가 없다
        for _ in range(10):
            yield b"x" * 500
    r = TestClient(app).post("/fitness-age", content=조각(), headers={"content-type": "application/json"})
    assert r.status_code == 413 and "너무 커요" in r.json()["detail"]


def test_상한_아래의_요청은_그대로_간다(monkeypatch):
    monkeypatch.setattr(m, "MAX_BODY_BYTES", 1000)
    r = TestClient(app).post("/fitness-age", json=측정)
    assert r.status_code == 200 and r.json()["체력나이"] > 0


def test_상한은_가장_큰_정상_요청보다_크다():
    """구독자의 커뮤니티 글 — 동영상 6개 × 4.2MB(base64) — 가 막히면 안 된다."""
    from backend import community
    구독 = community.LIMITS["구독"]
    assert m.MAX_BODY_BYTES > 구독["사진"] * 구독["동영상바이트"] + 구독["본문"] * 4
