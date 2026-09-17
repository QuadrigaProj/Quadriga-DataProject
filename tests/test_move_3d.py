"""영상이 없는 동작을 3D 캐릭터로 (M5).

고른 종목·기록 종목은 공식 영상이 없다. 그 자리에 회색 마네킹(Blender 인체
기본형을 Mixamo 로 리깅)이 실제 모션캡처 동작을 하는 모습을 띄우고, 아래에
대체했다고 적는다. 캐릭터·동작 파일은 assets/3d 에, three.js 는 js/vendor 에 함께 둔다 —
밖에서 받지 않으니 오프라인 시연에서도 돈다.
"""
from __future__ import annotations

import re
import struct
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"


def _js() -> str:
    return (FRONT / "js" / "move-3d.js").read_text(encoding="utf-8")


def _art() -> str:
    return (FRONT / "js" / "move-art.js").read_text(encoding="utf-8")


def _index() -> str:
    return (FRONT / "index.html").read_text(encoding="utf-8")


def _proc() -> str:
    """학습한 자세로 만든 동작(PROC) 표."""
    return _js().split("const PROC = {")[1].split("\n  };")[0]


def _clips() -> dict:
    표 = _js().split("const CLIPS = {")[1].split("\n  };")[0]
    return dict(re.findall(r"'([a-z0-9-]+)': '([a-z0-9-]+)'", 표))


def _glb_json(path: Path) -> dict:
    """GLB 의 JSON 덩이만 읽는다 (three.js 없이 구조만 본다)."""
    b = path.read_bytes()
    assert b[:4] == b"glTF", path
    length = struct.unpack_from("<I", b, 12)[0]
    return json.loads(b[20:20 + length].decode("utf-8"))


def test_three_js_는_같이_둔다_밖에서_받지_않는다():
    for f in ("three.module.min.js", "loaders/GLTFLoader.js", "utils/BufferGeometryUtils.js"):
        assert (FRONT / "js" / "vendor" / f).exists(), f
    js = _js()
    assert "import('three')" in js and "import('./vendor/loaders/GLTFLoader.js')" in js   # 이 파일 기준 상대경로
    assert "cdnjs" not in js and "jsdelivr" not in js
    html = _index()
    assert '"three": "./js/vendor/three.module.min.js"' in html                       # importmap 이 'three' 를 잇는다
    assert html.index('type="importmap"') < html.index('src="js/api.js"')             # 어떤 스크립트보다 앞


def test_캐릭터는_남녀_사람_몸_마네킹이고_Mixamo_뼈대가_있다():
    for sex in ("m", "f"):
        p = FRONT / "assets" / "3d" / f"mannequin-{sex}.glb"
        j = _glb_json(p)
        names = [n.get("name", "") for n in j["nodes"]]
        assert "mixamorig:Hips" in names and "mixamorig:LeftArm" in names and "mixamorig:RightUpLeg" in names, sex
        assert "mixamorig:LeftHandIndex1" in names, sex                                     # 손가락까지 — 기구를 쥔다
        assert len(j.get("skins", [])) >= 1 and len(j.get("meshes", [])) >= 1, sex
        assert "EXT_meshopt_compression" in j.get("extensionsRequired", []), sex           # gltfpack 으로 눌렀다
        assert p.stat().st_size < 320_000, sex                                               # 휴대폰에서도 금방 받는다
        assert j["animations"] and j["animations"][0]["channels"], sex                      # 한 프레임짜리 T 자세가 들어 있다
    assert not (FRONT / "assets" / "3d" / "ybot.glb").exists()                           # 옛 Y Bot 은 치웠다
    js = _js()
    assert "const MODEL = s => 'mannequin-' + SEX(s) + '.glb';" in js and "loader.setMeshoptDecoder(lib.Meshopt)" in js
    assert "const SEX = s => (String(s || '').toUpperCase() === 'F' ? 'f' : 'm');" in js   # 앱의 성별('M'/'F')로 고른다
    assert "sex: state.sex" in _index() and "MOVE_3D.preload(state.sex)" in _index()
    assert "import('./vendor/libs/meshopt_decoder.module.js')" in js
    assert (FRONT / "js" / "vendor" / "libs" / "meshopt_decoder.module.js").exists()


