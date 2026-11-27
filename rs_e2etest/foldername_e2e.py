"""E2E harness: the plugin logs through EDMC's handlers whatever its folder is called. Checks: foldername.md.

Run from the plugin folder:  python rs_e2etest/foldername_e2e.py
Writes rs_e2etest/out/<timestamp>-foldername/report.txt. Exit code 1 on a failure.

Each child runs a copy of the plugin from out/<ts>/<folder>/<name>, LOCALAPPDATA
set to the run folder, so the live database is never opened.
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
FOLDERS = ("RhinoSpotter", "EDRhinoSpotter", "EDRhinoSpotter-main")
COPY = ("load.py", "rs_api.py", "mining_sheet.json", "rs_core", "rs_ui", "data", "texture", "cards")


def child():
    """EDMC's logging as plug.py sets it up: a handler on "EDMarketConnector" whose
    format needs %(osthreadid)s, filled by a filter on f"EDMarketConnector.{folder}" only."""
    import logging
    import types
    plugin_dir, log_path = sys.argv[2], sys.argv[3]
    folder = os.path.basename(plugin_dir)

    class Config(dict):
        def get_str(self, key, default=None): return self.get(key, default)
        def get_bool(self, key, default=False): return self.get(key, default)
        def get_int(self, key, default=0): return self.get(key, default)
        def get_list(self, key, default=None): return self.get(key, default)
        def set(self, key, value): self[key] = value
        def delete(self, key, *args, **kwargs): self.pop(key, None)
    sys.modules["config"] = types.SimpleNamespace(appname="EDMarketConnector", config=Config())

    edmc = logging.getLogger("EDMarketConnector")
    edmc.setLevel(logging.DEBUG)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(osthreadid)s %(name)s %(message)s"))
    edmc.addHandler(handler)

    class Context(logging.Filter):
        def filter(self, record):
            record.osthreadid = 1
            return True
    logging.getLogger(f"EDMarketConnector.{folder}").addFilter(Context())

    sys.path.insert(0, plugin_dir)
    import load
    load.plugin_start3(plugin_dir)
    load.plugin_stop()


def main():
    out = os.path.join(HERE, "out", datetime.now().strftime("%Y%m%d-%H%M%S") + "-foldername")
    os.makedirs(out)
    lines, failed = [], 0

    def check(name, ok, detail=""):
        nonlocal failed
        failed += not ok
        lines.append(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""))
        print(lines[-1])

    for folder in FOLDERS:
        plugin_dir = os.path.join(out, folder.lower() + "-plugins", folder)
        os.makedirs(plugin_dir)
        for name in COPY:
            src = os.path.join(PLUGIN, name)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(plugin_dir, name),
                                ignore=shutil.ignore_patterns("__pycache__"))
            elif os.path.exists(src):
                shutil.copy2(src, plugin_dir)
        log_path = os.path.join(out, f"{folder}.log")
        env = dict(os.environ, LOCALAPPDATA=os.path.join(out, folder.lower() + "-data"))
        run = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", plugin_dir, log_path],
                             cwd=out, env=env, capture_output=True, text=True, timeout=120)
        with open(os.path.join(out, f"{folder}.stderr.txt"), "w", encoding="utf-8") as handle:
            handle.write(run.stderr)
        log = open(log_path, encoding="utf-8").read() if os.path.exists(log_path) else ""
        ours = [line for line in log.splitlines() if f"EDMarketConnector.{folder}" in line]
        check(f"{folder}: child exit 0", run.returncode == 0, run.stderr.strip()[-300:])
        check(f"{folder}: no '--- Logging error ---' on stderr", "Logging error" not in run.stderr,
              f"{run.stderr.count('Logging error')} errors")
        check(f"{folder}: 'running on' logged as EDMarketConnector.{folder}",
              any("running on" in line for line in ours), f"{len(ours)} lines")

    lines.append(f"{sum(l.startswith('PASS') for l in lines)}/{len(lines)} passed  ->  {out}")
    print(lines[-1])
    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        child()
    else:
        raise SystemExit(main())
