"""영상이 없는 동작을 3D 캐릭터로 (M5).

고른 종목·기록 종목은 공식 영상이 없다. 그 자리에 Mixamo(Adobe)의 무료
캐릭터 Y Bot 이 실제 모션캡처 동작을 하는 모습을 띄우고, 아래에 대체했다고
적는다. 캐릭터·동작 파일은 assets/3d 에, three.js 는 js/vendor 에 함께 둔다 —
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


def test_캐릭터는_Mixamo_Y_Bot_이고_뼈대가_있다():
    j = _glb_json(FRONT / "assets" / "3d" / "ybot.glb")
    names = [n.get("name", "") for n in j["nodes"]]
    assert "mixamorig:Hips" in names and "mixamorig:LeftArm" in names and "mixamorig:RightUpLeg" in names
    assert len(j.get("skins", [])) >= 1 and len(j.get("meshes", [])) >= 1
    assert (FRONT / "assets" / "3d" / "ybot.glb").stat().st_size < 4_000_000        # 한 번 받을 만한 크기


def test_동작_파일은_뼈대만_들어_있고_작다():
    """동작 파일마다 캐릭터를 또 넣지 않는다 — 뼈대 + 애니메이션만."""
    clips = _clips()
    for name in sorted(set(clips.values()) | {"idle"}):
        p = FRONT / "assets" / "3d" / "anim" / f"{name}.glb"
        assert p.exists(), name
        j = _glb_json(p)
        assert not j.get("meshes"), name
        assert j.get("animations") and j["animations"][0]["channels"], name
        assert "mixamorig:Hips" in [n.get("name", "") for n in j["nodes"]], name     # 같은 뼈 이름이라 그대로 붙는다
        assert p.stat().st_size < 400_000, name


def test_자세_그림이_있는_동작은_모두_처리된다():
    """move-art.js 의 34개 동작: 동작 파일이 있거나(CLIPS), 없으면 기본 자세로 대신하며 그렇다고 적는다."""
    ids = set(re.findall(r'id="pose-([a-z0-9-]+)"', _art()))
    clips = _clips()
    assert ids, "자세 그림이 없다"
    covered = ids & set(clips)
    assert len(covered) >= 20, sorted(covered)
    js = _js()
    assert "const clipName = (TWEAKS[id] && TWEAKS[id].base) || CLIPS[id] || FALLBACK_CLIP;" in js
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
    assert "U.mergeVertices(g, 1e-4); merged.computeVertexNormals();" in js     # 법선을 다시 계산한다
    assert "color: joints ? 0xA4A9B0 : 0xBCC1C7" in js                          # 회색 둘 (몸통은 한 덩이로 읽힌다)


def test_비슷한_동작은_뼈를_손봐_원래_동작에_가깝게():
    js = _js()
    손봄 = js.split("const TWEAKS = {")[1].split("\n  };")[0]
    assert "'knee-pushup': { pitchAtHands:" in 손봄 and "'mixamorig:LeftLeg': { set: [-90, 0, 0] }" in 손봄   # 무릎을 바닥에
    assert "'deadlift': { fist: true, bones: { 'mixamorig:LeftArm': hang" in 손봄                          # 팔은 늘어뜨리고 주먹을 쥔다
    assert "'shoulder-press': { base: 'idle', bones: press, fist: true }" in 손봄                           # 기본 자세 + 밀어 올리기 + 주먹
    assert "palmTo: 'head'" in js                                                                            # 손바닥은 머리 쪽으로
    assert "'one-leg': { base: 'idle', bones: oneLeg }" in 손봄                                             # 기본 자세 + 한 발 들기
    assert "const clipName = (TWEAKS[id] && TWEAKS[id].base) || CLIPS[id] || FALLBACK_CLIP;" in js
    적용 = js.split("const applyTweaks = t =>")[1].split("\n    };")[0]
    assert "pitchAtHands(tweak.pitchAtHands)" in 적용 and "aimBone(bone, how.aim)" in 적용
    assert "if (how.palmTo) palmToward(bone, how.palmTo);" in 적용 and "if (tweak.fist) fist();" in 적용
    assert "const palm = new T.Vector3(0, -1, 0).applyQuaternion(inv).normalize();" in js   # 손바닥 축은 T 자세에서 잰다
    assert "const norm = n => String(n).replace(/[^A-Za-z]/g, '');" in js       # GLTFLoader 가 ':' 를 지워도 뼈를 찾는다


def test_기구가_필요한_동작엔_기구를_붙인다():
    js = _js()
    기구 = js.split("const GEAR = {")[1].split("\n  };")[0]
    for id_, 이름 in (("barbell-squat", "backbar"), ("deadlift", "barbell"), ("dumbbell-curl", "dumbbells"), ("shoulder-press", "dumbbells"),
                     ("kettlebell-swing", "kettlebell"), ("jump-rope", "rope"), ("treadmill", "treadmill"), ("swim", "water")):
        assert f"'{id_}': '{이름}'" in 기구, id_
    만들기 = js.split("function makeGear(T, name, ctx)")[1].split("\n  }")[0]
    for 이름 in ("barbell", "backbar", "dumbbells", "kettlebell", "rope", "treadmill", "water"):
        assert f"case '{이름}':" in 만들기, 이름
    assert "grip('Left', a); grip('Right', b2);" in 만들기                                     # 손바닥 가운데를 잡는다
    assert "out.add(b.set(0, GRIP.along, 0).applyQuaternion(q));" in 만들기
    assert "new T.TubeGeometry(new T.CatmullRomCurve3(pts), 48, 0.008, 6, false)" in 만들기   # 줄넘기 줄은 손잡이 사이를 돈다
    assert "ctx.jump = { peak0:" in js                                                         # 뛰어오를 때 발밑을 지난다
    assert "if (gear.update) gear.update(clock.elapsedTime, action.time);" in js


def test_비슷한_동작으로_대신하는_것은_화면에_적는다():
    js = _js()
    근사 = js.split("const APPROX = {")[1].split("\n  };")[0]
    for id_ in ("knee-pushup", "deadlift", "shoulder-press", "one-leg"):
        assert f"'{id_}':" in 근사, id_
    assert "const note = CLIPS[id] ? (APPROX[id] || '') : GAP_NOTE;" in js
    assert "if (onNote) onNote(note);" in js
    html = _index()
    assert 'id="exercise3dSub"' in html
    보이기 = html.split("function show3dForStep(step)")[1].split("\n}")[0]
    assert "s.textContent = t || ''; s.hidden = !t;" in 보이기
    assert "MOVE_3D.start($('exercise3dCanvas'), pose, { onNote })" in 보이기


def test_빛과_그림자_카메라는_몸을_따라간다():
    js = _js().split("function setup(lib, me, clip)")[1].split("\n  }")[0]
    assert "renderer.shadowMap.enabled = true" in js and "ShadowMaterial" in js
    assert "new T.AnimationMixer(body)" in js and "mixer.clipAction(clip)" in js
    assert "prefers-reduced-motion: reduce" in js and "action.paused = true" in js
    assert "for (const b of boneList) { b.getWorldPosition(v); lo.min(v); hi.max(v); }" in js   # 뼈대 상자로 화면 맞춤
    assert "smoothAndGray(lib, body)" in js
    assert "if (h > 10) body.scale.setScalar(1 / h * 1.8);" in js                          # cm 로 오면 사람 키로


def test_플레이어에_붙어_있고_출처를_적는다():
    html = _index()
    assert html.index('src="js/move-art.js"') < html.index('src="js/move-3d.js"')
    assert 'id="exercise3d"' in html and 'id="exercise3dCanvas"' in html
    assert "*해당하는 영상이 없어 3D 동작으로 대체했습니다. (캐릭터·동작: Mixamo)" in html


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
    assert "me.renderer.dispose(); me.renderer.forceContextLoss();" in 멈춤
