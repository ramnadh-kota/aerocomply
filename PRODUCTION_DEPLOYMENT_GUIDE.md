> **Implementation status (2026-09-30):** this document is a design/target description. The implemented behaviour is documented in `DATA_ACQUISITION_ARCHITECTURE.md`, `ENTITLEMENT_ARCHITECTURE.md`, `SECURITY_ARCHITECTURE.md`, `OBSERVABILITY_ARCHITECTURE.md`, `PRODUCTION_RUNBOOK.md` and `FINAL_RELEASE_READINESS.md`. Topology items (Cloudflare, Redis cluster, TimescaleDB, Gunicorn sizing) are recommendations that have NOT been built or load-tested; the app has no Redis/queue/worker dependency today. Use `PRODUCTION_PREDEPLOYMENT_CHECKLIST.md`, `backend/scripts/production_preflight.sql`, `PRODUCTION_ROLLBACK_GUIDE.md`. Where this text disagrees with those, those win.

# KOTA AEROSPACE — PRODUCTION DEPLOYMENT & INFRASTRUCTURE GUIDE

## 1. System Architecture & Topology

```text
                                [ INTERNET / CLIENTS ]
                                          │
                                          ▼
                             [ Cloudflare / Edge WAF ]
                             (DDoS, TLS Termination, Rate Limit)
                                          │
                                          ▼
                          [ Application Load Balancer ]
                                          │
                     ┌────────────────────┴────────────────────┐
                     ▼                                         ▼
         [ Next.js 16.3 Frontend ]                 [ FastAPI Python 3.11 Backend ]
         (Port 3000, Multi-Replica)                (Port 8000, Multi-Replica Gunicorn)
                     │                                         │
                     └────────────────────┬────────────────────┘
                                          │
               ┌──────────────────────────┼──────────────────────────┐
               ▼                          ▼                          ▼
      [ PostgreSQL 16 + ]        [ Redis 7.2 Cluster ]      [ S3 Object Storage ]
      [ TimescaleDB Extension ]  (Session Cache, Queues,   (Documents, Flight Logs,
      (Core DB & Telemetry)       Rate Limiting, PubSub)    Evidence Packages)
```

---

## 2. Environment Configuration & Secrets

### 2.1 Backend Environment Variables (`.env.production`)
```env
# Runtime
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<<STRONG_256_BIT_RANDOM_KEY>>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# Database
DATABASE_URL=postgresql+psycopg://aerocomply_user:<<SECURE_PASSWORD>>@db-primary.internal:5432/aerocomply_prod
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30

# Redis & Caching
REDIS_URL=redis://:<<REDIS_PASSWORD>>@redis-master.internal:6379/0

# Security & CORS
ALLOWED_ORIGINS=https://app.kota-aerospace.com,https://api.kota-aerospace.com
SECURE_COOKIES=true

# AI & LLM Providers (Grounded Tools)
ANTHROPIC_API_KEY=<<SECURE_API_KEY>>
OPENAI_API_KEY=<<SECURE_API_KEY>>
DEFAULT_AI_PROVIDER=anthropic

# Object Storage (AWS S3 / Cloudflare R2)
S3_BUCKET_NAME=kota-production-evidence
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=<<AWS_KEY>>
AWS_SECRET_ACCESS_KEY=<<AWS_SECRET>>
```

### 2.2 Frontend Environment Variables (`.env.production`)
```env
NEXT_PUBLIC_API_BASE_URL=https://api.kota-aerospace.com
NEXT_PUBLIC_APP_NAME=Kota Aerospace
NEXT_PUBLIC_ENVIRONMENT=production
NODE_ENV=production
```

---

## 3. Database Migration & Deployment Order

1. **Pre-Deployment Check**:
   - Run `PRODUCTION_PREDEPLOYMENT_CHECKLIST.md`.
   - Take full database snapshot before migration.
2. **Apply Alembic Migrations**:
   ```bash
   cd backend
   alembic upgrade head
   ```
3. **Deploy Backend Containers**:
   - Rolling zero-downtime deployment (Health check: `GET /api/v1/health`).
4. **Deploy Frontend Containers**:
   - Rolling update of Next.js production build (`npm run build` $\rightarrow$ `npm run start`).
5. **Post-Deployment Verification**:
   - Run API smoke tests on `/api/v1/health`, `/api/v1/auth/me`, `/api/v1/suites`.
