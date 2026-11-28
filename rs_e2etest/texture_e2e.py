"""E2E harness for the per-body ground texture pick. Checks and blind spots: texture.md.

Run from the plugin folder:  python rs_e2etest/texture_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt and sheet-<family>.png. Exit code 1 on a failure.

Two children with LOCALAPPDATA set to out/<timestamp>/, holding a sqlite backup
copy of the live db, each with its own PYTHONHASHSEED. Each prints the texture
file of every cached body; the two lists must match.
"""

import gzip
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
MIN_BODIES = 24         # a family with this many cached bodies must use all 6 variants


def child(out):
    sys.path.insert(0, PLUGIN)
    from PIL import Image
    from rs_core import coverage, database, grounds
    assert database.PATH.startswith(os.environ["LOCALAPPDATA"]), database.PATH

    fails = []
    families = sorted(set(coverage.TEXTURE_OF.values()) | {"rocky"})

    # 1. every variant file is there and loads as the shipped size
    for family in families:
        for n in range(1, coverage.TEXTURE_VARIANTS + 1):
            name = family if n == 1 else f"{family}-{n}"
            path = coverage.TEXTURE_DIR / f"{name}{coverage.TEXTURE_EXT}"
            try:
                with Image.open(path) as picture:
                    if picture.size != (1920, 1920) or picture.mode != "RGB":
                        fails.append(f"{path.name}: {picture.size} {picture.mode}")
            except OSError as err:
                fails.append(f"{path.name}: {err}")

    # 2. pick per real body; printed for the cross-process compare in main()
    with database.connect() as conn:
        bodies = [(name, grounds.reground(json.loads(data)))
                  for name, data in conn.execute("SELECT name, data FROM bodies ORDER BY name")]
    picks = {}
    for body, ground in bodies:
        name = coverage.texture_name(ground, body)
        if name is not None:
            picks[body] = name
            print(f"PICK\t{body}\t{name}")
    spread = {}
    for body, name in picks.items():
        family = name.rsplit("-", 1)[0] if name[-1].isdigit() else name
        spread.setdefault(family, Counter())[name] += 1
    for family in families:
        counts = spread.get(family, Counter())
        total = sum(counts.values())
        row = [counts.get(family if n == 1 else f"{family}-{n}", 0)
               for n in range(1, coverage.TEXTURE_VARIANTS + 1)]
        print(f"spread {family:12s} {total:4d} bodies, variants 1-6: {row}")
        if total >= MIN_BODIES and 0 in row:
            fails.append(f"{family}: {total} bodies, a variant never picked: {row}")
    if coverage.texture_name("icy", None) != "icy":
        fails.append("texture_name without a body is not variant 1")
    # formula and file naming, computed here without texture_name
    import zlib
    for body, ground in bodies[:40]:
        family = coverage.texture_name(ground)
        if family is None:
            continue
        n = zlib.crc32(body.encode("utf-8")) % 6 + 1
        want = family if n == 1 else f"{family}-{n}"
        if picks[body] != want:
            fails.append(f"{body}: pick {picks[body]}, crc32 % 6 + 1 gives {want}")

    # 2b. a missing variant file falls back to variant 1, not plain ground
    import shutil
    import tempfile
    real_dir = coverage.TEXTURE_DIR
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        shutil.copy(real_dir / f"rocky{coverage.TEXTURE_EXT}", tmp)
        coverage.TEXTURE_DIR = type(real_dir)(tmp)
        body = next(b for b, name in picks.items() if name.startswith("rocky-") and name[-1].isdigit()
                    and not name.startswith(("rocky-ice", "rocky-metal")))
        coverage._textures.clear()
        got = coverage._texture("rock 80%+ [none]", 64, body)
        with Image.open(real_dir / f"rocky{coverage.TEXTURE_EXT}") as base:
            want = base.convert("RGB").resize((64, 64), Image.BICUBIC)
        if got is None or got.tobytes() != want.tobytes():
            fails.append(f"{body}: missing {picks[body]} did not fall back to rocky.jpg")
        else:
            print(f"fallback: {picks[body]} missing -> rocky.jpg")
        coverage.TEXTURE_DIR = real_dir
        coverage._textures.clear()

    # 3. live layer and saved picture of the same map load the same file
    seen = []
    real = coverage._texture

    def spy(ground, size, body=None):
        seen.append(coverage.texture_name(ground, body))
        return real(ground, size, body)

    coverage._texture = spy
    ground_of = dict(bodies)
    with database.connect() as conn:
        maps = [(body, name, json.loads(gzip.decompress(raw)))
                for body, name, raw in conn.execute("SELECT body, name, data FROM maps ORDER BY body, name")]
    drawn = {}
    for body, name, data in maps:
        cover = coverage.Coverage.from_dict(body, data)
        cover.ground = ground_of.get(body)
        if cover.ground is None:
            continue
        seen.clear()
        cover.layer(180, 6000.0)
        image = coverage.picture(cover.mask, ground=cover.ground, body=cover.body)
        if len(set(seen)) != 1 or seen[0] != picks.get(body):
            fails.append(f"{body} / {name}: layer and picture loaded {seen}, pick {picks.get(body)}")
        drawn.setdefault(seen[0], image)
    coverage._texture = real
    print(f"maps drawn {sum(1 for b, _, _ in maps if ground_of.get(b))} of {len(maps)}, "
          f"variants seen on maps {len(drawn)}")

    # 4. contact sheet per family of the files in use: picture() output, 240 px each
    for family in families:
        names = [family if n == 1 else f"{family}-{n}" for n in range(1, coverage.TEXTURE_VARIANTS + 1)]
        sheet = Image.new("RGB", (240 * len(names), 240), (0, 0, 0))
        for i, name in enumerate(names):
            with Image.open(coverage.TEXTURE_DIR / f"{name}{coverage.TEXTURE_EXT}") as picture:
                sheet.paste(picture.convert("RGB").resize((240, 240)), (240 * i, 0))
        sheet.save(os.path.join(out, f"sheet-{family}.png"))

    for line in fails:
        print(f"FAIL {line}")
    print(f"result {'FAIL' if fails else 'PASS'}: {len(fails)} failures")
    return 1 if fails else 0


