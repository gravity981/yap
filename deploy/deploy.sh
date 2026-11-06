#!/usr/bin/env bash
# Deploys a version of YAP on the LAN server (spec 5.6, 5.8).
#
#   deploy.sh <prod|staging> <image tag> [--restore <backup file>]
#
# Run it in the environment's directory (compose.yaml, .env). It
#   1. pulls the image; logs in to ghcr.io first if the file ghcr-token exists (only
#      needed for a private image),
#   2. creates the secret file APP_SECRET_KEY on the first deployment (never overwrites it),
#   3. prod: backs up the running database to BACKUP_DIR;
#      staging: replaces its database with the newest prod backup (PROD_BACKUP_DIR),
#   4. with --restore: replaces the database with that backup (rollback, spec 5.8),
#   5. starts the version and waits until /api/health reports it.
# The app applies database migrations on startup; if they fail, it does not start.
set -euo pipefail
cd "$(dirname "$0")"

IMAGE=ghcr.io/gravity981/yap
APP_UID=10001 # the image's user (Dockerfile)
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-120}

die() {
    echo "deploy: $*" >&2
    exit 1
}
step() { echo "==> $*"; }

usage="usage: deploy.sh <prod|staging> <image tag> [--restore <backup file>]"
env_name="${1:-}"
tag="${2:-}"
restore=""
if [[ "${3:-}" == "--restore" ]]; then
    restore="${4:?$usage}"
elif [[ -n "${3:-}" ]]; then
    die "$usage"
