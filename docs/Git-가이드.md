# Git 협업 가이드 (Quadriga-DataProject)

> **한 줄 요약**
> `main`은 잠겨 있습니다. 아무도 `main`에 직접 못 올립니다.
> **내 브랜치 만들기 → 작업 → 커밋 → 푸시 → PR 올리기 → 승인 받기 → 머지**
> 이 7단계가 전부입니다.

---

## 0. 딱 한 번만 하는 준비

### 0-1. 설치

| 프로그램 | 링크 | 비고 |
|---|---|---|
| Git | https://git-scm.com/downloads | 설치 중 옵션은 전부 **Next** 눌러도 됩니다 |
| VS Code | https://code.visualstudio.com | 코드 편집기 |
| Python 3.10+ | https://www.python.org/downloads | 설치 시 **Add Python to PATH** 체크 필수 |

설치 확인 — VS Code에서 터미널 열고(`Ctrl + \``, 맥은 `Cmd + \``) 아래 입력:

```bash
git --version
python --version
```

버전 숫자가 나오면 성공입니다.

### 0-2. 내 이름 등록 (커밋에 찍히는 이름)

```bash
git config --global user.name "본인 GitHub 아이디"
git config --global user.email "GitHub에 등록한 이메일"
```

> ⚠️ 이메일은 GitHub 계정 이메일과 **똑같아야** 커밋에 프로필 사진이 붙습니다.

### 0-3. 저장소 내려받기 (clone)

내 컴퓨터에서 프로젝트를 둘 폴더로 이동한 뒤:

```bash
git clone https://github.com/QuadrigaProj/Quadriga-DataProject.git
cd Quadriga-DataProject
```

로그인 창이 뜨면 GitHub 계정으로 로그인하세요. (비밀번호 대신 브라우저 인증이 뜹니다 → **Sign in with your browser** 누르면 됩니다.)

### 0-4. 파이썬 패키지 설치

```bash
pip install -r requirements.txt
```

### 0-5. `.env` 만들기

`.env.example`을 복사해서 `.env`로 이름을 바꾸고, 안의 `your_key_here`를 실제 인증키로 바꿉니다.
**인증키는 예현이한테 개인 DM으로 요청하세요. 단톡방/PR/코드에 절대 붙여넣지 마세요.**

---

## 1. 작업 시작 — 매번 하는 첫 두 줄

> 이거 안 하고 시작하면 나중에 충돌(conflict) 지옥이 열립니다. **무조건 먼저.**

```bash
git checkout main
git pull
```

- `checkout main` = "메인 작업본으로 돌아간다"
- `pull` = "다른 사람들이 올린 최신 코드를 내려받는다"

---

## 2. 내 브랜치 만들기

브랜치 = **내 전용 작업 복사본**. 여기서 뭘 해도 남한테 영향이 없습니다.

```bash
git checkout -b feat/fitness-age-ui
```

`-b`는 "새로 만들면서 이동"이라는 뜻입니다.

### 브랜치 이름 규칙

| 앞머리 | 언제 | 예시 |
|---|---|---|
| `feat/` | 새 기능 | `feat/routine-page` |
| `fix/` | 버그 수정 | `fix/bmi-calc` |
| `docs/` | 문서만 수정 | `docs/readme-update` |
| `refactor/` | 동작은 그대로, 코드 정리 | `refactor/api-client` |

- 전부 **영어 소문자 + 하이픈**
- 한글 ❌, 띄어쓰기 ❌, 대문자 ❌

지금 내가 어느 브랜치인지 확인:

```bash
git branch
```
`*` 표시가 붙은 게 현재 브랜치입니다.

---

## 3. 작업하고 → 커밋하기

코드를 고친 다음, **의미 있는 덩어리 하나**가 끝날 때마다 커밋합니다.

```bash
git status          # 내가 뭘 건드렸는지 확인
git add .           # 바뀐 파일 전부 담기
git commit -m "feat: 체력나이 결과 화면 추가"
```

### 커밋 메시지 규칙

```
<타입>: <한 줄 설명>
```

| 타입 | 뜻 |
|---|---|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `docs` | 문서 |
| `refactor` | 리팩터링 |
| `chore` | 설정/잡일 |

✅ 좋은 예
```
feat: 약점 항목 카드 UI 추가
fix: 어르신 연령대에서 체력나이가 음수로 나오던 문제 수정
docs: README에 실행 방법 추가
```

❌ 나쁜 예
```
수정
ㅁㄴㅇㄹ
update
final_최종_진짜최종
```

> **커밋은 자주, 잘게.** 하루 종일 작업하고 한 번에 커밋하면 나중에 뭐가 문제인지 아무도 못 찾습니다.

---

## 4. GitHub에 올리기 (push)

```bash
git push -u origin feat/fitness-age-ui
```

