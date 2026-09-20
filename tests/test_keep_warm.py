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
