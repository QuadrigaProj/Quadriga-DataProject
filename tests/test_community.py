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
    # L2: 비밀번호는 숫자만 받는다
    rid = a.post("/community/rooms", json={
        "name": "비밀 러닝", "is_private": True, "password": "824135",
    }).json()["id"]
    room = b.get("/community/rooms").json()["rooms"][0]
    assert room["종류"] == "group" and room["비공개"] is True
    assert b.post(f"/community/rooms/{rid}/join", json={"password": "999999"}).status_code == 403
    assert b.post(f"/community/rooms/{rid}/join", json={"password": "824135"}).status_code == 200
    with auth.db() as con:
        saved = con.execute("SELECT password_hash FROM chat_rooms WHERE id=?", (rid,)).fetchone()
    assert saved["password_hash"] != "824135"


def test_방장만_비공개방_비밀번호를_바꾼다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    rid = a.post("/community/rooms", json={
        "name": "비밀 모임", "is_private": True, "password": "111111",
    }).json()["id"]
    assert b.put(f"/community/rooms/{rid}/password", json={"password": "222222"}).status_code == 403
    assert a.put(f"/community/rooms/{rid}/password", json={"password": "222222"}).status_code == 200
    assert b.post(f"/community/rooms/{rid}/join", json={"password": "111111"}).status_code == 403
    assert b.post(f"/community/rooms/{rid}/join", json={"password": "222222"}).status_code == 200


def test_개인_채팅방은_상대만_참여자로_추가한다():
    """L1: 개인 채팅방은 방 만들기로 못 만든다. 상대 아이디로 열 때 생긴다."""
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    c = _login(app, "c@x.com", "다")
    hb = b.get("/community/me/handle").json()["아이디"]
    rid = a.post("/community/direct", json={"handle": hb}).json()["room_id"]
    room = b.get("/community/rooms").json()["rooms"][0]
    assert room["종류"] == "direct" and room["참여중"] is True and room["인원"] == 2
    assert c.post(f"/community/rooms/{rid}/join", json={}).status_code == 403


# ---------- 앱 내 아이디 ----------

def test_내_아이디가_생긴다():
    a = _login(app, "a@x.com", "가")
    me = a.get("/community/me/handle").json()
    assert me["닉네임"] == "가"
    assert me["아이디"] and len(me["아이디"]) == community.HANDLE_LEN
    # 여러 번 물어도 같은 아이디다
    assert a.get("/community/me/handle").json()["아이디"] == me["아이디"]


def test_아이디는_서로_다르다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    assert a.get("/community/me/handle").json()["아이디"] \
        != b.get("/community/me/handle").json()["아이디"]


def test_아이디에_이름이_들어가지_않는다():
    """이름에서 아이디를 만들면 본명이 새어 나간다."""
    a = _login(app, "hong@x.com", "홍길동")
    h = a.get("/community/me/handle").json()["아이디"]
    assert "hong" not in h
    assert set(h) <= set(community.HANDLE_ALPHABET)


def test_아이디로_사람을_찾는다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    h = b.get("/community/me/handle").json()["아이디"]
    found = a.get(f"/community/users/{h}").json()
    assert found["닉네임"] == "나" and found["아이디"] == h
    assert found["관계"] == "없음"


def test_찾은_사람의_정보는_닉네임과_아이디뿐이다():
    """체력나이·측정 기록·이메일이 새어 나가면 안 된다."""
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    h = b.get("/community/me/handle").json()["아이디"]
    found = a.get(f"/community/users/{h}").json()
    assert set(found) == {"닉네임", "아이디", "관계"}
    본문 = a.get(f"/community/users/{h}").text
    assert "b@x.com" not in 본문


def test_없는_아이디는_404():
    a = _login(app, "a@x.com", "가")
    assert a.get("/community/users/zzzzzz").status_code == 404


def test_이상한_아이디도_404로_끝난다():
    a = _login(app, "a@x.com", "가")
    for 나쁜 in ("", "  ", "a", "한글아이디", "a" * 40, "../etc", "%25"):
        assert a.get(f"/community/users/{나쁜}").status_code in (404, 405, 422)


