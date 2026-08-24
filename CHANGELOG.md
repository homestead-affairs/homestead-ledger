# Changelog

## [0.1.1](https://github.com/homestead-affairs/homestead-ledger/compare/v0.1.0...v0.1.1) (2026-08-24)


### Build

* **deps:** bump actions/checkout from 4 to 7 ([f073d28](https://github.com/homestead-affairs/homestead-ledger/commit/f073d2825b676ce436c24be2f8fe71e963ce1d37))
* **deps:** bump actions/checkout from 4 to 7 ([3bc20fb](https://github.com/homestead-affairs/homestead-ledger/commit/3bc20fbf9a5815a68638c719291bb9a315c4d683))
* **deps:** bump actions/download-artifact from 4 to 8 ([47be106](https://github.com/homestead-affairs/homestead-ledger/commit/47be10687c76ff409d5a94a5e787a0056b5d52b4))
* **deps:** bump actions/download-artifact from 4 to 8 ([f99cc35](https://github.com/homestead-affairs/homestead-ledger/commit/f99cc355269532387b75a1f0c7df52464b7ac526))
* **deps:** bump actions/setup-python from 5 to 7 ([60324dd](https://github.com/homestead-affairs/homestead-ledger/commit/60324dda875a1528e4ca471037dc00f5e9232c95))
* **deps:** bump actions/setup-python from 5 to 7 ([366d497](https://github.com/homestead-affairs/homestead-ledger/commit/366d4979303cd958ca958e9801988ff5a0a10e68))
* **deps:** bump actions/upload-artifact from 4 to 7 ([a28f2c5](https://github.com/homestead-affairs/homestead-ledger/commit/a28f2c5f493091e43380a3f12d10f2f00ed124f1))
* **deps:** bump actions/upload-artifact from 4 to 7 ([c845819](https://github.com/homestead-affairs/homestead-ledger/commit/c845819a5a89b845fd7a291298f7edd60fe023e9))

## [0.1.0](https://github.com/rudi193-cmd/homestead-ledger/compare/v0.0.1...v0.1.0) (2026-08-11)


### Added

* bite 0 — bind the seat (store binding, no-egress guard, CI, build plan) ([65dd02f](https://github.com/rudi193-cmd/homestead-ledger/commit/65dd02f071980241481237d59a36909e09752758))
* bite 1 — the books (accounts + transactions pack, registry, --demo) ([811eb47](https://github.com/rudi193-cmd/homestead-ledger/commit/811eb479b5b9e5fcb2f994a2a1a89730a42c3e3b))
* bite 1 — the books (accounts + transactions pack, registry, --demo) ([8489e51](https://github.com/rudi193-cmd/homestead-ledger/commit/8489e51f899d3b5da63c42a380f195d20514fe76))
* bite 2 — what's due (obligations pack, queue, recurring-charge detector) ([4f6c73d](https://github.com/rudi193-cmd/homestead-ledger/commit/4f6c73deeef55d3dc97f44123b8cd6bb928bd8c2))
* bite 3 — the tkinter app, a stdlib theme, and packaging ([5b404d2](https://github.com/rudi193-cmd/homestead-ledger/commit/5b404d298aec9e6cc37f4e86c92a8843f203b1a4))
* bite 4 — CSV import (header auto-detect, fingerprint dedup, --dry-run) ([3096927](https://github.com/rudi193-cmd/homestead-ledger/commit/3096927f580b12dc3d276d269cef9d1943baa32b))
* demo — seed a recurring charge so the detector visibly fires ([e655158](https://github.com/rudi193-cmd/homestead-ledger/commit/e655158932d330b07094de081ef965c1708126eb))
* finish bite 4 — wire the app to the real books; no-egress end-to-end ([1d9b84f](https://github.com/rudi193-cmd/homestead-ledger/commit/1d9b84fd5d86105ef84aa7a61184de708c8d3573))


### Fixed

* detail "Back" returns to the pane it was opened from ([033358d](https://github.com/rudi193-cmd/homestead-ledger/commit/033358d14d66f7a1cc6949375beddb89605fdd8c))


### Changed

* draw theme from the engine, drop the local copy; pin &gt;=0.1.0,&lt;1.0 ([b5c0dcb](https://github.com/rudi193-cmd/homestead-ledger/commit/b5c0dcb0518e86b67335b320154d1b5eefae1b8b))


### Build

* add the ledger's PyPI release chain (release-please + Trusted Publishing) ([1d1e002](https://github.com/rudi193-cmd/homestead-ledger/commit/1d1e002a7b5cd51e2a8280e8e6f21fe8961c4859))
* relicense to Apache-2.0 ([4e7fae9](https://github.com/rudi193-cmd/homestead-ledger/commit/4e7fae92d1f71fd4eb9b198095e2d762384657c2))

## Changelog

All notable changes to `homestead-ledger` are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is maintained by
[release-please](https://github.com/googleapis/release-please), which builds each
entry from the [Conventional Commits](https://www.conventionalcommits.org/)
prefixes on `main` — see `release-please-config.json` for which types cut a
release. The version is derived from the git tag (pyproject `dynamic =
["version"]` + hatch-vcs); there is no version literal in the source to drift.

**Generated entries are sometimes corrected by hand, and this is why.** This repo
merges with merge commits rather than squashing, and GitHub writes the PR title
into the merge commit body — which release-please parses *alongside* the commit
it merges, so one change can produce two identical entries.
`tools/changelog_dedup.py` rebuilds the newest section from the non-merge
commits so the duplicate never ships; see the engine's (`homestead-affairs`)
0.0.2 entry for the failure this closes.
