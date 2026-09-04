# CLAUDE.md

이 프로젝트의 AI 작업 규칙은 **[AGENTS.md](./AGENTS.md)** 에 정리되어 있습니다.
작업을 시작하기 전에 반드시 읽고 그 규칙을 따라주세요.

@AGENTS.md

## 요약 (자세한 내용은 AGENTS.md)

- `main` 에 직접 커밋하지 말고 `feat/` `fix/` `docs/` 브랜치 → PR
- `data/` 안 데이터 파일과 `.env` 는 커밋 금지
- 담당자 본인의 노트북만 수정, 다른 사람 `.ipynb` 는 건드리지 않기
- `.gitignore` · `requirements.txt` · `CONTRIBUTING.md` · `AGENTS.md` 는 요청받았을 때만 수정
- 들여쓰기 4칸, `snake_case`, 주석과 docstring은 한국어
- 한 번에 전체를 리팩터링하지 말고 작은 단위로 나누기