def test_아이디_조회도_로그인이_필요하다():
    """로그인 없이 찾게 두면 아이디를 훑어 회원 목록을 만들 수 있다."""
    a = _login(app, "a@x.com", "가")
    h = a.get("/community/me/handle").json()["아이디"]
    assert TestClient(app).get(f"/community/users/{h}").status_code == 401


# ---------- 상호 친구 ----------

def test_한쪽만_신청하면_아직_친구가_아니다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    hb = b.get("/community/me/handle").json()["아이디"]
    r = a.post("/community/friends", json={"handle": hb}).json()
    assert r["상태"] == "보냄"
    assert a.get("/community/friends").json()["보낸신청"][0]["닉네임"] == "나"
    assert b.get("/community/friends").json()["받은신청"][0]["닉네임"] == "가"
    assert a.get("/community/friends").json()["친구"] == []


def test_양쪽이_신청하면_친구가_된다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    ha = a.get("/community/me/handle").json()["아이디"]
    hb = b.get("/community/me/handle").json()["아이디"]
    a.post("/community/friends", json={"handle": hb})
    r = b.post("/community/friends", json={"handle": ha}).json()
    assert r["상태"] == "친구"
    for c, 상대 in ((a, "나"), (b, "가")):
        목록 = c.get("/community/friends").json()
        assert [x["닉네임"] for x in 목록["친구"]] == [상대]
        assert 목록["보낸신청"] == [] and 목록["받은신청"] == []


def test_같은_사람에게_두_번_신청해도_한_번이다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    hb = b.get("/community/me/handle").json()["아이디"]
    a.post("/community/friends", json={"handle": hb})
    a.post("/community/friends", json={"handle": hb})
    assert len(a.get("/community/friends").json()["보낸신청"]) == 1


def test_나_자신과는_친구가_안_된다():
    a = _login(app, "a@x.com", "가")
    ha = a.get("/community/me/handle").json()["아이디"]
    assert a.post("/community/friends", json={"handle": ha}).status_code == 400
    assert a.get(f"/community/users/{ha}").json()["관계"] == "나"


def test_친구를_끊으면_내가_건_줄만_사라진다():
    """상대가 건 신청은 상대 것이다 — 내가 지울 수 없다."""
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    ha = a.get("/community/me/handle").json()["아이디"]
    hb = b.get("/community/me/handle").json()["아이디"]
    a.post("/community/friends", json={"handle": hb})
    b.post("/community/friends", json={"handle": ha})
    assert a.delete(f"/community/friends/{hb}").json()["상태"] == "받음"
    assert a.get("/community/friends").json()["친구"] == []
    # 상대에게는 아직 '보냄' 이 남아 있다
    assert [x["닉네임"] for x in b.get("/community/friends").json()["보낸신청"]] == ["가"]


def test_없는_아이디로_친구_신청하면_404():
    a = _login(app, "a@x.com", "가")
    assert a.post("/community/friends", json={"handle": "zzzzzz"}).status_code == 404


def test_친구_기능도_로그인이_필요하다():
    c = TestClient(app)
    assert c.get("/community/friends").status_code == 401
    assert c.post("/community/friends", json={"handle": "abcdef"}).status_code == 401


# ---------- L1·L2. 개인 채팅은 '채팅 보내기' 로만, 방 만들기는 단체만 ----------

def test_방_만들기로는_개인_채팅방을_못_만든다():
    """상대를 지정하는 자리가 아예 없어야 한다."""
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    r = a.post("/community/rooms", json={
        "name": "몰래", "room_type": "direct", "member_email": "b@x.com"})
    assert r.status_code == 200                      # 남는 값은 무시되고
    rooms = a.get("/community/rooms").json()["rooms"]
    assert [x["종류"] for x in rooms] == ["group"]    # 단체방으로 만들어진다