fi
[[ "$env_name" == prod || "$env_name" == staging ]] || die "$usage"
[[ -n "$tag" ]] || die "$usage"
[[ "$tag" != latest ]] || die "deploy a fixed image tag, never latest"
if [[ "$env_name" == prod && ! "$tag" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    die "prod only takes release image tags (X.Y.Z), not $tag"
fi

[[ -f .env ]] || die ".env not found; copy .env.example to .env and adjust it"
[[ -f compose.yaml ]] || die "compose.yaml not found"
# deploy.sh and compose.yaml come from the same bundle: an older compose.yaml does not pass
# the version suffix to the app, and the health check below would wait for it in vain
grep -q APP_VERSION_SUFFIX compose.yaml ||
    die "compose.yaml is older than deploy.sh; copy both from the same release bundle"
env_value() { sed -n "s/^$1=//p" .env | tail -n 1; }
[[ "$(env_value APP_ENV)" == "$env_name" ]] ||
    die "this directory is configured for '$(env_value APP_ENV)', not '$env_name' (APP_ENV in .env)"
port="$(env_value APP_PORT)"
backup_dir="$(env_value BACKUP_DIR)"
backup_dir="${backup_dir:-./backups}"
previous_tag="$(env_value IMAGE_TAG)"
if [[ -n "$restore" && ! -f "$backup_dir/$restore" && ! -f "$restore" ]]; then
    die "backup $restore not found (looked in $backup_dir)"
fi

set_env() { # set_env <name> <value>: replaces or appends the line in .env
    if grep -q "^$1=" .env; then
        sed -i "s|^$1=.*|$1=$2|" .env
    else
        echo "$1=$2" >>.env
    fi
}

# The image is public; a token is only needed for a private copy of it
if [[ -f ghcr-token ]]; then
    ghcr_user="$(env_value GHCR_USER)"
    [[ -n "$ghcr_user" ]] || die "ghcr-token found, but GHCR_USER is not set in .env"
    step "Logging in to ghcr.io as $ghcr_user"
    docker login ghcr.io --username "$ghcr_user" --password-stdin <ghcr-token >/dev/null
fi

step "Pulling $IMAGE:$tag"
docker pull "$IMAGE:$tag" >/dev/null
version="$(docker image inspect --format \
    '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$IMAGE:$tag")"
[[ -n "$version" ]] || die "$IMAGE:$tag has no version label"
# A release candidate contains the version it is a candidate for; its rc.N is only in the
# image tag, so the app gets it as suffix and reports <version>-rc.N (spec 5.7)
suffix=""
if [[ "$tag" =~ ^${version//./\.}-(rc\.[0-9]+)$ ]]; then
    suffix="${BASH_REMATCH[1]}"
    version="$version-$suffix"
fi
echo "    version $version"

if [[ ! -f secrets/app_secret_key ]]; then
    step "Creating secrets/app_secret_key (first deployment of $env_name)"
    mkdir -p secrets
    chmod 700 secrets
    (umask 077 && head -c 32 /dev/urandom | base64 | tr -d '\n' >secrets/app_secret_key)
fi
mkdir -p "$backup_dir"

# The compose commands below run the new image
set_env IMAGE_TAG "$tag"
set_env APP_VERSION_SUFFIX "$suffix"
compose() { docker compose "$@"; }

# The container runs as an unprivileged user: it must be able to read the secret and write
# backups; the host user's group keeps access to both. Done as root inside the image, so
# deploy.sh itself needs no root rights.
step "Preparing access to the secret and the backup folder"
compose run --rm --no-deps --user root --entrypoint sh \
    --volume "$PWD/secrets:/secrets" app -c "
        chown $APP_UID:$(id -g) /secrets/app_secret_key /backups &&
        chmod 0440 /secrets/app_secret_key &&
        chmod 2770 /backups" >/dev/null

running_version=""
if [[ -n "$previous_tag" ]] && [[ -n "$(compose ps --quiet --status running app 2>/dev/null)" ]]; then
    running_version="$(docker compose exec -T app cat /app/VERSION 2>/dev/null || true)"
fi

backup=""
if [[ "$env_name" == prod && -n "$running_version" ]]; then
    backup="prod-$(date -u +%Y%m%dT%H%M%SZ)-${running_version//+/_}.db"
    step "Backing up the running database ($running_version) to $backup_dir/$backup"
    IMAGE_TAG="$previous_tag" compose exec -T app \
        python -m yap.cli backup "/backups/$backup" >/dev/null
fi

restore_from() { # restore_from <path in the container> [<extra compose run options>...]
    local file="$1"
    shift
    compose stop app >/dev/null 2>&1 || true
    compose run --rm --no-deps "$@" app \
        python -m yap.cli restore "$file" --force >/dev/null
}

if [[ -n "$restore" ]]; then
    step "Restoring the database from $restore"
    restore_from "/backups/$(basename "$restore")"
elif [[ "$env_name" == staging ]]; then
    prod_backups="$(env_value PROD_BACKUP_DIR)"
    [[ -n "$prod_backups" ]] || die "set PROD_BACKUP_DIR in .env (the prod backup folder)"
    newest="$(ls -t "$prod_backups"/*.db 2>/dev/null | head -n 1 || true)"
    if [[ -n "$newest" ]]; then
        step "Replacing the staging database with $(basename "$newest")"
        restore_from "/prod-backups/$(basename "$newest")" \
            --volume "$(cd "$prod_backups" && pwd):/prod-backups:ro"
    else
        # Before the first release there is no prod, so no backup either
        echo "deploy: warning: no prod backup in $prod_backups; staging keeps its own database" >&2
    fi
fi

step "Starting $tag"
compose up -d --remove-orphans >/dev/null

step "Waiting for /api/health to report $version"
health=""
for _ in $(seq 1 "$HEALTH_TIMEOUT"); do
    health="$(compose exec -T app python -c "
import json, urllib.request
print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3))['version'])
" 2>/dev/null || true)"
    [[ "$health" == "$version" ]] && break
    sleep 1
done

if [[ "$health" != "$version" ]]; then
    echo >&2
    echo "deploy: $tag did not become healthy (reports '${health:-nothing}'); last log lines:" >&2
    compose logs --tail 30 app >&2 || true
    if [[ -n "$previous_tag" ]]; then
        echo >&2
        echo "Roll back with:" >&2
        if [[ -n "$backup" ]]; then
            echo "  ./deploy.sh $env_name $previous_tag --restore $backup" >&2
        else
            echo "  ./deploy.sh $env_name $previous_tag" >&2
        fi
    fi
    exit 1
fi

echo "Deployed $IMAGE:$tag ($version) to $env_name on port $port"
if [[ -n "$backup" ]]; then
    echo "Backup before the deployment: $backup_dir/$backup"
fi
if [[ -z "$previous_tag" ]]; then
    echo "First deployment: create the admin account with"
    echo "  docker compose exec app python -m yap.cli create-admin <username>"
fi
