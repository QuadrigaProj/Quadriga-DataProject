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
    assert len(covered) >= 20, sorted(covered)
    js = _js()
    assert "const clipName = (TWEAKS[id] && TWEAKS[id].base) || (PROC[id] && PROC[id].base) || CLIPS[id] || FALLBACK_CLIP;" in js
    assert "FALLBACK_CLIP = 'idle'" in js
    assert "이 동작의 3D 동작은 아직 없어 기본 자세만 보여 줘요" in js
    표 = _index().split("const POSE_FOR_SPORT = {")[1].split("};")[0]
    종목 = dict(re.findall(r"(\w+): '([a-z0-9-]+)'", 표))
    for 자세 in 종목.values():
        assert 자세 in ids, 자세                                                       # 종목은 34개 동작 중 하나로
    for 종목명 in ("running", "walking", "swimming", "jumprope", "hiking", "gym", "crossfit", "pilates", "yoga"):
        assert 종목[종목명] in clips, 종목명                                            # 흔한 종목은 진짜 동작으로


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
    assert "'knee-pushup': { pitchAtHands:" in 손봄 and "'mixamorig:LeftLeg': { aim: shinBack }" in 손봄     # 무릎을 바닥에, 정강이는 뒤로 눕힌다
    만듦 = _proc()
    assert "'deadlift': { base: 'idle', period: 3.4, gear: 'barbell', fist: true" in 만듦                   # 힌지해서 바를 잡고 똑바로 선다
    assert "'shoulder-press': { base: 'idle', period: 2.4, gear: 'dumbbells', fist: true" in 만듦          # 어깨 위로 밀어 올린다
    assert "palmTo: 'head'" in 만듦                                                                          # 손바닥은 머리 쪽으로
    assert "'one-leg': { base: 'idle', period: 6" in 만듦 and "handsOnHips(C)" in 만듦                     # 손은 허리, 한 발 들기
    assert "const clipName = (TWEAKS[id] && TWEAKS[id].base) || (PROC[id] && PROC[id].base) || CLIPS[id] || FALLBACK_CLIP;" in js
    적용 = js.split("const applyTweaks = t =>")[1].split("\n    };")[0]
    assert "pitchAtHands(tweak.pitchAtHands)" in 적용 and "aimBone(bone, typeof how.aim === 'function' ? how.aim(posOf) : how.aim)" in 적용
    assert "if (how.palmTo) palmToward(bone, how.palmTo);" in 적용 and "if (tweak.fist) fist();" in 적용
    assert "const palm = new T.Vector3(0, -1, 0).applyQuaternion(inv).normalize();" in js   # 손바닥 축은 T 자세에서 잰다
    assert "const norm = n => String(n).replace(/[^A-Za-z]/g, '');" in js       # GLTFLoader 가 ':' 를 지워도 뼈를 찾는다


def test_기구가_필요한_동작엔_기구를_붙인다():
    js = _js()
    기구 = js.split("const GEAR = {")[1].split("\n  };")[0]
    for id_, 이름 in (("barbell-squat", "backbar"), ("deadlift", "barbell"), ("dumbbell-curl", "dumbbells"), ("shoulder-press", "dumbbells"),
                     ("kettlebell-swing", "kettlebell"), ("jump-rope", "rope"), ("treadmill", "treadmill"), ("swim", "water"),
                     ("bench-press", "bench"), ("lat-pulldown", "pulldown"), ("leg-press", "legpress"), ("cycle", "bike"), ("rowing", "rower"), ("calf-stretch", "wall")):
        assert f"'{id_}': '{이름}'" in 기구, id_
    만들기 = js.split("function makeGear(T, name, ctx)")[1].split("\n  }")[0]
    for 이름 in ("barbell", "backbar", "dumbbells", "kettlebell", "rope", "treadmill", "water", "bench", "pulldown", "legpress", "bike", "rower", "wall"):
        assert f"case '{이름}':" in 만들기, 이름
    assert "grip('Left', a); grip('Right', b2);" in 만들기                                     # 손바닥 가운데를 잡는다
    assert "out.add(b.set(0, GRIP.along, 0).applyQuaternion(q));" in 만들기
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
    assert "prefers-reduced-motion: reduce" in js and "action.paused = true" in js
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
                "crunch", "deadlift", "shoulder-press", "one-leg", "deep-breath", "shoulder-stretch", "neck-stretch"):   # 설명과 달랐던 것
        assert id_ in 만든_ids, id_
    assert ids <= (set(_clips()) | 만든_ids), sorted(ids - set(_clips()) - 만든_ids)                     # 34개 모두 진짜 동작
    for _, base, period in 있는:
        assert (FRONT / "assets" / "3d" / "anim" / "m" / f"{base}.glb").exists(), base                   # 바탕 동작 파일이 있다
        assert 1.5 <= float(period) <= 15, period
    노트 = (ROOT / "docs" / "3d-exercise-form-notes.md").read_text(encoding="utf-8")
    for id_ in ids:
        assert f"### {id_} " in 노트, id_                                                                # 동작마다 자세 설명이 있다
    js = _js()
    for 조각 in ("const ik2 = (a, target, l1, l2, bend) =>", "const orientBone = (bone, up, front) =>", "typeof how.ik === 'function' ? how.ik() : how.ik",
                 "const resetHips = () =>", "applyProc(clock.elapsedTime);", "const cycle = proc ? proc.period : clip.duration;"):
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