def test_동작_파일은_뼈대만_들어_있고_작다():
    """동작 파일마다 캐릭터를 또 넣지 않는다 — 뼈대 + 애니메이션만."""
    clips = _clips()
    for sex in ("m", "f"):                                                                  # 뼈대가 달라 성별마다 따로
        for name in sorted(set(clips.values()) | {"idle"}):
            p = FRONT / "assets" / "3d" / "anim" / sex / f"{name}.glb"
            assert p.exists(), (sex, name)
            j = _glb_json(p)
            assert not j.get("meshes"), name
            assert j.get("animations") and j["animations"][0]["channels"], name
            assert "mixamorig:Hips" in [n.get("name", "") for n in j["nodes"]], name     # 같은 뼈 이름이라 그대로 붙는다
            assert p.stat().st_size < 120_000, name                                              # gltfpack 으로 눌러 둔다
    assert "BASE + 'anim/' + key + '.glb' + VER" in _js() and "const key = SEX(sex) + '/' + name;" in _js()


def test_자세_그림이_있는_동작은_모두_처리된다():
    """move-art.js 의 34개 동작: 동작 파일이 있거나(CLIPS), 없으면 기본 자세로 대신하며 그렇다고 적는다."""
    ids = set(re.findall(r'id="pose-([a-z0-9-]+)"', _art()))
    clips = _clips()
    assert ids, "자세 그림이 없다"
    covered = ids & set(clips)
    assert len(covered) >= 19, sorted(covered)            # 수영·플랭크는 모션캡처 대신 직접 만든다 (PROC)
    js = _js()
    assert "const clipName = (TWEAKS[id] && TWEAKS[id].base) || (PROC[id] && PROC[id].base) || CLIPS[id] || FALLBACK_CLIP;" in js
    assert "FALLBACK_CLIP = 'idle'" in js
    assert "이 동작의 3D 동작은 아직 없어 기본 자세만 보여 줘요" in js
    표 = _index().split("const POSE_FOR_SPORT = {")[1].split("};")[0]
    종목 = dict(re.findall(r"(\w+): '([a-z0-9-]+)'", 표))
    for 자세 in 종목.values():
        assert 자세 in ids, 자세                                                       # 종목은 34개 동작 중 하나로
    만든 = set(re.findall(r"^    '([a-z0-9-]+)': \{ base:", _proc(), re.M))
    for 종목명 in ("running", "walking", "swimming", "jumprope", "hiking", "gym", "crossfit", "pilates", "yoga"):
        assert 종목[종목명] in clips or 종목[종목명] in 만든, 종목명                     # 흔한 종목은 진짜 동작으로 (수영은 직접 만든 자유형)


def test_겉모습은_매끈한_회색이다():
    """Mixamo 디자인 그대로가 아니라 — 각진 면을 매끈하게, 색은 회색 하나로."""
    js = _js().split("function smoothAndGray(lib, body)")[1].split("\n  }")[0]
    assert "g.deleteAttribute('normal'); g.deleteAttribute('uv');" in js        # 이음새까지 합쳐서
    assert "const merged = U.mergeVertices(g, tol); merged.computeVertexNormals();" in js   # 법선을 다시 계산한다
    assert "getSize(new T.Vector3()).length() * 1e-5" in js                     # '같은 자리' 기준은 몸 크기에 비례
    assert "color: 0xBCC1C7, roughness: 0.62" in js                               # 마네킹 회색 하나


def test_비슷한_동작은_뼈를_손봐_원래_동작에_가깝게():
    js = _js()
    손봄 = js.split("const TWEAKS = {")[1].split("\n  };")[0]
    assert "'knee-pushup': { bones: {" in 손봄 and "'mixamorig:LeftUpLeg': { aim: thighToFloor('Left') }" in 손봄 and "'mixamorig:LeftLeg': { aim: shinBack }" in 손봄     # 무릎을 바닥에, 정강이는 뒤로 눕힌다
    만듦 = _proc()
    assert "'deadlift': { base: 'idle', period: 3.4, gear: 'barbell', fist: true" in 만듦                   # 힌지해서 바를 잡고 똑바로 선다
    assert "'shoulder-press': { base: 'idle', period: 2.6, gear: 'seatpress', fist: true, still: true" in 만듦   # 벤치에 앉아 어깨 위로 밀어 올린다
    assert "palm: () => occiput(C, 1).palm" in 만듦                                                          # 손바닥은 뒤통수(머리 가운데)를 본다
    assert "'one-leg': { base: 'idle', period: 6" in 만듦 and "handsOnHips(C)" in 만듦                     # 손은 허리, 한 발 들기
    assert "const clipName = (TWEAKS[id] && TWEAKS[id].base) || (PROC[id] && PROC[id].base) || CLIPS[id] || FALLBACK_CLIP;" in js
    적용 = js.split("const applyTweaks = t =>")[1].split("\n    };")[0]
    assert "pitchAtHands(tweak.pitchAtHands)" in 적용 and "aims.set(bone, typeof how.aim === 'function' ? how.aim(posOf) : how.aim)" in 적용 and "aimBone(bone, aims.get(bone));" in 적용   # 방향은 돌리기 전에 다 계산
    assert "if (how.palmTo) palmToward(bone, how.palmTo);" in 적용 and "if (tweak.fist) fist();" in 적용
    assert "const palm = new T.Vector3(0, -1, 0).applyQuaternion(inv).normalize();" in js   # 손바닥 축은 T 자세에서 잰다
    assert "const norm = n => String(n).replace(/[^A-Za-z0-9]/g, '');" in js    # GLTFLoader 가 ':' 를 지워도 뼈를 찾는다 (숫자는 남긴다 — Spine1·Spine2)


