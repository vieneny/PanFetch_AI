# Command Reference

All commands run inside the project environment and reuse the desktop application's encrypted authorization.

## Start the desktop application

```powershell
uv run panfetch-ai
```

On Windows, double-click `启动PanFetch AI.vbs` for a console-free launch. Use `诊断启动PanFetch AI.bat` when installing dependencies or diagnosing startup failures.

## Check authorization and account quota

```powershell
uv run panfetch-ai-cli status
```

## View a directory

```powershell
uv run panfetch-ai-cli list "/示例目录"
```

## View a directory tree

```powershell
uv run panfetch-ai-cli tree "/示例目录" --depth 3 --limit 2000
uv run panfetch-ai-cli tree "/示例目录" --depth -1 --limit 0
```

## Search by filename

```powershell
uv run panfetch-ai-cli search "关键词" "/示例目录" --limit 100
```

## Identify chapter directories

```powershell
uv run panfetch-ai-cli chapters "/示例目录"
```

## Export an inventory

```powershell
uv run panfetch-ai-cli export "/示例目录" --depth -1 --limit 0 --format csv --output "目录清单.csv"
```

The desktop application's **快捷查看** tab provides the same common workflows as buttons.