- `origin` = GitHub 저장소
- `-u`는 **처음 한 번만** 필요합니다. 그 뒤로는 그냥 `git push`

터미널에 이런 링크가 뜹니다 — 이걸 클릭하면 5번으로 바로 넘어갑니다.

```
remote: Create a pull request for 'feat/fitness-age-ui' on GitHub by visiting:
remote:      https://github.com/QuadrigaProj/Quadriga-DataProject/pull/new/feat/fitness-age-ui
```

---

## 5. PR(Pull Request) 올리기 = "머지 승인 요청"

**PR = "제 코드 main에 합쳐도 될까요?" 하고 정식으로 요청하는 것**입니다.

### 5-1. PR 만들기

1. https://github.com/QuadrigaProj/Quadriga-DataProject 접속
2. 위쪽에 노란 띠로 **`feat/... had recent pushes`** + 초록 버튼 **`Compare & pull request`** → 클릭
   (안 보이면 상단 **Pull requests** 탭 → 초록 **New pull request** → base: `main` / compare: `내 브랜치` 선택)
3. 화살표 방향 확인 — **`base: main` ← `compare: 내 브랜치`** 가 맞는지 꼭 보세요
4. 제목은 커밋 메시지처럼: `feat: 체력나이 결과 화면 추가`
5. 본문은 템플릿이 자동으로 뜹니다. 빈칸 채우세요 (아래 5-2 참고)
6. 초록 버튼 **`Create pull request`** 클릭

### 5-2. PR 본문에 꼭 쓸 것

```markdown
## 무엇을 했나
- 체력나이 결과 화면(점수 + 신뢰구간 + 약점 카드) 추가

## 왜
- 기획안 4-2 화면 흐름 中 3단계

## 확인 방법
1. `uvicorn api.main:app --reload`
2. localhost:5173 접속 → 나이/성별 입력 → 결과 확인

## 스스로 체크
- [x] `.env`, CSV 같은 데이터 파일 안 올림
- [x] 내 컴퓨터에서 실행됨
- [ ] 아직 안 된 것: 차트 애니메이션
```

> 안 끝난 부분이 있어도 괜찮습니다. **숨기지 말고 적으세요.** 그게 리뷰어한테 제일 도움 됩니다.

### 5-3. 리뷰어(승인해 줄 사람) 지정 ⭐

**이걸 해야 "승인 요청"이 실제로 전달됩니다.**

PR 화면 **오른쪽 사이드바 맨 위 `Reviewers`** → 톱니바퀴(⚙️) 클릭 → 사람 선택

| 내가 | 리뷰어로 지정 |
|---|---|
| 민진 (Jjin39) | 예현 |
| 윤서 (yunseoo00) | 예현 |
| 다은 (daje0102) | 예현 |
| 예현 (yhjang0315-source) | 아무나 1명 |

지정하면 상대방한테 GitHub 알림 + 메일이 갑니다.
**추가로 단톡방에 PR 링크 한 번 던져주세요.** 알림 놓치는 경우가 많습니다.

```
PR 올렸어요 리뷰 부탁 🙏
https://github.com/QuadrigaProj/Quadriga-DataProject/pull/11
```

---

## 6. 리뷰 받고 → 머지

### 6-1. 승인이 필요합니다

이 저장소 `main`은 **최소 1명의 승인(Approve)** 이 있어야 머지됩니다.
승인 전에는 초록 `Merge` 버튼이 **회색으로 잠겨** 있습니다. 정상입니다. 기다리세요.

### 6-2. 리뷰어가 수정 요청했다면

터미널에서 **같은 브랜치 그대로** 고치고 다시 올리면 됩니다. PR을 새로 만들 필요 ❌

```bash
# 브랜치 바꾸지 말고 그 자리에서
git add .
git commit -m "fix: 리뷰 반영 - 변수명 수정"
git push
```

PR 페이지가 **자동으로 갱신**됩니다. 그리고 PR 대화창에 한 줄 남기세요:
> 리뷰 반영했습니다! 다시 봐주세요 🙏

### 6-3. 승인(Approved) 뜨면

PR 아래쪽 초록 버튼 **`Merge pull request`** → **`Confirm merge`**

머지되면 브랜치는 **자동으로 삭제**됩니다. (설정해 뒀습니다. 신경 안 써도 됩니다.)

### 6-4. 내가 남의 PR을 리뷰할 때

1. PR 열기 → **`Files changed`** 탭
2. 코드 읽기. 이상한 줄은 줄 번호 옆 **`+`** 눌러서 코멘트
3. 오른쪽 위 **`Review changes`** 버튼
4. 셋 중 선택
   - **Approve** — 괜찮음, 머지해도 됨 ✅
   - **Comment** — 그냥 의견
   - **Request changes** — 이건 고쳐야 함
5. **`Submit review`**

> 완벽할 필요 없습니다. **"돌아가고, 데이터/키 안 올라갔고, 기획안과 맞으면"** Approve 하세요.