def test_기구가_필요한_동작엔_기구를_붙인다():
    js = _js()
    기구 = js.split("const GEAR = {")[1].split("\n  };")[0]
    for id_, 이름 in (("barbell-squat", "backbar"), ("deadlift", "barbell"), ("dumbbell-curl", "dumbbells"), ("shoulder-press", "seatpress"),
                     ("kettlebell-swing", "kettlebell"), ("jump-rope", "rope"), ("treadmill", "treadmill"), ("swim", "water"),
                     ("bench-press", "bench"), ("lat-pulldown", "pulldown"), ("leg-press", "legpress"), ("cycle", "bike"), ("rowing", "rower"), ("calf-stretch", "wall")):
        assert f"'{id_}': '{이름}'" in 기구, id_
    만들기 = js.split("function makeGear(T, name, ctx)")[1].split("\n  }")[0]
    for 이름 in ("barbell", "backbar", "dumbbells", "seatpress", "kettlebell", "rope", "treadmill", "water", "bench", "pulldown", "legpress", "bike", "rower", "wall"):
        assert f"case '{이름}':" in 만들기, 이름
    assert "grip('Left', a); grip('Right', b2);" in 만들기                                     # 손바닥 가운데를 잡는다
    assert "out.add(b.set(0, (ctx.hand[side] && ctx.hand[side].along) || GRIP.along, 0).applyQuaternion(q));" in 만들기   # 손바닥 자리는 리깅마다 잰다
    assert "new T.TubeGeometry(new T.CatmullRomCurve3(pts), 48, 0.008, 6, false)" in 만들기   # 줄넘기 줄은 손잡이 사이를 돈다
    assert "ctx.jump = { peak0:" in js                                                         # 뛰어오를 때 발밑을 지난다
    assert "if (gear.update) gear.update(clock.elapsedTime, action.time);" in js


def test_비슷한_동작으로_대신하는_것은_화면에_적는다():
    js = _js()
    근사 = js.split("const APPROX = {")[1].split("\n  };")[0]
    assert "'knee-pushup':" in 근사
    assert "const note = APPROX[id] || (PROC[id] ? PROC_NOTE : (CLIPS[id] ? '' : GAP_NOTE));" in js
    assert "PROC_NOTE = '자세 설명을 보고 만든 3D 동작이에요'" in js                                          # 설명대로 만든 동작도 그렇다고 적는다
    assert "if (onNote) onNote(note);" in js
    html = _index()
    assert 'id="exercise3dSub"' in html
    보이기 = html.split("function show3dForStep(step)")[1].split("\n}")[0]
    assert "s.textContent = t || ''; s.hidden = !t;" in 보이기
    assert "MOVE_3D.start($('exercise3dCanvas'), pose, { onNote, sex: state.sex })" in 보이기


def test_빛과_그림자_카메라는_몸을_따라간다():
    js = _js().split("function setup(lib, me, clip)")[1].split("\n  }")[0]
    assert "r.shadowMap.enabled = true" in _js() and "ShadowMaterial" in js          # 그림자는 렌더러를 만들 때 켠다
    assert "new T.AnimationMixer(body)" in js and "mixer.clipAction(clip)" in js
    assert "prefers-reduced-motion: reduce" in js and "action.paused" not in js      # 움직임 줄이기여도 동작은 돈다 (카메라만 가만히)
    assert "for (const b of boneList) { b.getWorldPosition(v); lo.min(v); hi.max(v); }" in js   # 뼈대 상자로 화면 맞춤
    assert "smoothAndGray(lib, body)" in js
    assert "if (h > 0 && (h < 1.2 || h > 2.4)) body.scale.setScalar(1.75 / h);" in js   # 단위가 뭐든 사람 키로
    assert "if (me.tpose) {" in js and "b.quaternion.fromArray(tr.values, 0);" in js    # 처음 자세는 늘 T 자세


