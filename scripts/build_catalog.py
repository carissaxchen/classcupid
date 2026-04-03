#!/usr/bin/env python3
"""Build catalog.db from course JSON (run locally or on Vercel before deploy)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

OUT = ROOT / "catalog.db"
OUT.unlink(missing_ok=True)

os.environ.setdefault("SECRET_KEY", "build")
os.environ["SQLALCHEMY_DATABASE_URI_OVERRIDE"] = f"sqlite:///{OUT}"

from app import app


def main():
    runner = app.test_cli_runner()
    for name in ("2026_Fall_courses.json", "2027_Spring_courses.json"):
        path = ROOT / "data" / "json" / name
        if not path.is_file():
            print(f"Skip missing {path}", file=sys.stderr)
            continue
        print(f"Importing {path} ...")
        result = runner.invoke(args=["import-courses", str(path)])
        if result.exit_code != 0:
            print(result.output, file=sys.stderr)
            sys.exit(result.exit_code)
        if result.output.strip():
            print(result.output.strip())
    print(f"Done. Wrote {OUT}")


if __name__ == "__main__":
    main()
