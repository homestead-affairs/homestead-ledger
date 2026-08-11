# Changelog

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
