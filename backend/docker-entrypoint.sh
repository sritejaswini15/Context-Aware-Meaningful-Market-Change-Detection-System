#!/bin/sh
set -e
case "${1:-api}" in
  api)
    if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then alembic upgrade head; fi
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*" --workers "${WEB_CONCURRENCY:-2}"
    ;;
  worker)
    exec python -m app.workers.main
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
