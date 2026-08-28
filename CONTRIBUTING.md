# Contributing

[简体中文](CONTRIBUTING.zh-CN.md) | English

Thank you for improving PanFetch AI.

## Development setup

```powershell
uv sync --python 3.12 --system-certs
uv run pytest
uv run panfetch-ai
```

## Change requirements

- Keep cloud operations read-only unless the UI clearly previews and confirms the action.
- Never add credentials, downloaded files, manifests, screenshots containing private paths, or local configuration to Git.
- Add focused tests for filtering, path mapping, download integrity, and provider compatibility.
- Keep the desktop UI responsive; network and filesystem work belongs in background workers.
- Update both Chinese and English documentation whenever behavior, setup, or architecture changes.
- Prefer Chinese commit messages for this repository.

Before staging, run:

```powershell
uv run pytest
git status --short --ignored
git diff --check
```
