# Real-storage tests (M17.1)

The tests in this directory hit an **actual S3-compatible HTTP server**
through `StorageService` — real network calls, real HEAD/PUT/GET/DELETE
requests, real presigned URLs — never a `StorageService` double or a
Python-level mock of boto3. They prove the storage abstraction actually
works end-to-end, not just that the application calls boto3 correctly in
isolation (that narrower guarantee is what `tests/unit/test_storage_service.py`
already covers with a mocked client).

They are **excluded from the default test run** (see `pyproject.toml`'s
`addopts = "-m 'not real_storage'"`) because ordinary `pytest`/CI runs in
this repository are not guaranteed to have an S3-compatible service
available. Run them explicitly once you have one running:

```bash
pytest -m real_storage
```

## Starting a real S3-compatible endpoint

### Preferred: MinIO via Docker (this repo's own convention)

`infra/docker-compose.yml` already defines a `minio` service with the same
credentials this project's dev defaults expect
(`aerocomply` / `aerocomply_dev_secret`). If Docker is available:

```bash
docker compose -f infra/docker-compose.yml up -d minio
```

Then point the tests at it:

```bash
export REAL_STORAGE_S3_ENDPOINT_URL=http://localhost:9000
export REAL_STORAGE_S3_ACCESS_KEY=aerocomply
export REAL_STORAGE_S3_SECRET_KEY=aerocomply_dev_secret
export REAL_STORAGE_S3_BUCKET=aerocomply-evidence-test
export TEST_DATABASE_URL=postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test
pytest -m real_storage
```

### Fallback used to validate M17.1 in this environment: `moto_server`

Docker/MinIO were not available in the environment this milestone was
implemented and validated in (MinIO's own binary distribution at
`dl.min.io` has been discontinued — it now returns `410 Gone` for the
Windows/Linux/macOS server binaries). As the closest available substitute
that is still a **real, separate HTTP server** (not an in-process mock),
this milestone used [`moto`](https://github.com/getmoto/moto)'s standalone
S3 server, installed as a dev-only dependency:

```bash
pip install "moto[s3]"
moto_server -p 9000
```

then the same environment variables as above, pointed at
`http://127.0.0.1:9000`.

**This is an honest limitation, not a substitute claimed to be equivalent**:
`moto_server` implements the S3 HTTP API against an in-memory backend and is
purpose-built for exactly this kind of test, so it genuinely exercises
`StorageService`'s real network code path (HTTP requests, request signing,
presigned URL generation and redemption, HEAD-based existence checks) — but
it is not MinIO or AWS S3, and does not prove behavior specific to a real
provider (e.g. eventual consistency characteristics, provider-specific error
codes beyond the standard ones moto emulates). Anyone with Docker available
should prefer the real MinIO path above; these tests do not care which
server they're pointed at, since they only depend on `REAL_STORAGE_S3_*`
env vars and the standard S3 API.

## Cleanup

Each test uses a fresh, randomly-named object key (via `uuid.uuid4()`) so
tests never collide and can run in any order; the shared bucket is created
once per session if missing and is never deleted by the tests themselves.
Objects created and left behind by a real MinIO run can be cleared with
`mc rb --force local/aerocomply-evidence-test && mc mb local/aerocomply-evidence-test`,
or simply by discarding a throwaway `moto_server` process (all state is
in-memory and vanishes when the process exits).

## Database

These tests create real `Organization`/`User`/`Aircraft`/`WorkOrder`/`Task`/
`Evidence`/`EvidenceFile` rows against `TEST_DATABASE_URL`, reusing the exact
same `db_session`/`engine` fixtures as `tests/integration/` (real Alembic
migrations, one rolled-back transaction per test) — no new database
convention was introduced.
