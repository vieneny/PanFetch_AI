# PanFetch AI

[简体中文](README.md) | English

PanFetch AI is an open-source Windows desktop application for exploring, managing, downloading, and organizing Baidu Netdisk content with an AI assistant. It combines Baidu Netdisk OpenAPI, a configurable LLM, Baidu's official MCP service, the optional `bdpan` backend, and deterministic safety checks. Users describe an objective in natural language, inspect the resulting structured plan, and explicitly confirm every download or cloud write.

> PanFetch AI is currently Alpha software. Cloud deletion is not exposed. Upload, move, copy, rename, mkdir, share, transfer, and download operations always stop at a dedicated confirmation page before execution.

## Key capabilities

- Display the authorized account name, UID, avatar, membership tier, and storage quota.
- Ask contextual questions against the entire netdisk, the current workspace directory, or a custom remote path.
- Stream reasoning summaries and final answers, keep conversation context, and interrupt an active AI run immediately.
- Store local conversation history, requests, responses, and tool logs for later review.
- Orchestrate allowlisted tools with LangChain and LangGraph, with optional LangSmith tracing.
- Browse directories, jump to paths, render bounded directory trees, search by keyword or type, identify chapter folders, and export CSV inventories.
- Upload local files or directories with 4 MiB multipart uploads and background progress.
- Move, copy, rename, and share remote content, and create nested directories.
- Create 1-day, 7-day, 30-day, or permanent share links for files and folders anywhere in the authorized netdisk through Baidu's official MCP service.
- Use the optional `bdpan` backend for share-link transfer and share-link download workflows.
- Generate download plans from source paths, desired content, exclusions, destination, and organization rules.
- Connect to OpenAI, DeepSeek, SiliconFlow, Ollama, and other OpenAI-compatible providers.
- Support both `chat/completions` and `responses`, configurable API-key headers and prefixes, and additional non-secret headers.
- Run 1-10 concurrent downloads with retry, pause, resume, cancel, existing-file skip, size validation, and SHA-256 manifests.
- Build a local SQLite catalog to avoid repeated remote scans.
- Encrypt the Baidu Access Token and LLM API key with Windows DPAPI.
- Sign out of Baidu Netdisk, reauthorize the account, and test an unsaved LLM configuration before saving it.

## Workflow

```text
AI Q&A (global / current directory / custom path)
   |
   v
LangGraph: route -> tool -> answer
   |
   +--> LangChain Runnable -> controlled read tool / cloud-operation proposal
   |
   +--> LLMPlanner / local rules -> SelectionPlan JSON
   |
   v
Streaming answer + local history -> dedicated plan page -> user confirmation
   |
   v
DownloadManager -> temporary file -> size check -> atomic replace -> SHA-256 manifest
```

The LLM never receives an Access Token, API key, or temporary download URL. It cannot execute arbitrary commands or filesystem operations. Remote paths, extension filters, local destinations, and download results are validated again by deterministic application code.

## Technology stack

| Layer | Technology | Responsibility |
|---|---|---|
| Desktop UI | PySide6 / Qt | AI Q&A, workspace, plan review, progress, and settings |
| Netdisk integration | Baidu Netdisk OpenAPI / official MCP / Requests | Account, quota, directory, search, upload, metadata, download, and full-disk sharing |
| Optional Skill backend | `bdpan-storage` / WSL | Share-link transfer and download |
| Agent orchestration | LangChain / LangGraph | Runnable nodes, state graph, conversation context, and streaming events |
| Observability | LangSmith | Optional graph-run tracing |
| AI adapter | OpenAI-compatible HTTP APIs | Agent decisions and structured download plans |
| Deterministic execution | Python dataclasses and rules | Path, type, size, keyword, exclusion, and plan validation |
| Local index | SQLite | Cached remote file metadata |
| Credential protection | Windows DPAPI / pywin32 | Encrypted Access Token and API key storage |
| Environment and build | uv / PyInstaller | Reproducible dependencies, tests, and console-free EXE builds |

## Interface structure

