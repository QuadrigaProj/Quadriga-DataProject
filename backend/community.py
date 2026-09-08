"""커뮤니티 — 게시글·댓글·이모지 반응·기록 공유·운동 모임 채팅.

가입자(로그인 사용자)만 읽고 쓸 수 있다. 저장은 backend/auth.py 의 DB 계층
(SQLite 로컬 / Postgres 배포)을 그대로 쓴다.

사진·동영상은 data URL(base64)로 본문과 함께 저장한다. 용량이 커서 프로덕션은
객체 스토리지(S3 등)로 옮겨야 한다 — MEDIA_MAX_BYTES 로 크기를 제한한다.
채팅은 폴링 방식이다(GET .../messages?after=). 실시간이 필요하면 WebSocket 으로 바꾼다.
"""
from __future__ import annotations

import json
import re
import secrets
import time

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, Field

try:
    from backend import auth
except ImportError:
    import auth

# data URL 한 개의 최대 크기 (base64 인코딩 후 문자열 길이 기준)
MEDIA_MAX_BYTES = 8 * 1024 * 1024
MEDIA_MAX_COUNT = 4
ALLOWED_EMOJI = ["👍", "🔥", "💪", "👏", "🥲", "🎉"]

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS community_posts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL DEFAULT 'post',
  body       TEXT NOT NULL DEFAULT '',
  media      TEXT NOT NULL DEFAULT '[]',
  record     TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cposts_created ON community_posts(created_at DESC);
