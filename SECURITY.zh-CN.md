# 安全策略

简体中文 | [English](SECURITY.md)

## 凭据保存

PanFetch AI 不把百度 Access Token 或 LLM API Key 写入 JSON、源码、命令行参数或 Git 配置。Windows 下使用 DPAPI 加密凭据，并保存在已忽略的 `.secrets` 目录中。

禁止公开以下内容：

- `.secrets/`
- `local_settings.json`
- OAuth 成功页完整 URL
- 包含 `access_token` 的请求日志
- 临时下载直链
- 下载的个人文件或生成的清单

## AI 信任边界

目录名、文件名、分享链接和 LLM 返回都属于不可信输入。LLM 只能提出结构化计划；下载和全部云端写操作都需要明确的 UI 确认，删除能力未注册。

全盘分享通过百度官方托管 MCP，把规范化路径解析为文件 ID 后执行。分享链接转存和下载继续遵守 `bdpan` 后端的 `/apps/bdpan/` 范围限制。

## 报告安全问题

请通过 Git 托管平台的私有 Security Advisory 报告。公开 Issue 中不得包含真实凭据、个人路径或网盘内容。
