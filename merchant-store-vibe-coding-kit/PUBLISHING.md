# Publishing this kit in the PingBusiness monorepo

## Canonical locations

```text
Repository:          https://github.com/PingBusiness/PingBusiness
Branch:              main
Kit directory:       merchant-store-vibe-coding-kit/
Kit page:            https://github.com/PingBusiness/PingBusiness/tree/main/merchant-store-vibe-coding-kit
Agent entrypoint:    https://raw.githubusercontent.com/PingBusiness/PingBusiness/main/merchant-store-vibe-coding-kit/AGENTS.md
Latest stable asset: https://github.com/PingBusiness/PingBusiness/releases/latest/download/pingbusiness-merchant-store-vibe-coding-kit.zip
```

The kit lives inside the existing `PingBusiness/PingBusiness` monorepo. All
managed-platform adapters clone the repository root and then use
`/merchant-store-vibe-coding-kit` as the source root.

## Recommended upload method

Use the repository-upload archive supplied with this release. Its top level is:

```text
merchant-store-vibe-coding-kit/
.github/workflows/merchant-store-vibe-kit-validate.yml
.github/instructions/merchant-store-vibe-kit.instructions.md
```

From a clean working directory:

```bash
git clone https://github.com/PingBusiness/PingBusiness.git
cd PingBusiness

# Extract the repository-upload ZIP into this repository root.
# Replace the existing kit directory if this is an update.

python3 -m venv merchant-store-vibe-coding-kit/.venv
. merchant-store-vibe-coding-kit/.venv/bin/activate
python -m pip install PyYAML==6.0.2
cd merchant-store-vibe-coding-kit
./scripts/validate.sh
cd ..

git add merchant-store-vibe-coding-kit \
        .github/workflows/merchant-store-vibe-kit-validate.yml \
        .github/instructions/merchant-store-vibe-kit.instructions.md
git commit -m "Add PingBusiness merchant-store vibe coding kit 1.0.0-rc3"
git push
```

Using a branch and pull request instead of pushing directly to `main` is
recommended when the repository requires review.

## Verify the publication

After the change reaches `main`, verify:

```text
https://github.com/PingBusiness/PingBusiness/tree/main/merchant-store-vibe-coding-kit
https://raw.githubusercontent.com/PingBusiness/PingBusiness/main/merchant-store-vibe-coding-kit/AGENTS.md
```

Also confirm that the GitHub Actions workflow named **Validate merchant-store
vibe kit** completes successfully.

## GitHub Release asset

For this release candidate, create a pre-release with tag:

```text
merchant-store-vibe-kit-v1.0.0-rc3
```

Attach:

```text
pingbusiness-merchant-store-vibe-coding-kit-1.0.0-rc3.zip
pingbusiness-merchant-store-vibe-coding-kit-1.0.0-rc3.zip.sha256
```

After live platform, DNS/TLS, checkout, and backup-restore gates pass, create a
non-prerelease `1.0.0` release and attach the stable asset name:

```text
pingbusiness-merchant-store-vibe-coding-kit.zip
```

That stable name activates:

```text
https://github.com/PingBusiness/PingBusiness/releases/latest/download/pingbusiness-merchant-store-vibe-coding-kit.zip
```

Do not advertise that URL as available until the first non-prerelease asset has
actually been published.