CREATE TABLE IF NOT EXISTS community_comments (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id    INTEGER NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body       TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ccomments_post ON community_comments(post_id, created_at);
CREATE TABLE IF NOT EXISTS community_reactions (
  target_type TEXT NOT NULL,
  target_id   INTEGER NOT NULL,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  emoji       TEXT NOT NULL,
  created_at  INTEGER NOT NULL,
  PRIMARY KEY (target_type, target_id, user_id, emoji)
);
CREATE TABLE IF NOT EXISTS chat_rooms (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL,
  topic      TEXT NOT NULL DEFAULT '',
  room_type  TEXT NOT NULL DEFAULT 'group',
  is_private INTEGER NOT NULL DEFAULT 0,
  password_salt TEXT,
  password_hash TEXT,
  created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_members (
  room_id   INTEGER NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  joined_at INTEGER NOT NULL,
  PRIMARY KEY (room_id, user_id)
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id    INTEGER NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body       TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cmsg_room ON chat_messages(room_id, id);

/* 앱 내 아이디 — 다른 사람에게 보이는 유일한 식별자다.
   이메일로 사람을 찾게 두면 이메일이 곧 검색키가 된다(가입 여부가 새어 나간다). */
CREATE TABLE IF NOT EXISTS user_handles (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  handle  TEXT NOT NULL UNIQUE
);

/* 상호 친구 — 한 줄이 '신청' 이고, 양쪽 줄이 다 있으면 친구다.
   (a,b) 와 (b,a) 를 각각 두어 "내가 건 신청" 과 "받은 신청" 을 그대로 읽는다. */
CREATE TABLE IF NOT EXISTS friend_links (
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  other_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, other_id)
);
CREATE INDEX IF NOT EXISTS idx_friend_other ON friend_links(other_id);

/* 초대 — 넣는 순간 멤버가 되지 않는다. 받은 사람이 수락해야 들어간다.
   비공개 방이면 그때 비밀번호를 넣어야 한다(초대가 비밀번호를 건너뛰지 않게). */
CREATE TABLE IF NOT EXISTS chat_invites (
  room_id    INTEGER NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  invited_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (room_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_cinv_user ON chat_invites(user_id);

/* 채팅 요청 — 친구가 아닌 사람에게는 바로 말을 걸 수 없다.
   요청을 보내고 상대가 받아 줘야 1:1 방이 열린다. 아이디만 알면 아무나
   말을 걸 수 있으면 그게 곧 스팸 통로다. 친구끼리는 이 단계가 없다. */
CREATE TABLE IF NOT EXISTS chat_requests (
  from_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  to_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (from_id, to_id)
);
CREATE INDEX IF NOT EXISTS idx_creq_to ON chat_requests(to_id);
"""
SCHEMA_PG = (SCHEMA_SQLITE
             .replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"))


def init_db() -> None:
    schema = SCHEMA_PG if auth.is_postgres() else SCHEMA_SQLITE
    with auth.db() as con:
        for stmt in filter(str.strip, schema.split(";")):
            con.execute(stmt)
        # 이미 만들어진 서비스 DB에도 채팅방 설정 컬럼을 안전하게 더한다.
        if auth.is_postgres():
            for column in ("room_type TEXT NOT NULL DEFAULT 'group'",
                           "is_private INTEGER NOT NULL DEFAULT 0",
                           "password_salt TEXT", "password_hash TEXT"):
                con.execute(f"ALTER TABLE chat_rooms ADD COLUMN IF NOT EXISTS {column}")
        else:
            columns = {row["name"] for row in con.execute("PRAGMA table_info(chat_rooms)").fetchall()}
            for column in ("room_type TEXT NOT NULL DEFAULT 'group'",
                           "is_private INTEGER NOT NULL DEFAULT 0",
                           "password_salt TEXT", "password_hash TEXT"):
                if column.split()[0] not in columns:
                    con.execute(f"ALTER TABLE chat_rooms ADD COLUMN {column}")


DATA_URL = re.compile(r"^data:(image|video)/[\w.+-]+;base64,[A-Za-z0-9+/=\s]+$")


# 앱 내 아이디에 쓰는 글자. 헷갈리는 0/O, 1/l 은 뺀다.
HANDLE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
HANDLE_LEN = 6
HANDLE_RE = re.compile(r"^[a-z0-9]{3,20}$")


def _new_handle(con) -> str:
    """안 쓰는 아이디를 하나 만든다. 이름에서 만들지 않는다 — 본명이 새어 나간다."""
    for _ in range(50):
        h = "".join(secrets.choice(HANDLE_ALPHABET) for _ in range(HANDLE_LEN))
        if not con.execute("SELECT 1 FROM user_handles WHERE handle=?", (h,)).fetchone():
            return h
    raise HTTPException(503, "아이디를 만들지 못했어요. 잠시 뒤 다시 시도해 주세요.")


def _handle_in(con, user_id: int) -> str:
    """읽거나, 없으면 그 자리에서 만든다.

    다른 사람에게 보이는 유일한 식별자라 비어 있으면 안 된다 — 자기 아이디를
    한 번도 안 본 사람이 남의 화면에 '@없음' 으로 뜨게 된다.
    """
    r = con.execute("SELECT handle FROM user_handles WHERE user_id=?", (user_id,)).fetchone()
    if r:
        return r["handle"]
    h = _new_handle(con)
    con.execute("INSERT INTO user_handles (user_id, handle) VALUES (?,?)", (user_id, h))
    return h


def handle_for(user_id: int) -> str:
    """그 사람의 앱 내 아이디. 없으면 이때 만들어 준다(예전 가입자)."""
    with auth.db() as con:
        return _handle_in(con, user_id)


def _public_user(con, user_id: int) -> dict:
    """다른 사람에게 보여 주는 전부 — 닉네임과 아이디뿐이다.

    체력나이·측정 기록·이메일은 넣지 않는다. 여기서 한 번 막으면 화면이
    실수로 흘릴 일이 없다.
    """
    r = con.execute("SELECT display_name FROM users WHERE id=?", (user_id,)).fetchone()
    if not r:
        return {"아이디": None, "닉네임": "(탈퇴한 회원)"}
    return {"아이디": _handle_in(con, user_id), "닉네임": r["display_name"]}


def find_by_handle(handle: str) -> dict | None:
    """아이디로 사람 찾기. 정확히 맞아야 찾힌다 — 부분 검색은 목록 훑기가 된다."""
    handle = (handle or "").strip().lower()
    if not HANDLE_RE.match(handle):
        return None
    with auth.db() as con:
        r = con.execute("SELECT user_id FROM user_handles WHERE handle=?", (handle,)).fetchone()
        if not r:
            return None
        return {**_public_user(con, r["user_id"]), "user_id": r["user_id"]}


# ---------- 상호 친구 ----------

def _link(con, a: int, b: int) -> bool:
    return bool(con.execute("SELECT 1 FROM friend_links WHERE user_id=? AND other_id=?",
                            (a, b)).fetchone())


def friend_state(con, me: int, other: int) -> str:
    """'친구' | '보냄' | '받음' | '없음'"""
    if me == other:
        return "나"
    보냄, 받음 = _link(con, me, other), _link(con, other, me)
    if 보냄 and 받음:
        return "친구"
    return "보냄" if 보냄 else ("받음" if 받음 else "없음")


def are_friends(con, a: int, b: int) -> bool:
    return _link(con, a, b) and _link(con, b, a)


def request_friend(me: int, handle: str) -> dict:
    """아이디로 친구 신청. 상대가 이미 나에게 걸어 뒀으면 그 자리에서 친구가 된다."""
    target = find_by_handle(handle)
    if not target:
        raise HTTPException(404, "그 아이디를 쓰는 회원이 없어요.")
    other = target["user_id"]
    if other == me:
        raise HTTPException(400, "나 자신과는 친구가 될 수 없어요.")
    with auth.db() as con:
        if not _link(con, me, other):
            con.execute("INSERT INTO friend_links (user_id, other_id, created_at) VALUES (?,?,?)",
                        (me, other, int(time.time())))
        return {"상태": friend_state(con, me, other),
                "상대": {k: v for k, v in target.items() if k != "user_id"}}


def unfriend(me: int, handle: str) -> dict:
    """내가 건 줄만 지운다. 상대가 건 줄은 상대 것이다."""
    target = find_by_handle(handle)
    if not target:
        raise HTTPException(404, "그 아이디를 쓰는 회원이 없어요.")
    with auth.db() as con:
        con.execute("DELETE FROM friend_links WHERE user_id=? AND other_id=?",
                    (me, target["user_id"]))
        return {"상태": friend_state(con, me, target["user_id"])}


def friends(me: int) -> dict:
    """친구·보낸 신청·받은 신청을 한 번에."""
    with auth.db() as con:
        보냄 = [r["other_id"] for r in con.execute(
            "SELECT other_id FROM friend_links WHERE user_id=?", (me,)).fetchall()]
        받음 = [r["user_id"] for r in con.execute(
            "SELECT user_id FROM friend_links WHERE other_id=?", (me,)).fetchall()]
        보냄셋, 받음셋 = set(보냄), set(받음)
        친구 = 보냄셋 & 받음셋
        return {
            "친구": [_public_user(con, u) for u in sorted(친구)],
            "보낸신청": [_public_user(con, u) for u in sorted(보냄셋 - 친구)],
            "받은신청": [_public_user(con, u) for u in sorted(받음셋 - 친구)],
        }


def _clean_media(media) -> str:
    """[{type, url, name}] 검증 → JSON 문자열."""
    if not media:
        return "[]"
    if not isinstance(media, list) or len(media) > MEDIA_MAX_COUNT:
        raise HTTPException(400, f"사진·동영상은 최대 {MEDIA_MAX_COUNT}개까지예요.")
    out = []
    for m in media:
        url = (m or {}).get("url", "")
        if not DATA_URL.match(url):
            raise HTTPException(400, "사진·동영상 형식을 확인해 주세요.")
        if len(url) > MEDIA_MAX_BYTES:
            raise HTTPException(400, "파일이 너무 커요. 더 작은 파일로 올려주세요.")
        out.append({"type": "video" if url.startswith("data:video") else "image",
                    "url": url, "name": str(m.get("name", ""))[:120]})
    return json.dumps(out, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 게시글 · 댓글 · 반응
# ---------------------------------------------------------------------------

def create_post(user_id: int, *, body: str = "", media=None, kind: str = "post",
                record: dict | None = None) -> int:
    body = (body or "").strip()
    media_json = _clean_media(media)
    if not body and media_json == "[]" and not record:
        raise HTTPException(400, "내용이나 사진을 하나는 넣어주세요.")
    with auth.db() as con:
        return con.insert_id(
            "INSERT INTO community_posts (user_id, kind, body, media, record, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (user_id, kind, body[:4000], media_json,
             json.dumps(record, ensure_ascii=False) if record else None, int(time.time())))


def _reaction_summary(con, target_type: str, ids: list[int], me: int) -> dict[int, dict]:
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    rows = con.execute(
        f"SELECT target_id, emoji, user_id FROM community_reactions"
        f" WHERE target_type=? AND target_id IN ({marks})",
        (target_type, *ids)).fetchall()
    out: dict[int, dict] = {i: {"counts": {}, "mine": []} for i in ids}
    for r in rows:
        d = out[r["target_id"]]
        d["counts"][r["emoji"]] = d["counts"].get(r["emoji"], 0) + 1
        if r["user_id"] == me:
            d["mine"].append(r["emoji"])
    return out


def list_posts(me: int, *, before: int | None = None, limit: int = 20) -> list[dict]:
    limit = max(1, min(50, limit))
    with auth.db() as con:
        sql = ("SELECT p.*, u.display_name FROM community_posts p"
               " JOIN users u ON u.id = p.user_id")
        params: tuple = ()
        if before:
            sql += " WHERE p.id < ?"
            params = (before,)
        sql += " ORDER BY p.id DESC LIMIT ?"
        rows = con.execute(sql, (*params, limit)).fetchall()
        ids = [r["id"] for r in rows]
        counts = {}
        if ids:
            marks = ",".join("?" for _ in ids)
            for r in con.execute(
                    f"SELECT post_id, COUNT(*) c FROM community_comments"
                    f" WHERE post_id IN ({marks}) GROUP BY post_id", ids).fetchall():
                counts[r["post_id"]] = r["c"]
        reacts = _reaction_summary(con, "post", ids, me)
        핸들 = {u: _handle_in(con, u) for u in {r["user_id"] for r in rows}}
    return [_post_dict(r, me, counts.get(r["id"], 0), reacts.get(r["id"]),
                       핸들.get(r["user_id"])) for r in rows]


def _post_dict(r, me: int, comment_count: int, react: dict | None,
               handle: str | None = None) -> dict:
    return {
        "id": r["id"],
        "작성자": r["display_name"],
        # 프로필을 열려면 아이디가 있어야 한다. 닉네임은 겹칠 수 있다.
        "작성자아이디": handle,
        "내글": r["user_id"] == me,
        "종류": r["kind"],
        "본문": r["body"],
        "미디어": json.loads(r["media"] or "[]"),
        "기록": json.loads(r["record"]) if r["record"] else None,
        "작성시각": r["created_at"],
        "댓글수": comment_count,
        "반응": (react or {"counts": {}, "mine": []}),
    }


def get_post(me: int, post_id: int) -> dict:
    with auth.db() as con:
        r = con.execute(
            "SELECT p.*, u.display_name FROM community_posts p"
            " JOIN users u ON u.id = p.user_id WHERE p.id=?", (post_id,)).fetchone()
        if not r:
            raise HTTPException(404, "글을 찾을 수 없어요.")
        cs = con.execute(
            "SELECT c.*, u.display_name FROM community_comments c"
            " JOIN users u ON u.id = c.user_id WHERE c.post_id=? ORDER BY c.id", (post_id,)).fetchall()
        cids = [c["id"] for c in cs]
        preact = _reaction_summary(con, "post", [post_id], me)
        creact = _reaction_summary(con, "comment", cids, me)
        핸들 = {u: _handle_in(con, u)
              for u in {r["user_id"], *(c["user_id"] for c in cs)}}
    post = _post_dict(r, me, len(cs), preact.get(post_id), 핸들.get(r["user_id"]))
    post["댓글"] = [{
        "id": c["id"], "작성자": c["display_name"], "내글": c["user_id"] == me,
        "작성자아이디": 핸들.get(c["user_id"]),
        "본문": c["body"], "작성시각": c["created_at"],
        "반응": creact.get(c["id"], {"counts": {}, "mine": []}),
    } for c in cs]
    return post


def add_comment(user_id: int, post_id: int, body: str) -> int:
    body = (body or "").strip()
    if not body:
        raise HTTPException(400, "댓글 내용을 입력해 주세요.")
    with auth.db() as con:
        if not con.execute("SELECT 1 FROM community_posts WHERE id=?", (post_id,)).fetchone():
            raise HTTPException(404, "글을 찾을 수 없어요.")
        return con.insert_id(
            "INSERT INTO community_comments (post_id, user_id, body, created_at) VALUES (?,?,?,?)",
            (post_id, user_id, body[:2000], int(time.time())))


def toggle_reaction(user_id: int, target_type: str, target_id: int, emoji: str) -> dict:
    if target_type not in ("post", "comment"):
        raise HTTPException(400, "잘못된 대상이에요.")
    if emoji not in ALLOWED_EMOJI:
        raise HTTPException(400, "쓸 수 없는 이모지예요.")
    with auth.db() as con:
        hit = con.execute(
            "SELECT 1 FROM community_reactions WHERE target_type=? AND target_id=? AND user_id=? AND emoji=?",
            (target_type, target_id, user_id, emoji)).fetchone()
        if hit:
            con.execute(
                "DELETE FROM community_reactions WHERE target_type=? AND target_id=? AND user_id=? AND emoji=?",
                (target_type, target_id, user_id, emoji))
        else:
            con.execute(
                "INSERT INTO community_reactions (target_type, target_id, user_id, emoji, created_at)"
                " VALUES (?,?,?,?,?)", (target_type, target_id, user_id, emoji, int(time.time())))
        summary = _reaction_summary(con, target_type, [target_id], user_id)
    return summary.get(target_id, {"counts": {}, "mine": []})


def delete_post(user_id: int, post_id: int) -> None:
    with auth.db() as con:
        r = con.execute("SELECT user_id FROM community_posts WHERE id=?", (post_id,)).fetchone()
        if not r:
            raise HTTPException(404, "글을 찾을 수 없어요.")
        if r["user_id"] != user_id:
            raise HTTPException(403, "내 글만 지울 수 있어요.")
        con.execute("DELETE FROM community_posts WHERE id=?", (post_id,))


# ---------------------------------------------------------------------------
# 운동 모임 채팅
# ---------------------------------------------------------------------------

def list_rooms(me: int) -> list[dict]:
    """공개 단체 채팅방은 전부, 개인 채팅은 내가 속한 것만 돌려준다.

    단체 채팅방은 가입 전에도 둘러보고 들어갈 수 있어야 하니 전부 보여주지만,
    개인(1:1) 채팅은 참여자 두 사람만의 것이다. 필터 없이 전부 내보내면
    나와 무관한 두 사람의 1:1 대화 존재와 상대 닉네임까지 아무 로그인
    사용자에게 새어 나간다.
    """
    with auth.db() as con:
        rows = con.execute(
            "SELECT r.*, "
            " (SELECT COUNT(*) FROM chat_members m WHERE m.room_id=r.id) AS 인원,"
            " (SELECT COUNT(*) FROM chat_messages g WHERE g.room_id=r.id) AS 메시지수,"
            " (SELECT 1 FROM chat_members m WHERE m.room_id=r.id AND m.user_id=?) AS 참여"
            " FROM chat_rooms r"
            " WHERE r.room_type <> 'direct' OR"
            "  (SELECT 1 FROM chat_members m WHERE m.room_id=r.id AND m.user_id=?)"
            " ORDER BY r.id DESC", (me, me)).fetchall()
    out = []
    with auth.db() as con:
        for r in rows:
            방 = {"id": r["id"], "이름": r["name"], "주제": r["topic"],
                 "종류": r["room_type"], "비공개": bool(r["is_private"]),
                 "방장": r["created_by"] == me, "인원": r["인원"],
                 "메시지수": r["메시지수"], "참여중": bool(r["참여"])}
            if r["room_type"] == "direct":
                # 개인 채팅은 방 이름이 아니라 상대 이름으로 보여 준다
                상대 = con.execute(
                    "SELECT user_id FROM chat_members WHERE room_id=? AND user_id<>?",
                    (r["id"], me)).fetchone()
                if 상대:
                    방["상대"] = _public_user(con, 상대["user_id"])
                    방["이름"] = 방["상대"]["닉네임"]
            out.append(방)
    return out


# 비공개 방 비밀번호는 숫자만 받는다(요청 사항). 사람들이 다른 서비스에서 쓰는
# 비밀번호를 그대로 넣지 않게 하는 효과도 있다.
# \d 는 전각 숫자(１２３４)까지 받는다. 키패드로 칠 수 있는 숫자만 받는다.
ROOM_PIN_RE = re.compile(r"^[0-9]{4,12}$")


def _check_pin(password: str | None) -> str:
    pin = (password or "").strip()
    if not ROOM_PIN_RE.match(pin):
        raise HTTPException(400, "비공개 방 비밀번호는 숫자 4~12자리로 정해 주세요.")
    return pin


def _password_values(password: str) -> tuple[str, str]:
    """채팅방 비밀번호를 사용자 비밀번호와 같은 scrypt 방식으로 저장한다."""
    salt, password_hash = auth.hash_password(password)
    return salt.hex(), password_hash.hex()


def create_room(user_id: int, name: str, topic: str = "", *,
                is_private: bool = False, password: str | None = None) -> int:
    """사용자가 만드는 것은 **단체 채팅방뿐**이다 (L2).

    개인 채팅방은 만들지 않는다 — 상대 프로필에서 '채팅 보내기' 를 누를 때
    open_direct() 가 만든다. 방 만들기 화면에서 상대를 지정하게 두면
    아무나 대화를 열 수 있고, 이메일로 상대를 찾게 되어 가입 여부까지 샌다.
    """
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, "모임 이름을 입력해 주세요.")
    salt, password_hash = (None, None)
    if is_private:
        salt, password_hash = _password_values(_check_pin(password))
    with auth.db() as con:
        rid = con.insert_id(
            "INSERT INTO chat_rooms (name, topic, room_type, is_private, password_salt, password_hash, created_by, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (name[:80], (topic or "").strip()[:200], "group", int(is_private), salt,
             password_hash, user_id, int(time.time())))
        con.execute("INSERT INTO chat_members (room_id, user_id, joined_at) VALUES (?,?,?)",
                    (rid, user_id, int(time.time())))
    return rid


def _direct_room(con, a: int, b: int):
    return con.execute(
        "SELECT r.id FROM chat_rooms r"
        " WHERE r.room_type='direct'"
        "   AND EXISTS (SELECT 1 FROM chat_members m WHERE m.room_id=r.id AND m.user_id=?)"
        "   AND EXISTS (SELECT 1 FROM chat_members m WHERE m.room_id=r.id AND m.user_id=?)"
        "   AND (SELECT COUNT(*) FROM chat_members m WHERE m.room_id=r.id)=2"
        " ORDER BY r.id LIMIT 1", (a, b)).fetchone()


def _make_direct(con, a: int, b: int) -> int:
    now = int(time.time())
    rid = con.insert_id(
        "INSERT INTO chat_rooms (name, topic, room_type, is_private,"
        " password_salt, password_hash, created_by, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        ("개인 채팅", "", "direct", 0, None, None, a, now))
    for u in (a, b):
        con.execute("INSERT INTO chat_members (room_id, user_id, joined_at) VALUES (?,?,?)",
                    (rid, u, now))
    # 방이 생겼으면 오간 요청은 의미가 없다
    con.execute("DELETE FROM chat_requests WHERE (from_id=? AND to_id=?)"
                " OR (from_id=? AND to_id=?)", (a, b, b, a))
    return rid


def open_direct(me: int, handle: str) -> dict:
    """상대와의 1:1 방을 연다.

    친구면 바로 열린다. 친구가 아니면 **요청만 보내고**, 상대가 받아 줘야
    방이 생긴다. 이미 대화한 사이(방이 있음)면 요청 없이 그대로 연다.
    상대가 먼저 나에게 요청해 뒀으면 그 자리에서 열어 준다.

    아이디로만 연다 — 이메일을 받으면 그 주소의 가입 여부가 새어 나간다.
    """
    target = find_by_handle(handle)
    if not target:
        raise HTTPException(404, "그 아이디를 쓰는 회원이 없어요.")
    other = target["user_id"]
    if other == me:
        raise HTTPException(400, "나 자신과는 채팅할 수 없어요.")

    with auth.db() as con:
        기존 = _direct_room(con, me, other)
        if 기존:
            return {"room_id": 기존["id"], "새로": False, "상태": "열림",
                    "상대": _public_user(con, other)}

        받은것 = con.execute("SELECT 1 FROM chat_requests WHERE from_id=? AND to_id=?",
                           (other, me)).fetchone()
        if are_friends(con, me, other) or 받은것:
            rid = _make_direct(con, me, other)
            return {"room_id": rid, "새로": True, "상태": "열림",
                    "상대": _public_user(con, other)}

        if not con.execute("SELECT 1 FROM chat_requests WHERE from_id=? AND to_id=?",
                           (me, other)).fetchone():
            con.execute("INSERT INTO chat_requests (from_id, to_id, created_at)"
                        " VALUES (?,?,?)", (me, other, int(time.time())))
        return {"room_id": None, "새로": False, "상태": "요청함",
                "상대": _public_user(con, other)}


def chat_requests(me: int) -> dict:
    """받은/보낸 채팅 요청."""
    with auth.db() as con:
        받음 = [_public_user(con, r["from_id"]) for r in con.execute(
            "SELECT from_id FROM chat_requests WHERE to_id=? ORDER BY created_at DESC",
            (me,)).fetchall()]
        보냄 = [_public_user(con, r["to_id"]) for r in con.execute(
            "SELECT to_id FROM chat_requests WHERE from_id=? ORDER BY created_at DESC",
            (me,)).fetchall()]
    return {"받은요청": 받음, "보낸요청": 보냄}


def accept_chat(me: int, handle: str) -> dict:
    """받은 요청을 받아 준다 → 1:1 방이 열린다. 친구가 아니어도 된다."""
    target = find_by_handle(handle)
    if not target:
        raise HTTPException(404, "그 아이디를 쓰는 회원이 없어요.")
    other = target["user_id"]
    with auth.db() as con:
        if not con.execute("SELECT 1 FROM chat_requests WHERE from_id=? AND to_id=?",
                           (other, me)).fetchone():
            raise HTTPException(404, "받은 요청이 없어요.")
        기존 = _direct_room(con, me, other)
        rid = 기존["id"] if 기존 else _make_direct(con, me, other)
        con.execute("DELETE FROM chat_requests WHERE from_id=? AND to_id=?", (other, me))
        return {"room_id": rid, "상대": _public_user(con, other)}


def decline_chat(me: int, handle: str) -> dict:
    """받은 요청을 거절하거나, 내가 보낸 요청을 거둔다."""
    target = find_by_handle(handle)
    if not target:
        raise HTTPException(404, "그 아이디를 쓰는 회원이 없어요.")
    other = target["user_id"]
    with auth.db() as con:
        con.execute("DELETE FROM chat_requests WHERE (from_id=? AND to_id=?)"
                    " OR (from_id=? AND to_id=?)", (other, me, me, other))
    return {"ok": True}


def join_room(user_id: int, room_id: int, password: str | None = None) -> None:
    with auth.db() as con:
        room = con.execute("SELECT * FROM chat_rooms WHERE id=?", (room_id,)).fetchone()
        if not room:
            raise HTTPException(404, "모임을 찾을 수 없어요.")
        if con.execute("SELECT 1 FROM chat_members WHERE room_id=? AND user_id=?",
                       (room_id, user_id)).fetchone():
            return
        if room["room_type"] == "direct":
            raise HTTPException(403, "개인 채팅방에는 초대된 사람만 참여할 수 있어요.")
        if room["is_private"]:
            try:
                valid = auth.verify_password(password or "", bytes.fromhex(room["password_salt"]),
                                             bytes.fromhex(room["password_hash"]))
            except (TypeError, ValueError):
                valid = False
            if not valid:
                raise HTTPException(403, "비공개 방 비밀번호가 맞지 않아요.")
        con.execute("INSERT INTO chat_members (room_id, user_id, joined_at) VALUES (?,?,?)",
                    (room_id, user_id, int(time.time())))


def change_room_password(user_id: int, room_id: int, password: str) -> None:
    salt, password_hash = _password_values(_check_pin(password))
    with auth.db() as con:
        room = con.execute("SELECT * FROM chat_rooms WHERE id=?", (room_id,)).fetchone()
        if not room:
            raise HTTPException(404, "모임을 찾을 수 없어요.")
        if room["created_by"] != user_id:
            raise HTTPException(403, "방장만 비밀번호를 바꿀 수 있어요.")
        if room["room_type"] != "group" or not room["is_private"]:
            raise HTTPException(400, "비공개 단체 채팅방에서만 비밀번호를 바꿀 수 있어요.")
        con.execute("UPDATE chat_rooms SET password_salt=?, password_hash=? WHERE id=?",
                    (salt, password_hash, room_id))


def room_members(me: int, room_id: int) -> dict:
    """단체 채팅방 멤버 목록 (L6).

    멤버만 볼 수 있다. 보이는 것은 닉네임과 아이디뿐이다.
    """
    with auth.db() as con:
        room = con.execute("SELECT * FROM chat_rooms WHERE id=?", (room_id,)).fetchone()
        if not room:
            raise HTTPException(404, "모임을 찾을 수 없어요.")
        if not _is_member(con, room_id, me):
            raise HTTPException(403, "참여한 사람만 멤버를 볼 수 있어요.")
        rows = con.execute(
            "SELECT user_id FROM chat_members WHERE room_id=? ORDER BY joined_at, user_id",
            (room_id,)).fetchall()
        방장 = room["created_by"]
        멤버 = []
        for r in rows:
            u = _public_user(con, r["user_id"])
            u["방장"] = r["user_id"] == 방장
            u["나"] = r["user_id"] == me
            u["친구"] = are_friends(con, me, r["user_id"])
            멤버.append(u)
        초대중 = [_public_user(con, r["user_id"]) for r in con.execute(
            "SELECT user_id FROM chat_invites WHERE room_id=? ORDER BY created_at",
            (room_id,)).fetchall()]
    return {"이름": room["name"], "종류": room["room_type"],
            "내가방장": 방장 == me, "인원": len(멤버), "멤버": 멤버,
            "초대중": 초대중}


def kick_member(me: int, room_id: int, handle: str) -> dict:
    """방장이 멤버를 내보낸다 (L6). 방장 자신은 못 내보낸다 — 나가기를 쓴다."""
    target = find_by_handle(handle)
    if not target:
        raise HTTPException(404, "그 아이디를 쓰는 회원이 없어요.")
    with auth.db() as con:
        room = con.execute("SELECT * FROM chat_rooms WHERE id=?", (room_id,)).fetchone()
        if not room:
            raise HTTPException(404, "모임을 찾을 수 없어요.")
        # 방 종류가 더 근본적인 조건이다. 개인 채팅방이면 누가 묻든 안 되는 일이라
        # 방장 여부보다 먼저 본다.
        if room["room_type"] != "group":
            raise HTTPException(400, "단체 채팅방에서만 할 수 있어요.")
        if room["created_by"] != me:
            raise HTTPException(403, "방장만 멤버를 내보낼 수 있어요.")
        if target["user_id"] == me:
            raise HTTPException(400, "방장은 내보낼 수 없어요. 나가기를 눌러 주세요.")
        if not _is_member(con, room_id, target["user_id"]):
            raise HTTPException(404, "그 사람은 이 모임에 없어요.")
        con.execute("DELETE FROM chat_members WHERE room_id=? AND user_id=?",
                    (room_id, target["user_id"]))
    return room_members(me, room_id)


def invite_member(me: int, room_id: int, handle: str) -> dict:
    """멤버가 사람을 초대한다 (L6).

    **초대만 남기고 넣지는 않는다.** 받은 사람이 수락해야 들어가고,
    비공개 방이면 그때 비밀번호를 넣어야 한다. 초대가 비밀번호를 건너뛰면
    비공개가 무너진다.
    """
    target = find_by_handle(handle)
    if not target:
        raise HTTPException(404, "그 아이디를 쓰는 회원이 없어요.")
    with auth.db() as con:
        room = con.execute("SELECT * FROM chat_rooms WHERE id=?", (room_id,)).fetchone()
        if not room:
            raise HTTPException(404, "모임을 찾을 수 없어요.")
        if room["room_type"] != "group":
            raise HTTPException(400, "단체 채팅방에서만 할 수 있어요.")
        if not _is_member(con, room_id, me):
            raise HTTPException(403, "참여한 사람만 초대할 수 있어요.")
        if _is_member(con, room_id, target["user_id"]):
            raise HTTPException(400, "이미 참여 중인 사람이에요.")
        if con.execute("SELECT 1 FROM chat_invites WHERE room_id=? AND user_id=?",
                       (room_id, target["user_id"])).fetchone():
            raise HTTPException(400, "이미 초대한 사람이에요.")
        con.execute("INSERT INTO chat_invites (room_id, user_id, invited_by, created_at)"
                    " VALUES (?,?,?,?)",
                    (room_id, target["user_id"], me, int(time.time())))
    return room_members(me, room_id)


def cancel_invite(me: int, room_id: int, handle: str) -> dict:
    """보낸 초대를 거둔다. 멤버면 누구든 거둘 수 있다."""
    target = find_by_handle(handle)
    if not target:
        raise HTTPException(404, "그 아이디를 쓰는 회원이 없어요.")
    with auth.db() as con:
        if not _is_member(con, room_id, me):
            raise HTTPException(403, "참여한 사람만 할 수 있어요.")
        con.execute("DELETE FROM chat_invites WHERE room_id=? AND user_id=?",
                    (room_id, target["user_id"]))
    return room_members(me, room_id)


def my_invites(me: int) -> list[dict]:
    """내가 받은 초대. 비공개 방이면 수락할 때 비밀번호를 받아야 한다."""
    with auth.db() as con:
        rows = con.execute(
            "SELECT i.room_id, i.invited_by, i.created_at,"
            " r.name, r.is_private,"
            " (SELECT COUNT(*) FROM chat_members m WHERE m.room_id=r.id) AS 인원"
            " FROM chat_invites i JOIN chat_rooms r ON r.id=i.room_id"
            " WHERE i.user_id=? ORDER BY i.created_at DESC", (me,)).fetchall()
        return [{"room_id": r["room_id"], "이름": r["name"],
                 "비공개": bool(r["is_private"]), "인원": r["인원"],
                 "초대한사람": _public_user(con, r["invited_by"])} for r in rows]


def accept_invite(me: int, room_id: int, password: str | None = None) -> dict:
    """받은 초대를 수락한다. 비공개 방이면 비밀번호가 맞아야 들어간다."""
    with auth.db() as con:
        inv = con.execute("SELECT 1 FROM chat_invites WHERE room_id=? AND user_id=?",
                          (room_id, me)).fetchone()
        if not inv:
            raise HTTPException(404, "받은 초대가 없어요.")
    join_room(me, room_id, password)          # 비밀번호 확인은 여기서 한다
    with auth.db() as con:
        con.execute("DELETE FROM chat_invites WHERE room_id=? AND user_id=?", (room_id, me))
    return {"ok": True}


def decline_invite(me: int, room_id: int) -> dict:
    with auth.db() as con:
        con.execute("DELETE FROM chat_invites WHERE room_id=? AND user_id=?", (room_id, me))
    return {"ok": True}


def delete_room(user_id: int, room_id: int) -> None:
    """방장이 단체 채팅방을 통째로 없앤다 ("방 폭파").

    멤버·초대·메시지는 chat_rooms 의 ON DELETE CASCADE 로 함께 지워진다
    (auth.db() 가 SQLite에도 PRAGMA foreign_keys=ON 을 켜 둬서 실제로 동작한다).
    나가기(leave_room)와 달리 되돌릴 수 없고, 방에 있던 모두가 한 번에 나가진다.
    개인 채팅(1:1)은 대상이 아니다 — 상대가 있는 대화를 혼자 없앨 수는 없다.
    """
    with auth.db() as con:
        room = con.execute("SELECT * FROM chat_rooms WHERE id=?", (room_id,)).fetchone()
        if not room:
            raise HTTPException(404, "모임을 찾을 수 없어요.")
        if room["room_type"] != "group":
            raise HTTPException(400, "단체 채팅방만 없앨 수 있어요.")
        if room["created_by"] != user_id:
            raise HTTPException(403, "방장만 방을 없앨 수 있어요.")
        con.execute("DELETE FROM chat_rooms WHERE id=?", (room_id,))


def leave_room(user_id: int, room_id: int) -> None:
    with auth.db() as con:
        con.execute("DELETE FROM chat_members WHERE room_id=? AND user_id=?", (room_id, user_id))
        # 나간 사람에게 남아 있던 초대는 의미가 없다
        con.execute("DELETE FROM chat_invites WHERE room_id=? AND user_id=?", (room_id, user_id))


def _is_member(con, room_id: int, user_id: int) -> bool:
    return bool(con.execute("SELECT 1 FROM chat_members WHERE room_id=? AND user_id=?",
                            (room_id, user_id)).fetchone())


def messages(user_id: int, room_id: int, after: int = 0, limit: int = 50) -> list[dict]:
    with auth.db() as con:
        if not _is_member(con, room_id, user_id):
            raise HTTPException(403, "먼저 모임에 참여해 주세요.")
        rows = con.execute(
            "SELECT g.*, u.display_name FROM chat_messages g JOIN users u ON u.id=g.user_id"
            " WHERE g.room_id=? AND g.id > ? ORDER BY g.id LIMIT ?",
            (room_id, after, max(1, min(200, limit)))).fetchall()
    return [{"id": r["id"], "작성자": r["display_name"], "내글": r["user_id"] == user_id,
             "본문": r["body"], "작성시각": r["created_at"]} for r in rows]


def send_message(user_id: int, room_id: int, body: str) -> int:
    body = (body or "").strip()
    if not body:
        raise HTTPException(400, "메시지를 입력해 주세요.")
    with auth.db() as con:
        if not _is_member(con, room_id, user_id):
            raise HTTPException(403, "먼저 모임에 참여해 주세요.")
        return con.insert_id(
            "INSERT INTO chat_messages (room_id, user_id, body, created_at) VALUES (?,?,?,?)",
            (room_id, user_id, body[:2000], int(time.time())))


# ---------------------------------------------------------------------------
# 라우터
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/community", tags=["community"])


def _uid(token: str | None) -> int:
    user = auth.user_for_token(token)
    if not user:
        raise HTTPException(401, "커뮤니티는 로그인 후 이용할 수 있어요.")
    return user["id"]


class PostIn(BaseModel):
    body: str = Field("", max_length=4000)
    media: list[dict] = Field(default_factory=list)
    kind: str = Field("post", pattern="^(post|record)$")
    record: dict | None = None


class CommentIn(BaseModel):
    body: str = Field(..., max_length=2000)


class ReactionIn(BaseModel):
    target_type: str = Field(..., pattern="^(post|comment)$")
    target_id: int
    emoji: str


class RoomIn(BaseModel):
    """사용자가 만드는 것은 단체 채팅방뿐이다. 상대를 지정하는 자리가 없다 (L2)."""
    name: str = Field(..., max_length=80)
    topic: str = Field("", max_length=200)
    is_private: bool = False
    password: str | None = Field(None, max_length=12)


class HandleIn(BaseModel):
    handle: str = Field(..., max_length=20)


class RoomJoinIn(BaseModel):
    password: str | None = Field(None, max_length=128)


class RoomPasswordIn(BaseModel):
    password: str = Field(..., max_length=128)


class MessageIn(BaseModel):
    body: str = Field(..., max_length=2000)


@router.get("/meta")
def meta() -> dict:
    return {"이모지": ALLOWED_EMOJI, "미디어최대개수": MEDIA_MAX_COUNT,
            "미디어최대바이트": MEDIA_MAX_BYTES}


@router.get("/posts")
def get_posts(before: int | None = None, limit: int = 20,
              quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    return {"posts": list_posts(me, before=before, limit=limit)}


@router.post("/posts")
def post_new(body: PostIn, quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    pid = create_post(me, body=body.body, media=body.media, kind=body.kind, record=body.record)
    return get_post(me, pid)


@router.get("/posts/{post_id}")
def post_detail(post_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    return get_post(_uid(quadriga_session), post_id)


@router.delete("/posts/{post_id}")
def post_remove(post_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    delete_post(_uid(quadriga_session), post_id)
    return {"ok": True}


@router.post("/posts/{post_id}/comments")
def comment_new(post_id: int, body: CommentIn,
                quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    add_comment(me, post_id, body.body)
    return get_post(me, post_id)


@router.post("/reactions")
def reaction_toggle(body: ReactionIn, quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    return {"반응": toggle_reaction(me, body.target_type, body.target_id, body.emoji)}


@router.get("/rooms")
def rooms(quadriga_session: str | None = Cookie(None)) -> dict:
    return {"rooms": list_rooms(_uid(quadriga_session))}


@router.post("/rooms")
def room_new(body: RoomIn, quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    rid = create_room(me, body.name, body.topic,
                      is_private=body.is_private, password=body.password)
    return {"id": rid, "rooms": list_rooms(me)}


@router.post("/direct")
def direct_open(body: HandleIn, quadriga_session: str | None = Cookie(None)) -> dict:
    """상대 프로필의 '채팅 보내기' — 1:1 방을 열거나 이미 있으면 그 방을 준다 (L1)."""
    me = _uid(quadriga_session)
    out = open_direct(me, body.handle)
    return {**out, "rooms": list_rooms(me)}


@router.post("/rooms/{room_id}/join")
def room_join(room_id: int, body: RoomJoinIn | None = None,
              quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    join_room(me, room_id, body.password if body else None)
    return {"ok": True, "rooms": list_rooms(me)}


@router.put("/rooms/{room_id}/password")
def room_password(room_id: int, body: RoomPasswordIn,
                  quadriga_session: str | None = Cookie(None)) -> dict:
    change_room_password(_uid(quadriga_session), room_id, body.password)
    return {"ok": True}


@router.get("/rooms/{room_id}/members")
def room_member_list(room_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    return room_members(_uid(quadriga_session), room_id)


@router.post("/rooms/{room_id}/invite")
def room_invite(room_id: int, body: HandleIn,
                quadriga_session: str | None = Cookie(None)) -> dict:
    return invite_member(_uid(quadriga_session), room_id, body.handle)


@router.delete("/rooms/{room_id}/invite/{handle}")
def room_invite_cancel(room_id: int, handle: str,
                       quadriga_session: str | None = Cookie(None)) -> dict:
    return cancel_invite(_uid(quadriga_session), room_id, handle)


@router.get("/invites")
def invite_list(quadriga_session: str | None = Cookie(None)) -> dict:
    return {"초대": my_invites(_uid(quadriga_session))}


@router.post("/invites/{room_id}/accept")
def invite_accept(room_id: int, body: RoomJoinIn,
                  quadriga_session: str | None = Cookie(None)) -> dict:
    """수락. 비공개 방이면 비밀번호가 맞아야 들어간다."""
    me = _uid(quadriga_session)
    accept_invite(me, room_id, body.password)
    return {"ok": True, "rooms": list_rooms(me)}


@router.delete("/invites/{room_id}")
def invite_decline(room_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    return decline_invite(_uid(quadriga_session), room_id)


@router.post("/rooms/{room_id}/kick")
def room_kick(room_id: int, body: HandleIn,
              quadriga_session: str | None = Cookie(None)) -> dict:
    return kick_member(_uid(quadriga_session), room_id, body.handle)


@router.post("/rooms/{room_id}/leave")
def room_leave(room_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    leave_room(me, room_id)
    return {"ok": True, "rooms": list_rooms(me)}


@router.delete("/rooms/{room_id}")
def room_destroy(room_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    """방장이 단체 채팅방을 폭파한다 — 멤버·메시지·초대가 모두 함께 지워진다."""
    me = _uid(quadriga_session)
    delete_room(me, room_id)
    return {"ok": True, "rooms": list_rooms(me)}


@router.get("/rooms/{room_id}/messages")
def room_messages(room_id: int, after: int = 0,
                  quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    return {"messages": messages(me, room_id, after)}


@router.post("/rooms/{room_id}/messages")
def room_send(room_id: int, body: MessageIn,
              quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    send_message(me, room_id, body.body)
    return {"messages": messages(me, room_id, 0)[-30:]}


# ---------- 앱 내 아이디 · 상호 친구 ----------

@router.get("/me/handle")
def my_handle(quadriga_session: str | None = Cookie(None)) -> dict:
    """내 앱 내 아이디. 아직 없으면 이때 만들어진다."""
    me = _uid(quadriga_session)
    with auth.db() as con:
        나 = _public_user(con, me)
    나["아이디"] = handle_for(me)
    return 나


@router.get("/users/{handle}")
def user_lookup(handle: str, quadriga_session: str | None = Cookie(None)) -> dict:
    """아이디로 사람 찾기.

    닉네임과 아이디만 돌려준다. 체력나이·측정 기록·이메일은 넣지 않는다.
    """
    me = _uid(quadriga_session)
    found = find_by_handle(handle)
    if not found:
        raise HTTPException(404, "그 아이디를 쓰는 회원이 없어요.")
    other = found.pop("user_id")
    with auth.db() as con:
        found["관계"] = friend_state(con, me, other)
        # 채팅 버튼을 어떻게 그릴지 서버가 정한다 — 규칙이 화면에 흩어지지 않게
        if me == other:
            found["채팅"] = "나"
        elif _direct_room(con, me, other):
            found["채팅"] = "열림"
        elif con.execute("SELECT 1 FROM chat_requests WHERE from_id=? AND to_id=?",
                         (me, other)).fetchone():
            found["채팅"] = "요청함"
        elif con.execute("SELECT 1 FROM chat_requests WHERE from_id=? AND to_id=?",
                         (other, me)).fetchone():
            found["채팅"] = "받음"
        else:
            found["채팅"] = "가능"
    return found


@router.get("/chat-requests")
def chat_request_list(quadriga_session: str | None = Cookie(None)) -> dict:
    return chat_requests(_uid(quadriga_session))


@router.post("/chat-requests/{handle}/accept")
def chat_request_accept(handle: str, quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    out = accept_chat(me, handle)
    return {**out, "rooms": list_rooms(me)}


@router.delete("/chat-requests/{handle}")
def chat_request_decline(handle: str, quadriga_session: str | None = Cookie(None)) -> dict:
    return decline_chat(_uid(quadriga_session), handle)


@router.get("/friends")
def friend_list(quadriga_session: str | None = Cookie(None)) -> dict:
    return friends(_uid(quadriga_session))


@router.post("/friends")
def friend_add(body: HandleIn, quadriga_session: str | None = Cookie(None)) -> dict:
    """친구 신청. 상대도 나를 신청해 뒀으면 그 자리에서 친구가 된다."""
    return request_friend(_uid(quadriga_session), body.handle)


@router.delete("/friends/{handle}")
def friend_remove(handle: str, quadriga_session: str | None = Cookie(None)) -> dict:
    return unfriend(_uid(quadriga_session), handle)

