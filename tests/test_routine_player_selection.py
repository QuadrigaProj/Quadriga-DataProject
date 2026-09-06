"""영상 조건 필터와 단계별 배정의 경계 조건을 검증한다."""

from copy import deepcopy
import unittest

from backend.routine_player import PHASES, VideoFilter, build_video_routine, filter_videos, normalize_phase


def video(name, phase="본운동", **changes):
    """실제 API 데이터와 구분되는 모의 영상 한 행을 만든다."""
    row = {"file_url": f"https://example.com/{name}.mp4", "vdo_ttl_nm": name,
           "trng_se_nm": phase, "ftns_fctr_nm": "유연성", "trng_part_nm": "상체",
           "tool_nm": "맨몸", "trng_plc_nm": "집", "vdo_len": "01:00"}
    row.update(changes)
    return row


class FilteringTests(unittest.TestCase):
    """조건별 일치 방식과 제외·미확인 사유를 확인한다."""

    def test_each_field_can_filter_independently(self):
        for field_name, argument in (("ftns_fctr_nm", "factors"), ("trng_part_nm", "parts"),
                                     ("tool_nm", "tools"), ("trng_plc_nm", "places")):
            with self.subTest(field=field_name):
                rows = [video("a", **{field_name: "허용"}), video("b", **{field_name: "제외"})]
                result = filter_videos(rows, VideoFilter(**{argument: {"허용"}}))
                self.assertEqual([row["vdo_ttl_nm"] for row in result.videos], ["a"])
                self.assertEqual(result.rejected_count, 1)

    def test_conditions_are_combined_with_and(self):
        rows = [video("a"), video("b", tool_nm="덤벨"), video("c", trng_plc_nm="체육관")]
        result = filter_videos(rows, VideoFilter(factors={"유연성"}, parts={"상체"},
                                                 tools={"맨몸"}, places={"집"}))
        self.assertEqual(len(result.videos), 1)
        self.assertEqual(result.rejected_count, 2)

    def test_composite_tools_require_every_tool(self):
        rows = [video("a", tool_nm="매트/의자")]
        self.assertEqual(filter_videos(rows, VideoFilter(tools={"매트"})).rejected_count, 1)
        self.assertEqual(len(filter_videos(rows, VideoFilter(tools={"매트", "의자"})).videos), 1)

    def test_composite_factors_match_any_selected_factor(self):
        result = filter_videos([video("a", ftns_fctr_nm="근력·근지구력")], VideoFilter(factors={"근력"}))
        self.assertEqual(len(result.videos), 1)

    def test_no_substring_or_implicit_home_match(self):
        self.assertEqual(filter_videos([video("a", trng_plc_nm="집근처")], VideoFilter(places={"집"})).rejected_count, 1)
        self.assertEqual(filter_videos([video("a", trng_plc_nm="실내")], VideoFilter(places={"집"})).rejected_count, 1)

    def test_explicit_alias_and_custom_separator(self):
        rows = [video("a", tool_nm="요가매트&의자")]
        result = filter_videos(rows, VideoFilter(tools={"매트", "의자"}),
                               aliases={"tool_nm": {"요가매트": "매트"}}, separators=("&",))
        self.assertEqual(len(result.videos), 1)

    def test_excluded_parts_win_over_allowed_parts(self):
        result = filter_videos([video("a", trng_part_nm="상체/어깨")],
                               VideoFilter(parts={"상체"}, excluded_parts={"어깨"}))
        self.assertEqual(result.reasons, {"excluded:trng_part_nm": 1})

    def test_unknown_values_do_not_pass_required_conditions(self):
        rows = [video(str(i), tool_nm=value) for i, value in enumerate((None, "", "  ", 0, [], "매트//의자"))]
        missing = video("missing")
        del missing["tool_nm"]
        result = filter_videos(rows + [missing], VideoFilter(tools={"맨몸"}))
        self.assertEqual(result.unknown_count, 7)
        self.assertFalse(result.videos)

    def test_exclusion_requires_known_part(self):
        result = filter_videos([video("a", trng_part_nm=None)], VideoFilter(excluded_parts={"어깨"}))
        self.assertEqual(result.unknown_count, 1)

    def test_unspecified_conditions_are_not_required(self):
        result = filter_videos([{"vdo_ttl_nm": "정보 부족"}], VideoFilter())
        self.assertEqual(len(result.videos), 1)

    def test_invalid_conditions_raise(self):
        for criteria in (VideoFilter(tools="매트"), VideoFilter(places=set()), VideoFilter(parts={" "})):
            with self.subTest(criteria=criteria), self.assertRaises(ValueError):
                filter_videos([], criteria)

    def test_input_is_not_mutated_and_extra_fields_are_not_returned(self):
        rows = [video("a", unrelated="버릴 값")]
        original = deepcopy(rows)
        result = filter_videos(rows, VideoFilter())
        result.videos[0]["vdo_ttl_nm"] = "변경"
        self.assertEqual(rows, original)
        self.assertNotIn("unrelated", result.videos[0])


