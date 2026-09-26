"""커뮤니티 — 게시글·댓글·이모지 반응·기록 공유·운동 모임 채팅.

가입자(로그인 사용자)만 읽고 쓸 수 있다. 저장은 backend/auth.py 의 DB 계층
(SQLite 로컬 / Postgres 배포)을 그대로 쓴다.

사진·동영상은 data URL(base64)로 본문과 함께 저장한다. 용량이 커서 프로덕션은
객체 스토리지(S3 등)로 옮겨야 한다 — 그래서 크기와 개수를 꽉 잡는다(LIMITS). 배포 DB(Render 무료 Postgres)는
1GB 라, 사진 한 장 1MB 면 글 300개 남짓에 찬다.
채팅은 폴링 방식이다(GET .../messages?after=). 실시간이 필요하면 WebSocket 으로 바꾼다.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import secrets
import time

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, Field

try:
    from backend import auth, billing
except ImportError:
    import auth
    import billing

# 쓰기 제한 — 등급마다 다르다 (2026-09-22 예현 결정: 사진 최대 3장, 크기·본문 길이는 적정선에서).
#   무료  글 하루 5개 · 사진 3장(한 장 1MB, 화면이 긴 변 1600px 로 줄여 보낸다) · 동영상 3MB · 본문 1,000자
#   구독  한 달 구독(ai_addons 의 '구독')이 살아 있으면 — 글 하루 30개 · 사진 6장 · 본문 3,000자
# 댓글 300자 · 채팅 500자는 등급과 상관없다 — 긴 글이 아니라 대화다.
# 바이트는 data URL(base64) 문자열 길이 — 원본의 4/3.
# 하루바이트 = 하루에 올릴 수 있는 사진·동영상 합계(base64 길이) — 개수 제한을 다 채워도 DB 가 하루에 이만큼만 자란다.
LIMITS = {
    "무료": {"글하루": 5, "사진": 3, "사진바이트": 1_400_000, "동영상바이트": 4_200_000, "하루바이트": 20_000_000,
           "본문": 1000, "댓글": 300, "채팅": 500},
    "구독": {"글하루": 30, "사진": 6, "사진바이트": 1_400_000, "동영상바이트": 4_200_000, "하루바이트": 60_000_000,
           "본문": 3000, "댓글": 300, "채팅": 500},
}
# 예전 이름 — /meta 와 화면이 쓴다. 무료 등급 값이다.
MEDIA_MAX_BYTES = LIMITS["무료"]["동영상바이트"]
MEDIA_MAX_COUNT = LIMITS["무료"]["사진"]
KST = _dt.timezone(_dt.timedelta(hours=9))
ALLOWED_EMOJI = ["👍", "🔥", "💪", "👏", "🥲", "🎉"]


def tier_for(user_id: int) -> str:
    """'구독' 이 살아 있으면 구독, 아니면 무료."""
    try:
        return "구독" if billing.active_addon(user_id, "구독") else "무료"
    except Exception:                 # billing 표가 아직 없는 환경(초기화 전) — 무료로 본다
        return "무료"


def limits_for(user_id: int) -> dict:
    return dict(LIMITS[tier_for(user_id)])


def _day_start(now: float | None = None) -> int:
    """오늘(한국 시간) 0시의 epoch — 하루 글 수를 셀 때."""
    t = _dt.datetime.fromtimestamp(now if now is not None else time.time(), KST)
    return int(t.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS community_posts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL DEFAULT 'post',
  body       TEXT NOT NULL DEFAULT '',
  media      TEXT NOT NULL DEFAULT '[]',
  record     TEXT,
  created_at INTEGER NOT NULL,
  edited_at  INTEGER,
  /* 누가 볼 수 있는 글인지. all=전체, friends=친구 전체, chosen=고른 친구.
     예전 글에는 값이 없다 — 그때는 전체 공개뿐이었으니 all 로 읽는다. */
  audience   TEXT,
  /* 기록 공유 글이 어느 날의 기록인지 (YYYY-MM-DD) */
  record_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_cposts_created ON community_posts(created_at DESC);

/* 글을 누구에게 보일지 고른 사람들. audience='chosen' 인 글에만 쓴다.
   비어 있으면 글쓴이 말고는 아무도 못 본다 — 아무나 보이는 쪽으로 새지 않게. */
CREATE TABLE IF NOT EXISTS post_audience (
  post_id INTEGER NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (post_id, user_id)
);

/* 신고 — 글 · 댓글 · 메시지. 같은 사람이 같은 것을 두 번 신고할 수 없다. 관리자가 보고 지우거나 넘긴다. */
CREATE TABLE IF NOT EXISTS community_reports (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  target_type TEXT NOT NULL,           -- post | comment | message
  target_id   INTEGER NOT NULL,
  reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reason      TEXT NOT NULL DEFAULT '',
  created_at  INTEGER NOT NULL,
  handled_at  INTEGER,                 -- 관리자가 처리한 때(지웠든 넘겼든). NULL 이면 아직
  UNIQUE (target_type, target_id, reporter_id)
);

/* 자주 고르는 친구 묶음 — '고른 친구' 로 올릴 때 기본으로 채워 준다. */
CREATE TABLE IF NOT EXISTS share_chosen (
  user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  other_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, other_id)
);
CREATE TABLE IF NOT EXISTS community_comments (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id    INTEGER NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body       TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  edited_at  INTEGER
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
/* last_read_id — 이 사람이 이 방에서 어디까지 읽었는지(마지막으로 본 메시지 id).
   안 읽은 수는 이 값보다 뒤에 온 남의 글을 센다. 사람마다 다르므로 방이
   아니라 멤버 줄에 둔다. */
CREATE TABLE IF NOT EXISTS chat_members (
  room_id      INTEGER NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  joined_at    INTEGER NOT NULL,
  last_read_id INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (room_id, user_id)
);
/* 답장도 메시지다. reply_to 로 어떤 글에 단 것인지만 적어 둔다.
   따로 매달아 두면 대화가 시간순으로 읽히지 않는다. */
CREATE TABLE IF NOT EXISTS chat_messages (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id    INTEGER NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body       TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  edited_at  INTEGER,
  reply_to   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cmsg_room ON chat_messages(room_id, id);

/* 예전에 댓글을 따로 두던 자리. 지금은 답장도 chat_messages 의 한 줄이다.
   이 표는 옮겨 담기(_move_replies_into_messages)만을 위해 남겨 둔다 —
   없애 버리면 아직 옮기지 않은 DB 의 댓글이 그대로 사라진다. */
CREATE TABLE IF NOT EXISTS chat_replies (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id INTEGER NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body       TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  edited_at  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_creply_msg ON chat_replies(message_id, id);

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
        # 이미 만들어진 서비스 DB에도 늘어난 컬럼을 안전하게 더한다.
        _add_columns(con, "chat_rooms",
                     ["room_type TEXT NOT NULL DEFAULT 'group'",
                      "is_private INTEGER NOT NULL DEFAULT 0",
                      "password_salt TEXT", "password_hash TEXT"])
        for table in ("community_posts", "community_comments", "chat_messages"):
            _add_columns(con, table, ["edited_at INTEGER"])
        _add_columns(con, "chat_messages", ["reply_to INTEGER"])
        _add_columns(con, "chat_members", ["last_read_id INTEGER NOT NULL DEFAULT 0"])
        _add_columns(con, "community_posts", ["audience TEXT", "record_date TEXT"])
        _move_replies_into_messages(con)


def _move_replies_into_messages(con) -> None:
    """예전에 따로 두던 댓글(chat_replies)을 메시지로 옮긴다.

    답장도 메시지가 되면서 자리가 하나로 합쳐졌다. 옮기지 않으면 이미 달아
    둔 댓글이 화면에서 사라진다. 옮긴 줄은 지우므로 두 번 돌아도 그대로다.
    """
    try:
        rows = con.execute(
            "SELECT c.*, g.room_id FROM chat_replies c"
            " JOIN chat_messages g ON g.id = c.message_id ORDER BY c.id").fetchall()
    except Exception:
        return                      # 그 테이블을 만든 적이 없는 DB
    for r in rows:
        con.execute(
            "INSERT INTO chat_messages (room_id, user_id, body, created_at, edited_at, reply_to)"
            " VALUES (?,?,?,?,?,?)",
            (r["room_id"], r["user_id"], r["body"], r["created_at"],
             r["edited_at"], r["message_id"]))
    if rows:
        con.execute("DELETE FROM chat_replies")


def _add_columns(con, table: str, columns: list[str]) -> None:
    """없는 컬럼만 더한다. 배포(Postgres)와 로컬(SQLite) 문법이 다르다."""
    if auth.is_postgres():
        for column in columns:
            con.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column}")
        return
    있는것 = {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    for column in columns:
        if column.split()[0] not in 있는것:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column}")


DATA_URL = re.compile(r"^data:(image|video)/[\w.+-]+;base64,[A-Za-z0-9+/=\s]+$")


# 앱 내 아이디에 쓰는 글자 — 대소문자와 숫자 12자.
# 이메일을 식별자로 쓰면 가입 여부가 새어 나가고, 길어서 주고받기도 어렵다.
# 한 번 발급하면 바뀌지 않는다. 아무도 고칠 수 없다(고치는 길이 아예 없다).
HANDLE_ALPHABET = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                   "abcdefghijklmnopqrstuvwxyz"
                   "0123456789")
HANDLE_LEN = 12
# 예전에 만든 6자 소문자 아이디도 그대로 찾을 수 있어야 한다 — 아이디는 고정이다.
HANDLE_RE = re.compile(r"^[A-Za-z0-9]{3,20}$")


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
    # 대소문자를 구분한다. 눕혀서 찾으면 'Ab1' 과 'ab1' 이 같은 사람이 된다.
    handle = (handle or "").strip()
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


def _clean_media(media, 제한: dict | None = None) -> str:
    """[{type, url, name}] 검증 → JSON 문자열. 개수와 크기는 등급의 제한(LIMITS)대로."""
    제한 = 제한 or LIMITS["무료"]
    if not media:
        return "[]"
    if not isinstance(media, list) or len(media) > 제한["사진"]:
        raise HTTPException(400, f"사진·동영상은 최대 {제한['사진']}개까지예요."
                                 + ("" if 제한 is LIMITS["구독"] or 제한["사진"] >= LIMITS["구독"]["사진"] else
                                    f" 구독하면 {LIMITS['구독']['사진']}개까지 올릴 수 있어요."))
    out = []
    for m in media:
        url = (m or {}).get("url", "")
        if not DATA_URL.match(url):
            raise HTTPException(400, "사진·동영상 형식을 확인해 주세요.")
        동영상 = url.startswith("data:video")
        if len(url) > (제한["동영상바이트"] if 동영상 else 제한["사진바이트"]):
            raise HTTPException(400, "동영상은 3MB 아래로 올려주세요." if 동영상
                                     else "사진이 너무 커요. 앱이 줄여 보내는 크기(1MB)를 넘었어요.")
        out.append({"type": "video" if 동영상 else "image",
                    "url": url, "name": str(m.get("name", ""))[:120]})
    return json.dumps(out, ensure_ascii=False)


def _check_text(body: str, 상한: int, 이름: str) -> str:
    """길이를 넘으면 잘라 넣지 않고 거절한다 — 조용히 잘리면 쓴 사람이 모른다."""
    if len(body) > 상한:
        raise HTTPException(400, f"{이름}은 {상한:,}자까지예요. 지금 {len(body):,}자예요.")
    return body


def posts_today(user_id: int, now: float | None = None) -> int:
    with auth.db() as con:
        r = con.execute("SELECT COUNT(*) AS n FROM community_posts WHERE user_id=? AND created_at>=?",
                        (user_id, _day_start(now))).fetchone()
    return int(r["n"] or 0)


# 커뮤니티 사진 · 동영상을 DB 에 둘 수 있는 전체 합(base64 길이). 하루 상한(하루바이트)은 한 사람 몫이라 여럿이 올리면
# 끝이 없다. Neon 무료 DB 는 0.5GB 를 넘으면 쓰기가 막혀 로그인까지 안 된다 — 절반에서 멈추고, 사진 없는 글은 계속 받는다
# (2026-09-26 점검). 사진을 객체 저장소로 옮기면 이 값은 필요 없다.
MEDIA_TOTAL_BYTES = 250_000_000


def media_bytes_total() -> int:
    """DB 에 들어 있는 사진 · 동영상 전체의 합(base64 길이)."""
    with auth.db() as con:
        r = con.execute("SELECT COALESCE(SUM(LENGTH(media)), 0) AS n FROM community_posts").fetchone()
    return int(r["n"] or 0)


def media_bytes_today(user_id: int, now: float | None = None) -> int:
    """오늘 올린 사진·동영상의 합(base64 길이) — media 칸 그대로의 길이라 JSON 껍데기만큼 조금 크다."""
    with auth.db() as con:
        r = con.execute("SELECT COALESCE(SUM(LENGTH(media)), 0) AS n FROM community_posts WHERE user_id=? AND created_at>=?",
                        (user_id, _day_start(now))).fetchone()
    return int(r["n"] or 0)


# ---------------------------------------------------------------------------
# 게시글 · 댓글 · 반응
# ---------------------------------------------------------------------------

AUDIENCE = ("all", "friends", "chosen")


def _friend_ids(con, me: int) -> set[int]:
    보냄 = {r["other_id"] for r in con.execute(
        "SELECT other_id FROM friend_links WHERE user_id=?", (me,)).fetchall()}
    받음 = {r["user_id"] for r in con.execute(
        "SELECT user_id FROM friend_links WHERE other_id=?", (me,)).fetchall()}
    return 보냄 & 받음


def chosen_friends(me: int) -> list[dict]:
    """자주 고르는 친구 묶음. 친구가 아니게 된 사람은 빼고 돌려준다."""
    with auth.db() as con:
        고른것 = {r["other_id"] for r in con.execute(
            "SELECT other_id FROM share_chosen WHERE user_id=?", (me,)).fetchall()}
        친구 = _friend_ids(con, me)
        return [_public_user(con, u) for u in sorted(고른것 & 친구)]


def set_chosen_friends(me: int, handles: list[str]) -> list[dict]:
    """친구인 사람만 담는다. 친구가 아닌 사람을 담아 두면, 나중에 친구가
    되는 순간 예전에 올린 글까지 한꺼번에 보이게 된다."""
    with auth.db() as con:
        친구 = _friend_ids(con, me)
        ids = []
        for h in handles or []:
            r = con.execute("SELECT user_id FROM user_handles WHERE handle=?",
                            (str(h).strip(),)).fetchone()
            if not r:
                raise HTTPException(404, f"'{h}' 아이디를 쓰는 회원이 없어요.")
            if r["user_id"] not in 친구:
                raise HTTPException(400, "친구인 사람만 고를 수 있어요.")
            ids.append(r["user_id"])
        con.execute("DELETE FROM share_chosen WHERE user_id=?", (me,))
        for u in set(ids):
            con.execute("INSERT INTO share_chosen (user_id, other_id) VALUES (?,?)", (me, u))
    return chosen_friends(me)


def _audience_ids(con, me: int, audience: str, handles) -> list[int]:
    """'고른 친구' 로 올릴 때 볼 사람들. 안 주면 저장해 둔 묶음을 쓴다."""
    친구 = _friend_ids(con, me)
    if handles is None:
        고른것 = {r["other_id"] for r in con.execute(
            "SELECT other_id FROM share_chosen WHERE user_id=?", (me,)).fetchall()}
        return sorted(고른것 & 친구)
    out = []
    for h in handles:
        r = con.execute("SELECT user_id FROM user_handles WHERE handle=?",
                        (str(h).strip(),)).fetchone()
        if not r or r["user_id"] not in 친구:
            raise HTTPException(400, "친구인 사람만 고를 수 있어요.")
        out.append(r["user_id"])
    return sorted(set(out))


def create_post(user_id: int, *, body: str = "", media=None, kind: str = "post",
                record: dict | None = None, audience: str = "all",
                to: list[str] | None = None, record_date: str | None = None) -> int:
    body = (body or "").strip()
    제한 = limits_for(user_id)
    _check_text(body, 제한["본문"], "본문")
    media_json = _clean_media(media, 제한)
    if not body and media_json == "[]" and not record:
        raise HTTPException(400, "내용이나 사진을 하나는 넣어주세요.")
    if posts_today(user_id) >= 제한["글하루"]:
        raise HTTPException(429, f"글은 하루 {제한['글하루']}개까지예요. 내일 다시 올릴 수 있어요."
                                 + (f" 구독하면 하루 {LIMITS['구독']['글하루']}개까지 올릴 수 있어요." if 제한["글하루"] < LIMITS["구독"]["글하루"] else ""))
    if media_json != "[]" and media_bytes_today(user_id) + len(media_json) > 제한["하루바이트"]:
        raise HTTPException(429, f"오늘 올릴 수 있는 사진·동영상 용량({제한['하루바이트'] // 1_400_000}MB)을 다 썼어요. 내일 다시 올릴 수 있어요.")
    if media_json != "[]" and media_bytes_total() + len(media_json) > MEDIA_TOTAL_BYTES:
        raise HTTPException(507, "지금은 사진·동영상을 더 올릴 수 없어요(저장 공간이 찼어요). 사진 없이 글만 올려 주세요.")
    # 공유하는 기록에는 항목별 지표와 그날 운동까지 담긴다. 그래도 한 줄에
    # 들어갈 크기다 — 그보다 크면 화면에 쓰라고 보낸 것이 아니다.
    if record is not None and len(json.dumps(record, ensure_ascii=False)) > 4000:
        raise HTTPException(400, "공유할 기록이 너무 큽니다.")
    if audience not in AUDIENCE:
        raise HTTPException(400, "공개 범위가 올바르지 않아요.")
    with auth.db() as con:
        볼사람 = _audience_ids(con, user_id, audience, to) if audience == "chosen" else []
        pid = con.insert_id(
            "INSERT INTO community_posts"
            " (user_id, kind, body, media, record, created_at, audience, record_date)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (user_id, kind, body, media_json,
             json.dumps(record, ensure_ascii=False) if record else None,
             int(time.time()), audience, record_date))
        for u in 볼사람:
            con.execute("INSERT INTO post_audience (post_id, user_id) VALUES (?,?)", (pid, u))
        return pid


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


def _visible_sql(me: int) -> tuple[str, tuple]:
    """내가 볼 수 있는 글의 조건.

    내 글은 늘 보이고, 전체 공개도 보인다. '친구 전체' 는 서로 친구일 때만,
    '고른 친구' 는 글쓴이가 나를 고른 글만. 예전 글(audience 가 비어 있음)은
    전체 공개뿐이던 때의 것이라 all 로 읽는다.
    Postgres 는 OR 의 피연산자가 boolean 이어야 해서 EXISTS 로 감싼다.
    """
    return (
        " (p.user_id = ?"
        "  OR p.audience IS NULL OR p.audience = 'all'"
        "  OR (p.audience = 'friends'"
        "      AND EXISTS (SELECT 1 FROM friend_links f1"
        "                  WHERE f1.user_id = p.user_id AND f1.other_id = ?)"
        "      AND EXISTS (SELECT 1 FROM friend_links f2"
        "                  WHERE f2.user_id = ? AND f2.other_id = p.user_id))"
        "  OR (p.audience = 'chosen'"
        "      AND EXISTS (SELECT 1 FROM post_audience a"
        "                  WHERE a.post_id = p.id AND a.user_id = ?)))",
        (me, me, me, me))


def list_posts(me: int, *, before: int | None = None, limit: int = 20) -> list[dict]:
    limit = max(1, min(50, limit))
    with auth.db() as con:
        볼조건, 볼값 = _visible_sql(me)
        sql = ("SELECT p.*, u.display_name FROM community_posts p"
               " JOIN users u ON u.id = p.user_id WHERE" + 볼조건)
        params: tuple = 볼값
        if before:
            sql += " AND p.id < ?"
            params = (*볼값, before)
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
        "수정시각": r["edited_at"],
        "공개범위": r["audience"] or "all",
        "기록날짜": r["record_date"],
        "댓글수": comment_count,
        "반응": (react or {"counts": {}, "mine": []}),
    }


def get_post(me: int, post_id: int) -> dict:
    with auth.db() as con:
        볼조건, 볼값 = _visible_sql(me)
        r = con.execute(
            "SELECT p.*, u.display_name FROM community_posts p"
            " JOIN users u ON u.id = p.user_id WHERE p.id=? AND" + 볼조건,
            (post_id, *볼값)).fetchone()
        if not r:
            # 못 보는 글과 없는 글을 구분해 주지 않는다 — 있다는 사실도 정보다
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
        "수정시각": c["edited_at"],
        "반응": creact.get(c["id"], {"counts": {}, "mine": []}),
    } for c in cs]
    return post


def add_comment(user_id: int, post_id: int, body: str) -> int:
    body = _check_text((body or "").strip(), LIMITS["무료"]["댓글"], "댓글")
    if not body:
        raise HTTPException(400, "댓글 내용을 입력해 주세요.")
    with auth.db() as con:
        _visible_or_404(con, user_id, post_id)            # 못 보는 글에는 못 단다 — 있다는 사실도 정보다
        return con.insert_id(
            "INSERT INTO community_comments (post_id, user_id, body, created_at) VALUES (?,?,?,?)",
            (post_id, user_id, body, int(time.time())))


def _visible_or_404(con, me: int, post_id: int) -> None:
    """그 글이 나에게 보이는 글인지. 아니면 없는 글과 똑같이 404."""
    볼조건, 볼값 = _visible_sql(me)
    if not con.execute("SELECT 1 FROM community_posts p WHERE p.id=? AND" + 볼조건, (post_id, *볼값)).fetchone():
        raise HTTPException(404, "글을 찾을 수 없어요.")


def toggle_reaction(user_id: int, target_type: str, target_id: int, emoji: str) -> dict:
    if target_type not in ("post", "comment", "message"):
        raise HTTPException(400, "잘못된 대상이에요.")
    if emoji not in ALLOWED_EMOJI:
        raise HTTPException(400, "쓸 수 없는 이모지예요.")
    with auth.db() as con:
        # 채팅은 그 방 사람만 볼 수 있다. 남의 방 메시지에 이모지를 달 수는 없다.
        if target_type == "message":
            m = con.execute("SELECT room_id FROM chat_messages WHERE id=?",
                            (target_id,)).fetchone()
            if not m:
                raise HTTPException(404, "메시지를 찾을 수 없어요.")
            if not _is_member(con, m["room_id"], user_id):
                raise HTTPException(403, "먼저 모임에 참여해 주세요.")
        elif target_type == "post":
            _visible_or_404(con, user_id, target_id)      # 못 보는 글에는 못 단다
        else:
            c = con.execute("SELECT post_id FROM community_comments WHERE id=?", (target_id,)).fetchone()
            if not c:
                raise HTTPException(404, "댓글을 찾을 수 없어요.")
            _visible_or_404(con, user_id, c["post_id"])
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


def _mine_or_403(con, table: str, row_id: int, user_id: int, 이름: str, admin: bool = False):
    """내가 쓴 것만 고치거나 지울 수 있다. 없으면 404, 남의 것이면 403. 관리자(admin)는 지울 때만 예외."""
    r = con.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
    if not r:
        raise HTTPException(404, f"{이름}을 찾을 수 없어요.")
    if r["user_id"] != user_id and not admin:
        raise HTTPException(403, f"내 {이름}만 고치거나 지울 수 있어요.")
    return r


def _drop_reactions(con, target_type: str, ids: list[int]) -> None:
    """이모지에는 글을 가리키는 외래키가 없다(대상이 여러 종류라서).
       글을 지울 때 여기서 함께 지우지 않으면 남은 줄이 새 글에 붙는다."""
    if not ids:
        return
    marks = ",".join("?" for _ in ids)
    con.execute(f"DELETE FROM community_reactions"
                f" WHERE target_type=? AND target_id IN ({marks})", (target_type, *ids))


def _edited(body: str, 자리: int) -> str:
    body = (body or "").strip()
    if not body:
        raise HTTPException(400, "내용을 입력해 주세요.")
    return body[:자리]


def delete_post(user_id: int, post_id: int, admin: bool = False) -> None:
    with auth.db() as con:
        _mine_or_403(con, "community_posts", post_id, user_id, "글", admin=admin)
        con.execute("UPDATE community_reports SET handled_at=? WHERE target_type='post' AND target_id=? AND handled_at IS NULL",
                    (int(time.time()), post_id))
        cids = [c["id"] for c in con.execute(
            "SELECT id FROM community_comments WHERE post_id=?", (post_id,)).fetchall()]
        _drop_reactions(con, "comment", cids)
        _drop_reactions(con, "post", [post_id])
        con.execute("DELETE FROM community_comments WHERE post_id=?", (post_id,))
        con.execute("DELETE FROM community_posts WHERE id=?", (post_id,))


def edit_post(user_id: int, post_id: int, body: str) -> None:
    """본문만 고친다. 사진과 공유한 기록은 그대로 둔다."""
    _check_text(body, limits_for(user_id)["본문"], "본문")
    with auth.db() as con:
        _mine_or_403(con, "community_posts", post_id, user_id, "글")
        con.execute("UPDATE community_posts SET body=?, edited_at=? WHERE id=?",
                    (_edited(body, LIMITS["구독"]["본문"]), int(time.time()), post_id))


def delete_comment(user_id: int, comment_id: int, admin: bool = False) -> None:
    with auth.db() as con:
        _mine_or_403(con, "community_comments", comment_id, user_id, "댓글", admin=admin)
        con.execute("UPDATE community_reports SET handled_at=? WHERE target_type='comment' AND target_id=? AND handled_at IS NULL",
                    (int(time.time()), comment_id))
        _drop_reactions(con, "comment", [comment_id])
        con.execute("DELETE FROM community_comments WHERE id=?", (comment_id,))


def edit_comment(user_id: int, comment_id: int, body: str) -> None:
    _check_text(body, LIMITS["무료"]["댓글"], "댓글")
    with auth.db() as con:
        _mine_or_403(con, "community_comments", comment_id, user_id, "댓글")
        con.execute("UPDATE community_comments SET body=?, edited_at=? WHERE id=?",
                    (_edited(body, LIMITS["무료"]["댓글"]), int(time.time()), comment_id))


def delete_message(user_id: int, message_id: int, admin: bool = False) -> int:
    with auth.db() as con:
        r = _mine_or_403(con, "chat_messages", message_id, user_id, "메시지", admin=admin)
        con.execute("UPDATE community_reports SET handled_at=? WHERE target_type='message' AND target_id=? AND handled_at IS NULL",
                    (int(time.time()), message_id))
        _drop_reactions(con, "message", [message_id])
        # 답장은 남긴다. 원글이 없어졌다는 이유로 남의 글까지 지울 수는 없다.
        con.execute("UPDATE chat_messages SET reply_to=NULL WHERE reply_to=?", (message_id,))
        con.execute("DELETE FROM chat_messages WHERE id=?", (message_id,))
        return r["room_id"]


def edit_message(user_id: int, message_id: int, body: str) -> int:
    _check_text(body, LIMITS["무료"]["채팅"], "메시지")
    with auth.db() as con:
        r = _mine_or_403(con, "chat_messages", message_id, user_id, "메시지")
        con.execute("UPDATE chat_messages SET body=?, edited_at=? WHERE id=?",
                    (_edited(body, LIMITS["무료"]["채팅"]), int(time.time()), message_id))
        return r["room_id"]


# ---------------------------------------------------------------------------
# 신고 · 관리자 검토
# ---------------------------------------------------------------------------

REPORT_TARGETS = {"post": ("community_posts", "글"), "comment": ("community_comments", "댓글"), "message": ("chat_messages", "메시지")}


def report(user_id: int, target_type: str, target_id: int, reason: str = "") -> dict:
    """글 · 댓글 · 메시지를 신고한다. 내 것은 신고할 수 없고, 같은 것을 두 번 신고하면 그대로(한 번으로 친다).
    보이는 글에만 — 못 보는 글은 없는 글과 같은 404 (있다는 사실도 정보다). 메시지는 그 방 사람만."""
    if target_type not in REPORT_TARGETS:
        raise HTTPException(400, "잘못된 대상이에요.")
    table, 이름 = REPORT_TARGETS[target_type]
    reason = (reason or "").strip()[:200]
    with auth.db() as con:
        r = con.execute(f"SELECT * FROM {table} WHERE id=?", (target_id,)).fetchone()
        if not r:
            raise HTTPException(404, f"{이름}을 찾을 수 없어요.")
        if target_type == "post":
            _visible_or_404(con, user_id, target_id)
        elif target_type == "comment":
            _visible_or_404(con, user_id, r["post_id"])
        elif not _is_member(con, r["room_id"], user_id):
            raise HTTPException(403, "먼저 모임에 참여해 주세요.")
        if r["user_id"] == user_id:
            raise HTTPException(400, f"내 {이름}은 신고할 수 없어요. 직접 지울 수 있어요.")
        있음 = con.execute("SELECT 1 FROM community_reports WHERE target_type=? AND target_id=? AND reporter_id=?",
                          (target_type, target_id, user_id)).fetchone()
        if not 있음:
            con.execute("INSERT INTO community_reports (target_type, target_id, reporter_id, reason, created_at)"
                        " VALUES (?,?,?,?,?)", (target_type, target_id, user_id, reason, int(time.time())))
        n = con.execute("SELECT COUNT(*) AS n FROM community_reports WHERE target_type=? AND target_id=?",
                        (target_type, target_id)).fetchone()["n"]
    return {"ok": True, "신고수": int(n)}


def open_reports(limit: int = 50) -> list[dict]:
    """아직 처리하지 않은 신고 — 대상마다 하나로 묶고, 관리자가 볼 수 있게 내용 한 줄과 쓴 사람을 붙인다."""
    with auth.db() as con:
        rows = con.execute(
            "SELECT target_type, target_id, COUNT(*) AS n, MIN(created_at) AS first_at, MAX(reason) AS reason"
            " FROM community_reports WHERE handled_at IS NULL GROUP BY target_type, target_id"
            " ORDER BY first_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            table, 이름 = REPORT_TARGETS[r["target_type"]]
            t = con.execute(f"SELECT * FROM {table} WHERE id=?", (r["target_id"],)).fetchone()
            if not t:                                                # 이미 지워졌다 — 처리된 것으로 닫는다
                con.execute("UPDATE community_reports SET handled_at=? WHERE target_type=? AND target_id=? AND handled_at IS NULL",
                            (int(time.time()), r["target_type"], r["target_id"]))
                continue
            u = con.execute("SELECT display_name FROM users WHERE id=?", (t["user_id"],)).fetchone()
            body = t["body"] or ""
            out.append({"종류": r["target_type"], "이름": 이름, "id": int(r["target_id"]), "신고수": int(r["n"]),
                        "사유": r["reason"] or "", "처음신고": int(r["first_at"]),
                        "내용": body[:140] + ("…" if len(body) > 140 else ""),
                        "미디어": len(json.loads(t["media"] or "[]")) if r["target_type"] == "post" else 0,
                        "작성자": (u["display_name"] if u else "(탈퇴)"), "작성시각": int(t["created_at"])})
    return out


def dismiss_reports(target_type: str, target_id: int) -> int:
    """신고를 넘긴다(지우지 않고 처리 완료로). 돌려주는 값은 닫은 신고 수."""
    if target_type not in REPORT_TARGETS:
        raise HTTPException(400, "잘못된 대상이에요.")
    with auth.db() as con:
        return con.execute("UPDATE community_reports SET handled_at=? WHERE target_type=? AND target_id=? AND handled_at IS NULL",
                           (int(time.time()), target_type, target_id)).rowcount


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
            # 안 읽은 수 — 내가 마지막으로 본 뒤에 온 **남의** 글만 센다.
            # 내가 쓴 글은 쓰는 순간 읽은 것이라 세면 늘 안 읽은 것이 남는다.
            " (SELECT COUNT(*) FROM chat_messages g"
            "  WHERE g.room_id=r.id AND g.user_id<>?"
            "    AND g.id > COALESCE((SELECT m.last_read_id FROM chat_members m"
            "                         WHERE m.room_id=r.id AND m.user_id=?), 0)"
            " ) AS 안읽음,"
            " (SELECT 1 FROM chat_members m WHERE m.room_id=r.id AND m.user_id=?) AS 참여"
            " FROM chat_rooms r"
            # Postgres 는 OR 의 피연산자가 boolean 이어야 한다. 스칼라 서브쿼리
            # (SELECT 1 ...) 를 그대로 쓰면 SQLite 는 통과하지만 배포(Postgres)에서
            # "argument of OR must be type boolean" 으로 죽는다. EXISTS 로 감싼다.
            " WHERE r.room_type <> 'direct'"
            "  OR EXISTS (SELECT 1 FROM chat_members m"
            "             WHERE m.room_id=r.id AND m.user_id=?)"
            " ORDER BY r.id DESC", (me, me, me, me)).fetchall()
    out = []
    with auth.db() as con:
        for r in rows:
            방 = {"id": r["id"], "이름": r["name"], "주제": r["topic"],
                 "종류": r["room_type"], "비공개": bool(r["is_private"]),
                 "방장": r["created_by"] == me, "인원": r["인원"],
                 "메시지수": r["메시지수"], "참여중": bool(r["참여"]),
                 # 안 들어간 방에는 '안 읽음' 이 없다. 아직 내 대화가 아니다.
                 "안읽음": (r["안읽음"] if r["참여"] else 0)}
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
            # 숫자 비밀번호는 자동으로 다 넣어 볼 수 있다 — 로그인과 같은 잠금(5번 틀리면 15분). 방 하나 · 사람 하나 기준.
            잠금키 = f"room:{room_id}:{user_id}"
            남은초 = auth.guard_locked(잠금키)
            if 남은초:
                raise HTTPException(429, f"비밀번호를 여러 번 틀려 잠시 잠겼어요. {max(1, -(-남은초 // 60))}분 뒤에 다시 해 주세요.")
            try:
                valid = auth.verify_password(password or "", bytes.fromhex(room["password_salt"]),
                                             bytes.fromhex(room["password_hash"]))
            except (TypeError, ValueError):
                valid = False
            if not valid:
                남은횟수 = auth.guard_hit(잠금키, auth.LOGIN_MAX_FAILURES)
                raise HTTPException(429 if 남은횟수 == 0 else 403,
                                    "비밀번호를 여러 번 틀려 15분 동안 잠겼어요." if 남은횟수 == 0
                                    else "비공개 방 비밀번호가 맞지 않아요." + (f" ({남은횟수}번 더 틀리면 15분 잠겨요)" if 남은횟수 <= 2 else ""))
            auth.guard_clear(잠금키)
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


def mark_read(user_id: int, room_id: int, upto: int | None = None) -> int:
    """이 방을 어디까지 읽었는지 적는다. 적힌 자리를 돌려준다.

    ``upto`` 를 안 주면 그 방의 마지막 메시지까지 읽은 것으로 본다.
    뒤로 되돌리지 않는다 — 예전 글을 다시 봤다고 안 읽은 수가 늘어나면
    사용자는 읽지도 않은 글이 생겼다고 여긴다.
    """
    with auth.db() as con:
        if not _is_member(con, room_id, user_id):
            return 0
        if upto is None:
            끝 = con.execute("SELECT MAX(id) AS m FROM chat_messages WHERE room_id=?",
                            (room_id,)).fetchone()
            upto = (끝["m"] if 끝 else 0) or 0
        con.execute(
            "UPDATE chat_members SET last_read_id=? WHERE room_id=? AND user_id=?"
            "  AND last_read_id < ?", (upto, room_id, user_id, upto))
        줄 = con.execute(
            "SELECT last_read_id FROM chat_members WHERE room_id=? AND user_id=?",
            (room_id, user_id)).fetchone()
    return (줄["last_read_id"] if 줄 else 0) or 0


def messages(user_id: int, room_id: int, after: int = 0, limit: int = 50) -> list[dict]:
    """after 를 주면 그 뒤로 온 것, 안 주면 **가장 최근** 것부터 limit 개.

    예전에는 after 가 없을 때도 앞에서부터 잘라서, 대화가 길어지면 맨 처음
    50개만 돌려줬다. 화면은 늘 최근 대화를 보여 줘야 한다.
    고친 글·지운 글·이모지는 새 id 가 생기지 않아서, 화면이 이 목록을
    통째로 다시 그려야 반영된다.
    """
    limit = max(1, min(200, limit))
    with auth.db() as con:
        if not _is_member(con, room_id, user_id):
            raise HTTPException(403, "먼저 모임에 참여해 주세요.")
        if after:
            rows = con.execute(
                "SELECT g.*, u.display_name FROM chat_messages g JOIN users u ON u.id=g.user_id"
                " WHERE g.room_id=? AND g.id > ? ORDER BY g.id LIMIT ?",
                (room_id, after, limit)).fetchall()
        else:
            rows = con.execute(
                "SELECT g.*, u.display_name FROM chat_messages g JOIN users u ON u.id=g.user_id"
                " WHERE g.room_id=? ORDER BY g.id DESC LIMIT ?",
                (room_id, limit)).fetchall()
            rows = list(rows)[::-1]
        ids = [r["id"] for r in rows]
        react = _reaction_summary(con, "message", ids, user_id)
        원글 = _reply_targets(con, [r["reply_to"] for r in rows])
        # 프로필을 열려면 아이디가 있어야 한다. 닉네임은 겹칠 수 있다 (게시글과 같다).
        핸들 = {u: _handle_in(con, u) for u in {r["user_id"] for r in rows}}
    return [{"id": r["id"], "작성자": r["display_name"], "내글": r["user_id"] == user_id,
             "작성자아이디": 핸들.get(r["user_id"]),
             "본문": r["body"], "작성시각": r["created_at"],
             "수정시각": r["edited_at"],
             "반응": react.get(r["id"], {"counts": {}, "mine": []}),
             "답장": 원글.get(r["reply_to"])} for r in rows]


def _reply_targets(con, ids: list) -> dict[int, dict]:
    """답장이 가리키는 원글 — 누가 쓴 무슨 글인지 한 줄만.

    화면에 원글을 통째로 다시 그릴 필요는 없다. 어떤 글의 답장인지 알아보고
    눌러서 찾아갈 수 있으면 된다. 원글이 지워졌으면 아무것도 돌려주지 않는다.
    """
    쓸것 = sorted({i for i in ids if i})
    if not 쓸것:
        return {}
    marks = ",".join("?" for _ in 쓸것)
    rows = con.execute(
        f"SELECT g.id, g.body, u.display_name FROM chat_messages g"
        f" JOIN users u ON u.id=g.user_id WHERE g.id IN ({marks})", 쓸것).fetchall()
    return {r["id"]: {"id": r["id"], "작성자": r["display_name"],
                      "본문": r["body"][:60]} for r in rows}


def send_message(user_id: int, room_id: int, body: str,
                 reply_to: int | None = None) -> int:
    body = _check_text((body or "").strip(), LIMITS["무료"]["채팅"], "메시지")
    if not body:
        raise HTTPException(400, "메시지를 입력해 주세요.")
    with auth.db() as con:
        if not _is_member(con, room_id, user_id):
            raise HTTPException(403, "먼저 모임에 참여해 주세요.")
        if reply_to is not None:
            # 다른 방 글에 답장할 수는 없다 — 그 방 사람만 볼 수 있는 글이다
            대상 = con.execute("SELECT room_id FROM chat_messages WHERE id=?",
                             (reply_to,)).fetchone()
            if not 대상 or 대상["room_id"] != room_id:
                raise HTTPException(404, "답장할 메시지를 찾을 수 없어요.")
        return con.insert_id(
            "INSERT INTO chat_messages (room_id, user_id, body, created_at, reply_to)"
            " VALUES (?,?,?,?,?)",
            (room_id, user_id, body, int(time.time()), reply_to))


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
    body: str = Field("", max_length=LIMITS["구독"]["본문"])
    media: list[dict] = Field(default_factory=list)
    kind: str = Field("post", pattern="^(post|record)$")
    record: dict | None = None
    # 누가 볼 수 있는 글인지. 안 주면 전체 공개 — 지금까지와 같다.
    audience: str = Field("all", pattern="^(all|friends|chosen)$")
    # 'chosen' 일 때 볼 사람들. 안 주면 저장해 둔 묶음을 쓴다.
    to: list[str] | None = Field(None, max_length=100)
    # 기록 공유 글이 어느 날의 기록인지
    record_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class ChosenIn(BaseModel):
    handles: list[str] = Field(default_factory=list, max_length=100)


class PostEditIn(BaseModel):
    """글은 본문만 고친다. 사진과 공유한 기록은 그대로 둔다."""
    body: str = Field(..., max_length=LIMITS["구독"]["본문"])


class CommentIn(BaseModel):
    body: str = Field(..., max_length=LIMITS["무료"]["댓글"])


class ReportIn(BaseModel):
    target_type: str = Field(..., pattern="^(post|comment|message)$")
    target_id: int
    reason: str = Field("", max_length=200)


class ReactionIn(BaseModel):
    target_type: str = Field(..., pattern="^(post|comment|message)$")
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
    body: str = Field(..., max_length=LIMITS["무료"]["채팅"])
    # 답장이면 원글 id. 답장도 그냥 메시지라, 자리는 시간순 그대로다.
    reply_to: int | None = None


def _admin_uid(token: str | None) -> int:
    """관리자(main.ADMIN_USERS)만. 커뮤니티가 main 을 되돌아 부르지 않게 늦게 읽는다."""
    user = auth.user_for_token(token)
    if not user:
        raise HTTPException(401, "커뮤니티는 로그인 후 이용할 수 있어요.")
    try:
        from backend.main import is_admin
    except ImportError:
        from main import is_admin  # type: ignore
    if not is_admin(user):
        raise HTTPException(403, "관리자만 할 수 있어요.")
    return user["id"]


@router.post("/report")
def report_new(body: ReportIn, quadriga_session: str | None = Cookie(None)) -> dict:
    """글 · 댓글 · 메시지 신고. 관리자가 검토한다 — 신고했다고 바로 사라지진 않는다."""
    return report(_uid(quadriga_session), body.target_type, body.target_id, body.reason)


@router.get("/admin/reports")
def admin_reports(quadriga_session: str | None = Cookie(None)) -> dict:
    _admin_uid(quadriga_session)
    return {"신고": open_reports()}


@router.delete("/admin/{target_type}/{target_id}")
def admin_remove(target_type: str, target_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    """관리자가 아무 글 · 댓글 · 메시지나 지운다. 그 대상의 신고는 처리 완료로 닫힌다."""
    me = _admin_uid(quadriga_session)
    if target_type == "post":
        delete_post(me, target_id, admin=True)
    elif target_type == "comment":
        delete_comment(me, target_id, admin=True)
    elif target_type == "message":
        delete_message(me, target_id, admin=True)
    else:
        raise HTTPException(400, "잘못된 대상이에요.")
    print(f"[admin] {target_type} {target_id} 삭제 by user {me}", flush=True)
    return {"ok": True, "신고": open_reports()}


@router.post("/admin/{target_type}/{target_id}/dismiss")
def admin_dismiss(target_type: str, target_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    """신고를 넘긴다 — 지우지 않고 처리 완료로."""
    _admin_uid(quadriga_session)
    return {"닫음": dismiss_reports(target_type, target_id), "신고": open_reports()}


@router.get("/meta")
def meta(quadriga_session: str | None = Cookie(None)) -> dict:
    """화면이 그릴 것 — 이모지와 이 사람의 쓰기 제한(등급). 로그인 전에는 무료 등급 값."""
    user = auth.user_for_token(quadriga_session)
    등급 = tier_for(user["id"]) if user else "무료"
    제한 = dict(LIMITS[등급])
    관리자 = False
    if user:
        제한["오늘남은글"] = max(0, 제한["글하루"] - posts_today(user["id"]))
        try:
            from backend.main import is_admin
        except ImportError:
            from main import is_admin  # type: ignore
        관리자 = is_admin(user)
    return {"이모지": ALLOWED_EMOJI, "미디어최대개수": 제한["사진"],
            "미디어최대바이트": 제한["동영상바이트"], "등급": 등급, "제한": 제한, "관리자": 관리자,
            "신고": len(open_reports()) if 관리자 else None}


@router.get("/posts")
def get_posts(before: int | None = None, limit: int = 20,
              quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    return {"posts": list_posts(me, before=before, limit=limit)}


@router.post("/posts")
def post_new(body: PostIn, quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    pid = create_post(me, body=body.body, media=body.media, kind=body.kind,
                      record=body.record, audience=body.audience, to=body.to,
                      record_date=body.record_date)
    return get_post(me, pid)


@router.get("/posts/{post_id}")
def post_detail(post_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    return get_post(_uid(quadriga_session), post_id)


@router.delete("/posts/{post_id}")
def post_remove(post_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    delete_post(_uid(quadriga_session), post_id)
    return {"ok": True}


@router.put("/posts/{post_id}")
def post_edit(post_id: int, body: PostEditIn,
              quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    edit_post(me, post_id, body.body)
    return get_post(me, post_id)


@router.put("/comments/{comment_id}")
def comment_edit(comment_id: int, body: CommentIn,
                 quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    edit_comment(me, comment_id, body.body)
    return {"ok": True}


@router.delete("/comments/{comment_id}")
def comment_remove(comment_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    delete_comment(me, comment_id)
    return {"ok": True}


@router.put("/messages/{message_id}")
def message_edit(message_id: int, body: MessageIn,
                 quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    room_id = edit_message(me, message_id, body.body)
    return {"messages": messages(me, room_id, 0)}


@router.delete("/messages/{message_id}")
def message_remove(message_id: int, quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    room_id = delete_message(me, message_id)
    return {"messages": messages(me, room_id, 0)}


@router.post("/posts/{post_id}/comments")
def comment_new(post_id: int, body: CommentIn,
                quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    add_comment(me, post_id, body.body)
    return get_post(me, post_id)


@router.get("/share/chosen")
def share_chosen_get(quadriga_session: str | None = Cookie(None)) -> dict:
    """'고른 친구' 로 올릴 때 기본으로 채워 줄 사람들."""
    return {"고른친구": chosen_friends(_uid(quadriga_session))}


@router.put("/share/chosen")
def share_chosen_put(body: ChosenIn,
                     quadriga_session: str | None = Cookie(None)) -> dict:
    return {"고른친구": set_chosen_friends(_uid(quadriga_session), body.handles)}


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
    """방을 열어 메시지를 받아 가면 거기까지 읽은 것으로 본다.

    따로 '읽음' 을 누르게 하지 않는다. 화면에 띄운 것이 곧 읽은 것이다.
    """
    me = _uid(quadriga_session)
    목록 = messages(me, room_id, after)
    본데까지 = max((m["id"] for m in 목록), default=None)
    읽은자리 = mark_read(me, room_id, 본데까지)
    return {"messages": 목록, "읽은자리": 읽은자리}


@router.post("/rooms/{room_id}/messages")
def room_send(room_id: int, body: MessageIn,
              quadriga_session: str | None = Cookie(None)) -> dict:
    me = _uid(quadriga_session)
    send_message(me, room_id, body.body, body.reply_to)
    return {"messages": messages(me, room_id, 0)}


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