def test_플레이어에_붙어_있고_출처를_적는다():
    html = _index()
    assert html.index('src="js/move-art.js"') < html.index('src="js/move-3d.js"')
    assert 'id="exercise3d"' in html and 'id="exercise3dCanvas"' in html
    assert "*해당하는 영상이 없어 3D 동작으로 대체했습니다. (몸: Blender 인체 기본형 · 뼈대·동작: Mixamo)" in html
    js = _js()
    assert "if (onNote) onNote(LOADING_NOTE);" in js and "LOADING_NOTE = '3D 동작을 불러오는 중…'" in js   # 기다리는 동안 알려 준다
    assert "function preload(sex)" in js and "MOVE_3D.preload(state.sex)" in html            # 루틴 화면에서 내 성별 캐릭터를 미리 받아 둔다


def test_영상이_있으면_영상_없으면_3D():
    html = _index()
    본문 = html.split("function poseForStep(step)")[1].split("\n}")[0]
    assert "if (!step || youtubeVideoId(step.youtube_id)) return null;" in 본문
    assert "if (step.출처 === '기록') return step.id || null;" in 본문
    assert "POSE_FOR_SPORT[step.id] || null" in 본문
    멈춤 = html.split("function stopExerciseVideo()")[1].split("\n}")[0]
    assert "show3dForStep(step);" in 멈춤
    보이기 = html.split("function show3dForStep(step)")[1].split("\n}")[0]
    assert "MOVE_3D.stop(); box.hidden = true;" in 보이기


def test_화면을_떠나면_멈추고_자원을_돌려준다():
    assert "if(id !== 's4') MOVE_3D.stop();" in _index()
    멈춤 = _js().split("function stop(canvas)")[1].split("\n  }")[0]
    assert "cancelAnimationFrame(me.raf)" in 멈춤
    assert "if (o.geometry) o.geometry.dispose();" in 멈춤 and "me.renderer.renderLists.dispose(); me.renderer.clear();" in 멈춤
    assert "forceContextLoss" not in _js()                                    # 컨텍스트를 잃게 하면 같은 캔버스에 다시 못 그린다
    assert "const renderers = new WeakMap();" in _js() and "const renderer = getRenderer(T, canvas);" in _js()   # 캔버스마다 렌더러 하나


def test_학습한_자세로_만든_동작이_빈_동작을_다_채운다():
    """docs/3d-exercise-form-notes.md 에 정리한 자세대로 — 모션캡처가 없던 13개와 설명과 다르던 7개."""
    ids = set(re.findall(r'id="pose-([a-z0-9-]+)"', _art()))
    만듦 = _proc()
    있는 = set(re.findall(r"^    '([a-z0-9-]+)': \{ base: '([a-z-]+)', period: ([0-9.]+)", 만듦, re.M))
    만든_ids = {i for i, _, _ in 있는}
    for id_ in ("lunge", "bridge", "bench-press", "lat-pulldown", "leg-press", "cycle", "rowing", "hamstring-stretch", "calf-stretch",
                "hip-stretch", "twist", "side-plank", "dead-bug",                                        # 모션캡처가 없던 것
                "crunch", "deadlift", "shoulder-press", "one-leg", "deep-breath", "shoulder-stretch", "neck-stretch",
                "swim", "plank"):   # 설명과 달랐던 것 (수영은 평영, 플랭크는 팔 편 하이 플랭크였다)
        assert id_ in 만든_ids, id_
    assert ids <= (set(_clips()) | 만든_ids), sorted(ids - set(_clips()) - 만든_ids)                     # 34개 모두 진짜 동작
    for _, base, period in 있는:
        assert (FRONT / "assets" / "3d" / "anim" / "m" / f"{base}.glb").exists(), base                   # 바탕 동작 파일이 있다
        assert 1.5 <= float(period) <= 15, period
    노트 = (ROOT / "docs" / "3d-exercise-form-notes.md").read_text(encoding="utf-8")
    for id_ in ids:
        assert f"### {id_} " in 노트, id_                                                                # 동작마다 자세 설명이 있다
    js = _js()
    for 조각 in ("const ik2 = (a, target, l1, l2, bend) =>", "const orientBone = (bone, up, front) =>", "typeof how.ik === 'function' ? how.ik(posOf) : how.ik",
                 "const restoreMixed = () =>", "rememberMixed();", "applyProc(clock.elapsedTime);", "const cycle = proc ? proc.period : clip.duration;"):
        assert 조각 in js, 조각


