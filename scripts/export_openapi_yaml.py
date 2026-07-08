from __future__ import annotations

from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app


def main() -> None:
    output_path = ROOT / "openapi.yaml"
    output_path.write_text(yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
