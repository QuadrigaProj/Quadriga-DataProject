"""국민체력100 동영상 오퍼레이션의 명세와 제한된 표본 수집을 제공한다."""

import json
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


SOURCE_URL = "https://www.data.go.kr/data/15108846/openapi.do"
SPEC_CHECKED_AT = "2026-09-06"
BASE_URL = "https://apis.data.go.kr/B551014/SRVC_TODZ_VDO_PKG"
FIELDS = (
    "ftns_fctr_nm", "trng_se_nm", "trng_aim_nm", "tool_nm",
    "trng_plc_nm", "trng_part_nm", "vdo_len",
)
# 분석용 필드와 영상 식별·재생 확인용 필드만 보관한다.
MEDIA_FIELDS = ("file_url", "file_nm", "vdo_ttl_nm", "trng_nm", "oper_nm")
RETAINED_FIELDS = FIELDS + MEDIA_FIELDS


@dataclass(frozen=True)
class Operation:
    """공식 명세의 비교 대상 필드만 담는다."""

    name: str
    title: str
    request_fields: tuple[str, ...]
    response_fields: tuple[str, ...]


OPERATIONS = (
    Operation("TODZ_VDO_FTNS_CERT_I", "체력인증측정방법",
              ("ftns_fctr_nm", "tool_nm"),
              ("ftns_fctr_nm", "tool_nm", "vdo_len")),
    Operation("TODZ_VDO_TRNG_VIDEO_I", "운동처방동영상",
              ("trng_plc_nm", "tool_nm"),
              ("trng_plc_nm", "tool_nm", "vdo_len")),
    Operation("TODZ_VDO_MSCL_TRNG_I", "근골격계운동",
              ("trng_part_nm", "tool_nm"),
              ("trng_part_nm", "tool_nm", "vdo_len")),
    Operation("TODZ_VDO_STD_FTNS_I", "생애주기별표준운동", (), ("vdo_len",)),
    Operation("TODZ_VDO_ROUTINE_I", "목적별루틴운동",
              ("trng_aim_nm", "trng_se_nm", "tool_nm"),
              ("ftns_fctr_nm", "trng_se_nm", "trng_aim_nm", "tool_nm",
               "trng_part_nm", "vdo_len")),
    Operation("TODZ_VDO_VIEW_ALL_LIST_I", "동영상 목록", (), ("vdo_len",)),
    Operation("TODZ_VDO_TRNG_GUIDE_I", "운동처방가이드",
              ("ftns_fctr_nm", "tool_nm"),
              ("ftns_fctr_nm", "tool_nm", "trng_plc_nm", "vdo_len")),
)
OPERATION_BY_NAME = {operation.name: operation for operation in OPERATIONS}


class VideoApiError(RuntimeError):
    """인증키나 원본 응답을 포함하지 않는 API 오류다."""


@dataclass
class Page:
    """페이지 메타정보와 허용된 응답 값이다."""

    records: list[dict]
    total_count: int
    page_no: int
    page_size: int


@dataclass
class Sample:
    """수집 범위와 실패 여부를 데이터와 함께 보관한다."""

    operation: str
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    records: list[dict] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    planned_pages: list[int] = field(default_factory=list)
    total_count: int | None = None
    page_size: int = 100
    complete: bool = False
    error: str | None = None


def load_settings(project_root: Path) -> tuple[str | None, Path]:
    """저장소의 환경 설정을 읽으며 기존 환경변수를 우선한다."""
    from dotenv import dotenv_values

    root = Path(project_root).resolve()
    values = {**dotenv_values(root / ".env"), **os.environ}
    key = None
    for name in ("DATA_GO_KR_KEY", "API_KEY"):
        candidate = str(values.get(name) or "").strip()
        if candidate and candidate != "your_api_key_here":
            key = candidate
            break
    data_dir = Path(values.get("DATA_DIR") or "data/raw")
    if not data_dir.is_absolute():
        data_dir = root / data_dir
    return key, data_dir


def parse_response(payload: bytes) -> Page:
    """JSON/XML의 단일·복수 항목과 빈 결과를 같은 형태로 변환한다."""
    try:
        payload = payload.removeprefix(b"\xef\xbb\xbf")
        if payload.lstrip().startswith(b"<"):
            if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
                raise ValueError
            root = ElementTree.fromstring(payload)
            for element in root.iter():
                element.tag = element.tag.rsplit("}", 1)[-1]
            if root.tag != "response":
                raise VideoApiError("API 인증 또는 응답 형식 오류")
            code = root.findtext("header/resultCode")
            body_element = root.find("body")
            body = {}
            if body_element is not None:
                body = {name: body_element.findtext(name)
                        for name in ("pageNo", "numOfRows", "totalCount")}
                body["items"] = []
                for item in body_element.findall("items/item"):
                    record = {}
                    for child in item:
                        if child.tag not in RETAINED_FIELDS:
                            continue
                        nil = child.get("{http://www.w3.org/2001/XMLSchema-instance}nil")
                        record[child.tag] = None if nil in ("true", "1") else child.text or ""
                    body["items"].append(record)
        else:
            document = json.loads(payload)
            response = document.get("response", document)
            code = response.get("header", {}).get("resultCode")
            body = response.get("body", {})
        if str(code) not in ("0", "00", "0000"):
            # 서버 메시지는 요청 URL이나 인증키를 되돌려줄 수 있어 출력하지 않는다.
            raise VideoApiError("API 결과 코드 오류: 인증·요청 조건·호출량을 확인하세요")
        total = int(body["totalCount"])
        page_no = int(body["pageNo"])
        page_size = int(body["numOfRows"])
        if total < 0 or page_no < 1 or page_size < 1:
            raise ValueError
        items = body.get("items")
        if isinstance(items, dict):
            items = items.get("item")
        if items in (None, ""):
            items = []
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError
        records = [{name: item[name] for name in RETAINED_FIELDS if name in item}
                   for item in items]
        return Page(records, total, page_no, page_size)
    except VideoApiError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, ElementTree.ParseError):
        raise VideoApiError("API 응답 구조 또는 페이지 메타정보가 올바르지 않습니다") from None