def test_비공개_방은_숫자_비밀번호가_필수다():
    a = _login(app, "a@x.com", "가")
    for 나쁜 in (None, "", "   ", "abc123", "12", "1" * 13, "12 34", "１２３４"):
        r = a.post("/community/rooms", json={"name": "방", "is_private": True, "password": 나쁜})
        assert r.status_code in (400, 422), 나쁜
    assert a.post("/community/rooms",
                  json={"name": "방", "is_private": True, "password": "0417"}).status_code == 200


def test_공개_방은_비밀번호가_없어도_된다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    rid = a.post("/community/rooms", json={"name": "누구나"}).json()["id"]
    assert b.post(f"/community/rooms/{rid}/join", json={}).status_code == 200


def test_채팅_보내기는_같은_방을_두_번_만들지_않는다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    ha = a.get("/community/me/handle").json()["아이디"]
    hb = b.get("/community/me/handle").json()["아이디"]
    r1 = a.post("/community/direct", json={"handle": hb}).json()
    r2 = a.post("/community/direct", json={"handle": hb}).json()
    assert r1["새로"] is True and r2["새로"] is False
    assert r1["room_id"] == r2["room_id"]
    # 상대 쪽에서 열어도 같은 방이다
    r3 = b.post("/community/direct", json={"handle": ha}).json()
    assert r3["room_id"] == r1["room_id"] and r3["새로"] is False


def test_친구가_아니어도_채팅을_보낼_수_있다():
    """아이디를 알면 보낼 수 있다 — 게시글 글쓴이에게 바로 보내는 길이다."""
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    hb = b.get("/community/me/handle").json()["아이디"]
    assert a.post("/community/direct", json={"handle": hb}).status_code == 200


def test_나_자신과는_채팅방이_안_생긴다():
    a = _login(app, "a@x.com", "가")
    ha = a.get("/community/me/handle").json()["아이디"]
    assert a.post("/community/direct", json={"handle": ha}).status_code == 400


def test_없는_아이디로는_채팅방이_안_생긴다():
    a = _login(app, "a@x.com", "가")
    assert a.post("/community/direct", json={"handle": "zzzzzz"}).status_code == 404


def test_개인_채팅방은_상대_이름으로_보인다():
    """'개인 채팅' 이라는 방 이름 대신 상대 닉네임을 보여 준다."""
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    hb = b.get("/community/me/handle").json()["아이디"]
    a.post("/community/direct", json={"handle": hb})
    방 = a.get("/community/rooms").json()["rooms"][0]
    assert 방["이름"] == "나"
    assert 방["상대"] == {"닉네임": "나", "아이디": hb}
    # 상대 쪽에서는 내 이름으로 보인다
    assert b.get("/community/rooms").json()["rooms"][0]["이름"] == "가"


def test_채팅_열기도_로그인이_필요하다():
    c = TestClient(app)
    assert c.post("/community/direct", json={"handle": "abcdef"}).status_code == 401


# ---------- L5·L6. 단체 채팅방 멤버 관리 ----------

def _방(a):
    return a.post("/community/rooms", json={"name": "토요 러닝"}).json()["id"]


def test_멤버_목록에_인원수와_방장이_있다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    hb = b.get("/community/me/handle").json()["아이디"]
    rid = _방(a)
    a.post(f"/community/rooms/{rid}/invite", json={"handle": hb})
    m = a.get(f"/community/rooms/{rid}/members").json()
    assert m["인원"] == 2 and m["내가방장"] is True
    assert [u["닉네임"] for u in m["멤버"]] == ["가", "나"]
    assert m["멤버"][0]["방장"] is True and m["멤버"][1]["방장"] is False
    assert m["멤버"][0]["나"] is True


def test_멤버_목록도_닉네임과_아이디뿐이다():
    a = _login(app, "a@x.com", "가")
    m = a.get(f"/community/rooms/{_방(a)}/members").json()
    assert set(m["멤버"][0]) == {"닉네임", "아이디", "방장", "나", "친구"}
    assert "a@x.com" not in a.get(f"/community/rooms/{_방(a)}/members").text


def test_멤버가_아니면_목록을_못_본다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    assert b.get(f"/community/rooms/{_방(a)}/members").status_code == 403


