#!/bin/sh
# =====================================================================
# MinIO bootstrap: alias + создание bucket ${MINIO_BUCKET}.
# Идемпотентно — повторный запуск ничего не ломает.
# =====================================================================
set -eu

: "${MINIO_ENDPOINT:=http://minio:9000}"
: "${MINIO_ROOT_USER:?}"
: "${MINIO_ROOT_PASSWORD:?}"
: "${MINIO_BUCKET:=models}"

echo "[init] Waiting for MinIO at ${MINIO_ENDPOINT}..."
until mc alias set local "${MINIO_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null 2>&1; do
  sleep 1
done

echo "[init] Ensuring bucket '${MINIO_BUCKET}'..."
mc mb --ignore-existing "local/${MINIO_BUCKET}"
mc anonymous set download "local/${MINIO_BUCKET}" || true

echo "[init] MinIO ready."