---

## 7. 머지 끝난 뒤 (다음 작업 준비)

```bash
git checkout main
git pull
```

**끝. 그리고 다시 2번(브랜치 만들기)으로 갑니다.**

---

## 🔁 전체 흐름 한 장 요약

```
git checkout main && git pull          ← ① 최신화 (항상 먼저!)
git checkout -b feat/내-작업            ← ② 내 브랜치
        ...코드 작성...
git add .                              ← ③ 담기
git commit -m "feat: 설명"             ← ④ 저장
git push -u origin feat/내-작업         ← ⑤ 올리기
GitHub에서 PR 생성 + Reviewers 지정      ← ⑥ 승인 요청 ⭐
승인 받으면 Merge pull request          ← ⑦ 합치기
git checkout main && git pull          ← ①로 돌아가기
```

---

## 🚨 절대 하지 말 것

| 하지 말 것 | 왜 |
|---|---|
| `main`에서 바로 코드 수정 | 잠겨 있어서 push 자체가 거부됩니다 |
| `.env` 파일 커밋 | **인증키가 전 세계에 공개됩니다.** 최악의 사고 |
| CSV / 원본 데이터 커밋 | 저장소가 수백 MB로 불어납니다. `.gitignore`가 막아두긴 했지만 강제로 뚫지 마세요 |
| `git push --force` | 남의 작업이 통째로 사라질 수 있습니다 |
| 브랜치 하나에서 여러 기능 섞기 | 리뷰가 불가능해집니다. 기능 1개 = 브랜치 1개 = PR 1개 |
| 커밋 없이 하루 종일 작업 | 컴퓨터 꺼지면 다 날아갑니다 |

---

## 😱 이런 에러가 났어요

### `error: failed to push some refs`
남이 먼저 올린 게 있습니다.
```bash
git pull --rebase
git push
```

### `CONFLICT (content): Merge conflict in xxx.py`
같은 줄을 둘이 고쳤습니다. 파일을 열면 이렇게 생겼습니다:
```
<<<<<<< HEAD
내 코드
=======
남의 코드
>>>>>>> main
```
**`<<<<<<<`, `=======`, `>>>>>>>` 세 줄을 지우고**, 남길 코드만 남기세요. 그 다음:
```bash
git add .
git rebase --continue     # (pull --rebase 중이었다면)
git push
```
> 헷갈리면 **혼자 해결하지 말고 단톡방에 물어보세요.** 잘못 풀면 남의 코드가 사라집니다.

### `Updates were rejected because the tip of your current branch is behind`
```bash
git pull --rebase
```

### `fatal: not a git repository`
프로젝트 폴더 밖에 있습니다.
```bash
cd Quadriga-DataProject
```

### 실수로 `.env`를 커밋했어요 (아직 push 전)
```bash
git reset HEAD~1        # 커밋만 취소, 파일은 그대로
```
**이미 push 했다면 즉시 단톡방에 알리세요.** 키를 폐기하고 새로 발급해야 합니다. 혼자 조용히 지워도 기록에 남습니다.

### 다 꼬였어요 / 뭐가 뭔지 모르겠어요
지금까지 작업한 파일을 **다른 폴더에 복사해두고**, 폴더를 통째로 지운 뒤 다시 `clone` 하세요.
그게 제일 빠릅니다. 부끄러운 일 아닙니다.

---

## 💡 AI한테 시킬 때

Claude / GPT / Gemini 쓸 때 이 문장을 먼저 붙이세요:

```
이 저장소는 GitHub Flow를 씁니다.
- main 직접 수정 금지, 반드시 브랜치 → PR
- 브랜치 이름: feat/ fix/ docs/ refactor/ + 영어 소문자-하이픈
- 커밋 메시지: "feat: 한 줄 설명"
- .env와 data/ 아래 CSV는 절대 커밋하지 않음
지금부터 알려주는 작업에 대해, 실행할 git 명령어를 순서대로 알려줘.
```

명령어를 받으면 **한 줄씩** 실행하고, 에러가 나면 에러 메시지를 그대로 AI에 붙여넣어 물어보세요.

---

## 📌 자주 쓰는 명령어 치트시트

```bash
git status                    # 지금 상태 (제일 자주 씀)
git branch                    # 브랜치 목록 (* = 현재 위치)
git log --oneline -10         # 최근 커밋 10개
git diff                      # 뭘 바꿨는지 보기
git checkout main             # main으로 이동
git checkout -b feat/xxx      # 브랜치 만들며 이동
git checkout .                # 저장 안 한 수정 전부 되돌리기 (주의!)
git pull                      # 최신 받기
git push                      # 올리기
```

---

**막히면 30분 넘기지 말고 단톡방에 물어보세요.**
Git은 원래 헷갈립니다. 물어보는 게 훨씬 빠릅니다.