def main():
    out = os.path.join(HERE, "out", datetime.now().strftime("%Y%m%d-%H%M%S"))
    live = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter", "db", "rhinospotter.db")
    copy = os.path.join(out, "RhinoSpotter", "db", "rhinospotter.db")
    os.makedirs(os.path.dirname(copy))
    with sqlite3.connect(f"file:{live}?mode=ro", uri=True) as src, sqlite3.connect(copy) as dst:
        src.backup(dst)
    runs = []
    for seed in ("1", "2"):
        env = dict(os.environ, LOCALAPPDATA=out, PYTHONIOENCODING="utf-8", PYTHONHASHSEED=seed)
        runs.append(subprocess.run([sys.executable, os.path.abspath(__file__), "--child", out],
                                   cwd=PLUGIN, env=env, capture_output=True, text=True,
                                   encoding="utf-8"))
    report = [line for line in runs[0].stdout.splitlines() if not line.startswith("PICK")]
    first = [line for line in runs[0].stdout.splitlines() if line.startswith("PICK")]
    second = [line for line in runs[1].stdout.splitlines() if line.startswith("PICK")]
    same = first == second and bool(first)
    report.append(f"cross-process: {len(first)} picks, PYTHONHASHSEED 1 vs 2 "
                  f"{'identical' if same else 'DIFFER'}")
    for run in runs:
        if run.stderr.strip():
            report.append("stderr: " + run.stderr.strip()[-2000:])
    failed = not same or any(run.returncode for run in runs)
    report.append(f"overall {'FAIL' if failed else 'PASS'}")
    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(report) + "\n")
    print("\n".join(report))
    print(os.path.relpath(out, PLUGIN))
    return 1 if failed else 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        sys.exit(child(sys.argv[2]))
    sys.exit(main())
