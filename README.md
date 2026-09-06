# Quadriga-DataProject

> **체력나이 진단 기반 일상 운동 루틴 및 생활활동 처방 서비스**
> 측정은 3개월에 한 번, 운동은 매일.

[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/QuadrigaProj/Quadriga-DataProject/pulls)

---

## 📌 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 주제 | 국민체력100 측정 데이터로 **체력나이**를 산출하고, 부족한 체력요인을 보완하는 매일 10~15분 운동 루틴을 처방하는 서비스 |
| 공모전 | 2026년 국민체육진흥공단 공공데이터 활용 경진대회 · 서비스(웹/앱) 개발 부문 |
| 목표 | 측정 → 처방 → 실행 → 재측정 고리를 완성한다. 국민체력100은 측정과 처방을 제공하지만 그 처방을 일상에서 실행할 경로가 없다 |
| 기간 | 2026.09 ~ 2026.10.02 (접수 마감) |
| 활용 데이터 | 국민체력100 **체력인증센터 측정결과 정보** (296만 건) / **동영상 정보** (1.5만 건) |
| 기획안 | **[docs/기획안.md](./docs/기획안.md)** ← 작업 전 필독 |

## 🎯 핵심 구조

```
⓪ 로그인  구글 · 네이버 · 카카오 또는 이메일 → 기기가 바뀌어도 이어짐
            ↓
① 진단   집에서 3항목 자가 측정 → 체력나이 78세 (실제 72세)
            ↓
② 목적   다이어트 / 기초체력 / 낙상예방 / 수험생 / 유연성 / 특정운동
            ↓
③ 처방   가장 효율적인 약점 하나를 지목 → "근력을 고치면 -4세"
            ↓
④ 실행   매일 같은 시간 10~15분 루틴 · 4주마다 강도 상승
            ↓
⑤ 증명   3개월 뒤 재점검 → 78세 → 75세
```

**매일 숫자를 보여주지 않는다.** 매일 보는 숫자는 곧 무시되지만,
3개월에 한 번 바뀌는 숫자는 기다림이 된다. 이것이 설계의 중심이다.

## 👥 팀원

