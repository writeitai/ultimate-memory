# Releasing RememberStack

The `Release` workflow publishes one version to PyPI and GHCR, then creates a GitHub release
containing the Python distributions, the same version-pinned `compose.yaml`, and `.env.example`.
It accepts only tags exactly matching `vMAJOR.MINOR.PATCH`.

## One-time owner setup

Complete these steps in order:

1. Finish the focused name clearance and put the bounded CLA in place. These are governance
   gates, not release-workflow features.
2. Confirm the GitHub repository is `writeitai/remember-stack`, then update each existing clone:

   ```bash
   git remote set-url origin git@github.com:writeitai/remember-stack.git
   ```

   The readable hyphen belongs only to repository and container URLs; the product remains
   RememberStack and the Python distribution/import remain `rememberstack`. GitHub redirects
   ordinary repository and Git traffic after a rename, but the final name must be in place before
   configuring PyPI because the trusted identity includes the repository name.
3. In the GitHub repository, create an environment named `pypi`. Add yourself as a required
   reviewer so a tag cannot publish to PyPI without an explicit approval.
4. Create a PyPI account, enable two-factor authentication, and add a
   [pending Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
   with these exact values:

   | Field | Value |
   |---|---|
   | PyPI project name | `rememberstack` |
   | GitHub owner | `writeitai` |
   | Repository | `remember-stack` |
   | Workflow | `release.yml` |
   | Environment | `pypi` |

   A pending publisher does not reserve the PyPI name. Configure it only after the repository
   rename and publish promptly once the release gates are clear.
5. Protect tags matching `v*` so only maintainers can create or update release tags.

No PyPI password or long-lived API token belongs in GitHub secrets. The workflow requests a
short-lived OpenID Connect credential and grants `id-token: write` only to the PyPI job.

## Cutting a release

Prepare a normal pull request that updates both `project.version` in `pyproject.toml` and the
GHCR tag in `compose.yaml`. Update release-facing documentation in the same pull request. The
contract check rejects drift:

```bash
uv run python scripts/check_release_contract.py --tag v0.1.0
```

After that pull request is merged and `main` is green, tag its exact merge commit:

```bash
git switch main
git pull --ff-only
git tag -a v0.1.0 -m "RememberStack 0.1.0"
git push origin v0.1.0
```

The workflow validates the tag, runs the release test suite, builds the wheel and source
distribution, and publishes `rememberstack==0.1.0` plus
`ghcr.io/writeitai/remember-stack:0.1.0`. It creates the GitHub release only after both
registries accept their artifact.

PyPI and GHCR do not support an atomic cross-registry transaction. Never reuse a published
version after a partial failure: fix the cause, complete the missing publish when safe, or cut the
next patch version.

## First-release GHCR step

The first container package may be private. After the first successful image push, open the
`remember-stack` package settings in GitHub and change its visibility to **public** so anonymous
Compose pulls work. GitHub warns that a public package cannot be made private again.

The image carries standard OCI source labels generated from the repository metadata, which links
the package back to this repository. Docker Hub is intentionally not a second publication target.

## Verify the public artifacts

Run these checks from a clean machine or temporary directory:

```bash
uvx --from rememberstack==0.1.0 remember --version
docker pull ghcr.io/writeitai/remember-stack:0.1.0
gh release download v0.1.0 --repo writeitai/remember-stack \
  --pattern compose.yaml --pattern .env.example
cp .env.example .env
docker compose --env-file .env up --no-build --pull always --detach --wait
curl --fail http://localhost:8000/healthz
docker compose --env-file .env down --volumes
```

The final command deletes the disposable verification deployment and its volumes.
