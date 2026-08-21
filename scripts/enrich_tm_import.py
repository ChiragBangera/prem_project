#!/usr/bin/env python
"""Import a manual Transfermarkt CSV export into the enrichment SQLite cache.

Usage:
    uv run python scripts/enrich_tm_import.py --csv data/transfermarkt/manual.csv

CSV columns (header required):
    player_name,team_hint,market_value_eur,contract_end,foot,height_cm,fetched_at

Honest scope: values are a dated snapshot you exported yourself; nothing is
scraped here, and stale rows simply keep their old fetched_at date.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.analytics.enrichment import upsert_player_rows  # noqa: E402

REQUIRED = {"player_name"}


def _validate_contract_end(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        y, m, d = value.split("-")
        int(y), int(m), int(d)
        if len(y) != 4 or len(m) != 2 or len(d) != 2:
            raise ValueError
    except ValueError:
        print(f"  ! bad contract_end '{value}' (want YYYY-MM-DD) — keeping empty")
        return ""
    return value


def load_rows(csv_path: Path) -> list[dict]:
    today = date.today().isoformat()
    rows = []
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"CSV missing required column(s): {', '.join(sorted(missing))}")
        for raw in reader:
            name = (raw.get("player_name") or "").strip()
            if not name:
                continue
            value_raw = (raw.get("market_value_eur") or "").strip()
            try:
                value = int(float(value_raw)) if value_raw else None
                if value is not None and value <= 0:
                    raise ValueError
            except ValueError:
                print(f"  ! bad market_value_eur '{value_raw}' for {name} — ignored")
                value = None
            height_raw = (raw.get("height_cm") or "").strip()
            try:
                height = float(height_raw) if height_raw else None
            except ValueError:
                height = None
            rows.append(
                {
                    "player_name": name,
                    "team_hint": (raw.get("team_hint") or "").strip(),
                    "market_value_eur": value,
                    "contract_end": _validate_contract_end(raw.get("contract_end") or ""),
                    "foot": (raw.get("foot") or "").strip() or None,
                    "height_cm": height,
                    "fetched_at": (raw.get("fetched_at") or "").strip() or today,
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Transfermarkt CSV into enrichment cache")
    parser.add_argument("--csv", required=True, help="Path to manual.csv export")
    parser.add_argument("--db", default=None, help="SQLite target (default cache/enrichment.db)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    db_path = args.db or str(root / "cache" / "enrichment.db")

    rows = load_rows(Path(args.csv))
    if not rows:
        print("No valid rows found — nothing written.")
        return 1
    written = upsert_player_rows(db_path, rows)
    print(f"Wrote {written} player(s) to {db_path}")
    for row in rows[:5]:
        print(f"  + {row['player_name']} ({row['team_hint'] or 'no team'}) €{row['market_value_eur']}")
    if len(rows) > 5:
        print(f"  … and {len(rows) - 5} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
