> **Implementation status (2026-09-30):** this document is a design/target description. The implemented behaviour is documented in `DATA_ACQUISITION_ARCHITECTURE.md`, `ENTITLEMENT_ARCHITECTURE.md`, `SECURITY_ARCHITECTURE.md`, `OBSERVABILITY_ARCHITECTURE.md`, `PRODUCTION_RUNBOOK.md` and `FINAL_RELEASE_READINESS.md`. Correction: 169 remaining model/DB differences are individually reviewed and pinned by `test_schema_drift_guard.py`; migration 0065 fixed the real ones. Index-only differences are not the same as constraint drift. Where this text disagrees with those, those win.

# Kota Aerospace — Historical Schema Drift Forensic Report

## 1. Executive Summary
A comprehensive comparison between the SQLAlchemy ORM `Base.metadata` and the PostgreSQL relational database schema (at Alembic migration head `0061`) identified **175 itemized differences**.

None of the 175 items constitute a breaking defect or data-loss risk. They are categorized below into technical classifications with rationale.

---

## 2. Classification Summary

| Category | Item Count | Classification | Action Required |
|---|---|---|---|
| **Timestamp Nullability (`modify_nullable`)** | 59 | Intentional / Harmless | None (DB enforces `NOT NULL DEFAULT now()`) |
| **Database Performance Indexes (`remove_index` / `add_index`)** | 70 | Harmless Historical Optimization | None (Indexes exist in DB for query speed) |
| **Tenant Foreign Key Constraints (`remove_fk` / `add_fk`)** | 29 | Safe / Intentional | None (DB enforces FK cascades; models use mixins) |
| **Audit Columns (`remove_column`)** | 10 | Harmless Historical Artifact | None (Columns exist in DB; ORM queries ignore or read) |
| **Constraint Naming (`remove_constraint`)** | 7 | Harmless Naming Variation | None (Constraints exist and are enforced in DB) |

---

## 3. Detailed Category Breakdown

### 1. Timestamp Nullability (59 items)
- **Observed**: Alembic reports `modify_nullable` on `created_at` and `updated_at` across 59 tables.
- **Cause**: Database tables were created via DDL with `server_default=func.now(), nullable=False`. In SQLAlchemy model definitions, `TimestampMixin` declares `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())`.
- **Impact**: Zero runtime impact. PostgreSQL enforces non-null defaults at row insertion time.

### 2. Database Indexes (70 items: 30 remove_index, 40 add_index)
- **Observed**: Specific compound and single-column indexes exist in the PostgreSQL schema that are not declared explicitly in SQLAlchemy `__table_args__`.
  - Examples: `ix_assets_facility_id`, `ix_assets_org_active`, `ix_aog_events_status`, `ix_approval_requests_status_created_at`, `ix_applicability_evaluations_evaluated_at`.
- **Cause**: Historical migrations explicitly added optimized indexes for query performance during milestones M1-M18.
- **Impact**: Highly beneficial for live production query execution; removing them would degrade API read performance.

### 3. Foreign Key Constraints (29 items: 26 remove_fk, 3 add_fk)
- **Observed**: Constraints like `fk_applicability_conditions_org`, `fk_applicability_rules_org`, `fk_applicability_evaluations_org` exist in the database with `ON DELETE CASCADE`.
- **Cause**: Migrations defined named foreign keys directly; ORM models inherit `TenantScopedMixin` without explicit named constraints in Python metadata.
- **Impact**: Zero runtime impact. Database integrity and tenant cascades are preserved.

### 4. Audit Columns (10 items: remove_column)
- **Observed**: Columns like `updated_at` on historical immutable baseline tables (e.g. `asset_historical_baselines`).
- **Cause**: Baseline tables were created with standard timestamps; models treat baseline rows as immutable.
- **Impact**: Zero runtime impact.

---

## 4. Production Release Recommendation
- **Do NOT rewrite historical migrations**: Modifying historical Alembic scripts would invalidate deployment reproducibility on existing databases.
- **Do NOT drop existing database indexes**: The indexes present in PostgreSQL are required for fast multi-tenant queries.
- **Alembic Autogenerate Policy**: For future schema additions, author explicit migration scripts rather than relying on unreviewed autogenerate diffs.
