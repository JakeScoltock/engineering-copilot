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

# All three Lambdas share the full src/ tree and the same dependencies.
# boto3 is provided by the Lambda runtime and excluded from the zips.
build "query_api"       "pydantic>=2.0,<3.0" "httpx>=0.27,<1.0" "numpy>=1.26,<3.0"
build "query_streaming" "pydantic>=2.0,<3.0" "httpx>=0.27,<1.0" "numpy>=1.26,<3.0"
build "ingestion"       "pydantic>=2.0,<3.0" "httpx>=0.27,<1.0" "numpy>=1.26,<3.0"

echo "==> Done"
