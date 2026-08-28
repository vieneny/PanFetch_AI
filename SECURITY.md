# Security Policy

[简体中文](SECURITY.zh-CN.md) | English

## Credential storage

PanFetch AI never stores Baidu Access Tokens or LLM API keys in JSON, source code, command-line arguments, or Git configuration. On Windows, credentials are encrypted with DPAPI and saved under the ignored `.secrets` directory.

Do not publish any of the following:

- `.secrets/`
- `local_settings.json`
- OAuth success-page URLs
- request logs containing `access_token`
- temporary download links
- downloaded personal files or generated manifests

## AI trust boundary

Directory names, filenames, share URLs, and LLM responses are treated as untrusted data. The LLM can only propose a structured plan. Downloads and all cloud writes require an explicit UI confirmation; cloud deletion is not registered as a tool. Full-disk share creation uses Baidu's official hosted MCP service and resolves normalized paths to file IDs. Share-link transfer and share-link download remain restricted to `/apps/bdpan/` by the `bdpan` backend contract.

## Reporting a vulnerability

Please open a private security advisory in the Git hosting service. Do not include real credentials, personal file paths, or cloud content in a public issue.
