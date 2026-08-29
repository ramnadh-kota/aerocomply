# AeroComply

Aviation compliance intelligence platform. See [FOUNDATION.md](FOUNDATION.md) for the full engineering foundation document and [docs/adr/](docs/adr/) for architecture decision records.

## Running locally (M0)

Requires: Docker, Python 3.11+, Node 20+.

### 1. Start infrastructure

```bash
cd infra
docker compose up -d
```

This starts Postgres (5432), Neo4j (7474/7687), Redis (6379), and MinIO (9000/9001).

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

API available at `http://localhost:8000`, interactive docs at `http://localhost:8000/docs`.

Health checks: `GET /api/v1/health` (liveness), `GET /api/v1/health/ready` (readiness, checks DB).

### 3. Backend tests

```bash
cd backend
createdb -U aerocomply aerocomply_test   # or via psql/docker exec
export TEST_DATABASE_URL=postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test
pytest -v
```

### 4. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Frontend available at `http://localhost:3000`.

### 5. Try it end-to-end

```bash
curl -X POST http://localhost:8000/api/v1/auth/register-organization \
  -H "Content-Type: application/json" \
  -d '{"organization_name":"Demo Airline","admin_email":"admin@demo.com","admin_full_name":"Demo Admin","admin_password":"supersecret123"}'
```

Then log in at `http://localhost:3000/login` with those credentials.

## Repository structure

```
backend/    FastAPI application (see backend/app for module layout)
frontend/   Next.js application
infra/      docker-compose.yml for local dependencies
docs/adr/   Architecture Decision Records
FOUNDATION.md   Engineering foundation document (architecture, schema, API spec, milestones)
```
