# Packaging

Mirrors the engine's own packaging (`homestead/packaging/README.md`):
"self-contained" is a build-system property, so it is built alongside the
app rather than deferred — a double-clickable artifact, not a zip file with
instructions.

```bash
pip install pyinstaller
pip install .
pyinstaller packaging/homestead-ledger.spec
```

The built artifact lands at `dist/HomesteadLedger` (`dist/HomesteadLedger.exe`
on Windows), one file, no console, opening on the cover. Smoke-check it the
way CI does, without a display:

```bash
dist/HomesteadLedger --smoke
```

## What is not done here, and needs your certificates

Signing cannot be done in CI without secrets, and is listed rather than
faked:

- **macOS** — Developer ID application certificate, `codesign`, then
  `notarytool submit --wait` and `stapler staple`. Unsigned, Gatekeeper
  refuses.
- **Windows** — an Authenticode certificate and `signtool`. Unsigned,
  SmartScreen warns until reputation accrues.
- **Linux** — no signing requirement; ship the artifact.

Until these are wired the artifact is a build, not a release, and nothing
should describe it as installable by a household that isn't already trusting
an unsigned binary.
