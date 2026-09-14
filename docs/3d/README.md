# 3D 운동 캐릭터 만드는 법

영상이 없는 동작(고른 종목·기록 종목)은 회색 마네킹이 3D 로 보여 준다. 이 문서는 그 캐릭터와 동작 파일을 **어떻게 만들었고 어떻게 다시 만드는지** 적는다. 동작마다의 바른 자세는 [`../3d-exercise-form-notes.md`](../3d-exercise-form-notes.md), 코드는 `frontend/js/move-3d.js`.

## 무엇이 어디에 있나

| 파일 | 내용 |
|---|---|
| `frontend/assets/3d/mannequin-m.glb`, `mannequin-f.glb` | 남·여 캐릭터 (뼈대 52개, 한 프레임짜리 T 자세 포함, 각 115KB) |
| `frontend/assets/3d/anim/{m,f}/<id>.glb` | 동작 파일 25개씩 — 뼈대만 들어 있고 캐릭터는 없다. 뼈대가 성별마다 달라 따로 둔다 |
| `frontend/js/move-3d.js` | 불러오기·그리기. `CLIPS`(모션캡처 동작), `PROC`(설명대로 만든 동작), `GEAR`(기구), `TWEAKS`(무릎 푸시업), `qa`(검사 손잡이) |
| `frontend/js/move-notes.js` | 동작 아래에 띄우는 자세 설명 — `3d-exercise-form-notes.md` 에서 뽑은 것 |
| `frontend/js/vendor/` | three.js r160 + GLTFLoader + meshopt 디코더 (밖에서 받지 않는다) |

