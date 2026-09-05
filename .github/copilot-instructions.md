# GitHub Copilot 지침

이 저장소의 전체 작업 규칙은 **[AGENTS.md](../AGENTS.md)** 와 **[CONTRIBUTING.md](../CONTRIBUTING.md)** 에 있습니다.
코드를 제안하기 전에 두 파일을 참고하세요.

## 프로젝트

4인 데이터 분석 팀 프로젝트입니다. Python 3.11, pandas / numpy / scikit-learn / matplotlib / seaborn 을 씁니다.
분석은 `notebooks/` 에서 하고, 재사용하는 코드는 `src/` 에 함수로 뺍니다.

## 코드 스타일

- 들여쓰기 공백 4칸, 인코딩 UTF-8, 줄 끝 LF
- 함수·변수 `snake_case`, 상수 `UPPER_SNAKE`, 클래스 `PascalCase`
- 문자열은 큰따옴표
- 주석과 docstring은 **한국어**로
- 경로 하드코딩 금지 — `pathlib.Path` 와 `.env` 의 `DATA_DIR` 사용
- pandas는 긴 메서드 체이닝보다 단계별 변수로 나누기

## 하지 말 것

- `main` 브랜치에 직접 커밋 제안 — 브랜치는 `feat/` `fix/` `docs/` `refactor/` 로 시작
- `data/` 안 데이터 파일이나 `.env` 를 커밋 대상에 포함
- `.gitignore` · `requirements.txt` · `CONTRIBUTING.md` · `AGENTS.md` 를 요청 없이 수정
- 다른 담당자의 노트북 파일 수정
- 한 번에 전체를 리팩터링하거나 포맷팅

## 커밋 메시지

`<타입>: <한 줄 설명>` 형식을 씁니다. 타입은 `feat` `fix` `docs` `refactor` `chore` `data`.

```
feat: 사용자 이탈률 파생변수 추가
fix: 날짜 파싱 오류 수정
```