```text
AI Q&A
+----------------+--------------------------------------------------+
| Conversations  | Scope / contextual conversation / composer       |
|                | Run details (reasoning + tool log, collapsed)     |
+----------------+--------------------------------------------------+

Netdisk workspace
+----------------------+------------------------+--------------------+
| Account and folders  | File/folder table      | Quick actions      |
+----------------------+------------------------+--------------------+
| Download progress, pause/resume/cancel, and runtime log            |
+--------------------------------------------------------------------+

Download plan library                 Download plan detail
+-------------------------------+     +------------------------------------+
| Time / request / source / size| --> | folder tree / rules / destination  |
+-------------------------------+     +------------------------------------+

Operation plan
+--------------------------------------------------------------------+
| Sources, target, backend, risk, and explicit confirmation           |
+--------------------------------------------------------------------+
```

The application opens directly on AI Q&A. The home page intentionally keeps only the conversation list, scope, conversation, compact status, composer, and send/interrupt actions visible. User prompts use a restrained cyan band, while AI responses use a green identity label and neutral body text. Reasoning summaries and tool logs live in the collapsed **Run details** panel. Large download and cloud-operation plans open on dedicated pages instead of accumulating in the conversation view.

## AI Q&A and Agent tools

When no path is selected, the assistant works against the entire authorized netdisk. The scope can also follow the workspace's current directory or use a normalized custom absolute path. Each conversation includes recent context. Press `Enter` to send and `Shift+Enter` for a new line. **Interrupt** invalidates the current run, closes its streaming response, and allows a new request without waiting for stale events.

The internal workflow is `route -> tool -> answer`. Agent execution and AI plans are part of the same controlled graph: the Agent chooses one allowlisted action, while download and cloud-write requests produce structured plans for review.

| Tool | Behavior |
|---|---|
| `account` | Read the authorized account, membership, and quota |
| `list` | List direct children of a directory |
| `search` | Recursively search by keyword or common content type |
| `tree` | Build a bounded directory tree |
| `chapters` | Identify likely chapter folders at the current level |
| `inspect` | Summarize content from paths, names, types, sizes, and bounded samples |
| `prepare_download` | Generate a download preview without downloading |
| `prepare_upload` | Prepare a local file or directory upload |
| `prepare_move` / `prepare_copy` | Prepare a move or copy operation |
| `prepare_rename` / `prepare_mkdir` | Prepare rename or directory creation |
| `prepare_share` | Prepare a full-disk share link with a selected validity period |
| `prepare_transfer` | Prepare share-link transfer into the user's netdisk |
| `prepare_share_download` | Prepare transfer followed by a local download |

The Agent returns one JSON action from this allowlist. Paths, names, URLs, lengths, depth, and result counts are validated. Cloud-write tools produce an `OperationPlan`; they do not execute during model inference. The current `inspect` tool uses metadata and directory structure and does not silently download and parse document bodies.

Conversation history is local-only at `.panfetch-ai/assistant_history.jsonl`. Newly generated download plans are stored in `.panfetch-ai/download_plans.db` with their request, rules, and candidate paths. Both are ignored by Git. The plan library reads lightweight summaries first and restores the complete preview only after a plan is opened. Candidate files are grouped into a checkable folder tree; folders are collapsed by default and only checked leaf files reach the downloader.

Streaming bytes are explicitly decoded as UTF-8. On startup, a conservative atomic repair handles old UTF-8-as-Latin-1 history corruption without changing valid Chinese or English text.

LangSmith is optional:

```powershell
$env:LANGSMITH_TRACING = "true"
$env:LANGSMITH_API_KEY = "<langsmith-api-key>"
$env:LANGSMITH_PROJECT = "PanFetch-AI"
uv run panfetch-ai
```

## Backend capability boundaries

Logging in to the Baidu Netdisk Windows client is not API authorization. PanFetch AI uses the OAuth Access Token saved in Settings and does not read the desktop client's cookies or login session.

| Capability | Backend | Remote scope | Requirement |
|---|---|---|---|
| Account, quota, list, search, upload, move, copy, rename, mkdir | Baidu Netdisk OpenAPI | Entire authorized netdisk | OAuth scopes include `basic` and `netdisk` |
| Create share link | Official hosted MCP `file_sharelink_set` | Entire authorized netdisk except `/` itself | Valid OAuth token and reachable MCP service |
| Ordinary file download | OpenAPI metadata and download flow | Entire authorized netdisk | Valid OAuth token |
| Share-link transfer and download | `bdpan-storage` / WSL | `/apps/bdpan/` | `bdpan` installed and logged in inside WSL |

