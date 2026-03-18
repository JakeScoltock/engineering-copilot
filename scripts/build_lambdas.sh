#!/usr/bin/env bash
# Build Lambda deployment packages.
# Outputs zips to: infra/terraform/environments/dev/builds/
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILDS_DIR="${REPO_ROOT}/infra/terraform/environments/dev/builds"

mkdir -p "${BUILDS_DIR}"

build() {
  local name="$1"; shift
  echo "==> Building ${name}.zip"

  local tmp
  tmp="$(mktemp -d)"

  # Install Python dependencies (rest args are package specs)
  if [ "$#" -gt 0 ]; then
    pip install --quiet --target "${tmp}" "$@"
  fi

  # Copy full source tree
  cp -r "${REPO_ROOT}/src" "${tmp}/"

  # Zip
  (cd "${tmp}" && zip -qr "${BUILDS_DIR}/${name}.zip" .)
  rm -rf "${tmp}"

  echo "    ok -> ${BUILDS_DIR}/${name}.zip"
}

# query-api: only pydantic (boto3 is in the Lambda runtime)
build "query_api" "pydantic>=2.0,<3.0"

# ingestion: pydantic + httpx + numpy (boto3 is in the Lambda runtime)
build "ingestion" "pydantic>=2.0,<3.0" "httpx>=0.27,<1.0" "numpy>=1.26,<3.0"

echo "==> Done"