캐릭터 원본 — 몸: Blender 재단 [Human Base Meshes](https://www.blender.org/download/demo-files/) v1.4.1 (CC0) 의 `GEO-body_male_realistic` / `GEO-body_female_realistic`. 뼈대·동작: [Mixamo](https://www.mixamo.com/) (Adobe, 무료, 앱에 써도 된다). 리뷰에서 정한 모습: **사실체 그대로, 다리 12% 늘림, 머리카락·옷 없음, 전부 회색**.

## 캐릭터를 다시 만들 때

1. **몸 내보내기** (Blender 4.2 이상, 명령줄):
   ```bash
   blender -b human_base_meshes_bundle.blend --python docs/3d/blender_export_body.py -- out 0.12
   ```
   `out/m_long.obj`, `out/f_long.obj` 가 나온다 (다리 +12%, 발이 바닥, 가운데 정렬, 앞이 -Z·위가 Y).
2. **Mixamo 자동 리깅**: mixamo.com 로그인 → Upload Character → OBJ 올리기 → 정면 확인 → 마커 배치(턱·손목·팔꿈치·무릎·사타구니, Use Symmetry 켠 채) → Standard Skeleton(65) → NEXT → 걷는 미리보기 확인 → NEXT 로 확정.
   - 마커가 몸 밖(다리 사이 빈틈, 가는 손목 옆)에 걸리면 "Please place all markers on the character" 오류가 난다 — 몸 위로 조금 옮긴다.
   - **Mixamo 는 계정당 사용자 캐릭터를 하나만 둔다.** 새로 올리면 이전 캐릭터가 사라지므로, 한 캐릭터의 내보내기를 다 끝낸 뒤 다음 캐릭터를 올린다.
3. **내보내기·받기**: `docs/3d/mixamo_export.js` 를 콘솔에 붙여 넣고 T-Pose(skin: true)와 동작 25개(`MX.ITEMS`)를 하나씩 받는다. 파일은 Downloads 에 제품 이름(`Air Squat.fbx`)으로 떨어지니
   ```bash
   python docs/3d/collect_downloads.py work/m   # 최근 1시간 안에 받은 것을 id 이름으로 옮긴다
   ```
4. **변환** — FBX → GLB 는 [FBX2glTF](https://github.com/facebookincubator/FBX2glTF) (`npm i fbx2gltf`), 압축은 [gltfpack](https://github.com/zeux/meshoptimizer) (`npm i gltfpack`):
   ```bash
   FBX2glTF --binary -i work/m/tpose.fbx -o work/m/tpose.glb
   python docs/3d/smooth_crotch.py work/m/tpose.glb work/m/tpose_smooth.glb    # 사타구니를 마네킹처럼 매끈하게
   python docs/3d/strip_attrs.py work/m/tpose_smooth.glb work/m/tpose_lean.glb  # 법선·UV 를 뗀다 (앱이 다시 계산)
   gltfpack -i work/m/tpose_lean.glb -o frontend/assets/3d/mannequin-m.glb -cc -vpf
   for f in work/m/*.fbx; do FBX2glTF --binary -i "$f" -o "${f%.fbx}.glb"; done
   for f in work/m/<동작>.glb; do gltfpack -i "$f" -o frontend/assets/3d/anim/m/$(basename "$f") -cc; done
   ```
   `-vpf` 는 위치를 실수로 남겨 두는 옵션 — 이게 있어야 앱의 '같은 자리 꼭짓점 합치기'가 제대로 된다.
5. `frontend/js/move-3d.js` 의 `VER`(`?v=N`) 을 올린다 — 같은 이름의 옛 파일이 브라우저 캐시에서 나오지 않게.
6. `pytest tests/test_move_3d.py` — 파일 크기·뼈 이름·34개 동작 모두 있는지 본다. 브라우저에서는 `MOVE_3D.start(canvas, '동작id', { sex: 'F' })` 로 아무 캔버스에나 띄워 볼 수 있다.

## 동작을 더하거나 고칠 때

- **Mixamo 에 있는 동작**: `MX.ITEMS` 식으로 검색어·이름을 적어 두 성별 모두 받고, `move-3d.js` 의 `CLIPS` 에 `'동작id': '파일이름'` 을 더한다.
- **Mixamo 에 없는 동작**: `PROC` 표에 적는다. 시간(0~1)에 따른 자세를 세상 기준 방향(+Y 위, +Z 앞, +X 캐릭터 왼쪽)과 손·발 목표(`ik`)로 쓴다 — 뼈 기준 각도는 리깅마다 달라 쓰지 않는다. `base` 는 손가락·발 등 정하지 않은 뼈를 가져올 바탕 동작(idle·lying·kneel·plank). 기구가 필요하면 `GEAR` 와 `makeGear()` 에 더한다.
- 자세 설명은 `docs/3d-exercise-form-notes.md` 에 `### 동작id 이름` 으로 적고, `frontend/js/move-notes.js` 를 다시 뽑는다(문서의 `- ` 줄에서 `출처:` 만 빼면 된다). 테스트가 둘이 어긋나면 잡는다.

## 관절·관통 검사

동작을 만들거나 고친 뒤에는 관절이 사람처럼 꺾였는지, 몸·기구가 서로 뚫지 않는지 검사한다 (기준: [`../3d-joint-kinematics.md`](../3d-joint-kinematics.md)).

```bash
node docs/3d/qa_sample.js work/qa                      # 앱(127.0.0.1:8390)을 헤드리스 크롬으로 열어 동작마다 관절·기구 자리 24 프레임 + 그림 8장 (남·여)
python docs/3d/qa_check.py work/qa --sheets            # 위반 목록(report.txt) + sheets/<성별>_<동작>.jpg (위반 프레임은 빨간 테두리)
node docs/3d/qa_sample.js work/qa http://127.0.0.1:8390/ lunge,squat   # 몇 개만
```

`move-3d.js` 끝의 `MOVE_3D.qa(canvas)` 손잡이(멈춤·시간 이동·관절/기구 자리·살 두께)를 쓴다. 닿는 것(손을 허리에, 벤치에 눕기, 기구 쥐기)은 2~7cm 겹침까지 봐주고, 그 이상은 뚫는 것으로 잡는다.
자세 엔진은 팔꿈치·무릎이 굽는 쪽에 위팔·허벅지의 비틀림을 자동으로 맞춘다(`alignHinges`) — 자세 표에서 굽는 방향만 맞으면 된다.

## 캐릭터 후보 비교

`docs/3d/preview.html` 은 여러 GLB 를 같은 카메라·조명으로 찍는다. 저장소 루트에서 `python -m http.server 8000` 을 띄우고
`http://localhost:8000/docs/3d/preview.html?files=work/a.glb,work/b.glb` 를 연다. `snap=http://127.0.0.1:8393/snap` 을 붙이고 `python docs/3d/snap_server.py snaps` 를 띄워 두면 PNG 로 저장된다(카메라: `ty`, `dist`, `az`, `el`).

## 자주 걸린 것

- **두 번째 동작부터 안 뜬다**: 한 캔버스에 WebGL 컨텍스트는 하나. 렌더러를 캔버스마다 하나만 만들어 재사용한다(`forceContextLoss` 금지).
- **캐릭터가 거대하거나 안 보인다**: 파일 단위가 제각각(m·cm·0.01m). 앱이 묶인 자세의 꼭짓점으로 키를 재 1.75m 로 맞춘다 — 스킨 메시의 Box3 는 뼈가 움직이기 전이라 믿을 수 없다.
- **팔·손바닥 축이 틀어진다**: 자동 리깅은 올린 자세(A 자세)로 묶인다. 캐릭터 파일에 든 한 프레임짜리 T 자세를 먼저 입힌 뒤 '처음 자세'를 잰다.
- **척추 아래쪽이 자세를 안 따라온다**: 뼈 이름을 맞출 때 숫자까지 남겨야 한다(`Spine`·`Spine1`·`Spine2`). 글자만 남기면 셋이 한 이름이 되어 맨 마지막 것만 움직인다.
- **몸이 공중에 뜬다**: three.js 믹서는 값이 안 바뀐 프레임엔 뼈를 다시 쓰지 않는다. 우리가 덮어쓴 엉덩이는 '믹서가 마지막에 준 값'으로 되돌린다(처음 자세로 되돌리면 안 된다).
- **옷·머리카락**: 몸 표면을 복제해 부풀린 껍질로 만들어 봤지만 근육 굴곡을 따라가 이상했고, 리뷰에서 뺐다. 다시 하려면 껍질을 라플라시안으로 편 뒤 몸 밖 최소 간격을 지키게 밀어내는 방식이 그나마 낫다.
