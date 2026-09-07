# Mock data — AeroComply M0.5 prototype

Everything under `frontend/lib/mock/` is **fictional, demo-only data** used to
power the M0.5 interactive prototype. None of it represents real aircraft,
real regulatory requirements, or real compliance determinations. It exists to
demonstrate AeroComply's product experience before the real M1 backend
(PostgreSQL aviation schema, deterministic rules engine) is built — see
`FOUNDATION.md` and `docs/ontology/` for the actual domain design this mock
data is intentionally shaped to match.

Every screen that renders this data displays a "PROTOTYPE / MOCK DATA"
indicator (see `frontend/components/layout/AppShell.tsx`) so it is never
mistaken for a live system.