class RoutineSelectionTests(unittest.TestCase):
    """단계 순서·중복 없는 배정·불완전한 루틴의 상태를 확인한다."""

    def test_phase_normalization(self):
        for original, expected in ((" 준비 운동 ", "준비운동"), ("본", "본운동"), ("정리\t운동", "정리운동")):
            self.assertEqual(normalize_phase(original), expected)
        for value in (None, "", "본운동/정리운동", "워밍업", 1):
            self.assertIsNone(normalize_phase(value))

    def test_shuffled_input_produces_ordered_routine(self):
        rows = [video("c", "정리운동"), video("b", "본운동"), video("a", "준비운동")]
        result = build_video_routine(rows)
        self.assertEqual(result.status, "complete")
        self.assertEqual([step["phase"] for step in result.steps], list(PHASES))
        self.assertEqual([step["order"] for step in result.steps], [1, 2, 3])
        self.assertEqual(result.total_seconds, 180)

    def test_reassigns_shared_candidate_instead_of_missing_feasible_routine(self):
        rows = [video("shared", "준비운동"), video("alternative", "준비운동"),
                video("shared", "본운동"), video("cooldown", "정리운동")]
        result = build_video_routine(rows)
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.steps[0]["video"]["vdo_ttl_nm"], "alternative")
        self.assertEqual(len({step["file_url"] for step in result.steps}), 3)

    def test_duplicate_rows_do_not_meet_multiple_slots(self):
        rows = [video("a", "준備運動"), video("b"), video("b"), video("c", "정리운동")]
        rows[0]["trng_se_nm"] = "준비운동"
        result = build_video_routine(rows, counts={"준비운동": 1, "본운동": 2, "정리운동": 1})
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(result.missing, {"본운동": 1})
        self.assertIsNone(result.total_seconds)

    def test_one_url_cannot_fill_three_phases(self):
        result = build_video_routine([video("same", phase) for phase in PHASES])
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(sum(result.missing.values()), 2)

    def test_phase_filters_do_not_apply_main_factor_to_other_phases(self):
        rows = [video("a", "준비운동"), video("b", ftns_fctr_nm="근력"), video("c", "정리운동")]
        result = build_video_routine(rows, criteria=VideoFilter(places={"집"}),
                                     phase_filters={"본운동": VideoFilter(factors={"근력"})})
        self.assertEqual(result.status, "complete")
        rows[1]["trng_plc_nm"] = "체육관"
        self.assertEqual(build_video_routine(rows, criteria=VideoFilter(places={"집"}),
                                             phase_filters={"본운동": VideoFilter(factors={"근력"})}).status, "incomplete")

    def test_missing_phase_and_invalid_url_are_reported(self):
        result = build_video_routine([video("a", "준비운동", file_url=""), video("b", "알수없음")])
        self.assertEqual(result.missing, dict.fromkeys(PHASES, 1))
        self.assertEqual(result.diagnostics["invalid_url_rows"], 1)
        self.assertEqual(result.diagnostics["unknown_phase_rows"], 1)

    def test_numeric_duration_is_not_guessed(self):
        rows = [video(str(i), phase, vdo_len=60) for i, phase in enumerate(PHASES)]
        result = build_video_routine(rows)
        self.assertEqual(result.status, "complete")
        self.assertIsNone(result.total_seconds)
        self.assertEqual(len(result.unknown_duration_urls), 3)
        self.assertEqual(build_video_routine(rows, numeric_unit="seconds").total_seconds, 180)

    def test_duration_conflict_across_phases_is_excluded(self):
        rows = [video("a", "준비운동"), video("a", "본운동", vdo_len="02:00"),
                video("b"), video("c", "정리운동")]
        result = build_video_routine(rows)
        self.assertEqual(result.missing, {"준비운동": 1})
        self.assertEqual(len(result.duration_conflicts), 1)

    def test_requested_counts_and_stable_results(self):
        rows = [video(f"{phase}{i}", phase) for phase in PHASES for i in range(3)]
        counts = {"준비운동": 2, "본운동": 3, "정리운동": 2}
        result = build_video_routine(rows, counts=counts)
        self.assertEqual(len(result.steps), 7)
        self.assertEqual(result.total_seconds, 420)
        self.assertEqual(result, build_video_routine(rows, counts=counts))

    def test_invalid_counts_and_phase_names_raise(self):
        for counts in ({}, {"준비운동": 1}, dict.fromkeys(PHASES, 0), dict.fromkeys(PHASES, True)):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                build_video_routine([], counts=counts)
        with self.assertRaises(ValueError):
            build_video_routine([], phase_filters={"준비": VideoFilter()})


if __name__ == "__main__":
    unittest.main()