class VideoClient:
    """키를 기록하지 않고 공식 HTTPS 주소에만 요청한다."""

    def __init__(self, api_key: str, timeout: float = 20, retries: int = 2):
        if not api_key or api_key == "your_api_key_here":
            raise ValueError("유효한 API 인증키 설정이 필요합니다")
        if timeout <= 0 or not 0 <= retries <= 3:
            raise ValueError("시간 제한은 양수, 재시도는 0~3회여야 합니다")
        self._api_key = api_key
        self.timeout = timeout
        self.retries = retries

    def fetch_page(self, operation: str, page_no: int, page_size: int = 100,
                   filters: dict[str, str] | None = None) -> Page:
        """명세상 지원하는 비교 필드만 요청 필터로 허용한다."""
        if operation not in OPERATION_BY_NAME:
            raise ValueError("등록되지 않은 오퍼레이션입니다")
        if page_no < 1 or not 1 <= page_size <= 1000:
            raise ValueError("페이지는 1 이상, 페이지 크기는 1~1000이어야 합니다")
        filters = filters or {}
        if set(filters) - set(OPERATION_BY_NAME[operation].request_fields):
            raise ValueError("이 오퍼레이션이 지원하지 않는 요청 필터입니다")
        params = {"serviceKey": unquote(self._api_key), "pageNo": page_no,
                  "numOfRows": page_size, "resultType": "json", **filters}
        request = Request(f"{BASE_URL}/{operation}?{urlencode(params)}")
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return parse_response(response.read())
            except HTTPError as error:
                retryable = error.code in (429, 500, 502, 503, 504)
                if not retryable or attempt == self.retries:
                    raise VideoApiError(f"API HTTP 오류 ({error.code})") from None
            except (URLError, TimeoutError, OSError):
                if attempt == self.retries:
                    raise VideoApiError("API 네트워크 연결 또는 시간 초과 오류") from None
            time.sleep(2 ** attempt)
        raise VideoApiError("API 요청 실패")


def sample_pages(total_count: int, page_size: int, max_pages: int) -> list[int]:
    """전체 범위에 균등 간격으로 페이지를 배치한다. 무작위 표본은 아니다."""
    if total_count < 0 or not 1 <= page_size <= 1000 or max_pages < 1:
        raise ValueError("수집 범위 설정이 올바르지 않습니다")
    last = max(1, math.ceil(total_count / page_size))
    count = min(last, max_pages)
    if count == 1:
        return [1]
    return sorted({1 + round(index * (last - 1) / (count - 1))
                   for index in range(count)})


def collect_sample(client: VideoClient, operation: str, page_size: int = 100,
                   max_pages: int = 3) -> Sample:
    """동일한 무필터 조건으로 수집하며 실패·부분 수집을 구분한다."""
    sample_pages(0, page_size, max_pages)
    sample = Sample(operation=operation, page_size=page_size)
    try:
        first = client.fetch_page(operation, 1, page_size)
        sample.total_count = first.total_count
        sample.planned_pages = sample_pages(first.total_count, page_size, max_pages)
        for page_no in sample.planned_pages:
            page = first if page_no == 1 else client.fetch_page(operation, page_no, page_size)
            if (page.total_count != sample.total_count or page.page_no != page_no
                    or page.page_size != page_size):
                raise VideoApiError("수집 중 전체 건수 또는 페이지 정보가 달라졌습니다")
            expected = min(page_size, max(0, page.total_count - (page_no - 1) * page_size))
            if len(page.records) != expected:
                raise VideoApiError("페이지 항목 수가 전체 건수와 일치하지 않습니다")
            sample.records.extend(page.records)
            sample.pages.append(page_no)
        sample.complete = len(sample.records) == sample.total_count
    except VideoApiError as error:
        sample.error = str(error)
    return sample


def collect_all(client: VideoClient, page_size: int = 100, max_pages: int = 3) -> list[Sample]:
    """7개 오퍼레이션을 같은 페이지 크기와 최대 페이지 수로 조사한다."""
    return [collect_sample(client, operation.name, page_size, max_pages)
            for operation in OPERATIONS]
