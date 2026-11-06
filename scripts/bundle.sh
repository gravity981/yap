#!/usr/bin/env bash
# Packs the deployment bundle of a release (spec 5.6): the server files from deploy/ and
# the JSON Schemas of this version, as yap-<tag>-deploy.tar.gz.
#
#   bundle.sh <git tag> <output directory>    -> prints the path of the bundle
set -euo pipefail
tag="${1:?usage: bundle.sh <git tag> <output directory>}"
out="${2:?usage: bundle.sh <git tag> <output directory>}"
cd "$(dirname "$0")/.."

name="yap-${tag}-deploy"
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
mkdir -p "$staging/$name/schemas" "$out"
cp deploy/compose.yaml deploy/deploy.sh deploy/.env.example "$staging/$name/"
cp schemas/*.schema.json "$staging/$name/schemas/"
# Fixed permissions, whatever the checkout has (core.fileMode=false)
find "$staging/$name" -type d -exec chmod 755 {} +
find "$staging/$name" -type f -exec chmod 644 {} +
chmod 755 "$staging/$name/deploy.sh"
tar -czf "$out/$name.tar.gz" -C "$staging" "$name"
echo "$out/$name.tar.gz"
