"""Blender 사람 기본형 번들에서 사실체 몸(남·여)을 꺼내 다리를 늘리고 리깅용 OBJ 와 미리보기 GLB 를 낸다.

  blender -b human_base_meshes_bundle.blend --python blender_export_body.py -- <out_dir> <leg_k>
    leg_k: 다리(발목~사타구니)를 몇 배로 늘릴지 (앱은 0.12)

<out_dir>/{m,f}_long.obj 가 Mixamo 자동 리깅에 올리는 파일이다. *_long_hair.* 는 머리카락(남 숏컷·여 포니테일)을
붙인 버전인데 앱은 쓰지 않는다(리뷰에서 뺐다). 번들: https://www.blender.org/download/demo-files/ 의 Human Base Meshes (CC0).
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
out = Path(args[0]); out.mkdir(parents=True, exist_ok=True)
LEG_K = float(args[1]) if len(args) > 1 else 0.08


def select(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False); o.hide_viewport = False; o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def body_copy(S):
    """멀티레졸루션 0단계로 굳힌 몸 복사본 (변환 적용, 발이 z=0, 가운데)."""
    src = bpy.data.objects[f"GEO-body_{S}_realistic"]
    for m in src.modifiers:
        if m.type == "MULTIRES":
            m.levels = 0; m.render_levels = 0
    select([src])
    bpy.ops.object.duplicate()
    obj = bpy.context.active_object
    obj.name = f"body_{S}"
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    xs = [v.co.x for v in obj.data.vertices]; ys = [v.co.y for v in obj.data.vertices]; zs = [v.co.z for v in obj.data.vertices]
    dx, dy, dz = -(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs)
    for v in obj.data.vertices:
        v.co.x += dx; v.co.y += dy; v.co.z += dz
    return obj


def lengthen_legs(obj, k):
    me = obj.data
    zs = [v.co.z for v in me.vertices]; H = max(zs)
    crotch = 0.47 * H                                            # 사타구니 (Mixamo 관절 기준 허벅지 뿌리 0.56H 보다 조금 아래)
    ankle = 0.06 * H
    extra = k * (crotch - ankle)
    for v in me.vertices:
        if v.co.z > ankle:
            t = min(1.0, (v.co.z - ankle) / (crotch - ankle))
            v.co.z += extra * t
    print(f"LEGS {obj.name}: crotch {crotch:.3f} extra {extra:.3f} height {H:.3f} -> {H + extra:.3f}")
    return extra


def head_metrics(obj):
    zs = [v.co.z for v in obj.data.vertices]; H = max(zs); z_top = H
    head = [v for v in obj.data.vertices if v.co.z > z_top - 0.13 * H]
    cx = sum(v.co.x for v in head) / len(head)
    cy = sum(v.co.y for v in head) / len(head)
    y_back = max(v.co.y for v in head if v.co.z > z_top - 0.10 * H)
    return H, z_top, cx, cy, y_back


def make_cap(obj, S, style):
    """두피 면을 복제해 머리선으로 갈수록 두께가 0이 되는 매끈한 볼륨을 얹는다 — 턱이 생기지 않고 피부에 녹아든다."""
    import heapq
    H, z_top, cx, cy, y_back = head_metrics(obj)
    hair_front = 0.05 if style == "short" else 0.045              # 앞머리 선: 정수리에서 아래로 (m)
    hair_back = 0.12 if style == "short" else 0.13                 # 뒤: 목덜미까지
    thick = 0.022 if style == "short" else 0.026                   # 가운데 두께
    falloff = 0.045                                                # 머리선에서 이만큼 안쪽까지 두께가 오른다
    me = obj.data
    bm = bmesh.new(); bm.from_mesh(me)

    def on_scalp(v):
        dz = z_top - v.co.z
        if dz > 0.15 or dz < 0:
            return False
        front = (v.co.y - cy) < -0.015                           # 얼굴 쪽(-Y)
        side = abs(v.co.x - cx)
        if side > 0.062 and 0.045 < dz < 0.105:                  # 귀는 뺀다
            return False
        if front:
            return dz < hair_front + 0.012 * (side / 0.06) ** 2   # 관자놀이 쪽은 조금 더 내려온다
        return dz < hair_back
    # 1) 머리 전체를 떼어 두 번 잘게 나눈다 (머리선 계단이 잘아지게)
    head_faces = [f for f in bm.faces if all(0 <= z_top - v.co.z < 0.17 for v in f.verts)]
    hh = bmesh.new(); vm0 = {}
    for f in head_faces:
        vs = []
        for v in f.verts:
            if v.index not in vm0:
                vm0[v.index] = hh.verts.new(v.co)
            vs.append(vm0[v.index])
        try:
            hh.faces.new(vs)
        except ValueError:
            pass
    for _ in range(2):
        bmesh.ops.subdivide_edges(hh, edges=hh.edges[:], cuts=1, use_grid_fill=True, smooth=0.5)
    hh.normal_update()
    # 2) 잘게 나뉜 머리에서 두피 면만 고른다
    faces = [f for f in hh.faces if all(on_scalp(v) for v in f.verts)]
    hb = bmesh.new(); vmap = {}
    for f in faces:
        vs = []
        for v in f.verts:
            if v.index not in vmap:
                vmap[v.index] = hb.verts.new(v.co)
            vs.append(vmap[v.index])
        try:
            hb.faces.new(vs)
        except ValueError:
            pass
    hh.free()
    hb.verts.ensure_lookup_table(); hb.edges.ensure_lookup_table()
    hb.normal_update()
    # 경계(열린 모서리)에서의 거리 — 다익스트라
    dist = {v.index: float("inf") for v in hb.verts}
    heap = []
    for e in hb.edges:
        if e.is_boundary:
            for v in e.verts:
                dist[v.index] = 0.0; heap.append((0.0, v.index))
    heapq.heapify(heap)
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist[i]:
            continue
        v = hb.verts[i]
        for e in v.link_edges:
            o = e.other_vert(v); nd = d + (o.co - v.co).length
            if nd < dist[o.index]:
                dist[o.index] = nd; heapq.heappush(heap, (nd, o.index))
    # 부드러운 법선(이웃 평균)으로 밀어낸다
    for v in hb.verts:
        t = min(1.0, dist[v.index] / falloff); t = t * t * (3 - 2 * t)
        n = v.normal.copy()
        for e in v.link_edges:
            n += e.other_vert(v).normal
        n.normalize()
        v.co = v.co + n * (0.004 + thick * t)                  # 머리선에 4~5mm 얕은 단 — 머리카락으로 읽힌다 (세분화로 조금 줄어드는 것 감안)
    hme = bpy.data.meshes.new(f"hair_{S}"); hb.to_mesh(hme); hb.free(); bm.free()
    hair = bpy.data.objects.new(f"hair_{S}", hme)
    bpy.context.scene.collection.objects.link(hair)
    for p in hme.polygons:
        p.use_smooth = True
    ss = hair.modifiers.new("subsurf", "SUBSURF"); ss.levels = 1; ss.render_levels = 1      # 머리선을 부드러운 곡선으로
    ss.boundary_smooth = "ALL"                                                            # 가장자리 모서리도 둥글게
    print(f"HAIR {S} {style}: faces {len(faces)}")
    return hair, (H, z_top, cx, cy, y_back)


def make_ponytail(S, metrics):
    H, z_top, cx, cy, y_back = metrics
    base = Vector((cx, y_back - 0.005, z_top - 0.085))
    tilt = math.radians(28)
    d = Vector((0, math.sin(tilt), -math.cos(tilt)))            # 아래·뒤로
    depth = 0.30
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.030, radius2=0.010, depth=depth,
                                    location=base + d * (depth / 2), rotation=(math.pi + tilt, 0, 0))
    tail = bpy.context.active_object; tail.name = f"tail_{S}"
    for p in tail.data.polygons:
        p.use_smooth = True
    bend = tail.modifiers.new("bend", "SIMPLE_DEFORM"); bend.deform_method = "BEND"; bend.angle = math.radians(35); bend.deform_axis = "X"
    bpy.ops.mesh.primitive_torus_add(major_radius=0.024, minor_radius=0.005, location=base + d * 0.03, rotation=(math.pi / 2 + tilt, 0, 0))
    tie = bpy.context.active_object; tie.name = f"tie_{S}"
    for p in tie.data.polygons:
        p.use_smooth = True
    return [tail, tie]


def export(objs, name):
    select(objs)
    bpy.ops.export_scene.gltf(filepath=str(out / f"{name}.glb"), export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_materials="NONE", export_texcoords=False, export_normals=True,
                              export_skins=False, export_animations=False, export_morph=False)
    bpy.ops.wm.obj_export(filepath=str(out / f"{name}.obj"), export_selected_objects=True, apply_modifiers=True,
                          export_triangulated_mesh=True, export_normals=True, export_uv=True, export_materials=False,
                          forward_axis="NEGATIVE_Z", up_axis="Y", global_scale=1.0)
    print("EXPORTED", name)


for sex, S, style in (("m", "male", "short"), ("f", "female", "pony")):
    body = body_copy(S)
    lengthen_legs(body, LEG_K)
    export([body], f"{sex}_long")
    cap, metrics = make_cap(body, S, style)
    parts = [cap] + (make_ponytail(S, metrics) if style == "pony" else [])
    export([body] + parts, f"{sex}_long_hair")
