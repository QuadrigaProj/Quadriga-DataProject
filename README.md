# Quadriga-DataProject

> 한 줄 소개를 여기에 적어주세요. (주제 확정 후 작성)

[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/QuadrigaProj/Quadriga-DataProject/pulls)

---

## 📌 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 주제 | 🔜 미정 — 논의 중 ([#2](https://github.com/QuadrigaProj/Quadriga-DataProject/issues)) |
| 목표 | 주제 확정 후 작성 |
| 기간 | 2026.09 ~ 2026.  . |
| 데이터 출처 | 주제 확정 후 작성 |

## 👥 팀원

| 이름 | GitHub | 담당 |
|---|---|---|
| 장영훈 | [@yhjang0315-source](https://github.com/yhjang0315-source) | 총괄 / 저장소 관리 |
| (이름) | [@Jjin39](https://github.com/Jjin39) | (담당 영역) |
| (이름) | [@daje0102](https://github.com/daje0102) | (담당 영역) |
| (이름) | [@yunseoo00](https://github.com/yunseoo00) | (담당 영역) |

> 각자 자기 줄의 이름과 담당 영역을 채워주세요. 직접 수정하기 어려우면 이슈로 남겨주셔도 됩니다.

## 🗂 폴더 구조

```
Quadriga-DataProject/
├── data/
│   ├── raw/          # 원본 데이터 (Git 추적 안 함)
│   ├── interim/      # 중간 처리 데이터 (Git 추적 안 함)
│   ├── processed/    # 최종 분석용 데이터 (Git 추적 안 함)
│   └── sample/       # 공유용 소용량 샘플 (Git 추적 O)
├── notebooks/        # 탐색적 분석(EDA) 노트북
│   └── 01_eda_영훈.ipynb
├── src/              # 재사용 가능한 코드 모듈
│   ├── preprocess.py
│   ├── features.py
│   └── models.py
├── outputs/          # 그래프, 리포트 등 산출물 (Git 추적 안 함)
├── docs/             # 회의록, 기획 문서
├── requirements.txt
├── .gitignore
├── CONTRIBUTING.md   # 브랜치 전략 & 협업 규칙 ← 작업 전 필독
└── README.md
```

> ⚠️ **데이터 파일은 Git에 올리지 않습니다.** 원본 데이터는 팀 공용 드라이브에 두고,
> 경로만 `.env` 로 맞추거나 `data/raw/` 에 각자 내려받아 사용하세요.

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
```

패키지를 새로 설치했다면 반드시 반영해주세요.

```bash
pip freeze > requirements.txt
```

## 🌿 협업 방법

`main` 브랜치에는 **직접 push 할 수 없습니다.** 반드시 브랜치를 만들고 Pull Request로 합칩니다.

```bash
git switch -c feat/데이터-전처리
# ... 작업 ...
git add .
git commit -m "feat: 결측치 처리 로직 추가"
git push -u origin feat/데이터-전처리
```

자세한 브랜치 이름 규칙, 커밋 컨벤션, PR 절차는 **[CONTRIBUTING.md](./CONTRIBUTING.md)** 를 참고하세요.

## 📅 진행 상황

- 이슈: [Issues](https://github.com/QuadrigaProj/Quadriga-DataProject/issues)
- 보드: [Projects](https://github.com/QuadrigaProj/Quadriga-DataProject/projects)
