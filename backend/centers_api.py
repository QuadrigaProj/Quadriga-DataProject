"""체력인증센터 목록 — 국민체육진흥공단 '국민체력100 체력인증센터 측정건수 정보' 오픈API.

    https://www.data.go.kr/data/15114286/openapi.do
    GET https://apis.data.go.kr/B551014/SRVC_TODZ_NFA_TEST_CENTER_CNT/TODZ_NFA_TEST_CENTER_CNT
        serviceKey · pageNo · numOfRows · resultType=json · test_ym(측정연월, 선택)

서버의 DATA_GO_KR_KEY 로 한 번 받아 하루 동안 기억한다. 못 받으면 저장소에 둔 스냅숏
(data/sample/centers_kspo.json), 그것도 없으면 예전 예시 목록(centers.json)을 쓴다 — 어느 것을 썼는지 '출처' 로 알린다.
응답 칸 이름을 명세가 적어 두지 않아서(Swagger 가 비어 있다) 흔한 이름을 여러 개 알아보고, 모르는 칸은 버리지 않고
'원본' 에 남긴다.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import threading
import time
from urllib.parse import unquote

import httpx

try:
    from backend import geo
    from backend.paths import ROOT, load_json
except ImportError:                                   # backend/ 안에서 직접 실행할 때
    import geo  # type: ignore
    from paths import ROOT, load_json  # type: ignore

API_URL = "https://apis.data.go.kr/B551014/SRVC_TODZ_NFA_TEST_CENTER_CNT/TODZ_NFA_TEST_CENTER_CNT"
SOURCE_PAGE = "https://www.data.go.kr/data/15114286/openapi.do"
SNAPSHOT = ROOT / "data" / "sample" / "centers_kspo.json"
CACHE_SEC = 24 * 3600          # 하루에 한 번만 새로 받는다
RETRY_SEC = 10 * 60            # 못 받았으면 10분 뒤에 다시 해 본다
ROWS = 1000
MAX_PAGES = 5
TIMEOUT = 8

# 응답 칸 이름 후보 — 앞에 있는 것부터 쓴다
NAME_KEYS = ("center_nm", "cntr_nm", "fclty_nm", "fcltyNm", "centerNm", "center_name", "nm")
ADDR1_KEYS = ("center_addr1", "addr1", "center_addr", "addr", "road_addr", "rdnmadr", "address")
ADDR2_KEYS = ("center_addr2", "addr2", "detail_addr")
LAT_KEYS = ("la", "lat", "latitude", "center_la", "lttd", "y", "ypos", "map_y")
LON_KEYS = ("lo", "lon", "lng", "longitude", "center_lo", "lgtd", "x", "xpos", "map_x")
TEL_KEYS = ("telno", "tel", "tel_no", "center_tel", "phone", "telNo")
CNT_KEYS = ("test_cnt", "msrmt_cnt", "cnt", "center_cnt", "tot_cnt")
YM_KEYS = ("test_ym", "msrmt_ym", "ym")

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "items": None, "source": None, "fields": [], "error": None}


def service_key() -> str | None:
    """서버 환경변수의 인증키. 인코딩된 키(%2B 등)를 넣었어도 풀어서 쓴다 — httpx 가 다시 인코딩한다."""
    key = (os.environ.get("DATA_GO_KR_KEY") or "").strip()
    if not key or key == "your_api_key_here":
        return None
    return unquote(key) if "%" in key else key


def _first(row: dict, keys) -> object | None:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return v
    return None


def _num(v) -> float | None:
    try:
        f = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _approx_coord(addr: str) -> tuple[float, float] | None:
    """좌표가 없으면 주소의 낱말(시 · 도 · 구 이름)로 대략의 좌표를 찾는다(geo.PLACES).

    **앞에서부터** 본다 — 시·도가 먼저 잡혀야 한다. 뒤에서부터 보면 "울산광역시 남구 …" 의 '남구' 가 서울 '강남구' 에
    부분 일치해 울산 센터가 서울에 찍혔다(2026-09-22 배포 서버에서 확인). 시·도는 잡혔는데 구가 다른 도시 것이면 시·도만 쓴다.
    """
    words = str(addr).split()
    for i, word in enumerate(words[:3]):                 # 시·도 · 시·군·구 · 읍·면·동 까지만 — 그 뒤는 길 이름이다
        if i == 0 and word.startswith("서울"):
            continue                                     # 서울은 자치구로 잡는다 — '서울' 은 '서울역' 에 부분 일치해 버린다
        c = geo.geocode(word)
        if c:
            return c                                     # 광역시·도가 먼저 잡히면 그 도시 중심 — 구 이름은 다른 도시와 겹친다
    return None


def known_coords() -> dict[str, tuple[float, float, bool]]:
    """스냅숏에 적어 둔 센터 좌표 {이름: (위도, 경도, 어림인지)} — 공단 API 는 좌표를 주지 않아서 주소를 한 번 지오코딩해 뒀다."""
    return {c["fcltyNm"]: (c["la"], c["lo"], bool(c.get("좌표어림")))
            for c in (load_snapshot() or []) if c.get("la") is not None and c.get("lo") is not None}


def normalize(rows: list[dict], known: dict | None = None) -> list[dict]:
    """API 행 → 화면이 쓰는 모양(fcltyNm · addr · la · lo · telno · 측정건수 · 기준월). 같은 센터는 하나로 묶는다.

    좌표는 API 행 → 스냅숏의 지오코딩 좌표(known) → 주소 낱말의 어림 순서로 채운다.
    이름에 '업체' 가 들어가고 주소가 없는 행은 공단 자료의 시험 행이라 버린다("2026 국민체력100 1번 업체").
    """
    known = known_coords() if known is None else known
    out: dict[tuple, dict] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = _first(r, NAME_KEYS)
        if not name:
            continue
        addr = " ".join(str(x).strip() for x in (_first(r, ADDR1_KEYS), _first(r, ADDR2_KEYS)) if x)
        if "업체" in str(name) and not addr:
            continue
        la, lo = _num(_first(r, LAT_KEYS)), _num(_first(r, LON_KEYS))
        if la is not None and lo is not None and not (33 <= la <= 39 and 124 <= lo <= 132):
            la, lo = (lo, la) if (33 <= lo <= 39 and 124 <= la <= 132) else (None, None)   # 위도 · 경도가 뒤바뀐 경우
        approx = False
        if (la is None or lo is None) and str(name).strip() in known:
            la, lo, approx = known[str(name).strip()]
        if la is None or lo is None:
            c = _approx_coord(addr)
            if c:
                la, lo, approx = c[0], c[1], True
        key = (str(name).strip(), addr)
        item = out.get(key) or {"fcltyNm": str(name).strip(), "addr": addr, "la": la, "lo": lo,
                                "좌표어림": approx, "telno": _first(r, TEL_KEYS) or "", "측정건수": 0, "기준월": None}
        cnt, ym = _num(_first(r, CNT_KEYS)), _first(r, YM_KEYS)
        if cnt is not None:
            item["측정건수"] += int(cnt)
        if ym and (item["기준월"] is None or str(ym) > str(item["기준월"])):
            item["기준월"] = str(ym)
        out[key] = item
    return list(out.values())


def _items_of(payload: dict) -> tuple[list[dict], int | None]:
    """공공데이터포털 JSON — response.body.items.item (하나면 dict) 또는 body.items 가 곧 목록."""
    body = (payload.get("response") or payload).get("body") or {}
    items = body.get("items")
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    total = body.get("totalCount")
    return (items or []), (int(total) if str(total or "").isdigit() else None)


def fetch(key: str, *, client: httpx.Client | None = None, today: _dt.date | None = None) -> tuple[list[dict], list[str]]:
    """전국 센터 행을 받는다. 지난달 → 두 달 전 → 측정연월 없이 순서로 해 보고, 처음 나오는 것을 쓴다."""
    today = today or _dt.date.today()
    first_of_month = today.replace(day=1)
    last = first_of_month - _dt.timedelta(days=1)
    before = last.replace(day=1) - _dt.timedelta(days=1)
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        for ym in (last.strftime("%Y%m"), before.strftime("%Y%m"), None):
            rows: list[dict] = []
            for page in range(1, MAX_PAGES + 1):
                params = {"serviceKey": key, "pageNo": page, "numOfRows": ROWS, "resultType": "json"}
                if ym:
                    params["test_ym"] = ym
                r = client.get(API_URL, params=params)
                r.raise_for_status()
                got, total = _items_of(r.json())
                rows += got
                # 포털은 numOfRows 를 100 으로 깎아 주기도 한다 — totalCount 를 알면 그것을 기준으로 다음 쪽을 받는다
                if not got or (total is not None and len(rows) >= total) or (total is None and len(got) < ROWS):
                    break
            if rows:
                return rows, sorted({k for row in rows[:20] if isinstance(row, dict) for k in row})
        return [], []
    finally:
        if own:
            client.close()


def load_snapshot() -> list[dict] | None:
    try:
        data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    items = data.get("items") if isinstance(data, dict) else None
    return items or None


def items(force: bool = False) -> tuple[list[dict], str]:
    """(센터 목록, 출처). 출처는 'api' · 'snapshot' · 'sample' 중 하나."""
    now = time.time()
    with _lock:
        fresh = _cache["items"] is not None and now - _cache["at"] < (CACHE_SEC if _cache["source"] == "api" else RETRY_SEC)
        if fresh and not force:
            return _cache["items"], _cache["source"]
        key = service_key()
        got, source, fields, error = None, None, [], None
        if key:
            try:
                rows, fields = fetch(key)
                got = normalize(rows) or None
                source = "api" if got else None
                if not got:
                    error = "응답에 센터가 없음"
            except Exception as e:                    # 네트워크 · 인증 · 응답 모양 — 어떤 것이든 대비 목록으로
                error = f"{type(e).__name__}"
        if got is None:
            got = load_snapshot()
            source = "snapshot" if got else None
        if got is None:
            got = load_json("centers.json").get("items", [])
            source = "sample"
        _cache.update(at=now, items=got, source=source, fields=fields, error=error)
        return got, source


def status() -> dict:
    """진단용 — 어디서 받았는지, 몇 곳인지, 응답에 어떤 칸이 있었는지(값은 내지 않는다)."""
    got, source = items()
    return {"출처": source, "센터수": len(got), "응답필드": _cache["fields"], "오류": _cache["error"],
            "좌표어림": sum(1 for c in got if c.get("좌표어림")), "좌표없음": sum(1 for c in got if c.get("la") is None),
            "스냅숏좌표": len(known_coords()), "데이터": SOURCE_PAGE}