def test_우리가_만든_동작엔_바른_자세_설명을_같이_띄운다():
    """영상이 없어 3D 로 보여 주는 동작은 docs 의 자세 설명(js/move-notes.js)을 캔버스 아래에 같이 보여 준다."""
    notes_js = (FRONT / "js" / "move-notes.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="pose-([a-z0-9-]+)"', _art()))
    표 = json.loads(notes_js.split("const MOVE_NOTES = ")[1].rsplit(";", 1)[0])
    assert ids <= set(표), sorted(ids - set(표))                                                  # 34개 동작 모두
    노트 = (ROOT / "docs" / "3d-exercise-form-notes.md").read_text(encoding="utf-8")
    for id_, v in 표.items():
        assert 2 <= len(v["tips"]) <= 7 and v["name"], id_
        assert f"### {id_} {v['name']}" in 노트, id_                                                # 문서에서 뽑은 그대로
        assert all("출처" not in t for t in v["tips"]), id_                                          # 출처는 문서에만
    html = _index()
    assert html.index('src="js/move-notes.js"') < html.index('src="js/move-3d.js"')
    assert 'id="exercise3dTips"' in html and "function render3dTips(pose)" in html
    보이기 = html.split("function show3dForStep(step)")[1].split("\n}")[0]
    assert "render3dTips(pose);" in 보이기
    그리기 = html.split("function render3dTips(pose)")[1].split("\n}")[0]
    assert "MOVE_NOTES[pose]" in 그리기 and "note.name + ' — 이렇게 해요'" in 그리기


def test_움직임_줄이기_설정이어도_동작은_멈추지_않는다():
    """휴대폰의 '움직임 줄이기'(prefers-reduced-motion) 설정에서 캐릭터가 한 프레임만 그리고 멈춰 있었다.
    동작 자체가 보여 줄 내용이니 항상 돌리고, 카메라가 좌우로 도는 것만 뺀다."""
    js = _js()
    assert "action.paused = true" not in js
    assert "if (!still)" not in js and "if (still)" not in js
    assert "me.raf = requestAnimationFrame(frame);" in js
    assert "prefers-reduced-motion" in js and "calm ? 0 :" in js


def test_팔꿈치_무릎은_사람처럼_한쪽으로만_굽는다():
    """docs/3d-joint-kinematics.md — 경첩 관절: 아래팔·정강이가 굽는 쪽에 위팔·허벅지의 비틀림을 맞추고,
    아래팔·정강이는 위팔·허벅지에 대해 비틀리지 않게 한다. IK 로 움직인 팔다리 끝의 손·발은 부모가 정해진 뒤 다시 맞춘다."""
    js = _js()
    assert "const HINGES = [['LeftArm', 'LeftForeArm', [0, 0, 1]]" in js and "['LeftUpLeg', 'LeftLeg', [0, 0, -1]]" in js
    적용 = js.split("const applyProc = t => {")[1].split("\n    };")[0]
    assert 적용.count("aimPass();") == 4 and "alignHinges(table);" in 적용          # 방향 → IK(두 번) → 손·발 다시 → (어깨뼈 리듬이면 한 번 더) → 경첩
    assert "if (shrugged) { aimPass(); ikPass(); ikPass(); aimPass(); }" in 적용 and "Math.min(12 * D, (elev - 80 * D) * 0.15)" in 적용   # 팔을 수평 위로 들면 빗장뼈가 살짝(12° 까지) 따라 올라간다
    assert 적용.index("aimPass();") < 적용.index("ikPass(); ikPass();") < 적용.rindex("aimPass();") < 적용.index("alignHinges(table);")
    손봄 = js.split("const applyTweaks = t => {")[1].split("\n    };")[0]
    assert "alignHinges(byBone);" in 손봄
    정렬 = js.split("const alignHinges = table => {")[1].split("\n    };")[0]
    assert "if (table && !table.has(p) && !table.has(c)) continue;" in 정렬           # 모션캡처 뼈는 건드리지 않는다
    assert "hc.palmTo || hc.roll" in 정렬                                            # 손바닥 방향을 정한 아래팔은 비틀림을 그대로


def test_팔은_불러올_때_다시_리깅한다():
    """자동 리깅의 세 가지 흠을 장면마다 한 번 고친다 (리뷰: 팔꿈치~손·어깨·겨드랑이가 깨진다).
    ① 팔꿈치 관절이 아래팔 중간에 가 있다 → 어깨→손목의 56% 로 옮긴다 (fixElbows)
    ② 관절마다 뼈가 하나라 크게 돈 살이 꺼진다 → 비틀림 뼈 · 나눠 도는 관절 (addArmHelpers + driveHelpers)
    ③ 가중치가 8비트라 고쳐 쓰면 합이 1 에서 어긋난다 → 실수로 바꿔서 쓴다 (floatSkinWeights)"""
    js = _js()
    끝 = "\n  }"
    assert "const ELBOW_AT = 0.56, ELBOW_BLEND = 0.06;" in js
    팔꿈치 = js.split("function fixElbows(lib, body){")[1].split(끝)[0]
    assert "fore.position.multiplyScalar(want / l1)" in 팔꿈치 and "hand.position.copy(fore.worldToLocal(W.clone()))" in 팔꿈치   # 관절만 옮기고 손목은 제자리
    assert "sw = floatSkinWeights(T, m.geometry)" in 팔꿈치
    실수 = js.split("function floatSkinWeights(T, geometry){")[1].split(끝)[0]
    assert "new Float32Array(sw.count * 4)" in 실수 and "out[i * 4 + k] /= sum" in 실수                     # 합을 1 로 맞춘다
    보조 = js.split("function addArmHelpers(lib, body){")[1].split(끝)[0]
    assert "const TWIST_AT = [0, 0.2, 0.4, 0.6, 0.8];" in js and "const ELBOW_SWING_AT = [1 / 3, 2 / 3];" in js
    assert "sw = floatSkinWeights(T, m.geometry)" in 보조 and "b.helperOf = source;" in 보조
    assert "put(p.half, all * g * 2 * u * (1 - u)); put(p.arm, all * (g * u * u + (1 - g) * uw));" in 보조     # 어깨: (1−u)² : 2u(1−u) : u²
    assert "p.u = relax(u, SHOULDER_SMOOTH); p.uWide = relax(u, AXILLA_SMOOTH);" in 보조                      # 겨드랑이는 더 넓게 고르게
    assert "while (w.size > 4) {" in 보조 and "rung.get(small)" in 보조                                      # 영향 뼈 4개 — 넘치면 닮은 뼈에 합친다
    assert "m.bind(new T.Skeleton(bones, inverses), m.bindMatrix);" in 보조
    시작 = js.split("function setup(lib, me, clip){")[1]
    assert 시작.index("smoothAndGray(lib, body);") < 시작.index("fixElbows(lib, body);") < 시작.index("const helperRig = addArmHelpers(lib, body);") < 시작.index("if (me.tpose) {")   # 묶인 자세에서
    assert "if (o.isBone && !o.helperOf) { map.set(norm(o.name), o); boneList.push(o); }" in 시작            # 보조 뼈는 자세·검사에서 뺀다
    구동 = 시작.split("const driveHelpers = () => {")[1].split("\n    };")[0]
    assert "h.bone.quaternion.setFromAxisAngle(_hY, (h.tau - 1) * th);" in 구동 and "h.bone.quaternion.copy(j.bindQ).slerp(_h0, h.f);" in 구동
    assert "while (th - j.prev > Math.PI) th -= 2 * Math.PI;" in 구동                                         # ±180° 를 넘어가도 이어서 센다
    assert "applyProc(t); driveHelpers(); body.updateMatrixWorld(true); };" in 시작                           # 검사할 때도
    assert "applyProc(clock.elapsedTime);" in 시작 and 시작.index("applyProc(clock.elapsedTime);") < 시작.index("driveHelpers();\n      if (gear.update)")   # 매 프레임, 자세를 다 잡은 뒤


def test_손과_기구는_몸을_따라간다():
    """리뷰에서 나온 손·기구 흠: 엄지가 뻗친다, 앉을 때 바가 등을 뚫는다, 허리 짚은 손이 뜬다, 팔이 떨린다."""
    js = _js()
    assert "thumb: [[0.35, 0.45, 0.82], [0.0, 0.62, 0.78], [-0.4, 0.8, 0.45]]" in js                          # 엄지는 손잡이 아래로 돌아 손가락 끝을 덮는다
    주먹 = js.split("const fist = () => {")[1].split("\n    };")[0]
    assert "if (m[2] === 'Thumb' && GRIP.thumb) {" in 주먹 and "addScaledVector(h.radial, d[0])" in 주먹
    assert "const BACKBAR = [0, -0.005, -0.08];" in js and "ctx.carry('mixamorig:Spine2', b.fromArray(BACKBAR))" in js   # 바는 숙인 등을 따라간다
    proc = _proc()
    assert "'barbell-squat': { base: 'barbell-squat', period: 2.27, gear: 'backbar', fist: true" in proc      # 손도 바를 따라간다
    assert "'barbell-squat': '스쿼트 동작에 바를 쥔 손만 맞췄어요'" in js
    assert "const armT = side => ({ ik: p => add(p(side + 'Arm')," in proc                                    # 허리 비틀기: 편 팔도 IK 라 무릎 누르는 팔과 매끈하게 이어진다
    햄 = proc.split("'hamstring-stretch'")[1].split("} },")[0]
    assert "[L + 'UpLeg']: straight, [L + 'Leg']: straight" in 햄 and "[R + 'UpLeg']: { ik: [-half - 0.01, 0.086, BACK_Z], bend: [0, 0, 1] }" in 햄   # 뒷무릎은 앞으로 굽는다
    assert "[L + 'Arm']: { ik: p => [p(L + 'Arm').x + 0.15, 0.035, 0.07]" in proc.split("'bridge'")[1].split("} },")[0]   # 브리지: 손목을 바닥에 박아 둔다
    적용 = js.split("const applyProc = t => {")[1].split("\n    };")[0]
    assert "if (clavicles.has(bone)) { placeClavicle(bone); continue; }" in 적용 and "if (lift > 0.002) { lifts.set(cl, lift); shrugged = true; }" in 적용   # 빗장뼈는 늘 제자리에서 다시 놓는다
    assert "table.has(f) || (arm && table.get(arm) && table.get(arm).ik)" in 적용                             # 팔만 정한 자세는 손목을 곧게
    정렬 = js.split("const alignHinges = table => {")[1].split("\n    };")[0]
    assert "bend.fromArray(hp0.bend).negate();" in 정렬 and "lastBend.has(p)" in 정렬               # 편 팔은 IK 가 굽힐 쪽·마지막으로 굽었던 쪽을 이어 쓴다 (팔 떨림)
    손봄 = js.split("const TWEAKS = {")[1].split("\n  };")[0]
    assert "'run': { bones: runArms }" in 손봄 and "const tuck = (side, from, to, keep, inward) => p => {" in js   # 달리기: 벌어진 팔을 몸 가까이


def test_떨림과_손목_꼬임을_막는다():
    """리뷰 3차: 목·종아리 스트레칭·바벨 스쿼트의 잔 떨림, 손목이 갑자기 가늘어지며 꼬이는 것, 무릎 푸시업의 발목.
    ① 빗장뼈의 올림각을 '지금 빗장뼈'에서 재면 프레임마다 출발점이 달라(동작 파일이 덮어쓴 프레임 / 우리가 올려 둔 프레임) 어깨가 1cm 씩 오르내린다
    ② 손목은 비틀리지 않는다 — 손의 제 축 비틀림은 아래팔이 가져가고(비틀림 뼈가 나눠 갖는다), 못 받은 만큼은 손바닥을 덜 돌린다
    ③ 아래팔·정강이를 돌릴 게 없을 때 손·발 비틀림 맞추기까지 건너뛰던 버그
    ④ 우리가 돌려 둔 뼈가 다음 프레임에 남아(믹서는 값이 안 바뀐 뼈를 다시 쓰지 않는다) 한 번 더·덜 돌던 것 — 매 프레임 믹서가 준 자세에서 시작한다
    ⑤ 경첩 축을 임시 벡터에 두어 정강이를 돌린 프레임엔 발 맞추기가 엉뚱한 축으로 셈되던 것 (무릎 푸시업의 발이 한 프레임씩 30° 돌았다)
    ⑥ 수영: 손바닥 목표가 아래팔과 나란해지는 순간 아래팔이 한 프레임에 뒤집히던 것"""
    js = _js()
    적용 = js.split("const applyProc = t => {")[1].split("\n    };")[0]
    assert "const lifts = new Map(), clavicles = new Set();" in 적용 and "lifts.get(cl) || 0" in 적용          # 첫 풀이는 늘 들지 않은 자리에서
    assert 적용.index("h.quaternion.copy(restLocalQ.get(h));") < 적용.index("aimPass();")                       # 손목 중립은 palmTo 가 아래팔을 돌리기 전에, 늘 같은 값으로
    assert "if (pose.fist || proc.fist) fist(); else if (pose.open || proc.open) openHands();" in 적용
    assert "const openHands = () => {" in js and "'calf-stretch': { base: 'idle', period: 6, gear: 'wall', open: true" in _proc()   # 벽 짚은 손은 편다
    시작 = js.split("function setup(lib, me, clip){")[1]
    손목 = 시작.split("const untwistWrist = r => {")[1].split("\n    };")[0]
    assert "fore.quaternion.multiply(_hr.setFromAxisAngle(_hY, turn)); hand.quaternion.premultiply(_hr.setFromAxisAngle(_hY, -turn));" in 손목   # 아래팔이 돌고 손은 세상 방향 그대로
    assert "hand.quaternion.multiply(_hr.setFromAxisAngle(_hY, -r.short));" in 손목                            # 못 받은 만큼은 손을 되돌린다 — 손목에 남기지 않는다
    assert "const FOREARM_TWIST_MAX = TWIST_LIMIT;" in 시작 and "const TWIST_LIMIT = 100 * D, TWIST_LIMIT_STRAIGHT = 100 * D;" in 시작
    assert "for (const r of helperRig) { untwistWrist(r); for (const j of [r.upper, r.lower]) {" in 시작       # 비틀림 뼈를 놓기 전에
    정렬 = js.split("const alignHinges = table => {")[1].split("\n    };")[0]
    assert "if (Math.abs(turn) >= 0.02) {" in 정렬 and "if (Math.abs(turn) < 0.02) continue;" not in 정렬      # 돌릴 게 없어도 손·발 맞추기는 한다
    assert "if (keepTwist) continue;" in 정렬 and "fill" not in 정렬                                          # 손목에서 메우지 않는다
    assert "return [b[0] / l * 0.974, -0.225, b[2] / l * 0.974]; };" in js                                    # 무릎 푸시업: 발은 정강이 선보다 아래로 13° (발바닥 굽힘 45°)
    손봄 = js.split("const TWEAKS = {")[1].split("\n  };")[0]
    assert "'mixamorig:LeftToeBase': { rest: true }" in 손봄 and "if (how.rest && restLocalQ.has(bone)) bone.quaternion.copy(restLocalQ.get(bone));" in js
    proc = _proc()
    assert "[L + 'Arm']: { ik: gripBar(1), bend: [0.3, -1, 0] }" in proc and "const HAND_ON_BAR = { dir: N(0, -0.3, 0.954), palm: N(0, -0.954, -0.3) };" in proc   # 자전거: 손바닥이 손잡이에
    스쿼트 = proc.split("'barbell-squat': { base: 'barbell-squat'")[1].split("} },")[0]
    assert "ik: p => {" in 스쿼트 and "const n = C.pos('mixamorig:Neck')" not in 스쿼트                        # 쥘 자리는 IK 를 풀 때 셈한다 (미리 읽으면 손이 튄다)
    비틀기 = proc.split("'twist'")[1].split("} },")[0]
    assert "bend: [0, -0.7, -0.7] });" in 비틀기 and "bend: [-1, -0.15, -0.2] }," in 비틀기                     # 팔꿈치 방향이 맞아야 아래팔·위팔이 덜 비틀린다
    플랭크 = proc.split("'plank'")[1].split("} },")[0]
    assert "bend: [0, -1, 0.2] });" in 플랭크                                                                  # 손 방향을 통째로 정한 팔엔 palmTo 를 또 주지 않는다
    assert "const handAt = (side, w) => {" in proc and "upL > 0.9 ?" not in proc                              # 목 스트레칭: 손 방향은 서서히
    assert "mixedQ = boneList.map(b => b.quaternion.clone());" in 시작                                         # ④ 모든 뼈를 믹서가 마지막에 준 값으로 되돌려 두고 시작한다
    assert 시작.count("restoreMixed();") == 2 and 시작.count("rememberMixed();") == 2                           #    화면용(frame)·검사용(poseAt) 둘 다
    assert "h0 = _vh.fromArray(flex0).cross(axis0);" in 정렬 and "h0 = _v2" not in 정렬                        # ⑤ 경첩 축은 제 벡터에
    수영 = proc.split("'swim': {")[1].split("} },")[0]
    assert "palmTo" not in 수영.split("return { ik:")[1].split("};")[0]                                         # ⑥ 손바닥 방향은 따로 정하지 않는다 (아래팔 비틀림 0)


def test_발은_바닥과_정강이를_기준으로_둔다():
    """리깅의 발목은 바닥에서 0.09, 평평한 발 뼈는 N(0,-0.53,0.85) — 자세 표가 이 숫자를 쓴다."""
    js = _js()
    assert "const FLAT = N(0, -0.53, 0.85);" in js
    assert "const footFollow = (side, left = [1, 0, 0], deg = 60) => p => {" in js
    proc = _proc()
    for 동작 in ("'lunge'", "'deadlift'", "'hip-stretch'", "'hamstring-stretch'", "'lat-pulldown'"):
        assert "FLAT" in proc.split(동작)[1].split("} },")[0], 동작
    assert "footFollow(L, [1, 0, 0], 66)" in proc and "const footDir = a =>" in proc   # 로잉은 정강이를 따라가고, 자전거는 페달 각도에 맞춰 발끝을 내린다


def test_관절_검사_도구가_있고_기준_문서와_맞는다():
    """docs/3d/qa_sample.js(관절·기구 자리 뽑기) → docs/3d/qa_check.py(한계·관통 검사). 규칙 이름은 학습 문서의 표에 있어야 한다."""
    js = _js()
    assert "me.qa = {" in js and "return { start, stop, preload, qa," in js
    sample = (ROOT / "docs" / "3d" / "qa_sample.js").read_text(encoding="utf-8")
    check = (ROOT / "docs" / "3d" / "qa_check.py").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "3d-joint-kinematics.md").read_text(encoding="utf-8")
    assert "MOVE_3D.qa(c)" in sample and "qa.joints()" in sample and "qa.gear()" in sample
    for rule in re.findall(r'out\.append\(\("([A-Z_]+)"', check):
        assert rule in doc, rule
    assert "3d-joint-kinematics.md" in check
