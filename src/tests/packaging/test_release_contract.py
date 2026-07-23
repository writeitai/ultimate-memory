"""WP-7.6 acceptance tests for one release version across every artifact."""

from pathlib import Path
import subprocess
import sys
import tomllib


def test_release_contract_matches_package_compose_and_tag() -> None:
    """Accept the current package version, Compose image, and matching tag."""
    root = Path(__file__).resolve().parents[3]
    version = _project_version(root=root)
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "check_release_contract.py"),
            "--tag",
            f"v{version}",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert (
        result.stdout.strip() == f"release contract valid for RememberStack {version}"
    )


def test_release_contract_rejects_a_mismatched_tag() -> None:
    """Reject a tag that could publish PyPI and GHCR under different versions."""
    root = Path(__file__).resolve().parents[3]
    version = _project_version(root=root)
    invalid_tag = f"v{version}.invalid"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "check_release_contract.py"),
            "--tag",
            invalid_tag,
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert f"release tag must be 'v{version}', found '{invalid_tag}'" in result.stderr


def _project_version(*, root: Path) -> str:
    """Read the package version independently from the release checker process."""
    with (root / "pyproject.toml").open("rb") as pyproject:
        document = tomllib.load(pyproject)
    project = document.get("project")
    assert isinstance(project, dict)
    version = project.get("version")
    assert isinstance(version, str)
    return version
