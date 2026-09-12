# Production image for the KOTA'S AEROSPACE FastAPI backend.
# Build:  docker build -t aerocomply-backend .
# Run:    docker run -p 8000:8000 --env-file .env aerocomply-backend
#
# Migrations are NOT run automatically on container start — run
# `alembic upgrade head` as a separate deploy step against DATABASE_URL
# before (or immediately after) rolling out a new image, same as the local
# dev workflow. This keeps a bad migration from silently taking down every
# replica of a multi-instance deployment.

FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000

# Uvicorn reads $PORT so this image works unmodified on platforms that
# assign the port at runtime (Render, Railway, Fly, Cloud Run, etc).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