def test_방장만_내보낼_수_있다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    c = _login(app, "c@x.com", "다")
    hb = b.get("/community/me/handle").json()["아이디"]
    hc = c.get("/community/me/handle").json()["아이디"]
    rid = _방(a)
    a.post(f"/community/rooms/{rid}/invite", json={"handle": hb})
    a.post(f"/community/rooms/{rid}/invite", json={"handle": hc})
    # 멤버는 못 내보낸다
    assert b.post(f"/community/rooms/{rid}/kick", json={"handle": hc}).status_code == 403
    m = a.post(f"/community/rooms/{rid}/kick", json={"handle": hc}).json()
    assert m["인원"] == 2 and "다" not in [u["닉네임"] for u in m["멤버"]]
    # 나간 사람은 목록도 못 본다
    assert c.get(f"/community/rooms/{rid}/members").status_code == 403


def test_방장은_자기를_못_내보낸다():
    """방을 없앨 방법이 사라진다 — 나가기를 쓰게 한다."""
    a = _login(app, "a@x.com", "가")
    ha = a.get("/community/me/handle").json()["아이디"]
    rid = _방(a)
    assert a.post(f"/community/rooms/{rid}/kick", json={"handle": ha}).status_code == 400


def test_멤버가_아니면_초대할_수_없다():
    """초대는 비밀번호를 건너뛴다 — 아무나 부를 수 있으면 비공개가 무너진다."""
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    c = _login(app, "c@x.com", "다")
    hc = c.get("/community/me/handle").json()["아이디"]
    rid = a.post("/community/rooms",
                 json={"name": "비밀", "is_private": True, "password": "0417"}).json()["id"]
    assert b.post(f"/community/rooms/{rid}/invite", json={"handle": hc}).status_code == 403
    assert c.get(f"/community/rooms/{rid}/members").status_code == 403


def test_초대는_비밀번호_없이_들어가게_한다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    hb = b.get("/community/me/handle").json()["아이디"]
    rid = a.post("/community/rooms",
                 json={"name": "비밀", "is_private": True, "password": "0417"}).json()["id"]
    a.post(f"/community/rooms/{rid}/invite", json={"handle": hb})
    assert b.get(f"/community/rooms/{rid}/members").json()["인원"] == 2


def test_이미_있는_사람은_또_초대되지_않는다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    hb = b.get("/community/me/handle").json()["아이디"]
    rid = _방(a)
    a.post(f"/community/rooms/{rid}/invite", json={"handle": hb})
    assert a.post(f"/community/rooms/{rid}/invite", json={"handle": hb}).status_code == 400
    assert a.get(f"/community/rooms/{rid}/members").json()["인원"] == 2


def test_개인_채팅방에서는_멤버_관리를_안_한다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    c = _login(app, "c@x.com", "다")
    hb = b.get("/community/me/handle").json()["아이디"]
    hc = c.get("/community/me/handle").json()["아이디"]
    rid = a.post("/community/direct", json={"handle": hb}).json()["room_id"]
    assert a.post(f"/community/rooms/{rid}/invite", json={"handle": hc}).status_code == 400
    assert a.post(f"/community/rooms/{rid}/kick", json={"handle": hb}).status_code == 400


def test_나가면_목록에서_빠진다():
    a = _login(app, "a@x.com", "가")
    b = _login(app, "b@x.com", "나")
    hb = b.get("/community/me/handle").json()["아이디"]
    rid = _방(a)
    a.post(f"/community/rooms/{rid}/invite", json={"handle": hb})
    b.post(f"/community/rooms/{rid}/leave", json={})
    assert a.get(f"/community/rooms/{rid}/members").json()["인원"] == 1


def test_멤버_관리도_로그인이_필요하다():
    c = TestClient(app)
    assert c.get("/community/rooms/1/members").status_code == 401
    assert c.post("/community/rooms/1/invite", json={"handle": "abcdef"}).status_code == 401
    assert c.post("/community/rooms/1/kick", json={"handle": "abcdef"}).status_code == 401

