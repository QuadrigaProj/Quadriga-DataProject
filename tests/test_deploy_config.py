"""배포 설정 — 진짜 서비스는 Render 하나다.

정다은 계정의 Vercel 이 main 을 받을 때마다 화면 파일만 'Production' 으로 올리고 있었다
(https://quadriga-data-project.vercel.app). 거기에는 서버가 없어 /health · 측정 · 로그인이 모두 404 인데,
깃허브 저장소의 Deployments 에도 'Production' 으로 떠서 심사위원이 누를 수 있다 (2026-09-26 점검).
그쪽으로 들어와도 Render 로 넘어가게 모든 경로를 돌려보낸다.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER = "https://quadriga-fitness-age.onrender.com/$1"


def test_Vercel_사본은_모든_경로를_Render_로_보낸다():
    # Vercel 프로젝트의 루트가 저장소 맨 위든 frontend/ 든 설정을 읽도록 두 곳에 둔다
    for p in (ROOT / "vercel.json", ROOT / "frontend" / "vercel.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d["redirects"] == [{"source": "/(.*)", "destination": RENDER, "permanent": False}], p
