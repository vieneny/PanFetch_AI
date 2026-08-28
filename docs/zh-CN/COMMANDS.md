# 命令行参考

简体中文 | [English](../en-US/COMMANDS.md)

所有命令都在项目环境中运行，并复用桌面端以 DPAPI 加密保存的百度网盘授权。

## 启动桌面应用

```powershell
uv run panfetch-ai
```

Windows 日常启动可双击 `启动PanFetch AI.vbs`，不会弹出控制台。安装依赖或排查启动错误时使用 `诊断启动PanFetch AI.bat`。

## 查看授权、账号和容量

```powershell
uv run panfetch-ai-cli status
```

输出账号、UID、会员类型、容量、下载根目录和当前 LLM 配置，不输出 Token 或 API Key。

## 查看目录

```powershell
uv run panfetch-ai-cli list "/示例目录"
uv run panfetch-ai-cli list "/示例目录" --limit 200
```

## 递归查看目录树

```powershell
uv run panfetch-ai-cli tree "/示例目录" --depth 3 --limit 2000
uv run panfetch-ai-cli tree "/示例目录" --depth -1 --limit 0
```

`--depth -1` 表示不限深度，`--limit 0` 表示不限数量。大型目录可能需要较长时间。

## 按文件名搜索

```powershell
uv run panfetch-ai-cli search "关键词" "/示例目录" --limit 100
```

## 识别章节目录

```powershell
uv run panfetch-ai-cli chapters "/示例目录"
```

章节识别依据当前层级的目录名称和自然排序，不会下载文件正文。

## 导出目录清单

```powershell
uv run panfetch-ai-cli export "/示例目录" --depth -1 --limit 0 --format csv --output "目录清单.csv"
uv run panfetch-ai-cli export "/示例目录" --depth 3 --limit 2000 --format json --output "目录清单.json"
```

桌面端“快捷查看”页面提供目录、目录树、章节识别、索引和导出的图形入口。
