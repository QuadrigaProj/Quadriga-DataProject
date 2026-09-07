"""커뮤니티 — 게시글·댓글·이모지 반응·기록 공유·채팅 테스트.

DB 는 test_api.py 의 _clean_db 픽스처와 같은 방식으로 임시 SQLite 를 쓴다.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import auth, community        # noqa: E402
from backend.main import app               # noqa: E402


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    if auth.is_postgres():
        with auth.db() as con:
            auth.init_db(); community.init_db()
            for t in ("chat_messages", "chat_members", "chat_rooms",
                      "community_reactions", "community_comments", "community_posts",
                      "measurements", "sessions", "oauth_states", "users"):
                con.execute(f"DELETE FROM {t}")
    else:
        monkeypatch.setattr(auth, "DB_PATH", Path(tempfile.mkdtemp()) / "t.db")
        auth.init_db(); community.init_db()
    yield


def _login(client: TestClient, email: str, name: str) -> TestClient:
    c = TestClient(app)
    c.post("/auth/signup", json={"email": email, "password": "pw12345678", "display_name": name})
    return c


def test_로그인_안하면_401():
    c = TestClient(app)
    assert c.get("/community/posts").status_code == 401
    assert c.post("/community/posts", json={"body": "hi"}).status_code == 401


def test_게시글_피드_가입자끼리_보인다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    a.post("/community/posts", json={"body": "오늘 스쿼트 100개"})
    feed = b.get("/community/posts").json()["posts"]
    assert feed[0]["본문"] == "오늘 스쿼트 100개"
    assert feed[0]["작성자"] == "가"
    assert feed[0]["내글"] is False


def test_빈_글은_거절():
    a = _login(app, "a@x.com", "가")
    assert a.post("/community/posts", json={"body": "   "}).status_code == 400


def test_댓글():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    pid = a.post("/community/posts", json={"body": "같이 뛰실 분"}).json()["id"]
    r = b.post(f"/community/posts/{pid}/comments", json={"body": "저요!"}).json()
    assert r["댓글수"] == 1
    assert r["댓글"][0]["본문"] == "저요!" and r["댓글"][0]["작성자"] == "나"


def test_이모지_반응_토글():
    a = _login(app, "a@x.com", "가")
    pid = a.post("/community/posts", json={"body": "3개월 -4세!"}).json()["id"]
    r1 = a.post("/community/reactions", json={"target_type": "post", "target_id": pid, "emoji": "🔥"}).json()
    assert r1["반응"]["counts"]["🔥"] == 1 and "🔥" in r1["반응"]["mine"]
    r2 = a.post("/community/reactions", json={"target_type": "post", "target_id": pid, "emoji": "🔥"}).json()
    assert r2["반응"]["counts"].get("🔥", 0) == 0        # 다시 누르면 취소


def test_쓸수없는_이모지_거절():
    a = _login(app, "a@x.com", "가")
    pid = a.post("/community/posts", json={"body": "x"}).json()["id"]
    assert a.post("/community/reactions",
                  json={"target_type": "post", "target_id": pid, "emoji": "💩"}).status_code == 400


def test_사진_data_url_검증():
    a = _login(app, "a@x.com", "가")
    ok = "data:image/png;base64,iVBORw0KGgoAAAANS"
    assert a.post("/community/posts", json={"body": "", "media": [{"url": ok, "name": "a.png"}]}).status_code == 200
    bad = a.post("/community/posts", json={"media": [{"url": "http://x/a.png"}]})
    assert bad.status_code == 400


def test_기록_공유():
    a = _login(app, "a@x.com", "가")
    r = a.post("/community/posts", json={
        "kind": "record", "body": "이번 주 4일 완료",
        "record": {"연속일": 4, "체력나이변화": -2},
    }).json()
    assert r["종류"] == "record"
    assert r["기록"]["연속일"] == 4


def test_내_글만_지운다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    pid = a.post("/community/posts", json={"body": "지울 글"}).json()["id"]
    assert b.delete(f"/community/posts/{pid}").status_code == 403
    assert a.delete(f"/community/posts/{pid}").status_code == 200
    assert a.get(f"/community/posts/{pid}").status_code == 404


# ---------- 채팅 ----------

def test_채팅_모임_만들고_참여하고_대화():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    rid = a.post("/community/rooms", json={"name": "한강 러닝 모임", "topic": "토 아침 7시"}).json()["id"]
    # 안 들어온 사람은 메시지 못 봄
    assert b.get(f"/community/rooms/{rid}/messages").status_code == 403
    b.post(f"/community/rooms/{rid}/join")
    a.post(f"/community/rooms/{rid}/messages", json={"body": "토요일 봬요"})
    b.post(f"/community/rooms/{rid}/messages", json={"body": "넵!"})
    msgs = b.get(f"/community/rooms/{rid}/messages").json()["messages"]
    assert [m["본문"] for m in msgs] == ["토요일 봬요", "넵!"]
    assert msgs[1]["내글"] is True


def test_채팅_after_로_새_메시지만():
    a = _login(app, "a@x.com", "가")
    rid = a.post("/community/rooms", json={"name": "모임"}).json()["id"]
    m1 = a.post(f"/community/rooms/{rid}/messages", json={"body": "첫 메시지"}).json()["messages"][-1]["id"]
    a.post(f"/community/rooms/{rid}/messages", json={"body": "두번째"})
    new = a.get(f"/community/rooms/{rid}/messages", params={"after": m1}).json()["messages"]
    assert [m["본문"] for m in new] == ["두번째"]


def test_방_목록_참여여부():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    a.post("/community/rooms", json={"name": "축구 모임"})
    rooms = b.get("/community/rooms").json()["rooms"]
    assert rooms[0]["이름"] == "축구 모임"
    assert rooms[0]["참여중"] is False and rooms[0]["인원"] == 1


def test_비공개_단체방은_비밀번호를_검증하고_목록에_표시한다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    rid = a.post("/community/rooms", json={
        "name": "비밀 러닝", "room_type": "group", "is_private": True, "password": "run1234",
    }).json()["id"]
    room = b.get("/community/rooms").json()["rooms"][0]
    assert room["종류"] == "group" and room["비공개"] is True
    assert b.post(f"/community/rooms/{rid}/join", json={"password": "wrong"}).status_code == 403
    assert b.post(f"/community/rooms/{rid}/join", json={"password": "run1234"}).status_code == 200
    with auth.db() as con:
        saved = con.execute("SELECT password_hash FROM chat_rooms WHERE id=?", (rid,)).fetchone()
    assert saved["password_hash"] != "run1234"


def test_방장만_비공개방_비밀번호를_바꾼다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    rid = a.post("/community/rooms", json={
        "name": "비밀 모임", "is_private": True, "password": "old1234",
    }).json()["id"]
    assert b.put(f"/community/rooms/{rid}/password", json={"password": "new1234"}).status_code == 403
    assert a.put(f"/community/rooms/{rid}/password", json={"password": "new1234"}).status_code == 200
    assert b.post(f"/community/rooms/{rid}/join", json={"password": "old1234"}).status_code == 403
    assert b.post(f"/community/rooms/{rid}/join", json={"password": "new1234"}).status_code == 200


def test_개인_채팅방은_상대만_참여자로_추가한다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    c = _login(app, "c@x.com", "다")
    rid = a.post("/community/rooms", json={
        "name": "가와 나", "room_type": "direct", "member_email": "b@x.com",
    }).json()["id"]
    room = b.get("/community/rooms").json()["rooms"][0]
    assert room["종류"] == "direct" and room["참여중"] is True and room["인원"] == 2
    assert c.post(f"/community/rooms/{rid}/join", json={}).status_code == 403
