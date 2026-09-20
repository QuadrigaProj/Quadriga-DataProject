"""배포 서버를 깨워 두는 예약 실행(.github/workflows/keep-warm.yml).

Render 무료 요금제는 15분 동안 접속이 없으면 서버를 끄고, 다음 첫 접속은 30초~1분이 걸린다.
간격을 누가 "아끼려고" 15분 이상으로 늘리면 조용히 쓸모가 없어진다 — 그걸 막는다.
"""
from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "keep-warm.yml"
SPIN_DOWN_MIN = 15          # Render 가 서버를 끄기까지의 분


def _src() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_잠들기_전에_두드린다():
    cron = re.search(r'- cron: "([^"]+)"', _src()).group(1)
    분 = cron.split()[0]
    간격 = int(분.split("/")[1])
    assert cron.split()[1:] == ["*", "*", "*", "*"]                     # 날마다 · 시간마다
    # 깃허브 예약은 한 번쯤 밀린다 — 한 번 건너뛰어도 15분이 안 되게 둔다
    assert 간격 * 2 < SPIN_DOWN_MIN, "간격이 길면 한 번 밀렸을 때 서버가 잠든다"
    assert not 분.startswith(("0", "*")), "정각은 깃허브가 가장 붐빈다"


def test_서버가_살아_있는지_묻는_주소를_부른다():
    src = _src()
    assert "APP_URL: https://quadriga-fitness-age.onrender.com" in src
    assert '"$APP_URL/health"' in src                                   # 가볍고, 로그인도 DB 도 필요 없다
    from fastapi.testclient import TestClient
    from backend import main as m
    assert TestClient(m.app).get("/health").status_code == 200


def test_저장소_권한을_갖지_않고_실패해도_빨간불을_켜지_않는다():
    src = _src()
    assert "permissions: {}" in src                                     # 밖으로 요청 하나 보낼 뿐이다
    assert "actions/checkout" not in src
    assert "|| true" in src and "::warning::" in src                    # 두드리는 일이지 감시가 아니다 — 실패 메일을 쏟아내지 않는다
    assert "--max-time 100" in src                                      # 잠들어 있었다면 깨어나는 데 1분쯤 걸린다


# ---------- 서버가 스스로를 두드린다 ----------
# 깃허브 예약 실행은 5분 간격을 지켜 주지 않았다 — 첫 실행까지 3시간 23분, 그 뒤에도 서버가 다시 잠들어 있었다(2026-09-21).
# 그래서 서버가 직접 10분마다 자기 바깥 주소를 부른다. 깃허브 쪽은 '잠들었을 때 깨우는' 몫으로 남긴다.

def test_바깥_주소를_알_때만_스스로를_두드린다(monkeypatch):
    from backend import main as m
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    assert m.keep_awake_url() is None                                   # 로컬 · 테스트에서는 아무 일도 하지 않는다
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://quadriga-fitness-age.onrender.com/")
    assert m.keep_awake_url() == "https://quadriga-fitness-age.onrender.com/health"      # Render 가 넣어 주는 값
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://fitage.example.com")
    assert m.keep_awake_url() == "https://fitage.example.com/health"    # 직접 정한 주소가 먼저다
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    assert m.keep_awake_url() is None                                   # https 가 아니면 배포가 아니다
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://fitage.example.com")
    monkeypatch.setattr(m, "KEEP_AWAKE_EVERY_SEC", 0.0)
    assert m.keep_awake_url() is None                                   # 0 으로 끈다
    assert 0 < 600 <= SPIN_DOWN_MIN * 60 * 0.75                         # 기본 10분 — 15분보다 넉넉히 짧다
    src = Path(m.__file__).read_text(encoding="utf-8")
    assert 'KEEP_AWAKE_EVERY_SEC = float(os.getenv("KEEP_AWAKE_EVERY_SEC", "600"))' in src
    시작 = src.split("async def lifespan(")[1].split("app = FastAPI(")[0]
    assert "깨우기 = asyncio.create_task(_keep_awake(url)) if url else None" in 시작
    assert 시작.index("yield") < 시작.index("깨우기.cancel()")            # 내려갈 때 멈춘다


def test_한_번_못_불러도_계속_두드린다(monkeypatch):
    import asyncio
    from backend import main as m
    부른것 = []

    class 가짜:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            부른것.append(url)
            if len(부른것) == 1:
                raise RuntimeError("잠깐 끊김")

    monkeypatch.setattr(m.httpx, "AsyncClient", 가짜)
    monkeypatch.setattr(m, "KEEP_AWAKE_EVERY_SEC", 0.01)

    async def 돌린다():
        task = asyncio.create_task(m._keep_awake("https://x.example/health"))
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(돌린다())
    assert len(부른것) >= 3 and set(부른것) == {"https://x.example/health"}      # 첫 번째가 터져도 멈추지 않았다

