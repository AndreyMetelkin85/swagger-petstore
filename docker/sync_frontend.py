"""Copy the reviewed frontend sources into the self-contained project build context."""

import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1]).resolve()
target = Path(__file__).resolve().parents[1] / "ui"
if not (source / "package-lock.json").is_file():
    raise SystemExit("Frontend source must contain package-lock.json")
target.mkdir(exist_ok=True)
for name in ("src", "public", "qa", "tests"):
    shutil.copytree(
        source / name,
        target / name,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".venv", "__pycache__", "screenshots", "ci", "*result.json"),
    )
for name in ("package.json", "package-lock.json", "index.html", "tsconfig.json", "vite.config.ts"):
    shutil.copy2(source / name, target / name)
