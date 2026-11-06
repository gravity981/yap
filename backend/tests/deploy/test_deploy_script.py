"""deploy/deploy.sh against a fake `docker` that records its calls (spec 5.6, 5.8).

The real Docker run is checked on staging for every release candidate (test strategy §9).
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"

# Answers like docker: the image's version label, the running container's version and
# what /api/health reports, with the suffix from .env like the app; every call is appended
# to $FAKE_LOG.
FAKE_DOCKER = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
case "$*" in
    login*) cat > /dev/null ;;
    "image inspect"*) echo "$FAKE_VERSION" ;;
    "compose ps"*) [[ -n "$FAKE_RUNNING_VERSION" ]] && echo container-id ;;
    "compose exec -T app cat /app/VERSION") echo "$FAKE_RUNNING_VERSION" ;;
    "compose exec -T app python -c"*)
        suffix="$(sed -n 's/^APP_VERSION_SUFFIX=//p' .env)"
        echo "$FAKE_HEALTH${FAKE_HEALTH:+${suffix:+-$suffix}}" ;;
    "compose logs"*) echo "log line" ;;
esac
exit 0
"""

ENV = """APP_ENV={env}
COMPOSE_PROJECT_NAME=yap-{env}
DB_VOLUME=yap-db-{env}
APP_PORT=8000
COOKIE_SECURE=false
BACKUP_DIR=./backups
GHCR_USER=gravity981
{extra}IMAGE_TAG={tag}
"""


class Server:
    def __init__(
        self, tmp_path: Path, env: str = "prod", tag: str = "", extra: str = "", token: bool = False
    ) -> None:
        self.dir = tmp_path / env
        self.dir.mkdir()
        for name in ("deploy.sh", "compose.yaml"):
            (self.dir / name).write_text((DEPLOY / name).read_text())
        (self.dir / ".env").write_text(ENV.format(env=env, tag=tag, extra=extra))
        if token:
            (self.dir / "ghcr-token").write_text("token")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        fake = bin_dir / "docker"
        fake.write_text(FAKE_DOCKER)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.log = tmp_path / f"docker-{env}.log"
        self.environ = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_LOG": str(self.log),
            "FAKE_VERSION": "1.2.0",
            "FAKE_RUNNING_VERSION": "",
            "FAKE_HEALTH": "1.2.0",
            "HEALTH_TIMEOUT": "2",
        }

    def deploy(self, *args: str, **fake: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.dir / "deploy.sh"), *args],
            capture_output=True,
            text=True,
            env={**self.environ, **fake},
            timeout=60,
        )

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def env(self, name: str) -> str:
        lines = (self.dir / ".env").read_text().splitlines()
        return [line.split("=", 1)[1] for line in lines if line.startswith(f"{name}=")][-1]


@pytest.mark.req("NFR-09")
@pytest.mark.parametrize(
    ("args", "message"),
    [
        ((), "usage"),
        (("test", "1.2.0"), "usage"),
        (("prod", "latest"), "never latest"),
        (("prod", "1.2.0-rc.1"), "only takes release image tags"),
        (("prod", "1.1.0_build.57"), "only takes release image tags"),
        (("staging", "1.2.0-rc.1"), "configured for 'prod'"),
        (("prod", "1.2.0", "--restore", "missing.db"), "backup missing.db not found"),
    ],
)
def test_wrong_calls_are_refused_before_anything_happens(
    tmp_path: Path, args: tuple[str, ...], message: str
) -> None:
    server = Server(tmp_path)
    result = server.deploy(*args)
    assert result.returncode == 1 and message in result.stderr
    assert server.calls() == []


@pytest.mark.req("NFR-09")
def test_an_older_compose_file_is_refused_before_anything_happens(tmp_path: Path) -> None:
    # A compose.yaml from before the version suffix: the app would report 1.2.0, while
    # deploy.sh waits for 1.2.0-rc.1 until the health check times out
    server = Server(tmp_path, env="staging", extra="PROD_BACKUP_DIR=./prod-backups\n")
    compose = server.dir / "compose.yaml"
    compose.write_text(
        "".join(
            line
            for line in compose.read_text().splitlines(keepends=True)
            if "APP_VERSION_SUFFIX" not in line
        )
    )
    result = server.deploy("staging", "1.2.0-rc.1")
    assert result.returncode == 1 and "compose.yaml is older than deploy.sh" in result.stderr
    assert server.calls() == []


@pytest.mark.req("NFR-09", "REV-15")
def test_first_deployment_creates_the_secret_and_starts_the_version(tmp_path: Path) -> None:
    server = Server(tmp_path)
    result = server.deploy("prod", "1.2.0")
    assert result.returncode == 0, result.stderr
    secret = server.dir / "secrets" / "app_secret_key"
    assert len(secret.read_text()) >= 40
    assert stat.S_IMODE((server.dir / "secrets").stat().st_mode) == 0o700
    assert server.env("IMAGE_TAG") == "1.2.0"
    assert server.env("APP_VERSION_SUFFIX") == ""  # a release reports exactly its version
    calls = server.calls()
    assert calls[0] == "pull ghcr.io/gravity981/yap:1.2.0"  # public, no login
    assert any(c.startswith("compose up -d") for c in calls)
    assert not any("cli backup" in c for c in calls)  # nothing ran before
    assert "create-admin" in result.stdout
    # A second deployment keeps the secret
    key = secret.read_text()
    server.deploy("prod", "1.2.0", FAKE_RUNNING_VERSION="1.2.0")
    assert secret.read_text() == key


