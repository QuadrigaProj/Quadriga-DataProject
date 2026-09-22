"""나이에 따라 거의 움직이지 않는 항목의 환산 — 또래 순위로 나이를 매긴다 (backend/fitness_age.py rank_age · bmi_age).

예전에는 모든 항목을 '내 기록이 몇 살의 중앙값인가' 로 읽었다. 성인 유연성은 중앙값이 나이에 따라 거의 평평해서
(여성 해마다 0.006cm, 오르내림이 다섯 번 뒤집힌다) 34세 여성이 12cm → 16cm 로 좋아졌는데 42세 → 47.7세로 늙게 나왔다.
"""
import pytest

from backend import fitness_age as fa
from backend.paths import find_data


def _data_ready() -> bool:
    try:
        find_data("fitness_distribution.csv")
        return True
    except FileNotFoundError:
        return False


needs_data = pytest.mark.skipif(not _data_ready(), reason="분포 데이터 없음")
FLEX = "앉아윗몸앞으로굽히기"


@pytest.fixture(scope="module")
def d():
    return fa.load()


@needs_data
def test_성인_유연성만_나이_신호가_없다(d):
    """순위로 매길 항목은 손으로 고르지 않는다 — 분포표에서 잰 신호로 가른다."""
    for sex in ("F", "M"):
        assert fa.age_signal(d, "성인", sex, FLEX) < fa.AGE_SIGNAL_MIN
        assert fa.age_signal(d, "성인", sex, "교차윗몸일으키기") >= fa.AGE_SIGNAL_MIN
        assert fa.age_signal(d, "어르신", sex, FLEX) >= fa.AGE_SIGNAL_MIN        # 어르신 유연성은 나이에 따라 줄어든다
    # 신호가 있는 항목은 지금까지처럼 곡선으로 읽는다
    assert fa.item_age(d, "성인", "F", "교차윗몸일으키기", 20, 34) == fa.convert_age(d, "성인", "F", "교차윗몸일으키기", 20)


@needs_data
@pytest.mark.parametrize("sex, age", [("F", 34), ("M", 34), ("F", 55), ("M", 25)])
def test_성인_유연성은_좋아질수록_어려진다(d, sex, age):
    ages = [fa.item_age(d, "성인", sex, FLEX, cm, age) for cm in (0, 4, 8, 12, 16, 20, 24, 28)]
    assert all(a is not None for a in ages)
    assert all(b <= a for a, b in zip(ages, ages[1:]))              # 한 번도 거꾸로 가지 않는다
    assert ages[0] > ages[-1]
    # 실제 나이 ±15세, 그리고 성인 구간(21.5~62세) 안에 머문다
    assert all(max(21.5, age - 15) <= a <= min(62.0, age + 15) or a == age for a in ages)


@needs_data
def test_보고된_사례_12cm에서_16cm로_늘면_어려진다(d):
    전 = fa.fitness_age(d, "성인", "F", flexibility=12, strength=20, bmi=21.5, age=34)
    후 = fa.fitness_age(d, "성인", "F", flexibility=16, strength=20, bmi=21.5, age=34)
    assert 후["항목별"]["유연성"] < 전["항목별"]["유연성"]
    assert 후["체력나이"] < 전["체력나이"]


@needs_data
def test_또래_중앙값이면_실제_나이다(d):
    row, _, _ = fa._peer_row(d, "성인", "F", 34, FLEX)
    assert fa.item_age(d, "성인", "F", FLEX, float(row["p50"]), 34) == pytest.approx(34, abs=0.5)


@needs_data
def test_나이를_모르면_순위로_매기지_않는다(d):
    """또래를 정할 수 없다 — 없는 나이를 만들어 비교하지 않는다. 화면은 언제나 나이를 함께 보낸다."""
    assert fa.item_age(d, "성인", "F", FLEX, 12) is None
    assert fa.bmi_age(d, "성인", "F", 27.0) is None


@needs_data
def test_순위_한_칸은_같은_사람의_기본_항목_눈금이다(d):
    assert fa.years_per_sd(d, "성인", "F") == pytest.approx(25.0, abs=0.5)
    assert fa.years_per_sd(d, "성인", "M") == pytest.approx(23.3, abs=0.5)
    assert fa.years_per_sd(d, "어르신", "F") == pytest.approx(14.9, abs=0.5)


@needs_data
@pytest.mark.parametrize("gbn, sex, age", [("성인", "F", 34), ("성인", "M", 45), ("어르신", "F", 72), ("어르신", "M", 72)])
def test_BMI_정상_범위는_실제_나이_벗어나면_단조롭게_늘어난다(d, gbn, sex, age):
    for bmi in (18.5, 20.0, 22.0, 22.9):
        assert fa.bmi_age(d, gbn, sex, bmi, age) == age
    위 = [fa.bmi_age(d, gbn, sex, b, age) for b in (23.5, 24.0, 25.0, 27.0, 30.0, 35.0)]   # 23 에서 0 으로 시작해 이어진다
    아래 = [fa.bmi_age(d, gbn, sex, b, age) for b in (18.4, 17.5, 16.5, 15.0)]
    for seq in (위, 아래):
        assert all(a > age for a in seq)
        assert all(b >= a for a, b in zip(seq, seq[1:]))
        assert max(seq) <= age + fa.STABILIZE_LIMIT


@needs_data
def test_성장기_BMI는_나이로_바꾸지_않는다(d):
    """성장기의 체력나이는 발달 수준이다 — BMI 로는 말할 수 없다. 또래비교에는 그대로 나온다."""
    r = fa.fitness_age(d, "성장기", "F", flexibility=10, strength=150, bmi=20.5, age=15)
    assert "체성분" not in r["항목별"]
    assert "체성분" in fa.peer_report(d, "성장기", "F", 15, bmi=20.5)


@needs_data
def test_BMI는_비만_저체중_단계마다_5세씩_더한다(d):
    """대한비만학회 비만 단계(전단계 23 · 1단계 25 · 2단계 30 · 3단계 35), WHO 저체중 단계(17 · 16 · 15)."""
    assert fa.bmi_age(d, "성인", "M", 25.0, 45) == 50.0
    assert fa.bmi_age(d, "성인", "M", 26.0, 45) == 51.0          # 흔한 중년 남성 체형 — 상한까지 가지 않는다
    assert fa.bmi_age(d, "성인", "M", 30.0, 45) == 55.0
    assert fa.bmi_age(d, "성인", "F", 17.0, 25) == 30.0
    assert fa.bmi_age(d, "어르신", "F", 40.0, 70) == 85.0        # 3단계 넘어서는 +15세에서 멈춘다

