"""GLB 에서 법선·UV 를 뗀다 — 앱이 법선을 다시 계산하니 필요 없고, 떼야 gltfpack 이 같은 자리 꼭짓점을 합쳐 파일이 4배 작아진다.

  python strip_attrs.py <in.glb> <out.glb>
"""
import json
import struct
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
b = src.read_bytes()
n = struct.unpack("<I", b[12:16])[0]
j = json.loads(b[20:20 + n])
for m in j["meshes"]:
    for p in m["primitives"]:
        for k in ("NORMAL", "TEXCOORD_0", "TANGENT"):
            p["attributes"].pop(k, None)
js = json.dumps(j, separators=(",", ":")).encode()
while len(js) % 4:
    js += b" "
rest = b[20 + n:]                                                 # BIN 덩이 (헤더 포함)
out = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + len(rest)) + struct.pack("<II", len(js), 0x4E4F534A) + js + rest
dst.write_bytes(out)
print("wrote", dst, len(out))
