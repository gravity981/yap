#!/usr/bin/env bash
# Builds the production image locally (spec 5.2): version <last release>+local.<commit>,
# image tag `local`. Not pushed.
set -euo pipefail
cd "$(dirname "$0")/.."
image="${IMAGE:-ghcr.io/gravity981/yap}"
version="$(bash scripts/version.sh local)"
commit="$(git rev-parse HEAD)"
echo "Building ${image}:local with version ${version}"
docker build \
    --build-arg APP_VERSION="${version}" \
    --build-arg APP_COMMIT="${commit}" \
    --tag "${image}:local" \
    .
