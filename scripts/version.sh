#!/usr/bin/env bash
# Version of a build (spec 5.2), printed to stdout.
#
#   version.sh build <run number>   -> <last release>+build.<N>   (CI)
#   version.sh local                -> <last release>+local.<short commit>
#   version.sh last-release         -> <last release>
#   version.sh image-tag <version>  -> the version as Docker image tag ('+' becomes '_')
set -euo pipefail

last_release() {
    local tag
    tag="$(git describe --tags --abbrev=0 --match 'v[0-9]*' --exclude '*-*' 2>/dev/null || true)"
    echo "${tag#v}" | sed 's/^$/0.0.0/'
}

case "${1:-}" in
    build)
        [[ "${2:-}" =~ ^[0-9]+$ ]] || { echo "usage: version.sh build <run number>" >&2; exit 2; }
        echo "$(last_release)+build.$2"
        ;;
    local) echo "$(last_release)+local.$(git rev-parse --short HEAD)" ;;
    last-release) last_release ;;
    image-tag)
        [[ -n "${2:-}" ]] || { echo "usage: version.sh image-tag <version>" >&2; exit 2; }
        echo "${2//+/_}"
        ;;
    *) echo "usage: version.sh build <N> | local | last-release | image-tag <version>" >&2; exit 2 ;;
esac
