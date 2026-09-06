"""네트워크 없이 수집 실패와 비교 결과의 경계 조건을 검증한다."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from backend.nfa_video_api import (
    FIELDS, OPERATIONS, Page, Sample, VideoApiError, VideoClient,
    collect_all, collect_sample, load_settings, parse_response, sample_pages,
)
from backend.routine_comparison import (
    combine_samples, compare_overlap, duration_seconds, evaluate_scenario, profile_sample,
    save_comparison, schema_comparison, video_identity,
)


def response_bytes(items, total=1, page=1, size=100, code="00"):
    """실제 데이터가 아닌 응답 구조 검증용 JSON을 만든다."""
    return json.dumps({"response": {"header": {"resultCode": code}, "body": {
        "items": items, "totalCount": total, "pageNo": page, "numOfRows": size,
    }}}).encode()


class ApiTests(unittest.TestCase):
    """키 보호, 응답 정규화, 페이지 표본 범위를 확인한다."""

    def test_single_item_and_allowlist(self):
        row = {"ftns_fctr_nm": "근력", "rptt_tcnt_nm": "999",
               "ecrg_cycl_nm": "999", "trng_hr_nm": "999"}
        page = parse_response(response_bytes({"item": row}))
        self.assertEqual(page.records, [{"ftns_fctr_nm": "근력"}])

    def test_empty_response_variants(self):
        for items in (None, "", [], {"item": []}, {"item": ""}):
            self.assertEqual(parse_response(response_bytes(items, total=0)).records, [])

    def test_xml_and_multiple_rows(self):
        xml = b"<response><header><resultCode>0</resultCode></header><body><totalCount>2</totalCount><pageNo>1</pageNo><numOfRows>100</numOfRows><items><item><tool_nm/></item><item><vdo_len>01:30</vdo_len></item></items></body></response>"
        self.assertEqual(parse_response(xml).records, [{"tool_nm": ""}, {"vdo_len": "01:30"}])

    def test_xml_preserves_explicit_null_and_accepts_utf8_bom(self):
        xml = (
            "<response xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">"
            "<header><resultCode>0</resultCode></header><body>"
            "<totalCount>1</totalCount><pageNo>1</pageNo><numOfRows>100</numOfRows>"
            "<items><item><tool_nm xsi:nil=\"true\"/><trng_plc_nm/>"
            "</item></items></body></response>"
        ).encode("utf-8")
        for prefix in (b"", b"\xef\xbb\xbf"):
            with self.subTest(bom=bool(prefix)):
                page = parse_response(prefix + xml)
                self.assertEqual(page.records, [{"tool_nm": None, "trng_plc_nm": ""}])

    def test_json_accepts_utf8_bom(self):
        page = parse_response(b"\xef\xbb\xbf" + response_bytes({"item": {"tool_nm": "매트"}}))
        self.assertEqual(page.records, [{"tool_nm": "매트"}])

    def test_error_is_not_an_empty_dataset(self):
        for payload in (response_bytes([], code="30"), b"<OpenAPI_ServiceResponse/>",
                        b"<html>error</html>", b"{}", response_bytes([42])):
            with self.assertRaises(VideoApiError):
                parse_response(payload)

    def test_evenly_spaced_pages(self):
        self.assertEqual(sample_pages(950, 100, 3), [1, 5, 10])
        self.assertEqual(sample_pages(200, 100, 3), [1, 2])
        self.assertEqual(sample_pages(0, 100, 3), [1])

    def test_partial_sample_and_collection_failure(self):
        class Client:
            def fetch_page(self, operation, page_no, page_size):
                if page_no > 1:
                    raise VideoApiError("모의 연결 실패")
                return Page([{"tool_nm": "매트"}], 3, 1, 1)

        sample = collect_sample(Client(), OPERATIONS[0].name, page_size=1, max_pages=2)
        self.assertEqual(sample.planned_pages, [1, 3])
        self.assertEqual(sample.pages, [1])
        self.assertFalse(sample.complete)
        self.assertEqual(profile_sample(sample)["scope"], "failed")
        self.assertEqual(len(collect_all(Client(), 1, 2)), 7)

    def test_server_page_mismatch(self):
        class Client:
            def fetch_page(self, operation, page_no, page_size):
                return Page([{}], 2, 1, 1)

        sample = collect_sample(Client(), OPERATIONS[0].name, 1, 2)
        self.assertIsNotNone(sample.error)
        self.assertFalse(sample.complete)

    def test_complete_empty_collection(self):
        class Client:
            def fetch_page(self, operation, page_no, page_size):
                return Page([], 0, 1, page_size)

        sample = collect_sample(Client(), OPERATIONS[0].name)
        self.assertTrue(sample.complete)
        self.assertIsNone(profile_sample(sample)["fields"][FIELDS[0]]["valid_rate"])

    def test_key_encoding_and_network_error_redaction(self):
        with patch("backend.nfa_video_api.urlopen", side_effect=URLError("SECRET")) as opener:
            client = VideoClient("a%2Bb%2Fc%3D", retries=0)
            with self.assertRaises(VideoApiError) as captured:
                client.fetch_page("TODZ_VDO_ROUTINE_I", 1)
            self.assertNotIn("SECRET", str(captured.exception))
            self.assertIsNone(captured.exception.__cause__)
            params = parse_qs(urlsplit(opener.call_args.args[0].full_url).query)
            self.assertEqual(params["serviceKey"], ["a+b/c="])
            self.assertNotIn("a%2B", repr(client))

    def test_unsupported_filter_never_sent(self):
        with patch("backend.nfa_video_api.urlopen") as opener:
            with self.assertRaises(ValueError):
                VideoClient("test").fetch_page("TODZ_VDO_ROUTINE_I", 1,
                                               filters={"trng_plc_nm": "집"})
            opener.assert_not_called()

    def test_dotenv_alias_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env").write_text("API_KEY=local\nDATA_DIR=data/raw\n", encoding="utf-8")
            with patch.dict("os.environ", {"DATA_GO_KR_KEY": "environment"}, clear=True):
                key, data_dir = load_settings(root)
                self.assertEqual(key, "environment")
                self.assertEqual(data_dir, root / "data" / "raw")


class ComparisonTests(unittest.TestCase):
    """시간 단위와 결측 정보가 잘못된 선별 근거가 되지 않는지 확인한다."""

    def test_schema_has_seven_operations_and_only_selected_fields(self):
        self.assertEqual(len(schema_comparison()), 7)
        routine = next(row for row in schema_comparison() if row["operation"] == "TODZ_VDO_ROUTINE_I")
        self.assertEqual(routine["trng_plc_nm"], "absent")
        self.assertEqual(routine["ftns_fctr_nm"], "response")

    def test_four_missing_states_and_invalid_type(self):
        sample = Sample("test", records=[{}, {"tool_nm": None}, {"tool_nm": "  "},
                                         {"tool_nm": []}, {"tool_nm": "매트"}])
        profile = profile_sample(sample)["fields"]["tool_nm"]
        self.assertEqual([profile[key] for key in ("missing", "null", "blank", "invalid", "valid")], [1]*5)
        self.assertEqual(profile["valid_rate"], 0.2)

    def test_duration_unit_must_be_explicit(self):
        self.assertIsNone(duration_seconds("90"))
        self.assertEqual(duration_seconds("90", "seconds"), 90)
        self.assertEqual(duration_seconds(1.5, "minutes"), 90)
        self.assertEqual(duration_seconds("01:30"), 90)
        self.assertEqual(duration_seconds("1:02:03"), 3723)
        self.assertEqual(duration_seconds("1분 30초"), 90)
        for value in ("01:99", 0, -1, "NaN", "inf", True):
            self.assertIsNone(duration_seconds(value, "seconds"))

    def test_duplicate_scene_rows_do_not_inflate_video_counts(self):
        sample = Sample("left", records=[{"file_url": "https://example.com/a.mp4"}]*3)
        other = Sample("right", records=[{"file_url": "https://example.com/a.mp4"}, {}])
        self.assertEqual(profile_sample(sample)["unique_videos"], 1)
        self.assertEqual(compare_overlap([sample, other])[0]["shared_videos"], 1)
        self.assertIsNone(video_identity({"file_nm": "same.mp4", "row_num": 1}))

    def test_routine_requires_known_conditions_and_distinct_videos(self):
        sample = Sample("test", records=[
            {"file_url": f"https://example.com/{index}.mp4", "trng_se_nm": stage,
             "tool_nm": "매트", "vdo_len": "01:00"}
            for index, stage in enumerate(("준비", "본", "정리"))
        ])
        stages = {"warmup": {"준비"}, "main": {"본"}, "cooldown": {"정리"}}
        result = evaluate_scenario(sample, {"tool_nm": {"매트"}}, stages, (180, 200))
        self.assertEqual(result["example"]["seconds"], 180)
        result = evaluate_scenario(sample, {"trng_plc_nm": {"집"}}, stages, (180, 200))
        self.assertIsNone(result["example"])
        self.assertEqual(result["unknown_rows"], 3)
        for row in sample.records:
            row["file_url"] = "https://example.com/same.mp4"
        self.assertIsNone(evaluate_scenario(sample, {}, stages, (180, 200))["example"])

    def test_saved_report_excludes_forbidden_fields(self):
        sample = Sample("test", records=[{"tool_nm": "매트", "trng_hr_nm": "secret"}])
        with tempfile.TemporaryDirectory() as temporary:
            destination = save_comparison([sample], Path(temporary))
            content = destination.read_text(encoding="utf-8")
            self.assertNotIn("trng_hr_nm", content)
            self.assertNotIn("secret", content)

    def test_combining_sources_does_not_invent_complete_metadata(self):
        left = Sample("left", records=[{"file_url": "https://example.com/a.mp4", "tool_nm": "매트"}])
        right = Sample("right", records=[{"file_url": "https://example.com/a.mp4", "trng_plc_nm": "집"}])
        combined = combine_samples([left, right])
        self.assertEqual(len(combined.records), 2)
        self.assertFalse(any("tool_nm" in row and "trng_plc_nm" in row for row in combined.records))
        self.assertFalse(combined.complete)

    def test_conflicting_lengths_are_not_silently_selected(self):
        sample = Sample("test", records=[
            {"file_url": "https://example.com/a.mp4", "trng_se_nm": "준비", "vdo_len": value}
            for value in ("01:00", "02:00")
        ])
        stages = {"warmup": {"준비"}, "main": {"본"}, "cooldown": {"정리"}}
        result = evaluate_scenario(sample, {}, stages, (180, 200))
        self.assertEqual(result["duration_conflicts"], 1)
        self.assertEqual(result["stage_counts"]["warmup"], 0)

    def test_conflicting_lengths_across_stages_are_excluded(self):
        sample = Sample("test", records=[
            {"file_url": "https://example.com/a.mp4", "trng_se_nm": "준비", "vdo_len": "01:00"},
            {"file_url": "https://example.com/a.mp4", "trng_se_nm": "본", "vdo_len": "02:00"},
            {"file_url": "https://example.com/b.mp4", "trng_se_nm": "본", "vdo_len": "01:00"},
            {"file_url": "https://example.com/c.mp4", "trng_se_nm": "정리", "vdo_len": "01:00"},
        ])
        stages = {"warmup": {"준비"}, "main": {"본"}, "cooldown": {"정리"}}
        result = evaluate_scenario(sample, {}, stages, (180, 200))
        self.assertIsNone(result["example"])
        self.assertEqual(result["duration_conflicts"], 1)
        self.assertEqual(result["stage_counts"], {"warmup": 0, "main": 1, "cooldown": 1})


if __name__ == "__main__":
    unittest.main()
