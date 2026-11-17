#!/bin/sh
set -eu
# One worker for the SQLite-backed demo. PORT is injected by many hosting providers.
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
