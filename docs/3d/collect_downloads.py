"""크롬이 Downloads 에 받은 Mixamo FBX(제품 이름) 를 동작 id 이름으로 옮긴다.

  python collect_downloads.py <dest_dir> [제품이름=id ...]

"Male Sitting Pose" 처럼 제품 이름이 같은 동작은  "Male Sitting Pose=sit-reach"  식으로 그때그때 알려 준다.
최근 1시간 안에 받은 파일만 옮긴다.
"""
import re, shutil, sys, time
from pathlib import Path
DL = Path.home() / "Downloads"; dest = Path(sys.argv[1]); dest.mkdir(parents=True, exist_ok=True)   # 경로 하드코딩 대신 홈 폴더 기준
NAMES = {"T-Pose": "tpose", "Air Squat": "squat", "Push Up": "pushup", "Plank": "plank", "Situps": "crunch", "Burpee": "burpee",
         "Back Squat": "barbell-squat", "Bicep Curl": "dumbbell-curl", "Kettlebell Swing": "kettlebell-swing", "Jumping Rope": "jump-rope",
         "Ascending Stairs": "stair", "Swimming": "swim", "Arm Stretching": "shoulder-stretch", "Neck Stretching": "neck-stretch",
         "Breathing Idle": "deep-breath", "Treadmill Running": "treadmill", "Sumo High Pull": "deadlift", "Front Raises": "shoulder-press",
         "Standard Walk": "walk", "Running": "run", "Pistol": "one-leg", "Idle": "idle", "Lying Down": "lying", "Kneeling": "kneel"}
for a in sys.argv[2:]:
    k, v = a.split("="); NAMES[k] = v
recent = time.time() - 3600
moved = []
for f in sorted(DL.glob("*.fbx"), key=lambda p: p.stat().st_mtime):
    if f.stat().st_mtime < recent:
        continue
    m = re.match(r"^(.*?)(?: \((\d+)\))?\.fbx$", f.name)
    base = m.group(1)
    if base not in NAMES:
        print("skip", f.name); continue
    target = dest / f"{NAMES[base]}.fbx"
    shutil.move(str(f), str(target)); moved.append((f.name, target.name, target.stat().st_size))
for a, b, s in moved:
    print(f"{a} -> {b} {s}")
print("total", len(moved), "in", dest, ":", len(list(dest.glob('*.fbx'))))
