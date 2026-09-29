# KOTA Aerospace — Backup & Disaster Recovery Runbook

## 1. Objectives & SLA Targets

- **Recovery Point Objective (RPO)**: < 15 minutes (continuous WAL archiving + automated snapshots).
- **Recovery Time Objective (RTO)**: < 1 hour to full operational state.
- **Data Integrity**: Cryptographic checksum verification on database restores and evidence file storage.

---

## 2. Backup Strategy

### 2.1 PostgreSQL Database
1. **Automated Daily Base Backups**:
   - `pg_dump -Fc -Z 9 -f backup_aerocomply_$(date +%Y%m%d_%H%M%S).dump aerocomply`
   - Encrypted at rest (AES-256) and replicated to geographically distinct off-site cold storage.
2. **Point-In-Time Recovery (PITR)**:
   - Write-Ahead Logging (WAL) stream continuous archival.
   - Enables recovery to any discrete second within the 30-day retention window.
3. **Retention Policy**:
   - Hourly WAL segments: 7 days.
   - Daily snapshots: 30 days.
   - Monthly compliance snapshots: 7 years (per civil aviation record retention requirements).

### 2.2 Evidence & Object Storage
- Immutable write-once-read-many (WORM) storage for uploaded compliance documents, maintenance photographic evidence, and flight records.
- Cross-region asynchronous replication with versioning enabled.

---

## 3. Restoration Procedure

1. **Verify Target Environment**:
   - Ensure clean database instance running the target PostgreSQL version (v15+).
2. **Restore Database**:
   ```bash
   pg_restore --clean --if-exists --no-owner -d aerocomply_target /path/to/backup.dump
   ```
3. **Run Alembic Verification**:
   ```bash
   cd backend
   alembic heads
   alembic check
   ```
4. **Execute Post-Restore Smoke Tests**:
   - Run `pytest tests/integration/test_configurable_freshness_and_smoke.py` to confirm tenant integrity, asset state, and RBAC functionality.
