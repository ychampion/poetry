"""Exercise published Poetry versions on the reporter's Qt example and an independent Tk app."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

PIN = "ebee912d6ef565cb6e5ed4652385a8e5001c1dbc"
HERE = Path(__file__).resolve().parent
WINDOWS = os.name == "nt"
BIN = "Scripts" if WINDOWS else "bin"
arguments = ["release notes", "café"]


def run(command, cwd, env, *, check=True):
    return subprocess.run(command, cwd=cwd, env=env, check=check, timeout=420)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("version")
    p.add_argument("poetry", type=Path)
    p.add_argument("result", type=Path)
    args = p.parse_args()
    fixed = args.version != "2.4.3"
    tool = args.poetry.resolve()
    with tempfile.TemporaryDirectory(prefix="launch-") as directory:
        base = Path(directory)
        project = base / "reporter"
        project.mkdir()
        shutil.copy(HERE / "pyproject.toml", project)
        shutil.copytree(HERE / "poetry_gui_scripts", project / "poetry_gui_scripts")
        env = dict(os.environ, POETRY_VIRTUALENVS_IN_PROJECT="true",
                   POETRY_CONFIG_DIR=str(base / "config"), POETRY_DATA_DIR=str(base / "data"),
                   QT_QPA_PLATFORM="offscreen", PYTHONUTF8="1")
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONPATH", None)
        version = subprocess.check_output([tool, "--version"], env=env, text=True).strip()
        assert args.version in version, version
        results = {"poetry": version, "platform": sys.platform, "python": sys.version.split()[0],
                   "observations": {}}

        def install(path):
            run([tool, "env", "use", sys.executable], path, env)
            run([tool, "install", "--only", "main", "--no-ansi", "--no-interaction"], path, env)

        def observe(label, path, command, expected, extra=None):
            marker = base / (label + ".json")
            child = dict(env, LAUNCH_RECEIPT=str(marker), **(extra or {}))
            proc = run(command, path, child, check=False)
            if expected and proc.returncode == 0:
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.1)
            data = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
            print(label, proc.returncode, data, flush=True)
            assert (proc.returncode == 0) == expected and bool(data) == expected, label
            if label.startswith("qt") and data:
                assert data["arguments"] == arguments, data
                assert data["kind"] == "console" or data["visible"], data
            if label.startswith("android") and data:
                assert data["title"] == "Android Translator" and data["visible"] and data["children"] > 0, data
            results["observations"][label] = {"returncode": proc.returncode, **data}
            return data

        def launcher(path, name, wheel=False):
            extension = (".exe" if wheel else ".cmd") if WINDOWS else ""
            return path / ".venv" / BIN / (name + extension)

        install(project)
        for name in ["console-check", "mygui"]:
            gui = name == "mygui"
            exists = fixed or not gui
            wrapper = launcher(project, name)
            assert wrapper.is_file() == exists, wrapper
            results["observations"][name + "-editable-wrapper"] = wrapper.is_file()
            modes = {"run": [tool, "run", name]}
            if exists:
                modes["direct"] = [wrapper]
            for mode, cmd in modes.items():
                data = observe(f"qt-{name}-{mode}", project, [*cmd, *arguments], exists)
                if WINDOWS and data:
                    assert Path(data["executable"]).name.lower() == ("pythonw.exe" if gui else "python.exe"), data

        run([tool, "build", "--format", "wheel"], project, env)
        wheel, = (project / "dist").glob("*.whl")
        project_python = project / ".venv" / BIN / ("python.exe" if WINDOWS else "python")
        run([tool.parent / ("python.exe" if WINDOWS else "python"), "-m", "pip", "--python",
             project_python, "install", "--force-reinstall", "--no-deps", wheel], base, env)
        wheel_data = observe("qt-wheel", base, [launcher(project, "mygui", wheel=True), *arguments], True)
        assert "site-packages" in Path(wheel_data["source"]).parts, wheel_data

        if args.version in ("2.4.3", "2.5.2"):
            app = base / "android"
            run(["git", "init", "-q", str(app)], base, env)
            run(["git", "fetch", "-q", "--depth", "1",
                 "https://github.com/marcovisona/android-translator.git", PIN], app, env)
            run(["git", "checkout", "-q", "--detach", "FETCH_HEAD"], app, env)
            assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=app, text=True).strip() == PIN
            # This checkout's published lock predates its current dependency groups.
            run([tool, "lock", "--no-interaction"], app, env)
            run(["git", "diff", "--exit-code", "--", "pyproject.toml", "*.py"], app, env)
            results["observations"]["android-lock"] = "refreshed in disposable checkout"
            install(app)
            run([tool, "run", "android-translator", "--help"], app, env)
            results["observations"]["android-console-help"] = True
            probe = base / "observation"
            probe.mkdir()
            shutil.copyfile(HERE / "sitecustomize.fixture", probe / "sitecustomize.py")
            wrapper = launcher(app, "android-translator-gui")
            assert wrapper.is_file() == fixed, wrapper
            results["observations"]["android-editable-wrapper"] = wrapper.is_file()
            data = observe("android-gui", app, [tool, "run", "android-translator-gui"], fixed,
                           {"PYTHONPATH": str(probe)})
            if WINDOWS and data:
                assert Path(data["executable"]).name.lower() == "pythonw.exe", data
        args.result.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
