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

```
Quadriga-DataProject/
├── docs/             # 기획안, 회의록, 발표자료
│   └── 기획안.md
├── data/
│   ├── raw/          # API 원본 응답 (Git 추적 안 함)
│   ├── processed/    # 연령·성별 분포 등 가공 결과 (Git 추적 안 함)
│   └── sample/       # 공유용 소용량 샘플 (Git 추적 O)
├── notebooks/        # 데이터 분석 (체력나이 산출식 검증 등)
├── src/              # 재사용 코드 모듈
├── requirements.txt
├── .gitignore
├── AGENTS.md         # AI 도구 사용 규칙
├── CONTRIBUTING.md   # 브랜치 전략 & 협업 규칙 ← 작업 전 필독
└── README.md
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

# 3. 패키지 설치
pip install -r requirements.txt

# 4. 노트북 출력 자동 제거 (한 번만)
nbstripout --install
```

패키지를 새로 설치했다면 반드시 반영해주세요.

```bash
pip freeze > requirements.txt
```

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
