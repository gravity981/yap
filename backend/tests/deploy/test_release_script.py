"""scripts/release.sh and scripts/bundle.sh: the rules of the release workflows (spec 5.4,
5.6), run against a temporary git repository."""

import subprocess
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "release.sh").write_text((REPO / "scripts/release.sh").read_text())
    git(tmp_path, "init", "-q")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return tmp_path


def tag(repo: Path, *tags: str) -> None:
    for name in tags:
        git(repo, "tag", name)


def release(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(repo / "scripts/release.sh"), *args], capture_output=True, text=True
    )


@pytest.mark.req("NFR-09")
def test_candidates_are_numbered_per_version(repo: Path) -> None:
    assert release(repo, "candidate", "1.0.0").stdout.strip() == "v1.0.0-rc.1"
    tag(repo, "v1.0.0-rc.1", "v1.0.0-rc.2", "v1.1.0-rc.7")
    assert release(repo, "candidate", "1.0.0").stdout.strip() == "v1.0.0-rc.3"
    assert release(repo, "candidate", "1.1.0").stdout.strip() == "v1.1.0-rc.8"


@pytest.mark.req("NFR-09")
@pytest.mark.parametrize(
    ("version", "message"),
    [
        ("1.2", "not a version"),
        ("v1.2.0", "not a version"),
        ("01.2.0", "not a version"),
        ("1.2.0", "already released"),
        ("1.1.9", "not higher than the last release 1.2.0"),
    ],
)
def test_invalid_candidates_are_refused(repo: Path, version: str, message: str) -> None:
    tag(repo, "v1.2.0", "v1.10.0-rc.1")
    result = release(repo, "candidate", version)
    assert result.returncode == 1 and message in result.stderr


def test_versions_compare_numerically(repo: Path) -> None:
    tag(repo, "v1.9.0")
    assert release(repo, "candidate", "1.10.0").stdout.strip() == "v1.10.0-rc.1"


@pytest.mark.req("NFR-09")
def test_only_the_latest_candidate_is_promoted(repo: Path) -> None:
    tag(repo, "v1.2.0-rc.1", "v1.2.0-rc.2")
    assert release(repo, "promote", "v1.2.0-rc.2").stdout.strip() == "1.2.0"
    result = release(repo, "promote", "v1.2.0-rc.1")
    assert result.returncode == 1 and "only the latest candidate" in result.stderr
    assert "does not exist" in release(repo, "promote", "v1.2.0-rc.3").stderr
    assert "not a candidate tag" in release(repo, "promote", "v1.2.0").stderr
    tag(repo, "v1.2.0")
    assert "already released" in release(repo, "promote", "v1.2.0-rc.2").stderr


def test_previous_release_for_release_notes(repo: Path) -> None:
    assert release(repo, "previous-release", "v1.0.0").stdout.strip() == ""
    tag(repo, "v1.0.0", "v1.1.0-rc.1", "v1.1.0", "v1.10.0")
    assert release(repo, "previous-release", "v1.2.0-rc.1").stdout.strip() == "v1.1.0"
    assert release(repo, "previous-release", "v1.1.0").stdout.strip() == "v1.0.0"
    assert release(repo, "previous-release", "v1.11.0").stdout.strip() == "v1.10.0"


@pytest.mark.parametrize(
    ("tag", "env", "image_tag"),
    [("v1.2.0", "prod", "1.2.0"), ("v1.2.0-rc.3", "staging", "1.2.0-rc.3")],
)
def test_notes_list_the_install_and_update_commands(
    repo: Path, tag: str, env: str, image_tag: str
) -> None:
    notes = release(repo, "notes", tag, "owner/yap").stdout
    url = f"https://github.com/owner/yap/releases/download/{tag}/yap-{tag}-deploy.tar.gz"
    install, update = notes.split("**Update**")
    for part in (install, update):
        assert f'curl -fsSL "{url}" | tar -xz' in part
        assert f"./deploy.sh {env} {image_tag}" in part
    assert f'mv "yap-{tag}-deploy" {env} && cd {env}' in install
    assert "cp .env.example .env" in install
    assert ("create-admin" in install) == (env == "prod")  # staging gets prod's accounts
    assert f'"yap-{tag}-deploy/deploy.sh" {env}/' in update
    assert ".env.example" not in update  # an update keeps the existing .env


def test_notes_refuse_other_tags(repo: Path) -> None:
    result = release(repo, "notes", "1.2.0", "owner/yap")
    assert result.returncode == 1 and "neither a release" in result.stderr


def commit(repo: Path, subject: str, author: str = "t") -> None:
    git(
        repo,
        "-c",
        f"user.name={author}",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        subject,
    )


@pytest.mark.req("NFR-09")
def test_changelog_sorts_the_commits_since_the_previous_release(repo: Path) -> None:
    commit(repo, "Old change")
    tag(repo, "v1.0.0")
    commit(repo, "feat(rebalance): Before/after chart")
    commit(repo, "Add history chart")
    commit(repo, "fix: Band status below target")
    commit(repo, "step 2.1 - Drafts")
    commit(repo, "docs: Screenshots")
    commit(repo, "Bump actions/cache from 5 to 6", author="dependabot[bot]")
    result = release(repo, "changelog", "v1.1.0", "owner/yap", "HEAD")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "What's changed since v1.0.0" in out
    assert out.index("### Added") < out.index("### Fixed") < out.index("### Changed")
    assert out.index("### Changed") < out.index("### Dependencies")
    assert "- Before/after chart (" in out and "- Add history chart (" in out
    assert "- Band status below target (" in out
    assert "- Drafts (" in out  # the step prefix is dropped
    assert "Screenshots" not in out and "Old change" not in out
    assert "owner/yap/compare/v1.0.0...v1.1.0" in out


@pytest.mark.req("NFR-09")
def test_changelog_of_the_first_release_lists_everything(repo: Path) -> None:
    commit(repo, "Something")
    out = release(repo, "changelog", "v0.1.0", "owner/yap", "HEAD").stdout
    assert "- init (" in out and "- Something (" in out and "compare" not in out


@pytest.mark.req("NFR-09", "IMP-09")
def test_bundle_contains_the_server_files_and_schemas(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(REPO / "scripts/bundle.sh"), "v1.2.0-rc.1", str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    with tarfile.open(result.stdout.strip()) as bundle:
        members = {m.name: m for m in bundle.getmembers()}
    root = "yap-v1.2.0-rc.1-deploy"
    assert {f"{root}/{name}" for name in ("compose.yaml", "deploy.sh", ".env.example")} <= set(
        members
    )
    assert f"{root}/schemas/thesis.v1.schema.json" in members
    assert members[f"{root}/deploy.sh"].mode == 0o755
    assert members[f"{root}/compose.yaml"].mode == 0o644
