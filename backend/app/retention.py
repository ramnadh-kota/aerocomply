"""Retention CLI (run from cron / a Kubernetes CronJob):  python -m app.retention [--execute] [--org UUID]

Dry-run by default. --execute additionally requires RETENTION_DESTRUCTIVE_ENABLED=true and enabled policies."""
from __future__ import annotations

import argparse
import json
import sys
import uuid

from app.db.session import SessionLocal
from app.services import retention_service


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument("--org", type=uuid.UUID, default=None)
    args = ap.parse_args()
    with SessionLocal() as db:
        try:
            results = retention_service.run_retention(db, dry_run=not args.execute, organization_id=args.org)
        except retention_service.RetentionError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        db.commit()
    print(json.dumps({"dry_run": not args.execute, "results": [r.to_dict() for r in results]}, indent=2))
    return 1 if any(r.error for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