| 이름 | GitHub | 담당 |
|---|---|---|
| 장예현 | [@yhjang0315-source](https://github.com/yhjang0315-source) | 총괄 / 저장소 관리 |
| 유민진 | [@Jjin39](https://github.com/Jjin39) | (담당 영역) |
| 정다은 | [@daje0102](https://github.com/daje0102) | (담당 영역) |
| 염윤서 | [@yunseoo00](https://github.com/yunseoo00) | (담당 영역) |

## 🗂 폴더 구조

**사람이 아니라 역할로 나눕니다. 파일에 주인은 없습니다** — 필요하면 누구든 어느 파일이든 고쳐서 PR 올리세요.

```
Quadriga-DataProject/
├── frontend/                    # 화면 (브라우저에서 도는 것 전부)
│   ├── index.html               #   로그인 + 6개 화면 · 스타일 · 화면 로직
│   └── js/api.js                #   백엔드 호출 계층
├── backend/                     # 서버 (계산 · 데이터 전부)
│   ├── main.py                  #   FastAPI 엔드포인트 — 화면이 붙는 지점
│   ├── fitness_age.py           #   체력나이 산출 + 약점 지목
│   ├── prescription.py          #   실제 처방 기록 기반 운동 추천
│   ├── auth.py                  #   계정 · 세션 · 측정 기록 (SQLite / Postgres)
│   ├── daily.py                 #   일상 처방 · 강도 점증 · 영상 필터
│   ├── paths.py                 #   데이터 경로 탐색
│   ├── collect_measurements.py  #   공공데이터 수집
│   └── build_distribution.py    #   분포표 · 처방 빈도 생성
├── data/
│   ├── raw/                     # API 원본 응답 (Git 추적 안 함)
│   ├── processed/               # 가공 결과 (Git 추적 안 함)
│   └── sample/                  # 공유용 소용량 샘플 (Git 추적 O)
├── tests/                       # API 스모크 테스트
├── notebooks/                   # 데이터 분석 (여기만 담당자별 파일)
├── docs/
│   ├── 기획안.md
│   └── Git-가이드.md             # Git 처음이면 여기부터 ← 작업 전 필독
├── render.yaml                  # 배포 설정 (Render Blueprint)
├── requirements.txt             # 서버 실행용
├── requirements-dev.txt         # 분석 · 노트북용
├── AGENTS.md                    # AI 도구 사용 규칙
└── CONTRIBUTING.md              # 브랜치 전략 & 협업 규칙 ← 작업 전 필독
```

> ⚠️ **API 키와 데이터 파일은 절대 커밋하지 않습니다.**
> 키는 `.env` 에 넣으세요. `.env.example` 을 복사해서 쓰면 됩니다.

## 🔑 공공데이터 API

활용신청 승인 완료 (2026-09-06 ~ 2028-09-06).

| 데이터 | 엔드포인트 |
|---|---|
| 측정결과 정보 | `apis.data.go.kr/B551014/SRVC_NFA_TEST_RESULT/TODZ_NFA_TEST_RESULT_NEW` |
| 동영상 정보 | `apis.data.go.kr/B551014/SRVC_TODZ_VDO_PKG/` (오퍼레이션 7종) |

```bash
# .env
DATA_GO_KR_KEY=발급받은_인증키
```

인증키는 총괄에게 요청하세요. **채팅방에 붙여넣지 마세요.**

## ⚙️ 개발 환경 세팅

```bash
# 1. 클론
git clone https://github.com/QuadrigaProj/Quadriga-DataProject.git
cd Quadriga-DataProject

# 2. 가상환경 생성 & 활성화
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. 패키지 설치 (서버 실행용)
pip install -r requirements.txt

# 3-1. 분석·노트북까지 하려면
pip install -r requirements-dev.txt

# 4. 노트북 출력 자동 제거 (한 번만)
nbstripout --install
```

패키지를 새로 설치했다면 반드시 반영해주세요.

```bash
pip freeze > requirements.txt
```

## 🚀 실행

```bash
uvicorn backend.main:app --reload
```

한 서버가 화면과 API 를 함께 내보냅니다.

- **화면: http://localhost:8000**
- API 문서(눌러보며 테스트): http://localhost:8000/docs

`data/sample/` 의 샘플 데이터로 clone 직후 바로 돌아갑니다.
직접 수집한 데이터를 `data/processed/` 에 두면 그쪽을 우선 사용합니다.

### 엔드포인트

| 메서드 | 경로 | 용도 | 화면 |
|---|---|---|---|
| `GET` | `/health` | 데이터 로드 여부 | 앱 시작 시 |
| `GET` | `/purposes` | 목적 6종 목록 | 화면 2 |
| `POST` | `/fitness-age` | 측정값 → 체력나이 + 약점 | 화면 1 · 5 |
| `GET` | `/routine` | 준비 2 → 본 3 → 정리 2 루틴 | 화면 4 |
| `GET` | `/daily` | 계단 · 도보 제안 + 주차별 강도 | 화면 3 |
| `GET` | `/videos` | 요인 · 부담부위로 거른 동영상 | 화면 4 |
| `GET` | `/video-routine` | 준비→본→정리 **영상** 루틴 (`routine_player.py`) | 화면 4 |
| `GET` | `/centers` | 가까운 인증센터 | (예정) |
| `POST` | `/recheck` | 3개월 뒤 변화량 + 측정편차 판정 | 화면 6 |
| `GET` | `/auth/providers` | 활성화된 소셜 제공자 | 화면 0 |
| `POST` | `/auth/signup` · `/auth/login` · `/auth/logout` | 이메일 계정 | 화면 0 |
| `GET` | `/auth/{provider}/start` | 소셜 로그인 시작 | 화면 0 |
| `GET`·`DELETE` | `/auth/me` | 내 계정 조회 · 삭제 | 프로필 |
| `GET`·`POST` | `/me/measurements` | 측정 기록 (기기 간 이어보기) | 전체 |

<details>
<summary>요청 · 응답 예시</summary>

**POST `/fitness-age`**

```json
{ "age_gbn": "성인", "sex": "M",
  "flexibility": 8.0, "strength": 25,
  "height_cm": 175, "weight_kg": 74 }
```

```json
{ "체력나이": 46.2,
  "신뢰구간": 9.1,
  "항목별": { "유연성": 52.0, "근력": 62.0, "체성분": 24.7 },
  "약점": { "약점": "근력", "개선효과": 12.4,
           "전체": { "유연성": 9.1, "근력": 12.4, "체성분": 0.0 } } }
```

> 화면에는 `46세 (±9세)` 처럼 **편차를 함께** 보여줍니다.
> 자가 측정 오차를 숨기지 않는 것이 심사에서의 방어 포인트입니다.

**GET `/routine?age_gbn=성인&sex=M&purpose=다이어트&weak_factor=근력`**

`weak_factor` 에는 `/fitness-age` 응답의 `약점.약점` 을 그대로 넘깁니다.

```json
[ { "단계": "준비운동", "운동명": "전신 루틴 스트레칭", "체력요인": "유연성" },
  { "단계": "본운동",   "운동명": "앉았다 일어서기",   "체력요인": "근력" },
  { "단계": "정리운동", "운동명": "하지 루틴 스트레칭2", "체력요인": "유연성" } ]
```

</details>

### 로그인

| 수단 | 상태 |
|---|---|
| 구글 · 네이버 · 카카오 | `.env` 에 키를 넣으면 활성화. 없으면 버튼이 비활성으로 표시됩니다 |
| 이메일 + 비밀번호 | 항상 사용 가능 |
| 가입 없이 이 기기에서만 | 로그인 화면 맨 아래 링크. 브라우저에만 저장됩니다 |

로그인하면 측정 기록이 서버에 남아 **다른 기기에서도 이어집니다.**

#### 받는 정보 — 이게 전부입니다

```
로그인 수단 (제공자 식별자 또는 이메일)
닉네임
체력 측정값과 그 결과
```

**휴대폰 번호 · 주소 · 생년월일은 묻지 않습니다.** 소셜 로그인 응답에 그런 값이
섞여 와도 `backend/auth.py` 의 `KEEP_FIELDS` 에서 걸러져 DB 에 닿지 않습니다.
받지 않은 정보는 유출될 수도, 잘못 쓸 수도 없습니다.

계정 삭제(`DELETE /auth/me`)는 측정 기록까지 함께 지웁니다.

#### 비밀번호 처리

평문으로 두지 않습니다. 계정마다 다른 소금(salt)을 만들어 **scrypt**(n=2¹⁴)로 늘려
저장하고, 비교는 상수 시간으로 합니다. 표준 라이브러리만 씁니다.

- 없는 계정과 틀린 비밀번호의 응답을 **같게** 둡니다 (가입 여부를 알아낼 수 없게)
- 세션 쿠키는 `HttpOnly` + `SameSite=Lax` — 자바스크립트가 못 읽고 다른 사이트에서 실려 나가지 않습니다

#### 소셜 로그인 설정

서버를 켜고 **http://localhost:8000/auth/setup** 에 들어가면, 각 콘솔에 등록할
리디렉션 URI 가 **지금 서버 주소 기준으로** 그대로 나옵니다. 복사해서 붙여넣으세요.

| 제공자 | 콘솔 | 리디렉션 URI |
|---|---|---|
| 구글 | console.cloud.google.com/apis/credentials | `http://localhost:8000/auth/google/callback` |
| 네이버 | developers.naver.com/apps | `http://localhost:8000/auth/naver/callback` |
| 카카오 | developers.kakao.com/console/app | `http://localhost:8000/auth/kakao/callback` |

> **이 주소는 브라우저로 직접 여는 페이지가 아닙니다.** 로그인이 끝난 뒤 제공자가
> 우리 서버를 부를 때 쓰는 통로입니다. 직접 열면 "여긴 통로다" 라는 안내만 나오는데,
> 그게 정상 동작이자 서버가 살아있다는 확인입니다.

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

키를 넣은 뒤에는 **서버를 다시 시작**해야 반영됩니다.

> 권한(scope)은 **이메일 · 닉네임만** 신청하세요. 휴대폰 번호나 생일 항목은
> 신청하지 않습니다. 받아도 서버에서 버리지만, 애초에 요청하지 않는 게 맞습니다.
>
> 키는 `.env` 에만 넣고 커밋하지 마세요. `.env` 는 `.gitignore` 에 있습니다.

### 알려진 한계

| 항목 | 상태 |
|---|---|
| 만 11세 미만 | 유아기 데이터는 `age_degree` 가 개월 수(48~83)라 나이 축이 다르고 표본도 적어 제외 |
| 평형성 · 민첩성 | 자가 측정이 어려워 화면에 넣지 않음 (`8자보행`·`3m표적돌아오기` 는 어르신 데이터에만 존재) |
| 체성분(BMI) 백분위 | BMI 는 U자형이라 "상위 몇 %" 가 성립하지 않음 → 또래 중앙값과의 차이만 표시 |
| 동영상 · 인증센터 | 서비스키 발급 전이라 `data/sample/` 목업 사용. 필드명은 실제 API 명세에 맞춰 둠 |

### 연령군

| 연령군 | 나이 | 연령구간 | 근력/순발력 항목 | 숫자 읽는 법 |
|---|---|---|---|---|
| 성장기 | 11~18 | **1세 단위 8구간** | 제자리멀리뛰기 (cm) | 실제 나이보다 **높을수록** 좋음 (발달 수준) |
| 성인 | 19~64 | 5세 단위 9구간 | 교차윗몸일으키기 (회) | 실제 나이보다 **낮을수록** 좋음 |
| 어르신 | 65+ | 5세 단위 4구간 | 의자앉았다일어서기 (회) | 실제 나이보다 **낮을수록** 좋음 |

> 성장기를 5세 단위로 묶으면 구간이 `10~14`·`15~19` 둘뿐이라 보간이 양 끝값에
> 붙어 누구나 같은 값이 나옵니다. 원본 `age_degree` 는 1세 단위이고 나이×성별당
> 표본이 2,000건을 넘으므로 잘게 나눠도 안정적입니다.
>
> 성장기는 나이가 들수록 기록이 좋아져 방향이 반대입니다. 그래서 응답에
> `해석` 문구와 `또래비교`(백분위)를 함께 주고, 화면도 "발달 수준" 으로 읽습니다.

### 테스트

```bash
pytest -q
```

API 응답 모양이 바뀌면 화면이 조용히 깨집니다. `backend/` 를 고쳤다면 PR 전에 한 번 돌려주세요.

## ☁️ 배포 (Render)

`render.yaml` 이 있어 Blueprint 로 한 번에 올라갑니다.

1. [render.com](https://render.com) 에 GitHub 계정으로 로그인
2. **New → Blueprint** → 이 저장소 선택 → **Apply**
3. 웹 서비스와 Postgres 가 함께 생성되고 `DATABASE_URL` 이 자동 연결됩니다
4. 배포가 끝나면 **Environment** 에서 `PUBLIC_BASE_URL` 을 실제 주소로 채웁니다
   (예: `https://quadriga-fitness-age.onrender.com`)
5. 소셜 로그인을 쓰려면 각 `CLIENT_ID`/`CLIENT_SECRET` 도 여기에 넣습니다

> **키는 Render 대시보드에만 넣으세요.** 저장소에 커밋하지 않습니다.

### 저장소는 환경에 따라 갈립니다

| 환경 | DB | 데이터 |
|---|---|---|
| 로컬 | SQLite (`data/app.db`) | 그 컴퓨터에만 |
| 배포 | Postgres (`DATABASE_URL`) | 영구 저장, 기기 간 공유 |

코드는 하나입니다. `DATABASE_URL` 이 있으면 Postgres, 없으면 SQLite 로 붙습니다.
테스트도 양쪽에서 모두 통과하는지 확인합니다.

```bash
pytest -q                                    # SQLite
DATABASE_URL=postgresql://... pytest -q      # Postgres
```

### 배포 후 소셜 로그인

`PUBLIC_BASE_URL` 을 넣으면 `/auth/setup` 의 리디렉션 URI 가 **배포 주소로 바뀝니다.**
각 콘솔에 로컬용과 배포용 **둘 다** 등록해두면 개발과 시연을 함께 할 수 있습니다.

```
http://localhost:8000/auth/google/callback      ← 개발
https://<배포주소>/auth/google/callback          ← 시연
```

### 무료 플랜 주의

15분간 요청이 없으면 서비스가 잠들고, 다음 접속에서 깨어나는 데 **약 30초**가 걸립니다.
심사·시연 직전에 한 번 열어서 깨워두세요.

## 🌿 협업 방법

`main` 브랜치에는 **직접 push 할 수 없습니다.** 반드시 브랜치를 만들고 Pull Request로 합칩니다.

```bash
git switch -c feat/체력나이-산출
# ... 작업 ...
git add .
git commit -m "feat: 체력나이 역산 로직 추가"
git push -u origin feat/체력나이-산출
```

자세한 규칙은 **[CONTRIBUTING.md](./CONTRIBUTING.md)** 를 참고하세요.

## 🤖 AI 도구 (ChatGPT · Claude · Copilot)

팀원마다 다른 AI를 쓰기 때문에, 결과물이 따로 놀지 않도록 공통 규칙을 정해뒀습니다.
**AI에게 작업을 시키기 전에 [AGENTS.md](./AGENTS.md) 를 먼저 읽히세요.** 복붙용 프롬프트도 거기 있습니다.

## 📅 진행 상황

- 이슈: [Issues](https://github.com/QuadrigaProj/Quadriga-DataProject/issues)
- 보드: [Projects](https://github.com/QuadrigaProj/Quadriga-DataProject/projects)


---

## 🧩 역할 분담

**역할은 "누가 이 부분을 끌고 가는가" 이지, "누구 파일인가" 가 아닙니다.**
어떤 파일이든 누구나 고쳐서 PR 올릴 수 있습니다. 남의 코드를 고쳤다면
PR 본문에 왜 고쳤는지 한 줄만 적어주세요.

| 역할 | 주도 | 주로 만지는 곳 |
|---|---|---|
| **A. 체력나이 산출** | 유민진 | `backend/fitness_age.py` · `backend/build_distribution.py` |
| **B. 루틴 · 동영상** | 염윤서 | `backend/daily.py` (영상 필터) · `frontend/` 화면 4 |
| **C. 화면 · UI** | 정다은 | `frontend/` 전체 |
| **D. 처방 로직** | 장예현 | `backend/prescription.py` · `backend/main.py` |

### 의존 관계

```
데이터 수집 (296만 건 페이징)  ← A·D 공통 선행. 한 번만 하고 공유
        ├─→ A 체력나이 ──┬─→ D 약점 지목 계산
        │                └─→ C 프로필·목표 화면에 실제 값 연결
        └─→ D pres_note 파싱 (A와 무관하게 병렬 가능)

B 루틴·동영상 — 거의 독립
```

화면은 이미 `/fitness-age` `/routine` `/daily` 에 붙어 있습니다.
이제 A·D 가 계산을 고치면 **화면은 손대지 않아도 값이 따라 바뀝니다.**

### 일정

| 주차 | 할 일 |
|---|---|
| 1주차 | 데이터 수집 · A 착수 · B 착수 · C 더미로 착수 |
| 2주차 | A 완료 → D 계산 로직 · B 완료 → D 지원 |
| 3주차 | 통합, 화면에 실제 데이터 연결 |
| 4주차 | 시연 준비, 사례보고서 작성 |

접수 마감 **2026-10-02 24시**. 공고상 **시제품 구현 완료**가 필수 조건이다.
