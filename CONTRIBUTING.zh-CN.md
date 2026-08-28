# 贡献指南

简体中文 | [English](CONTRIBUTING.md)

## 开发环境

```powershell
uv sync --python 3.12 --system-certs
uv run pytest
uv run panfetch-ai
```

## 变更要求

- 云端写操作必须经过清晰的预览与人工确认；不得绕过操作计划。
- 不得提交凭据、下载内容、个人目录结构、清单、截图或本机配置。
- 过滤、路径映射、下载完整性和服务兼容性变更需要有针对性的测试。
- 网络和文件系统操作必须放在后台任务中，不能阻塞 Qt 主线程。
- 修改用户行为时同步更新中文与英文文档。
- 本仓库优先使用中文提交信息。

提交前运行：

```powershell
uv run pytest
git status --short --ignored
git diff --check
```