**Check connections** reports Baidu OAuth, the configured LLM, official MCP full-disk sharing, and optional `bdpan` transfer/download separately. An unavailable optional backend does not disable unrelated capabilities.

### Full-disk sharing

Older builds used `bdpan share`, which restricted share creation to `/apps/bdpan/`. PanFetch AI now uses the official MCP `file_sharelink_set` tool:

```text
selected file or folder anywhere in the netdisk
  -> OperationPlan and explicit confirmation
  -> OpenAPI parent listing and exact normalized path match
  -> resolve fs_id
  -> official MCP file_sharelink_set
  -> validate link, extraction code, and validity period
  -> show result with one-click copy
```

This flow does not use Windows-client cookies, BDUSS, unofficial endpoints, or the optional `bdpan` installation. The generated link and extraction code can be copied together from the operation result page.

## Requirements

- Windows 10 or Windows 11
- Python 3.12-3.14
- [uv](https://docs.astral.sh/uv/)
- A Baidu Netdisk OAuth Access Token with `basic` and `netdisk`
- Optional: `bdpan` installed and logged in inside WSL for share-link transfer and download

## Install and run

```powershell
git clone <repository-url>
cd panfetch-ai
uv sync --python 3.12 --system-certs
uv run pytest
uv run panfetch-ai
```

On Windows, double-click `启动PanFetch AI.vbs` for a console-free launch. Run `诊断启动PanFetch AI.bat` when installing dependencies or diagnosing startup failures.

## Baidu authorization

Open **Settings > Baidu Netdisk**, then select **Open authorization page**. After login and authorization, paste the Access Token from the success page into Settings and save. The token is encrypted for the current Windows user with DPAPI and written to `.secrets/baidu-token.dpapi`.

The account card supports reauthorization and sign-out. Signing out removes only the local authorization and does not modify remote files. Production or redistributed builds should use a Client ID created in the Baidu Netdisk Open Platform; any default trial Client ID may change independently.

The primary official endpoints are:

- Authorized user info: `/rest/2.0/xpan/nas?method=uinfo&openapi=xpansdk`
- Quota: `/api/quota?openapi=xpansdk`
- Full-disk sharing: official MCP tool `file_sharelink_set`

Reference: [baidu-netdisk/mcp](https://github.com/baidu-netdisk/mcp)

A token can also be supplied for the current process:

```powershell
$env:BAIDU_NETDISK_ACCESS_TOKEN = "<access-token>"
uv run panfetch-ai
```

Never commit a token, a complete OAuth success URL, or a request log containing `access_token`.

## LLM configuration

The LLM is optional. Local deterministic rules still support paths, extensions, common exclusions, and organization modes without an LLM.

| Setting | Meaning |
|---|---|
| Provider preset | OpenAI, DeepSeek, SiliconFlow, Ollama, or Custom |
| Base URL | Provider API root, usually ending in `/v1` |
| API mode | `chat/completions` or `responses` |
| Model | Provider-supported model ID |
| API key | DPAPI-encrypted, or supplied with `PANFETCH_LLM_API_KEY` |
| Key header | `Authorization` by default; `x-api-key`, `api-key`, and others are supported |
| Key prefix | `Bearer` by default; leave empty for a raw key |
| Custom headers | Non-secret JSON object such as an organization or gateway routing header |

**Test connection** uses the current unsaved form values in a minimal conversation request, so the Base URL, endpoint mode, model, and API key can be verified before saving. It never logs the key or request authorization headers.

## Usage

1. On AI Q&A, choose the entire netdisk, current workspace directory, or a custom path.
2. Ask where material is located, what a directory contains, or request selected formats for download.
3. Continue in context or restore an earlier local conversation from the left rail.
4. Open a generated download or operation plan on its dedicated page.
5. Inspect sources, target, backend, candidates, exclusions, and risk information.
6. Confirm explicitly; pause, resume, or cancel downloads when needed.

Organization modes include preserving the source tree, grouping by source directory, year, or file type.

## CLI

The CLI and desktop application share the same encrypted authorization and local settings:

```powershell
uv run panfetch-ai-cli status
uv run panfetch-ai-cli list "/example"
uv run panfetch-ai-cli tree "/example" --depth 3 --limit 2000
uv run panfetch-ai-cli search "keyword" "/example" --limit 100
uv run panfetch-ai-cli chapters "/example"
uv run panfetch-ai-cli export "/example" --depth -1 --limit 0 --format csv --output "inventory.csv"
```

See the [English command reference](docs/en-US/COMMANDS.md), [architecture document](docs/en-US/ARCHITECTURE.md), and [documentation index](docs/README.md).

## Project structure

```text
panfetch_ai/
  app.py                  Qt entry point and global exception handling
  cli.py                  command-line entry point
  logging_setup.py        dated and redacted runtime logs
  core/
    config.py             configuration, DPAPI secrets, and path conventions
    netdisk.py            Baidu Netdisk OpenAPI client
    baidu_mcp.py          official hosted MCP full-disk sharing adapter
    bdpan.py              native/WSL detection, isolation, and command adapter
    cancellation.py       cooperative cancellation for chat, scan, and HTTP
    operations.py         cloud-operation plans, validation, and executor
    agent.py              Agent intent and allowlisted tools
    assistant_workflow.py LangGraph state, LangChain nodes, LangSmith tracing
    history.py            local JSONL conversations and tool logs
    plan_history.py       SQLite plan summaries and complete preview recovery
    plan_preview.py       folder-first final download summaries
    models.py             remote item and download-plan models
    planner.py            LLM protocol adapter and local parsing
    rules.py              deterministic filtering and preview generation
    structure.py          directory tree, chapters, and CSV output
    catalog.py            local SQLite index
    downloader.py         concurrency, retries, validation, and atomic writes
  ui/
    assistant_page.py     focused AI Q&A and collapsed run details
    download_plan_tree.py checkable folder tree and parent-child state
    plan_history_page.py  historical download plan list
    main_window.py        workspace, download plan, and operation controller
    settings_dialog.py    Baidu, download, and LLM settings
    workers.py            Qt thread-pool task wrappers
    styles.py             application styles
tests/                    core and UI smoke tests
scripts/                  build and UI rendering helpers
docs/                     bilingual architecture and command references
```

Detailed ownership and trust boundaries are documented in [Architecture](docs/en-US/ARCHITECTURE.md).

## Local data

These paths are ignored by Git:

| Path | Content |
|---|---|
| `.secrets/` | DPAPI-encrypted Baidu Token and LLM API key |
| `local_settings.json` | Download root, concurrency, and non-secret LLM settings |
| `.panfetch-ai/` | SQLite catalog, download plan history, and AI conversations |
| `downloads/` | Default download destination |
| `exports/` | Exported inventories |
| `logs/` | Redacted runtime logs |
| `build/`, `dist/` | PyInstaller build output |
| `artifacts/` | Local UI verification screenshots |

Credentials, downloaded content, private remote structures, manifests, and machine-specific settings are not part of the open-source repository. See [Security](SECURITY.md).

## Development and testing

```powershell
uv sync --python 3.12 --system-certs
uv run pytest
uv run python -m panfetch_ai
```

Tests cover configuration serialization, DPAPI boundaries, response parsing, account and quota APIs, official MCP payloads, multipart upload, cloud-write confirmation, path isolation, deterministic selection, recursive directory expansion, download layout, LangGraph orchestration, UTF-8 streaming, history repair, and multi-page UI construction.

## Build a Windows EXE

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

`panfetch-ai.spec` uses `console=False` and produces `dist\PanFetch AI.exe`. Do not distribute `.secrets/`, `local_settings.json`, logs, downloaded content, or any private screenshot with the executable.

## Contributing and license

Run `uv run pytest`, `git status --short --ignored`, and `git diff --check` before submitting changes. Behavior, setup, and architecture changes must update both language versions. See [Contributing](CONTRIBUTING.md).

PanFetch AI is licensed under the [MIT License](LICENSE). Binary distribution of PySide6 also requires compliance with the applicable Qt for Python LGPL, GPL, or commercial terms.
