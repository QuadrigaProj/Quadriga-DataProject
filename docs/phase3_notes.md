# Phase 3 구현 메모 (InBody · 홈 체력측정 · 센터 · 연령대)

## 구현됨

| 스펙 | 위치 | 비고 |
|---|---|---|
| 1-A InBody | `backend/bodycomp.py` · `POST /bodycomp` · s1 "InBody" 탭 | 체지방률·BMI 분포로 **근거 있는** 추정 체력나이. 골격근량·체수분·허리둘레는 판정 기준(대한비만학회·WHO·AWGS)이 있는 것만 '분석'으로 표시. 임의 산식 없음 |
| 1-B 홈 체력측정 | `backend/hometest.py` · `POST /hometest` · s1 "홈 체력측정" 탭 | 30초 점프 → `반복점프`, 30초 컬업 → `교차윗몸일으키기` (같은 측정이라 환산). 무릎푸시업·2분하이니는 공개 대응 항목이 없어 **등급(A~E)만**, 체력나이엔 미반영 |
| 16 센터 연결 | `backend/geo.py` · `GET /centers?region=` · s5 하단 | 역/지역명 → 내장 좌표표로 지오코딩 → **직선거리**순. 길찾기 API 없어 도보시간 안 만듦. 예약은 국민체력100 공식 페이지 링크 |
| 17 운동 영상 | (기존) `/video-routine` | 표준 동작명 유지. 실제 `file_url` 바인딩은 서비스키 후 |

## 남은 작업 (외부 키 필요)

### 2. 연령대 5개 체력나이 (유아기·유소년)
`data.go.kr/data/15108938` (국민체력100 측정결과, **체지방률·허리둘레·반복점프·윗몸말아올리기** 포함)에서
유아기·유소년 분포를 수집해야 함. 현재:
- `backend/collect_measurements.py` + `build_distribution.py` 파이프라인이 성인/성장기/어르신만 채워져 있음
- 유아기·유소년은 `fitness_age()` 가 `체력나이=None` 을 반환 → 화면은 홈 등급/루틴만 제공 (억지 산출 안 함)
- **할 일**: 서비스키 발급 → 수집 스크립트에 `age_gbn IN (유아기, 유소년)` 추가 → `data/processed/fitness_distribution.csv` 갱신. 스키마·코드 변경 불필요

### 17. KSPO 영상 `file_url`
서비스키 발급 후 `backend/nfa_video_api.py` 로 각 루틴 코드의 `kspo` 필터를 실제 API 에 질의.
