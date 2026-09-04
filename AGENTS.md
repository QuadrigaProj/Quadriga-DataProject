# AGENTS.md

이 저장소에서 **AI 코딩 도구**(ChatGPT·Codex, Claude, Copilot 등)를 쓸 때 지켜야 할 규칙입니다.
사람이 지켜야 할 Git 규칙은 [CONTRIBUTING.md](./CONTRIBUTING.md) 에 있습니다.

> 팀원마다 다른 AI를 씁니다. 도구가 달라도 **같은 규칙을 따르게 해서** 코드 스타일이 파일마다 튀지 않고,
> 같은 파일을 서로 갈아엎어 충돌 나는 일이 없도록 하는 게 이 파일의 목적입니다.

**작업을 시작할 때 이 파일을 AI에게 먼저 읽히세요.** 맨 아래에 복붙용 프롬프트가 있습니다.

---

## 1. 프로젝트 개요

- 데이터 분석 단체 프로젝트 (4인)
- Python 3.11 기준, pandas / numpy / scikit-learn / matplotlib / seaborn
- 분석은 `notebooks/` 에서, 재사용 코드는 `src/` 에 함수로

## 2. 절대 하지 말 것

AI에게 아래를 시키지 마세요. 시켜도 거절하도록 이 파일을 먼저 읽히세요.

| ❌ | 이유 |
|---|---|
| `main` 브랜치에 직접 커밋·푸시 | 리뷰 없이 코드가 들어감. 보호 규칙에도 막힘 |
| `data/` 안 원본 데이터 커밋 | 저장소 용량 폭발, 100MB 넘으면 push 실패 |
| `.env` · API 키 · 토큰 커밋 | 유출 사고. 히스토리에 영원히 남음 |
| 다른 사람 노트북 파일 수정 | `.ipynb` 충돌은 수동 해결이 매우 어려움 |
| `.gitignore` · `requirements.txt` · `CONTRIBUTING.md` · `AGENTS.md` 임의 재작성 | 팀 합의 사항. 바꿔야 하면 PR 설명에 이유를 쓰기 |
| 전체 포맷팅 / 대규모 리팩터링 한 번에 | diff가 폭발해서 리뷰가 불가능해짐 |
| 라이브러리 마음대로 추가 | 팀원 환경이 깨짐. 꼭 필요하면 `requirements.txt` 에 함께 추가 |

## 3. 파일 소유권 — 충돌의 90%는 여기서 납니다

**노트북은 담당자별로 파일을 나눕니다.** 한 파일을 두 명이 건드리지 않습니다.

```
notebooks/
├── 01_eda_예현.ipynb
├── 02_eda_민진.ipynb
├── 03_eda_다은.ipynb
└── 04_eda_윤서.ipynb
```

- 여러 명이 쓰는 코드는 **`src/` 에 함수로 빼고 노트북에서 import** 합니다.
- `src/` 파일을 고쳐야 하면 PR 올리기 전에 팀 채팅방에 한마디 남기세요.

## 4. 노트북 출력 정리 (설정 필수)

`.ipynb` 의 실행 결과(output)가 그대로 커밋되면 충돌이 지옥이 됩니다. **클론 직후 한 번만** 설정하세요.

```bash
pip install nbstripout
nbstripout --install
```

이후로는 커밋할 때 출력이 자동으로 제거됩니다. 노트북 파일 자체는 그대로 남습니다.

## 5. 코드 스타일

AI마다 기본 스타일이 달라서, 아래로 통일합니다. (`.editorconfig` 가 에디터에도 적용됩니다.)

- 들여쓰기 **공백 4칸**, 인코딩 UTF-8, 줄 끝 LF
- 함수·변수 `snake_case`, 상수 `UPPER_SNAKE`, 클래스 `PascalCase`
- 문자열은 큰따옴표 `"..."`
- **경로 하드코딩 금지** — `pathlib.Path` 와 `.env` 의 `DATA_DIR` 사용
- pandas는 긴 메서드 체이닝보다 **단계별 변수**로 나누기 (리뷰가 쉬워집니다)
- 주석과 docstring은 **한국어**로

```python
# 권장
from pathlib import Path
import pandas as pd

DATA_DIR = Path("data/raw")

def load_sales(filename: str) -> pd.DataFrame:
    """매출 원본 CSV를 읽어 날짜 컬럼을 datetime으로 변환한다."""
    df = pd.read_csv(DATA_DIR / filename)
    df["date"] = pd.to_datetime(df["date"])
    return df
```

## 6. 커밋과 PR

- 커밋 메시지 규칙은 [CONTRIBUTING.md](./CONTRIBUTING.md) 를 따릅니다. AI가 만든 커밋도 예외 없습니다.
- **PR 본문의 "무엇을 / 왜"는 본인이 직접 씁니다.** AI 출력을 그대로 붙여넣지 마세요.
  리뷰어가 알아야 하는 건 코드 설명이 아니라 *왜 이렇게 했는지* 입니다.
- PR 하나에 파일이 10개를 넘으면 쪼개세요.
- **AI가 짠 코드도 본인이 이해한 뒤에 올립니다.** 설명 못 하는 코드는 올리지 않기.

## 7. AI에게 붙여넣을 프롬프트 (복붙용)

새 대화를 시작할 때마다 아래를 먼저 넣으세요.

```
이 저장소는 Quadriga-DataProject라는 4인 데이터 분석 팀 프로젝트야.
작업 전에 저장소 루트의 AGENTS.md 와 CONTRIBUTING.md 를 읽고 그 규칙을 지켜줘.

특히 이것만은 꼭 지켜:
- main 브랜치에 직접 커밋하지 말고, feat/ fix/ docs/ 로 시작하는 브랜치를 만들어서 PR로 올려
- data/ 안의 데이터 파일과 .env 는 절대 커밋하지 마
- 내 담당 노트북 파일만 수정하고, 다른 사람 노트북은 건드리지 마
- .gitignore, requirements.txt, CONTRIBUTING.md, AGENTS.md 는 내가 요청할 때만 수정해
- 들여쓰기 4칸, snake_case, 주석은 한국어
- 한 번에 전체를 리팩터링하지 말고 작은 단위로 나눠서 작업해
```

## 8. 도구별 메모

| 도구 | 이 파일을 읽는 방법 |
|---|---|
| ChatGPT / Codex | `AGENTS.md` 를 자동으로 읽습니다. 웹 ChatGPT면 내용을 직접 붙여넣으세요 |
| Claude / Claude Code | `CLAUDE.md` 가 이 파일을 참조합니다 |
| GitHub Copilot | 채팅 시작할 때 위 7번 프롬프트를 붙여넣으세요 |

---

규칙에 고칠 부분이 보이면 이 파일도 PR로 바꾸면 됩니다. 혼자 고치지 말고 팀에 물어보세요.
