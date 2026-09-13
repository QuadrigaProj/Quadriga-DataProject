"""사실체 기본 몸의 사타구니를 마네킹처럼 매끈하게 다듬는다 (GLB 의 꼭짓점 좌표만 바꾼다).

리깅·스킨 가중치는 그대로 두고 POSITION 만 고치므로 Mixamo 동작은 그대로 붙는다.
법선은 앱이 불러올 때 다시 계산하니 여기서는 손대지 않는다.

python smooth_crotch.py <in.glb> <out.glb>
"""
import json
import struct
import sys
from pathlib import Path

import numpy as np

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
raw = bytearray(src.read_bytes())
json_len = struct.unpack_from("<I", raw, 12)[0]
j = json.loads(raw[20:20 + json_len])
bin_off = 20 + json_len + 8                       # BIN 덩이 시작 (헤더 8바이트 뒤)

CT = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def accessor(i):
    a = j["accessors"][i]
    bv = j["bufferViews"][a["bufferView"]]
    off = bin_off + bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    n = a["count"] * NC[a["type"]]
    arr = np.frombuffer(raw, dtype=CT[a["componentType"]], count=n, offset=off)
    return arr.reshape(a["count"], NC[a["type"]]), off


prim = j["meshes"][0]["primitives"][0]
P, p_off = accessor(prim["attributes"]["POSITION"])
P = P.astype(np.float64).copy()
I, _ = accessor(prim["indices"])
I = I.reshape(-1).astype(np.int64)
H = P[:, 1].max() - P[:, 1].min()

# 같은 자리의 꼭짓점(UV 이음새로 갈라진 것)은 한 점으로 본다
key = np.round(P / H, 6)
_, rep, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
inv = inv.reshape(-1)
U = P[rep]                                        # 대표 꼭짓점
tri = inv[I].reshape(-1, 3)

# 이웃 목록
nbr = [set() for _ in range(len(U))]
for a, b, c in tri:
    nbr[a].update((b, c)); nbr[b].update((a, c)); nbr[c].update((a, b))

# 다듬을 영역: 사타구니 앞쪽 (키 기준 비율). 관절 위치는 골반 0.587H, 허벅지 뿌리 0.561H 에서 잰 것.
y0, y1 = 0.43 * H, 0.565 * H
sel = (U[:, 1] > y0) & (U[:, 1] < y1) & (np.abs(U[:, 0]) < 0.05 * H) & (U[:, 2] > 0.015 * H)
idx = np.where(sel)[0]
print("smooth region verts", len(idx), "of", len(U))

# 경계는 고정하고 안쪽만 라플라시안으로 여러 번 평균 — 튀어나온 부분이 주변 곡면에 녹아든다
S = U.copy()
for it in range(80):
    new = S.copy()
    for v in idx:
        ns = list(nbr[v])
        if ns:
            new[v] = S[ns].mean(axis=0)
    S = new
moved = np.linalg.norm(S[idx] - U[idx], axis=1) / H
print("moved (rel. height): mean %.4f max %.4f" % (moved.mean(), moved.max()))
# 영역의 앞쪽 돌출이 얼마나 줄었는지
print("front z before %.4f after %.4f (rel. height)" % (U[idx][:, 2].max() / H, S[idx][:, 2].max() / H))

# 원래 배열(중복 포함)에 되돌려 쓴다
P2 = S[inv].astype(np.float32)
raw[p_off:p_off + P2.nbytes] = P2.tobytes()
# accessor 의 min/max 도 맞춘다
acc = j["accessors"][prim["attributes"]["POSITION"]]
acc["min"] = [float(x) for x in P2.min(axis=0)]
acc["max"] = [float(x) for x in P2.max(axis=0)]
js = json.dumps(j, separators=(",", ":")).encode("utf-8")
while len(js) % 4:
    js += b" "
body = raw[bin_off - 8:]                          # BIN 덩이 (헤더 포함)
out = bytearray()
out += b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + len(body))
out += struct.pack("<II", len(js), 0x4E4F534A) + js
out += body
dst.write_bytes(out)
print("wrote", dst, len(out))
