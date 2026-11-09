#!/usr/bin/env bash
# Rules of the release workflows (spec 5.4), as commands the workflows call:
#
#   release.sh candidate <version>    checks a new release candidate of <version>
#                                     (SemVer, higher than the last release, not released
#                                     yet) and prints its git tag, e.g. v1.2.0-rc.3
#   release.sh promote <candidate>    checks that <candidate> (e.g. v1.2.0-rc.3) can be
#                                     promoted (latest candidate, not released yet) and
#                                     prints the release version, e.g. 1.2.0
#   release.sh previous-release <tag> the release tag before <tag>, for release notes
#   release.sh changelog <tag> <owner/repo> [ref] what was added, fixed and changed since the
#                                     previous release, from the commit messages, for
#                                     release notes
#   release.sh notes <tag> <owner/repo> the commands to install or update an environment
#                                     with the bundle of <tag>, for release notes: prod for
#                                     a release, staging for a candidate
#
# Needs the git tags (fetch-depth 0).
set -euo pipefail
cd "$(dirname "$0")/.."

die() {
    echo "release: $*" >&2
    exit 1
}
semver='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
tag_exists() { git rev-parse -q --verify "refs/tags/$1" >/dev/null; }
releases() { git tag --list 'v[0-9]*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V || true; }
candidates() { # candidates <version>: its rc numbers, ascending
    git tag --list "v$1-rc.*" | sed -n "s/^v$1-rc\.\([0-9]\+\)$/\1/p" | sort -n
}

case "${1:-}" in
    candidate)
        version="${2:?usage: release.sh candidate <version>}"
        [[ "$version" =~ $semver ]] || die "$version is not a version X.Y.Z"
        tag_exists "v$version" && die "v$version is already released"
        last="$(releases | tail -n 1)"
        last="${last#v}"
        if [[ -n "$last" && "$(printf '%s\n%s\n' "$last" "$version" | sort -V | tail -n 1)" != "$version" ]]; then
            die "$version is not higher than the last release $last"
        fi
        [[ "$version" != "$last" ]] || die "$version is already released"
        number="$(candidates "$version" | tail -n 1)"
        echo "v$version-rc.$((${number:-0} + 1))"
        ;;
    promote)
        candidate="${2:?usage: release.sh promote <candidate tag>}"
        [[ "$candidate" =~ ^v([0-9]+\.[0-9]+\.[0-9]+)-rc\.([0-9]+)$ ]] ||
            die "$candidate is not a candidate tag vX.Y.Z-rc.N"
        version="${BASH_REMATCH[1]}"
        number="${BASH_REMATCH[2]}"
        tag_exists "$candidate" || die "$candidate does not exist"
        tag_exists "v$version" && die "v$version is already released"
        latest="$(candidates "$version" | tail -n 1)"
        [[ "$number" == "$latest" ]] ||
            die "only the latest candidate can be promoted: v$version-rc.$latest"
        echo "$version"
        ;;
    previous-release)
        tag="${2:?usage: release.sh previous-release <tag>}"
        version="${tag#v}"
        version="${version%%-*}"
        releases | while read -r release; do
            if [[ "$release" != "v$version" &&
                "$(printf '%s\n%s\n' "${release#v}" "$version" | sort -V | head -n 1)" == "${release#v}" ]]; then
                echo "$release"
            fi
        done | tail -n 1
        ;;
    changelog)
        tag="${2:?usage: release.sh changelog <tag> <owner/repo>}"
        repo="${3:?usage: release.sh changelog <tag> <owner/repo>}"
        previous="$(bash "$0" previous-release "$tag")"
        range="${previous:+$previous..}${4:-$tag}" # the ref of a release that is not tagged yet: its candidate
        # One line per commit (merge commits are skipped, so pull requests and direct
        # commits to main count the same), sorted by the start of its message:
        # "feat:"/"Add" is Added, "fix:"/"Fix" is Fixed, Dependabot is Dependencies, the
        # rest is Changed; "chore:", "docs:", "test:", "ci:" and "build:" are left out.
        # An optional "feat(scope): " prefix and a "step 1.2 - " prefix are dropped.
        added="" fixed="" changed="" deps=""
        while IFS=$'\x1f' read -r sha author subject; do
            [[ -n "$sha" ]] || continue
            shopt -s nocasematch
            [[ "$subject" =~ ^step\ [0-9.]+\ -\ (.+)$ ]] && subject="${BASH_REMATCH[1]}" # the stage steps
            if [[ "$subject" =~ ^(chore|test|tests|ci|docs|build)(\([^\)]*\))?:\  ]]; then
                :  # housekeeping: not part of the notes
            elif [[ "$author" == *"[bot]" || "$subject" =~ ^bump\  ]]; then
                deps+="- $subject (\`$sha\`)"$'\n'
            elif [[ "$subject" =~ ^(feat|feature|add|added)(\([^\)]*\))?(:\ |\ ) ]]; then
                text="$subject"
                [[ "$subject" =~ ^(feat|feature)(\([^\)]*\))?:\ (.*)$ ]] && text="${BASH_REMATCH[3]}"
                added+="- ${text^} (\`$sha\`)"$'\n'
            elif [[ "$subject" =~ ^(fix|fixed|bugfix)(\([^\)]*\))?(:\ |\ ) ]]; then
                text="$subject"
                [[ "$subject" =~ ^(fix|bugfix)(\([^\)]*\))?:\ (.*)$ ]] && text="${BASH_REMATCH[3]}"
                fixed+="- ${text^} (\`$sha\`)"$'\n'
            else
                changed+="- $subject (\`$sha\`)"$'\n'
            fi
            shopt -u nocasematch
        done < <(git log --no-merges --format='%h%x1f%an%x1f%s' "$range")
        echo "## What's changed${previous:+ since $previous}"
        [[ -z "$added" ]] || printf '\n### Added\n\n%s' "$added"
        [[ -z "$fixed" ]] || printf '\n### Fixed\n\n%s' "$fixed"
        [[ -z "$changed" ]] || printf '\n### Changed\n\n%s' "$changed"
        [[ -z "$deps" ]] || printf '\n### Dependencies\n\n%s' "$deps"
        if [[ -n "$previous" ]]; then
            printf '\n**Full changelog:** https://github.com/%s/compare/%s...%s\n' "$repo" "$previous" "$tag"
        fi
        ;;
    notes)
        tag="${2:?usage: release.sh notes <tag> <owner/repo>}"
        repo="${3:?usage: release.sh notes <tag> <owner/repo>}"
        if [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            env_name=prod
            env_hint="adjust if needed"
            admin=$'\ndocker compose exec app python -m yap.cli create-admin <username> --investor --currency CHF'
        elif [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-rc\.[0-9]+$ ]]; then
            env_name=staging
            env_hint="set APP_ENV=staging, COMPOSE_PROJECT_NAME, DB_VOLUME, APP_PORT, PROD_BACKUP_DIR"
            admin="" # staging starts from the newest prod backup, accounts included
        else
            die "$tag is neither a release vX.Y.Z nor a candidate vX.Y.Z-rc.N"
        fi
        bundle="yap-$tag-deploy" # as named by scripts/bundle.sh
        url="https://github.com/$repo/releases/download/$tag/$bundle.tar.gz"
        cat <<EOF
**First installation** of $env_name, on a server with Docker and Docker Compose:

\`\`\`bash
mkdir -p ~/yap && cd ~/yap
curl -fsSL "$url" | tar -xz
mv "$bundle" $env_name && cd $env_name
cp .env.example .env    # $env_hint
./deploy.sh $env_name ${tag#v}$admin
\`\`\`

**Update** of an existing $env_name (keeps its .env, secrets and backups):

\`\`\`bash
cd ~/yap
curl -fsSL "$url" | tar -xz
cp "$bundle/compose.yaml" "$bundle/deploy.sh" $env_name/
rm -rf "$bundle"
cd $env_name && ./deploy.sh $env_name ${tag#v}
\`\`\`
EOF
        ;;
    *) die "usage: release.sh candidate <version> | promote <candidate> | previous-release <tag> | changelog <tag> <owner/repo> [ref] | notes <tag> <owner/repo>" ;;
esac
