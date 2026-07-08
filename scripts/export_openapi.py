from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import app


def main() -> None:
    output_path = Path("openapi.json")
    output_path.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {output_path.resolve()}")


if __name__ == "__main__":
    main()
