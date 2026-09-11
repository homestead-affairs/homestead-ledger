# Changelog

## [0.6.0](https://github.com/homestead-affairs/homestead-ledger/compare/v0.5.0...v0.6.0) (2026-09-11)


### Added

* compose and export the household's Chapter 13 debt schedule ([b55424d](https://github.com/homestead-affairs/homestead-ledger/commit/b55424df8308b9d8a9d7cafc73c46e99cb37cb88))
* compose and export the household's Chapter 13 debt schedule ([dc7a816](https://github.com/homestead-affairs/homestead-ledger/commit/dc7a816fb69c550f7a6a421c8e81be13c4fc0660))


### Fixed

* refuse an --out this export cannot honour, and anchor the I-44 carve-out ([1fa0b35](https://github.com/homestead-affairs/homestead-ledger/commit/1fa0b35cdb5945d0555ac49a8c9834d0a1e3de30))

## [0.5.0](https://github.com/homestead-affairs/homestead-ledger/compare/v0.4.0...v0.5.0) (2026-09-11)


### Added

* account instances — a label, never a kind, and one number record ([6fa5d6a](https://github.com/homestead-affairs/homestead-ledger/commit/6fa5d6a3eee809428f954f412f8a294ef6daa40e))


### Fixed

* refuse a retired flag on `transaction add` instead of writing it into the payee ([5dadf2d](https://github.com/homestead-affairs/homestead-ledger/commit/5dadf2d5f21863a6bab8aad27b444fa14f39a521))

## [0.4.0](https://github.com/homestead-affairs/homestead-ledger/compare/v0.3.0...v0.4.0) (2026-09-11)


### Added

* cadence-driven due-date roll-forward and obligation paid-by tracking ([f23a1d8](https://github.com/homestead-affairs/homestead-ledger/commit/f23a1d8cbeef74bf996bd8d0d4b04c343dcc81f9))


### Fixed

* anchor a month-end obligation's due day, and stop a stale paid mark ([d2c53e9](https://github.com/homestead-affairs/homestead-ledger/commit/d2c53e9468ae114d14d60a8f766c300313362dd3))

## [0.3.0](https://github.com/homestead-affairs/homestead-ledger/compare/v0.2.1...v0.3.0) (2026-09-11)


### Added

* three account packs, registry-driven classification, liability sign ([6235ef6](https://github.com/homestead-affairs/homestead-ledger/commit/6235ef69e8db1af341fab2453e2ad3acc6080cc1))


### Fixed

* refuse the declarations this bite added but never read ([1a5f8b9](https://github.com/homestead-affairs/homestead-ledger/commit/1a5f8b9e9a20c69f40b23765d2af5d5a5c7d9797))

## [0.2.1](https://github.com/homestead-affairs/homestead-ledger/compare/v0.2.0...v0.2.1) (2026-09-11)


### Fixed

* drain a refused request body before the socket closes ([8ffd7c1](https://github.com/homestead-affairs/homestead-ledger/commit/8ffd7c19cee3065740a1ac7342d45cd7354b59f5))
* let the declared bank date format win, and stop echoing the cell ([b437790](https://github.com/homestead-affairs/homestead-ledger/commit/b4377906b3c47e66bd1db274f4f6decac0948539))
* parse importer dates to ISO with a per-bank format table ([0e710dc](https://github.com/homestead-affairs/homestead-ledger/commit/0e710dc755dbe7b65c91feeca9f3a421e1895001))

## [0.2.0](https://github.com/homestead-affairs/homestead-ledger/compare/v0.1.1...v0.2.0) (2026-09-11)


### Added

* obligation and transaction entry a household can use itself ([52610d2](https://github.com/homestead-affairs/homestead-ledger/commit/52610d2186f853c4a3d0b2d66ab3f87902400800))


### Fixed

* close the orphaned Records tab, the add-obligation race, and the doors' refusals ([0ee200e](https://github.com/homestead-affairs/homestead-ledger/commit/0ee200eb9e82273c88629158a47dafae6d9d9906))

## [0.1.1](https://github.com/homestead-affairs/homestead-ledger/compare/v0.1.0...v0.1.1) (2026-08-24)


### Build

* **deps:** bump actions/upload-artifact from 4 to 7 ([c845819](https://github.com/homestead-affairs/homestead-ledger/commit/c845819a5a89b845fd7a291298f7edd60fe023e9))
* **deps:** bump actions/download-artifact from 4 to 8 ([f99cc35](https://github.com/homestead-affairs/homestead-ledger/commit/f99cc355269532387b75a1f0c7df52464b7ac526))
* **deps:** bump actions/checkout from 4 to 7 ([3bc20fb](https://github.com/homestead-affairs/homestead-ledger/commit/3bc20fbf9a5815a68638c719291bb9a315c4d683))
* **deps:** bump actions/setup-python from 5 to 7 ([366d497](https://github.com/homestead-affairs/homestead-ledger/commit/366d4979303cd958ca958e9801988ff5a0a10e68))

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
