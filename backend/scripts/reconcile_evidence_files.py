"""M16.8: run EvidenceFile <-> object-storage reconciliation.

There is no background-job/scheduler infrastructure in this codebase (no
Celery/RQ/cron) -- this script is the operational entry point, following the
same "standalone script with direct DATABASE_URL access" pattern already
established by scripts/create_platform_admin.py for the other task in this
codebase that legitimately runs outside any single tenant's request/response
authorization context. Scheduling it (cron, a platform task runner, etc.) is
intentionally deferred to whoever operates a given deployment.

By default this only discovers and reports anomalies -- it NEVER mutates
anything unless --apply-repairs is passed, and even then only the one
SAFE_TO_REPAIR case this milestone defines (a DELETED row whose object still
exists in storage) is ever touched; see
app/services/evidence_reconciliation_service.py for the full repair policy
and why every other anomaly is left for manual review.

Usage (reads DATABASE_URL and the app's S3_* settings from the environment,
same as the app itself):

    DATABASE_URL=postgresql+psycopg://... \\
        python scripts/reconcile_evidence_files.py

    # Scope to one organization instead of the whole platform:
    python scripts/reconcile_evidence_files.py --organization-id <uuid>

    # Actually repair SAFE_TO_REPAIR anomalies (default is discovery-only):
    python scripts/reconcile_evidence_files.py --apply-repairs \\
        --actor-user-id <uuid-of-the-platform-operator-authorizing-this>

Never prints a storage key, signed URL, or raw provider error text -- only
the safe summary/anomaly fields from ReconciliationResult.
"""

import argparse
import os
import sys
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.evidence_reconciliation_service import (  # noqa: E402
    apply_repairs,
    scan_evidence_files,
)
from app.services.storage import get_storage_service  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--organization-id",
        type=uuid.UUID,
        default=None,
        help="Scope the scan to one organization. Default: scan every organization.",
    )
    parser.add_argument(
        "--apply-repairs",
        action="store_true",
        help="Actually repair SAFE_TO_REPAIR anomalies. Default: discovery-only (report only).",
    )
    parser.add_argument(
        "--actor-user-id",
        type=uuid.UUID,
        default=None,
        help="User id of the platform operator authorizing this run, recorded on any repair "
        "audit event. Omit for an unattended/system-initiated run (audit user_id is nullable).",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db: Session = SessionLocal()
    try:
        storage_service = get_storage_service()
        result = scan_evidence_files(db, storage_service, organization_id=args.organization_id)

        print(f"Scanned:                 {result.scanned_count}")
        print(f"Consistent / no action:  {result.consistent_count}")
        print(f"Anomalies:               {result.anomaly_count}")
        print(f"  Safe to repair:        {result.repairable_count}")
        print(f"  Manual review:         {result.manual_review_count}")
        print(f"Infrastructure failures: {result.infrastructure_failure_count}")
        if result.failures:
            print("\nInfrastructure failure details:")
            for f in result.failures:
                print(f"  - {f}")
        if result.anomalies:
            print("\nAnomaly details:")
            for a in result.anomalies:
                print(
                    f"  - evidence_file_id={a.evidence_file_id} "
                    f"organization_id={a.organization_id} status={a.db_status} "
                    f"object_exists={a.object_exists} classification={a.classification.value}: "
                    f"{a.detail}"
                )

        if args.apply_repairs and result.repairable_count > 0:
            repaired = apply_repairs(
                db, storage_service, anomalies=result.anomalies, actor_user_id=args.actor_user_id
            )
            print(f"\nRepaired: {repaired} of {result.repairable_count} SAFE_TO_REPAIR anomalies.")
        elif result.repairable_count > 0:
            print(
                f"\n{result.repairable_count} anomalies are SAFE_TO_REPAIR but were not repaired "
                "(pass --apply-repairs to repair them)."
            )
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
