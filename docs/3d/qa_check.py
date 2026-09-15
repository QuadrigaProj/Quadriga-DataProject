"""3D 동작 검사 2단계 — qa_sample.js 가 뽑은 관절·기구 자리로
  (1) 관절이 사람 관절처럼 꺾였는지 (무릎·팔꿈치가 거꾸로·옆으로 꺾이지 않았는지, 고관절·발목·손목·목·허리가 한계 안인지),
  (2) 몸끼리, 몸과 기구가 서로 뚫고 지나가지 않는지 (닿는 건 괜찮다)
검사한다. 한계값의 근거는 docs/3d-joint-kinematics.md.

    python docs/3d/qa_check.py <qa 폴더> [--sheets] [--only id,id,...]

결과: 화면에 동작별 위반 목록, <qa 폴더>/report.json, --sheets 면 <qa 폴더>/sheets/<성별>_<동작>.jpg (위반 프레임에 빨간 테두리).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

B = ""                # 뼈 이름은 접두어(mixamorig, :)를 뗀 것으로 맞춘다 — GLTFLoader 가 ':' 를 지운다


def short(name: str) -> str:
    return name.replace("mixamorig", "").replace(":", "")
TOL_BODY = 0.025      # 몸끼리 이만큼(m)까지 겹치는 건 '닿음'으로 본다
TOL_HAND = 0.035      # 손은 허리·머리·허벅지에 얹는 동작이 많아 조금 더 너그럽게
TOL_GEAR = 0.03       # 기구에 앉거나 기대는 건 닿음
TOL_FLOOR = 0.045     # 누우면 등이 눌린다 (여성 몸통은 앞뒤 두께가 더 커서 조금 더)

# ---------- 작은 수학 ----------
def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def ang(a, b) -> float:
    """두 방향 사이 각(도)."""
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(unit(a), unit(b)))))))


def qrot(q, v):
    """사원수 [x,y,z,w] 로 벡터를 돌린다."""
    x, y, z, w = q
    vx, vy, vz = v
    tx = 2 * (y * vz - z * vy)
    ty = 2 * (z * vx - x * vz)
    tz = 2 * (x * vy - y * vx)
    return np.array([vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx)])


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz])


def qinv(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def seg_dist(p1, q1, p2, q2):
    """두 선분 사이 가장 가까운 두 점 (c1 on 1, c2 on 2) 과 거리."""
    d1 = q1 - p1; d2 = q2 - p2; r = p1 - p2
    a = float(np.dot(d1, d1)); e = float(np.dot(d2, d2)); f = float(np.dot(d2, r))
    if a < 1e-12 and e < 1e-12:
        return p1, p2, float(np.linalg.norm(r))
    if a < 1e-12:
        s = 0.0; t = max(0.0, min(1.0, f / e))
    else:
        c = float(np.dot(d1, r))
        if e < 1e-12:
            t = 0.0; s = max(0.0, min(1.0, -c / a))
        else:
            b = float(np.dot(d1, d2)); den = a * e - b * b
            s = max(0.0, min(1.0, (b * f - c * e) / den)) if den > 1e-12 else 0.0
            t = (b * s + f) / e
            if t < 0:
                t = 0.0; s = max(0.0, min(1.0, -c / a))
            elif t > 1:
                t = 1.0; s = max(0.0, min(1.0, (b - c) / a))
    c1 = p1 + d1 * s; c2 = p2 + d2 * t
    return c1, c2, float(np.linalg.norm(c1 - c2))


def point_seg_dist(p, a, b):
    d = b - a; L2 = float(np.dot(d, d))
    s = max(0.0, min(1.0, float(np.dot(p - a, d)) / L2)) if L2 > 1e-12 else 0.0
    c = a + d * s
    return c, float(np.linalg.norm(p - c))


# ---------- 프레임 하나 ----------
class Frame:
    def __init__(self, data: dict, rest: dict, radii: dict):
        self.J = {short(k): (np.array(v[:3]), np.array(v[3:])) for k, v in data["joints"].items()}
        self.rest = {short(k): np.array(v) for k, v in rest.items()}
        self.radii = {short(k): v for k, v in radii.items()}
        self.gear = data.get("gear", [])

    def has(self, n): return (B + n) in self.J
    def P(self, n): return self.J[B + n][0]
    def Q(self, n): return self.J[B + n][1]
    def Q0(self, n): return self.rest[B + n]

    def rotdir(self, n, d0):
        """T 자세(rest)에서 세상 방향 d0 였던 것이 지금 어느 방향인가 — 뼈의 회전을 따라간다."""
        return qrot(qmul(self.Q(n), qinv(self.Q0(n))), np.array(d0, dtype=float))

    def restdir(self, n):
        return qrot(self.Q0(n), np.array([0.0, 1.0, 0.0]))

    def seg(self, a, b): return self.P(b) - self.P(a)

    def rad(self, n, i=0):
        r = self.radii.get(B + n)
        return float(r[i]) if r else 0.05


# ---------- 관절 검사 ----------
def check_joints(F: Frame) -> list[tuple[str, str, float, str]]:
    """(규칙, 부위, 값, 설명) 목록. 값은 도(°)."""
    out = []
    hip_up = F.rotdir("Hips", [0, 1, 0]); hip_front = F.rotdir("Hips", [0, 0, 1]); hip_left = F.rotdir("Hips", [1, 0, 0])
    for side, sgn in (("Left", 1.0), ("Right", -1.0)):
        # 무릎: 굽힘 각과 굽는 방향 (허벅지 뼈 기준 '뒤'가 굽는 쪽)
        thigh = unit(F.seg(side + "UpLeg", side + "Leg")); shank = unit(F.seg(side + "Leg", side + "Foot"))
        flex = ang(thigh, shank)
        if flex > 150:
            out.append(("KNEE_OVER", side, flex, "무릎이 너무 접혔다 (>150°)"))
        perp = shank - thigh * float(np.dot(shank, thigh))
        if np.linalg.norm(perp) > math.sin(8 * math.pi / 180):
            bend = unit(perp)
            back = F.rotdir(side + "UpLeg", [0, 0, -1]); lat = F.rotdir(side + "UpLeg", [1, 0, 0])
            a = float(np.dot(bend, back)); l = abs(float(np.dot(bend, lat)))
            if a < -0.5:
                out.append(("KNEE_BACK", side, flex, "무릎이 뒤로 꺾였다 (과신전)"))
            elif l > 0.6 and flex > 12:
                out.append(("KNEE_SIDE", side, flex, "무릎이 옆으로 꺾였다 (허벅지 방향과 안 맞음)"))
        # 고관절: 골반 기준 굽힘·폄·벌림·모음
        d = thigh
        flex_hip = math.degrees(math.atan2(float(np.dot(d, hip_front)), float(np.dot(d, -hip_up))))
        abd = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(d, hip_left)) * sgn))))
        if flex_hip > 140:                                                 # 앉아 웅크리면(로잉 캐치) 135° 가까이 간다
            out.append(("HIP_FLEX", side, flex_hip, "고관절이 너무 굽혔다 (>140°)"))
        if flex_hip < -35:
            out.append(("HIP_EXT", side, -flex_hip, "고관절이 너무 뒤로 폈다 (>35°)"))
        if abd > 55:
            out.append(("HIP_ABD", side, abd, "다리를 너무 벌렸다 (>55°)"))
        if abd < -40:
            out.append(("HIP_ADD", side, -abd, "다리가 몸 가운데를 지나 너무 모였다 (>40°)"))
        # 발목: T 자세의 정강이–발 각도를 기준으로 발등 굽힘·발바닥 굽힘, 옆으로 꺾임
        if F.has(side + "ToeBase"):
            foot = unit(F.seg(side + "Foot", side + "ToeBase"))
            a0 = ang(F.restdir(side + "Leg"), F.restdir(side + "Foot")); a = ang(shank, foot)
            if a - a0 > 40:
                out.append(("ANKLE_DORSI", side, a - a0, "발등을 너무 당겼다 (>40°)"))
            if a0 - a > 55:
                out.append(("ANKLE_PLANTAR", side, a0 - a, "발끝을 너무 폈다 (>55°)"))
            lat_s = F.rotdir(side + "Leg", [1, 0, 0])
            side_a = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(foot, lat_s))))))
            if abs(side_a) > 30:
                out.append(("ANKLE_SIDE", side, abs(side_a), "발이 옆으로 꺾였다 (>30°)"))
        # 팔꿈치: 굽힘 각과 굽는 방향 (위팔 뼈 기준 '앞'이 굽는 쪽)
        upper = unit(F.seg(side + "Arm", side + "ForeArm")); fore = unit(F.seg(side + "ForeArm", side + "Hand"))
        eflex = ang(upper, fore)
        if eflex > 150:
            out.append(("ELBOW_OVER", side, eflex, "팔꿈치가 너무 접혔다 (>150°)"))
        perp = fore - upper * float(np.dot(fore, upper))
        if np.linalg.norm(perp) > math.sin(8 * math.pi / 180):
            bend = unit(perp)
            front = F.rotdir(side + "Arm", [0, 0, 1]); lat = F.rotdir(side + "Arm", [0, 1, 0])
            a = float(np.dot(bend, front)); l = abs(float(np.dot(bend, lat)))
            if a < -0.5:
                out.append(("ELBOW_BACK", side, eflex, "팔꿈치가 거꾸로 꺾였다"))
            elif l > 0.6 and eflex > 12:
                out.append(("ELBOW_SIDE", side, eflex, "팔꿈치가 옆으로 꺾였다 (위팔 방향과 안 맞음)"))
        # 손목
        mid = side + "HandMiddle1"
        if F.has(mid):
            hand = unit(F.seg(side + "Hand", mid)); w = ang(fore, hand)
            if w > 95:                                                  # 푸시업처럼 바닥을 짚으면 90° 가까이 꺾인다
                out.append(("WRIST", side, w, "손목이 너무 꺾였다 (>95°)"))
        # 어깨: 팔이 등 뒤로
        s2_front = F.rotdir("Spine2", [0, 0, 1])
        if float(np.dot(upper, -s2_front)) > 0.87:
            out.append(("SHOULDER_BACK", side, math.degrees(math.asin(float(np.dot(upper, -s2_front)))), "팔이 등 뒤로 꺾였다"))
    # 허리: 골반 '위' 와 척추 방향
    spine = unit(F.seg("Spine", "Neck"))
    bend = ang(hip_up, spine)
    if bend > 75:
        out.append(("SPINE_BEND", "", bend, "허리가 골반에 대해 너무 꺾였다 (>75°)"))
    side_b = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(spine, hip_left))))))
    if abs(side_b) > 40:
        out.append(("SPINE_SIDE", "", abs(side_b), "허리가 옆으로 너무 꺾였다 (>40°)"))
    # 목
    if F.has("HeadTop_End"):
        s2 = unit(F.seg("Spine2", "Neck")); head = unit(F.seg("Head", "HeadTop_End"))
        nb = ang(s2, head)
        if nb > 60:
            out.append(("NECK_BEND", "", nb, "목이 너무 꺾였다 (>60°)"))
        hf = F.rotdir("Head", [0, 0, 1]); sf = F.rotdir("Spine2", [0, 0, 1])
        hf = hf - head * float(np.dot(hf, head)); sf = sf - head * float(np.dot(sf, head))
        if np.linalg.norm(hf) > 0.2 and np.linalg.norm(sf) > 0.2:
            tw = ang(hf, sf)
            if tw > 80:
                out.append(("NECK_TWIST", "", tw, "머리가 너무 돌아갔다 (>80°)"))
    return out


# ---------- 관통 검사 ----------
class Cap:
    def __init__(self, name, a, b, r, rx=None, rz=None, lat=None, front=None):
        self.name = name; self.a = a; self.b = b; self.r = r
        self.rx = rx; self.rz = rz; self.lat = lat; self.front = front   # 몸통: 타원 단면

    def radius_toward(self, n):
        """n 방향으로의 살 두께 (몸통은 옆·앞뒤가 달라 타원으로)."""
        if self.rx is None:
            return self.r
        axis = unit(self.b - self.a)
        p = n - axis * float(np.dot(n, axis))
        if np.linalg.norm(p) < 1e-6:
            return min(self.rx, self.rz)
        p = unit(p)
        nl = float(np.dot(p, self.lat)); nf = float(np.dot(p, self.front))
        den = math.sqrt((self.rz * nl) ** 2 + (self.rx * nf) ** 2)
        return self.rx * self.rz / den if den > 1e-9 else min(self.rx, self.rz)


def capsules(F: Frame) -> dict[str, Cap]:
    C = {}
    for side in ("Left", "Right"):
        C[side + "Thigh"] = Cap(side + "Thigh", F.P(side + "UpLeg"), F.P(side + "Leg"), F.rad(side + "UpLeg"))
        C[side + "Shank"] = Cap(side + "Shank", F.P(side + "Leg"), F.P(side + "Foot"), F.rad(side + "Leg"))
        if F.has(side + "ToeBase"):
            C[side + "Foot"] = Cap(side + "Foot", F.P(side + "Foot"), F.P(side + "ToeBase"), F.rad(side + "Foot"))
        C[side + "UpperArm"] = Cap(side + "UpperArm", F.P(side + "Arm"), F.P(side + "ForeArm"), F.rad(side + "Arm"))
        C[side + "ForeArm"] = Cap(side + "ForeArm", F.P(side + "ForeArm"), F.P(side + "Hand"), F.rad(side + "ForeArm"))
        tip = F.P(side + "HandMiddle1") if F.has(side + "HandMiddle1") else F.P(side + "Hand") + unit(F.seg(side + "ForeArm", side + "Hand")) * 0.08
        C[side + "Hand"] = Cap(side + "Hand", F.P(side + "Hand"), tip, F.rad(side + "Hand"))
    C["Pelvis"] = Cap("Pelvis", F.P("Hips"), F.P("Spine1"), F.rad("Hips"), F.rad("Hips", 1), F.rad("Hips", 2), F.rotdir("Hips", [1, 0, 0]), F.rotdir("Hips", [0, 0, 1]))
    C["Chest"] = Cap("Chest", F.P("Spine1"), F.P("Spine2") + (F.P("Neck") - F.P("Spine2")) * 0.5, F.rad("Spine1"), F.rad("Spine1", 1), F.rad("Spine1", 2), F.rotdir("Spine2", [1, 0, 0]), F.rotdir("Spine2", [0, 0, 1]))
    if F.has("HeadTop_End"):
        c = F.P("Head") + (F.P("HeadTop_End") - F.P("Head")) * 0.5
        C["Head"] = Cap("Head", c, c, 0.10)
    return C


PAIRS = []
for s, o in (("Left", "Right"), ("Right", "Left")):
    PAIRS += [(s + "Thigh", o + "Thigh", 0.05), (s + "Shank", o + "Shank", TOL_BODY), (s + "Thigh", o + "Shank", TOL_BODY),
              (s + "Foot", o + "Foot", 0.05), (s + "Foot", o + "Shank", 0.03), (s + "Foot", o + "Thigh", 0.03),
              (s + "UpperArm", o + "UpperArm", 0.02), (s + "ForeArm", o + "ForeArm", 0.05), (s + "ForeArm", o + "UpperArm", 0.05),
              (s + "Hand", o + "ForeArm", 0.07), (s + "Hand", o + "UpperArm", 0.07)]   # 한 손이 다른 팔을 잡는 동작(어깨 스트레칭)
for s in ("Left", "Right"):
    for t in ("Pelvis", "Chest"):
        PAIRS += [(s + "UpperArm", t, 0.06), (s + "ForeArm", t, 0.04), (s + "Hand", t, 0.07)]   # 손을 허리·가슴에 얹는 동작은 살이 눌린다, 위팔은 가슴 옆에 붙는다
        if t == "Chest":
            PAIRS.append((s + "Thigh", t, TOL_BODY))
    PAIRS += [(s + "ForeArm", "Head", TOL_BODY), (s + "Hand", "Head", TOL_HAND), (s + "UpperArm", "Head", TOL_BODY),
              (s + "Thigh", "Head", TOL_BODY), (s + "Shank", "Head", TOL_BODY), (s + "Foot", "Head", 0.02)]
    for lo in ("Thigh", "Shank", "Foot"):
        for o in ("Left", "Right"):
            PAIRS += [(s + "ForeArm", o + lo, 0.05), (s + "Hand", o + lo, 0.05), (s + "UpperArm", o + lo, 0.05)]   # 팔·손은 허벅지를 스치는 동작이 많다
PAIRS = list(dict.fromkeys(PAIRS))


def pair_depth(c1: Cap, c2: Cap) -> float:
    p, q, d = seg_dist(c1.a, c1.b, c2.a, c2.b)
    n = p - q
    r1 = c1.radius_toward(-n) if c1.rx is not None else c1.r
    r2 = c2.radius_toward(n) if c2.rx is not None else c2.r
    return r1 + r2 - d


def check_penetration(F: Frame) -> list[tuple[str, str, float, str]]:
    out = []
    C = capsules(F)
    for a, b, tol in PAIRS:
        if a not in C or b not in C:
            continue
        depth = pair_depth(C[a], C[b])
        if depth > tol:
            out.append(("PEN_BODY", f"{a}-{b}", depth * 100, "몸끼리 겹친다 (cm)"))
    # 기구
    body_caps = [c for n, c in C.items() if not n.endswith("Hand") and not n.endswith("Foot")]
    for gi, g in enumerate(F.gear):
        worst = 0.0; where = ""
        if g.get("obb"):
            m = np.array(g["obb"]["m"], dtype=float).reshape(4, 4).T          # three.js 는 열 우선
            inv = np.linalg.inv(m); mn = np.array(g["obb"]["min"]); mx = np.array(g["obb"]["max"])
            for c in body_caps:
                r = min(c.rx, c.rz) if c.rx is not None else c.r
                if c.name in ("Pelvis", "LeftThigh", "RightThigh"):
                    r -= 0.06                                               # 앉으면 살이 눌린다
                for s in np.linspace(0, 1, 7):
                    p = c.a + (c.b - c.a) * s
                    lp = (inv @ np.array([p[0], p[1], p[2], 1.0]))[:3]
                    over = np.maximum(np.maximum(mn - lp, 0), lp - mx)
                    d = float(np.linalg.norm(over))
                    if d == 0.0:
                        d = -float(np.min(np.minimum(lp - mn, mx - lp)))          # 안에 있으면 음수
                    depth = r - d
                    if depth > worst:
                        worst = depth; where = c.name
        else:
            for pt in g.get("pts", []):
                p = np.array(pt, dtype=float)
                for c in body_caps:
                    cp, d = point_seg_dist(p, c.a, c.b)
                    r = c.radius_toward(p - cp) if c.rx is not None else c.r
                    depth = r - d
                    if depth > worst:
                        worst = depth; where = c.name
        if worst > TOL_GEAR:
            out.append(("PEN_GEAR", f"{g['kind']}#{gi}-{where}", worst * 100, "기구가 몸을 뚫는다 (cm)"))
    # 바닥
    for name, (p, q) in F.J.items():
        lim = -0.05 if ("Foot" in name or "Toe" in name) else -0.04 if "Hand" in name else -0.02
        if p[1] < lim:
            out.append(("FLOOR", name, -p[1] * 100, "바닥 아래로 내려갔다 (cm)"))
    down = np.array([0.0, -1.0, 0.0])
    for n, c in C.items():
        if n.endswith("Foot") or n.endswith("Hand"):
            continue
        r = c.radius_toward(down) if c.rx is not None else c.r
        for p in (c.a, c.b):
            if p[1] - r < -TOL_FLOOR:
                out.append(("FLOOR_BODY", n, (r - p[1]) * 100, "살이 바닥을 뚫는다 (cm)"))
                break
    return out


# ---------- 봐주는 것 ---------- (동작 글롭, "규칙 부위" 글롭): 모션캡처에서 손·팔이 허벅지를 스치거나 누운 팔이 가슴 옆에 닿는 것처럼
# 사람이 실제로 하는 접촉. 새 동작을 검사할 때 여기 없는 것만 보면 된다.
import fnmatch
ALLOW = [
    ("burpee", "PEN_BODY *-*Thigh"), ("burpee", "PEN_BODY *-*Shank"), ("burpee", "PEN_BODY *Thigh-Chest"), ("burpee", "HIP_FLEX *"),   # 웅크렸다 손 짚을 때 손·팔이 다리를 스치고 가슴이 허벅지에 닿는다
    ("kettlebell-swing", "PEN_BODY *-*Thigh"), ("walk", "PEN_BODY *-*Thigh"), ("squat", "PEN_BODY *Hand-*Thigh"),
    ("jump-rope", "PEN_BODY *Foot-*Shank"), ("treadmill", "PEN_BODY *Foot-*Shank"), ("run", "PEN_BODY *Thigh-*Shank"),
    ("swim", "FLOOR*"),                                                             # 물속 — 바닥이 없다
    ("*", "PEN_BODY *UpperArm-Chest"),                                              # 위팔은 가슴 옆에 붙는다 (6cm 까지는 아래 tol 로, 그 이상만 잡히면 여기서)
    ("crunch", "PEN_BODY *Hand-Chest"),                                             # 머리 뒤에 댄 손이 목·어깨에 닿는다
    ("rowing", "HIP_FLEX *"), ("rowing", "PEN_BODY *Thigh-Chest"), ("leg-press", "PEN_BODY *Thigh-Chest"),   # 웅크리면 가슴이 허벅지에 닿는다
]


def allowed(motion: str, key: str) -> bool:
    return any(fnmatch.fnmatch(motion, m) and fnmatch.fnmatch(key, k) for m, k in ALLOW)


# ---------- 실행 ----------
def run(folder: Path, only: set[str] | None, sheets: bool):
    report = {}
    files = sorted(folder.glob("*.json"))
    for f in files:
        if f.name == "report.json":
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        if only and d["id"] not in only:
            continue
        key = f"{d['sex']}_{d['id']}"
        found: dict[str, dict] = {}
        for i, fr in enumerate(d["frames"]):
            F = Frame(fr, d["rest"], d["radii"])
            for rule, part, val, msg in check_joints(F) + check_penetration(F):
                k = f"{rule} {part}".strip()
                if allowed(d["id"], k):
                    continue
                e = found.setdefault(k, {"rule": rule, "part": part, "msg": msg, "max": 0.0, "frames": []})
                e["max"] = max(e["max"], val); e["frames"].append(i)
        report[key] = {"id": d["id"], "sex": d["sex"], "n": len(d["frames"]), "issues": found}
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = []
    bad = 0
    for key, r in report.items():
        if not r["issues"]:
            continue
        bad += 1
        lines.append(f"== {key}")
        for k, e in sorted(r["issues"].items()):
            fr = e["frames"]; n = r["n"]
            span = f"{len(fr)}/{n} frames" if len(fr) < n else "all frames"
            lines.append(f"   {k:34s} max {e['max']:6.1f}  {span}  — {e['msg']}")
    lines.append(f"\n{bad}/{len(report)} 동작에 문제, 규칙: {sum(len(r['issues']) for r in report.values())}건")
    text = "\n".join(lines)
    (folder / "report.txt").write_text(text, encoding="utf-8")
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("utf-8", "replace").decode("ascii", "replace"))
    if sheets:
        make_sheets(folder, report)


def make_sheets(folder: Path, report: dict):
    from PIL import Image, ImageDraw
    out = folder / "sheets"; out.mkdir(exist_ok=True)
    for key, r in report.items():
        imgs = sorted(folder.glob(f"{key}_*.jpg"), key=lambda p: int(p.stem.rsplit("_", 1)[1]))
        if not imgs:
            continue
        n = r["n"]; per = n // len(imgs)
        W = 200; sheet = Image.new("RGB", (W * len(imgs), W + 34), (250, 250, 244)); dr = ImageDraw.Draw(sheet)
        for i, p in enumerate(imgs):
            im = Image.open(p).convert("RGB").resize((W, W)); sheet.paste(im, (i * W, 0))
            fi = i * per
            hits = [k for k, e in r["issues"].items() if fi in e["frames"]]
            if hits:
                dr.rectangle([i * W, 0, i * W + W - 1, W - 1], outline=(220, 40, 40), width=4)
            dr.text((i * W + 4, W + 2), f"{key} f{fi}", fill=(30, 30, 30))
            dr.text((i * W + 4, W + 16), ", ".join(h.split(" ")[0] for h in hits)[:40], fill=(200, 30, 30))
        sheet.save(out / f"{key}.jpg", quality=88)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(1)
    folder = Path(args[0])
    only = None
    if "--only" in args:
        only = set(args[args.index("--only") + 1].split(","))
    run(folder, only, "--sheets" in args)
