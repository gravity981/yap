#!/usr/bin/env bash
# Starts an image with an empty database and checks that it serves the app and reports
# the expected version (spec 5.3, image smoke test).
#
#   smoke-test.sh <image> <expected version>
set -euo pipefail
image="${1:?usage: smoke-test.sh <image> <expected version>}"
expected="${2:?usage: smoke-test.sh <image> <expected version>}"
port="${SMOKE_PORT:-18000}"
name="itk-smoke-$$"

cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$name" -p "127.0.0.1:${port}:8000" "$image" >/dev/null
for _ in $(seq 1 60); do
    if health="$(curl -fsS "http://127.0.0.1:${port}/api/health" 2>/dev/null)"; then
        break
    fi
    sleep 1
done
if [[ -z "${health:-}" ]]; then
    echo "The app did not become healthy; container log:" >&2
    docker logs "$name" >&2
    exit 1
fi

check() {  # check <what> <actual> <expected>
    if [[ "$2" != "$3" ]]; then
        echo "FAIL: $1 is '$2', expected '$3'" >&2
        exit 1
    fi
    echo "ok: $1 = $2"
}
json() { python3 -c "import json, sys; print(json.load(sys.stdin)$1)"; }

check "health status" "$(echo "$health" | json '["status"]')" "ok"
check "health version" "$(echo "$health" | json '["version"]')" "$expected"
check "API version" "$(curl -fsS "http://127.0.0.1:${port}/api/version" | json '["version"]')" "$expected"
check "image label" "$(docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$image")" "$expected"
check "/app/VERSION" "$(docker exec "$name" cat /app/VERSION)" "$expected"
check "frontend served" "$(curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${port}/")" "200"
# Download first, then search: grep -q stops reading early, which makes curl fail under
# pipefail although the text was found
index_html="$(curl -fsS "http://127.0.0.1:${port}/")"
bundle="$(grep -o 'assets/index-[^"]*\.js' <<<"$index_html" | head -n 1 || true)"
[[ -n "$bundle" ]] || { echo "FAIL: no JavaScript bundle in index.html" >&2; exit 1; }
bundle_js="$(curl -fsS "http://127.0.0.1:${port}/${bundle}")"
if grep -qF "\`${expected}\`" <<<"$bundle_js"; then
    echo "ok: frontend has version ${expected} compiled in"
else
    echo "FAIL: frontend does not contain version ${expected}" >&2
    exit 1
fi
# By content: unknown paths get index.html with status 200 (frontend routes)
licenses="$(curl -fsS "http://127.0.0.1:${port}/third-party-licenses.txt")"
check "third-party licenses served" "$(head -n 1 <<<"$licenses")" \
    "Third-party software in the YAP frontend"
check "runs as" "$(docker exec "$name" id -un)" "app"
echo "Smoke test passed for ${image} (${expected})"
