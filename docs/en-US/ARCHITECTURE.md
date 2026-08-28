# PanFetch AI Architecture

[简体中文](../zh-CN/ARCHITECTURE.md) | English

PanFetch AI separates conversational orchestration, controlled netdisk tools, and deterministic download execution.

```text
PySide6 UI
  |-- AssistantPage: focused Q&A, scope, history, collapsible run details
  |-- Workspace: account, directory browser, file/folder selection, quick commands
  |-- Plan library: SQLite history summaries and plan selection
  |-- Download plan: rules, folder-first candidate tree, destination, confirmation
  |-- Operation plan: target, backend, risk, confirmation, result
  |-- download queue and progress
  |
Application services
  |-- ConfigStore       DPAPI credentials and non-secret settings
  |-- ConversationStore local JSONL turns, tool logs, and atomic session deletion
  |-- PlanHistoryStore  local SQLite summaries and complete preview recovery
  |-- BaiduNetdiskClient directory, search, metadata, upload, file manager
  |-- BaiduMcpClient    official hosted MCP adapter for full-disk sharing
  |-- BdpanBackend      optional native/WSL transfer and share-download adapter
  |-- OperationExecutor confirmed cloud writes only
  |-- Catalog           local SQLite index
  |-- LLMPlanner        OpenAI-compatible plan generation
  |-- NetdiskAgent      allowlisted intent routing and tool execution
  |-- AssistantWorkflow LangGraph state + LangChain Runnable nodes
  |-- rules             deterministic include/exclude evaluation
  |-- DownloadManager   path mapping, concurrency, retry, integrity
  |
Baidu Netdisk API / LLM API / local filesystem
```

`AssistantPage` owns only presentation widgets and keyboard behavior. `MainWindow` wires those widgets to application services and owns orchestration state. This keeps the high-change Q&A layout separate from the already large workspace and operation controller.

## Assistant graph

```text
START
  |
  v
route    LLM/local intent -> one allowlisted AgentDecision
  |
  v
tool     read tools / prepare_download / prepare_write_operation
  |
  v
answer   OpenAI-compatible SSE -> thinking and answer events
  |
  v
END      persist request, response, scope, action and logs locally
```

Each node is wrapped by LangChain `RunnableLambda` and composed with LangGraph `StateGraph`. The compiled invocation is decorated with LangSmith `traceable`; LangSmith network tracing is inactive unless the standard `LANGSMITH_TRACING` and credential environment variables are configured.

Each assistant run owns a cancellation token and monotonically increasing UI run ID. Interrupting invalidates the run ID immediately, closes the active streaming response, and causes graph and scan checkpoints to raise cancellation. Late events from an older worker are ignored, so a new question can start without waiting for a stale request to time out.

Session deletion is enabled only while the assistant is idle and a history entry is selected. `ConversationStore` removes every turn matching that `session_id` and atomically replaces the JSONL file from a same-directory temporary file, preserving malformed lines and all unrelated sessions.

Scope is explicit state. `/` means global netdisk, while current and custom scopes provide a normalized absolute remote path. Recent conversation turns are passed to both routing and download planning, and candidate paths from the previous result support follow-up requests such as “download the PDFs among those.”

## Safety contract

The LLM returns a `SelectionPlan` JSON object. It never receives credentials or download links and cannot invoke filesystem operations. Every remote path is normalized, every local destination is resolved under an absolute root, and downloads use short temporary names plus atomic replacement.

The Agent returns exactly one allowlisted JSON action per turn. Read-only tools may execute immediately. `prepare_download` creates a download preview; every upload, move, copy, rename, mkdir, share, transfer, or share-link download creates an `OperationPlan`. Neither plan executes until the user confirms it in its dedicated page. Delete is not registered.

Native Python/OpenAPI code handles account, quota, list, search, metadata, upload, mkdir, move, copy, rename and direct downloads. Full-disk share creation resolves normalized paths to file IDs and calls the official hosted MCP `file_sharelink_set` tool with the existing OAuth token. `BdpanBackend` remains responsible for share transfer and share-link download; it is auto-detected and can use a native `bdpan` executable or WSL. Official `bdpan-storage` currently does not support native Windows, and its remote scope remains restricted to `/apps/bdpan/`.

`inspect` identifies content from directory names, file names, extensions, sizes, and bounded path samples. It does not silently download or parse remote document bodies.

## Provider compatibility

The LLM adapter supports OpenAI-compatible `chat/completions` and `responses` endpoints. Presets only populate Base URL, API mode, and model examples. Users can select the API-key header name and prefix, override all non-secret fields, and add non-secret custom JSON headers; the API key is always stored separately with DPAPI.

SSE is consumed as raw bytes and decoded explicitly as UTF-8, avoiding `requests` charset guesses. `ConversationStore` repairs previously persisted UTF-8-as-Latin-1 mojibake only when a reversible conversion lowers a conservative corruption score, then atomically replaces the JSONL file.

## Download lifecycle

1. Scan source paths and build a preview, then persist its summary and complete candidate payload locally.
2. Select a historical plan; a worker reads SQLite and parses the complete JSON while the UI thread remains responsive.
3. Restore a collapsed, checkable folder tree. Only top-level Qt items are created initially; expanding a folder materializes its direct children.
4. Expand any manually selected workspace folders recursively in a background worker and deduplicate files.
5. Select a local destination and confirm the folder-first content summary, file count, byte size, and organization mode.
6. Query at most ten file IDs per Baidu metadata request.
7. Download with 1-10 workers and up to three attempts per file.
8. Stream to `.part-*`, calculate SHA-256, and verify expected size.
9. Atomically move the completed file and write `PanFetch AI下载清单.json`.

Selection keys and the complete file map live in the tree's data model rather than in visible Qt leaf items. Select all, clear, and invert therefore cover collapsed descendants, while only final checked files reach the downloader. Opening a plan does not duplicate its candidate files into the workspace table.

## Local data

Credentials live under `.secrets/`; non-secret settings use `local_settings.json`; catalog, conversation, and plan-history data use `.panfetch-ai/`. The plan library reads summaries only and restores full candidates in a worker when a detail is opened. All of these paths are ignored by Git. Logs are redacted but still should not be committed.
