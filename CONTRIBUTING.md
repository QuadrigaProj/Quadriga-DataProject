# 협업 가이드 (Contributing)

Quadriga-DataProject 팀의 Git 협업 규칙입니다. **작업 시작 전에 한 번 읽어주세요.**

---

## 1. 브랜치 전략

우리는 **GitHub Flow**(간단한 버전)를 씁니다. 학교/단기 프로젝트에 가장 적합합니다.

```
main ─────●──────────●──────────●────▶  (항상 동작하는 최신 상태)
           \        /  \       /
            ●──●───●    ●──●──●
         feat/eda      feat/model
```

| 브랜치 | 용도 | 규칙 |
|---|---|---|
| `main` | 언제나 정상 동작하는 코드 | **직접 push 금지**, PR로만 병합 |
| `feat/*` | 새 기능·분석 추가 | 작업 끝나면 PR → 병합 후 삭제 |
| `fix/*` | 버그 수정 | 〃 |
| `docs/*` | 문서·README 수정 | 〃 |
| `refactor/*` | 결과 변화 없는 코드 정리 | 〃 |

### 브랜치 이름 규칙

```
<타입>/<작업내용-요약>

예시)
feat/eda-매출데이터
feat/model-randomforest
fix/결측치-처리오류
docs/readme-팀원추가
```

- 소문자 + 하이픈(`-`) 사용, 띄어쓰기 금지
- 한글도 괜찮지만 팀 내에서 통일하기

### 브랜치는 짧게 유지하기

한 브랜치에 3일 이상 쌓아두면 충돌이 커집니다. **작업 단위를 작게 쪼개서 자주 PR** 하세요.

---

## 2. 커밋 컨벤션

```
<타입>: <무엇을 했는지 한 줄>

feat: 사용자 이탈률 파생변수 추가
fix: 날짜 파싱 오류 수정 (2월 29일 처리)
docs: README에 환경 세팅 방법 추가
refactor: 전처리 함수 src/preprocess.py로 분리
chore: requirements.txt 업데이트
data: 샘플 데이터 100행 추가
```

| 타입 | 언제 |
|---|---|
| `feat` | 새 기능, 새 분석, 새 모델 |
| `fix` | 버그·오류 수정 |
| `docs` | 문서만 수정 |
| `refactor` | 동작은 그대로, 코드 구조만 개선 |
| `chore` | 패키지, 설정 파일 등 잡일 |
| `data` | 샘플 데이터 추가/수정 |

- 제목은 50자 이내, 마침표 없이
- "수정함", "작업" 같은 모호한 메시지 ❌

---

## 3. 작업 흐름 (매번 이 순서대로)

```bash
# ① main 최신화 — 항상 여기서 시작
git switch main
git pull origin main

# ② 새 브랜치 생성
git switch -c feat/eda-매출데이터

# ③ 작업 후 커밋
git add .
git commit -m "feat: 매출 데이터 EDA 노트북 추가"

# ④ 원격에 push
git push -u origin feat/eda-매출데이터

# ⑤ GitHub에서 'Compare & pull request' 클릭 → PR 작성 → 리뷰 요청

# ⑥ 병합된 후 로컬 정리
git switch main
git pull origin main
git branch -d feat/eda-매출데이터
```

---

## 4. Pull Request 규칙

- **제목**: 커밋 컨벤션과 동일하게 (`feat: 매출 데이터 EDA 추가`)
- **본문**: PR 템플릿이 자동으로 뜹니다. 빈칸 채워주세요.
- **리뷰어**: 최소 **1명** 지정 → 승인(Approve) 받아야 병합 가능
- **본인 PR을 본인이 병합**하는 건 승인 후에는 OK
- 병합 방식은 **Squash and merge** 권장 (커밋 히스토리가 깔끔해짐)
- 병합 후 브랜치는 삭제 (GitHub가 버튼으로 안내해줌)

### 리뷰할 때

- 24시간 안에는 확인해주기
- 지적할 땐 이유와 대안을 같이 (`이 부분 for문 대신 벡터연산 쓰면 빠를 것 같아요`)
- 사소한 제안은 `nit:` 을 붙여서 (반영 안 해도 되는 의견이라는 뜻)

---

## 5. 충돌(Conflict) 났을 때

당황하지 마세요. 대부분 이렇게 해결됩니다.

```bash
git switch main
git pull origin main
git switch feat/내브랜치
git merge main          # 여기서 충돌 발생

# 파일 열어서 <<<<<<< ======= >>>>>>> 부분을 직접 정리
git add .
git commit -m "chore: main 브랜치와 충돌 해결"
git push
```

> **노트북(.ipynb)은 충돌이 특히 지저분합니다.**
> 같은 노트북을 두 명이 동시에 수정하지 말고, 파일명에 담당자를 붙이세요.
> 예: `notebooks/01_eda_영훈.ipynb`, `notebooks/02_eda_지민.ipynb`

---

## 6. 하지 말아야 할 것

| ❌ | 이유 |
|---|---|
| `main`에 직접 push | 리뷰 없이 코드가 들어가고, 브랜치 보호 규칙에 막힘 |
| `git push --force` (공용 브랜치에) | 남의 커밋이 사라짐 |
| 데이터 원본 파일 커밋 | 저장소 용량 폭발, 100MB 넘으면 push 자체가 실패 |
| `.env`, API 키 커밋 | 유출 사고. 한 번 올라가면 히스토리에 영원히 남음 |
| 커밋 하나에 20개 파일 뭉치기 | 리뷰 불가능, 문제 생겨도 되돌리기 어려움 |

실수로 큰 파일이나 키를 커밋했다면 **push 하기 전에** 알려주세요. push 전이면 쉽게 되돌릴 수 있습니다.

```bash
git reset --soft HEAD~1   # 직전 커밋만 취소 (작업 내용은 유지)
```


---

## 7. AI 도구를 쓸 때

팀원마다 쓰는 AI가 다릅니다(ChatGPT·Codex, Claude, Copilot 등). 도구가 달라도 결과물이 따로 놀지 않도록
**[AGENTS.md](./AGENTS.md)** 에 공통 규칙을 정리해뒀습니다. AI에게 작업을 시키기 전에 그 파일을 먼저 읽히세요.
복붙용 프롬프트도 거기 있습니다.

가장 중요한 것 두 가지:

1. **AI가 짠 코드도 본인이 이해한 뒤에 올립니다.** 설명 못 하는 코드는 PR에 넣지 않기.
2. **노트북 출력 제거 설정을 꼭 하세요.** 클론 직후 한 번만 하면 됩니다.

   ```bash
   pip install nbstripout
   nbstripout --install
   ```