@pytest.mark.req("NFR-08", "NFR-09")
def test_prod_is_backed_up_before_a_new_version_starts(tmp_path: Path) -> None:
    server = Server(tmp_path, tag="1.1.0")
    result = server.deploy("prod", "1.2.0", FAKE_RUNNING_VERSION="1.1.0")
    assert result.returncode == 0, result.stderr
    calls = server.calls()
    backup = next(c for c in calls if "cli backup" in c)
    assert backup.startswith("compose exec -T app python -m yap.cli backup")
    assert "-1.1.0.db" in backup and "/backups/prod-" in backup
    assert calls.index(backup) < next(i for i, c in enumerate(calls) if c.startswith("compose up"))
    assert "Backup before the deployment" in result.stdout


@pytest.mark.req("NFR-09")
def test_a_failed_start_prints_the_rollback_command(tmp_path: Path) -> None:
    server = Server(tmp_path, tag="1.1.0")
    result = server.deploy("prod", "1.2.0", FAKE_RUNNING_VERSION="1.1.0", FAKE_HEALTH="")
    assert result.returncode == 1
    assert "did not become healthy" in result.stderr
    assert "./deploy.sh prod 1.1.0 --restore prod-" in result.stderr
    assert "log line" in result.stderr


@pytest.mark.req("NFR-09")
def test_rollback_restores_the_backup_before_starting(tmp_path: Path) -> None:
    server = Server(tmp_path, tag="1.2.0")
    (server.dir / "backups").mkdir()
    (server.dir / "backups" / "prod-1.db").write_text("x")
    result = server.deploy(
        "prod",
        "1.1.0",
        "--restore",
        "prod-1.db",
        FAKE_VERSION="1.1.0",
        FAKE_HEALTH="1.1.0",
        FAKE_RUNNING_VERSION="1.2.0",
    )
    assert result.returncode == 0, result.stderr
    calls = server.calls()
    restore = next(c for c in calls if "cli restore" in c)
    assert restore.endswith("restore /backups/prod-1.db --force")
    assert calls.index("compose stop app") < calls.index(restore)
    assert calls.index(restore) < next(i for i, c in enumerate(calls) if c.startswith("compose up"))


@pytest.mark.req("NFR-09")
def test_staging_starts_from_the_newest_prod_backup(tmp_path: Path) -> None:
    prod_backups = tmp_path / "prod-backups"
    prod_backups.mkdir()
    for name, age in (("prod-old.db", 200), ("prod-new.db", 100)):
        path = prod_backups / name
        path.write_text("x")
        os.utime(path, (path.stat().st_atime - age, path.stat().st_mtime - age))
    server = Server(tmp_path, env="staging", extra=f"PROD_BACKUP_DIR={prod_backups}\n")
    result = server.deploy("staging", "1.2.0-rc.1")
    assert result.returncode == 0, result.stderr
    # The image contains 1.2.0; the app reports the candidate's rc.1 too (spec 5.7)
    assert server.env("APP_VERSION_SUFFIX") == "rc.1"
    assert "(1.2.0-rc.1) to staging" in result.stdout
    restore = next(c for c in server.calls() if "cli restore" in c)
    assert f"--volume {prod_backups}:/prod-backups:ro" in restore
    assert restore.endswith("restore /prod-backups/prod-new.db --force")
    assert not any("cli backup" in c for c in server.calls())


def test_staging_needs_a_prod_backup(tmp_path: Path) -> None:
    server = Server(tmp_path, env="staging")
    result = server.deploy("staging", "1.2.0-rc.1")
    assert result.returncode == 1 and "PROD_BACKUP_DIR" in result.stderr


def test_staging_keeps_its_database_without_a_prod_backup(tmp_path: Path) -> None:
    prod_backups = tmp_path / "prod-backups"
    prod_backups.mkdir()
    server = Server(tmp_path, env="staging", extra=f"PROD_BACKUP_DIR={prod_backups}\n")
    result = server.deploy("staging", "0.1.0-rc.1", FAKE_VERSION="0.1.0", FAKE_HEALTH="0.1.0")
    assert result.returncode == 0, result.stderr
    assert "no prod backup" in result.stderr
    assert not any("cli restore" in c for c in server.calls())
    assert any(c.startswith("compose up") for c in server.calls())


@pytest.mark.req("NFR-09")
def test_a_token_logs_in_before_pulling(tmp_path: Path) -> None:
    server = Server(tmp_path, token=True)
    result = server.deploy("prod", "1.2.0")
    assert result.returncode == 0, result.stderr
    assert server.calls()[:2] == [
        "login ghcr.io --username gravity981 --password-stdin",
        "pull ghcr.io/gravity981/yap:1.2.0",
    ]


def test_a_token_needs_the_user(tmp_path: Path) -> None:
    server = Server(tmp_path, token=True)
    env = server.dir / ".env"
    env.write_text(env.read_text().replace("GHCR_USER=gravity981\n", ""))
    result = server.deploy("prod", "1.2.0")
    assert result.returncode == 1 and "GHCR_USER" in result.stderr
    assert server.calls() == []
