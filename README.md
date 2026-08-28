# PanFetch AI

PanFetch AI 是一个面向 Windows 的开源 AI 百度网盘管理、下载与本地整理工具。它将百度网盘 OpenAPI、可配置的大语言模型、`bdpan` Skill 后端和确定性安全规则组合在桌面界面中：用户用自然语言描述目标，程序生成可核对的结构化计划，确认后才执行下载或网盘写操作。

> 当前处于 Alpha 阶段。不提供删除工具；上传、移动、复制、重命名、创建文件夹、分享和转存均须在独立计划页人工确认。

## 主要能力

- 自动读取已鉴权账号的昵称、UID、头像、会员类型和网盘容量，并显示在网盘工作台。
- AI 问答页面提供上下文对话，可按全局网盘、当前目录或指定路径提问，并流式区分思考、工具轨迹和最终回答；运行中可随时中断。
- 本地保存会话历史、请求、回答和执行日志，可随时回看并继续追问。
- 使用 LangChain + LangGraph 编排受控工具，通过可选 LangSmith tracing 观测每次运行。
- 浏览目录、按路径跳转、递归查看目录树、按关键词或文件类型搜索、章节识别和 CSV 导出。
- 上传本地文件或文件夹，支持 4 MiB 分片和后台进度反馈。
- 移动、复制、重命名网盘内容，以及创建多级文件夹。
- 通过百度官方 MCP 为全盘任意文件或文件夹生成 1 天、7 天、30 天或永久分享链接。
- 通过可选 `bdpan` 后端下载分享链接并转存分享内容。
- 使用自然语言描述来源路径、包含内容、排除条件、保存位置和整理方式。
- 支持 OpenAI、DeepSeek、硅基流动、Ollama 及其他 OpenAI-compatible 服务。
- 同时兼容 `chat/completions` 与 `responses` 接口，可配置模型、请求头、Key 请求头和前缀。
- LLM 只生成 JSON 下载计划，下载前展示文件数量、总大小、排除原因和目标路径；文件和文件夹都可作为下载入口。
- 支持 1-10 个并发任务、失败重试、暂停、继续、取消、已存在文件跳过和大小校验。
- 下载时计算 SHA-256，并生成可审计的下载清单。
- 通过 SQLite 建立本地目录索引，减少重复扫描。
- 百度 Access Token 和 LLM API Key 使用 Windows DPAPI 加密保存。
- 支持百度网盘退出、重新授权，以及用当前未保存的 LLM 配置检测真实对话接口。

## 工作流程

```text
AI 问答（全局 / 当前目录 / 指定路径）
   |
   v
LangGraph: route -> tool -> answer
   |
   +--> LangChain Runnable -> 受控读取工具 / 写操作计划
   |
   +--> LLMPlanner / 本地规则 -> SelectionPlan(JSON)
   |
   v
流式思考/回答 + 历史与日志 -> 独立下载/操作计划详情 -> 用户确认
   |
   v
DownloadManager -> 临时文件 -> 大小校验 -> 原子落盘 -> SHA-256 清单
```

LLM 不接收 Access Token、API Key 或下载直链，也不能直接执行命令和文件操作。所有远程路径、扩展名过滤、本地目标目录及下载结果都由程序代码再次校验。

## 技术栈

| 层级 | 技术 | 作用 |
|---|---|---|
| 桌面界面 | PySide6 / Qt | AI 问答、三栏工作台、下载与写操作计划、后台任务与设置 |
| 网盘接入 | 百度网盘 OpenAPI / 官方 MCP / Requests | 用户信息、容量、全盘分享、目录、搜索、上传、文件管理、元数据与下载 |
| Skill 后端 | `bdpan-storage` / WSL | 分享链接下载与分享转存 |
| Agent 编排 | LangChain / LangGraph | Runnable 节点、状态图、上下文和流式事件 |
| 可观测性 | LangSmith | 可选的图运行追踪，不配置也可本地使用 |
| AI 适配 | OpenAI-compatible HTTP API | 生成 Agent 动作与结构化下载计划 |
| 规则执行 | Python dataclass + 确定性规则 | 路径、类型、大小、关键词和排除项校验 |
| 本地索引 | SQLite | 保存已扫描的目录和文件元数据 |
| 凭据保护 | Windows DPAPI / pywin32 | 加密 Access Token 与 LLM API Key |
| 环境与构建 | uv / PyInstaller | 依赖锁定、测试和无控制台 EXE 打包 |

## 界面结构

```text
AI 问答页面
┌──────────────┬──────────────────────────────┬──────────────────┐
│ 历史会话     │ 上下文对话 / 路径范围        │ 思考阶段 / 工具日志│
└──────────────┴──────────────────────────────┴──────────────────┘

网盘工作台
┌──────────────────┬───────────────────────────┬─────────────────────┐
│ 账号、容量、目录 │ 文件与文件夹列表          │ 快捷查看            │
├──────────────────┴───────────────────────────┴─────────────────────┤
│ 下载进度、暂停/继续/取消、运行日志                                │
└───────────────────────────────────────────────────────────────────┘

下载计划详情
┌────────────────────────────────────────────────────────────────────┐
│ 来源与筛选规则 / 完整候选表格 / 保存位置 / 确认下载               │
└────────────────────────────────────────────────────────────────────┘

网盘操作计划
┌────────────────────────────────────────────────────────────────────┐
│ 操作来源与目标 / 执行后端 / 风险提示 / 二次确认 / 执行结果         │
└────────────────────────────────────────────────────────────────────┘
```

程序启动后会自动调用百度网盘的用户信息与容量接口；授权有效时，左侧显示头像、昵称、会员类型、UID、已用容量、总容量和剩余容量。

## AI 问答页面

AI 问答是程序默认页面。未选择路径时作用域为整个网盘，也可切换为工作台当前目录或手动指定绝对路径。每个会话会带上最近上下文；模型流式返回时，思考摘要进入独立区域，最终回答逐字进入对话，路径、路由、工具调用和扫描过程进入运行轨迹。

对话输入框使用 `Enter` 发送，`Shift+Enter` 换行。发送后“中断”按钮启用；中断会立即停止界面接收旧请求的事件、关闭活动流式响应，并把本次状态记录为已中断，随后可以直接发起新问题。

内部使用 LangGraph 的 `route -> tool -> answer` 状态图。LangChain `RunnableLambda` 包装每个节点，Agent 负责受控工具路由，AI 下载计划是 `prepare_download` 的结构化结果，两者属于同一条编排链路。下载请求只生成候选，仍会停在人工确认步骤。当前工具白名单包括：

| 工具 | 行为 |
|---|---|
| `account` | 查看已鉴权账号、会员类型和容量 |
| `list` | 查看指定目录的直接子项 |
| `search` | 在指定路径按关键词、图片、文档等类型递归搜索 |
| `tree` | 生成有限深度和数量的目录树 |
| `chapters` | 识别当前层级的章节目录 |
| `inspect` | 根据目录结构、文件名、格式、大小和样例识别资料组成 |
| `prepare_download` | 生成下载候选与预览，不直接下载 |
| `prepare_upload` | 准备上传本地文件或文件夹 |
| `prepare_move` / `prepare_copy` | 准备移动或复制网盘内容 |
| `prepare_rename` / `prepare_mkdir` | 准备重命名或创建文件夹 |
| `prepare_share` | 准备为全盘任意文件或文件夹创建指定有效期的分享链接 |
| `prepare_transfer` | 准备将分享内容转存到自己的网盘 |
| `prepare_share_download` | 准备先转存分享内容再下载到本地 |

Agent 是助手内部的受控执行能力，AI 计划是下载或网盘变更请求产生的结构化结果。LLM 只能返回白名单中的 JSON 动作，参数还会经过路径、名称、URL、长度、深度和数量限制；目录名、文件名和模型输出均按不可信数据处理。写操作只生成 `OperationPlan`，不会在模型调用阶段执行。

当前“识别资料内容”基于网盘元数据和目录结构，不会在未确认的情况下下载并解析文档正文。历史记录保存在 `.panfetch-ai/assistant_history.jsonl`，只存在本机，清理该文件即可清除历史。

SSE 流按原始字节使用 UTF-8 解码，不依赖服务端是否返回 `charset`。启动时会检测并原子修复旧历史中典型的 UTF-8/Latin-1 乱码，不会修改正常中文和英文文本。

LangSmith 为可选能力。需要追踪图运行时设置：

```powershell
$env:LANGSMITH_TRACING = "true"
$env:LANGSMITH_API_KEY = "<langsmith-api-key>"
$env:LANGSMITH_PROJECT = "PanFetch-AI"
uv run panfetch-ai
```

该设计结合了百度官方 [bdpan-storage](https://github.com/baidu-netdisk/bdpan-storage) 的自然语言工具路由、转存能力与凭据隔离原则，以及 [baidu-netdisk/mcp](https://github.com/baidu-netdisk/mcp) 的全盘分享和 4 MiB 分片上传能力。PanFetch AI 不提供删除工具，其他云端修改均要求人工确认。

## 后端能力边界

PanFetch AI 不把“已登录百度网盘 Windows 客户端”等同于 API 授权。目录、账号、上传、下载和全盘分享使用设置页保存的 OAuth Access Token；Windows 客户端登录状态不会被读取，也不会复用客户端 Cookie。

| 能力 | 执行后端 | 远端范围 | 前置条件 |
|---|---|---|---|
| 账号、容量、列表、搜索、上传、移动、复制、重命名、新建目录 | 百度网盘 OpenAPI | 已授权账号全盘 | OAuth Token 包含 `basic`、`netdisk` |
| 创建分享链接 | 百度官方托管 MCP `file_sharelink_set` | 已授权账号全盘，不能直接选择根目录 `/` | OAuth Token 有效且 MCP 服务可达 |
| 普通文件下载 | OpenAPI 元数据与下载链路 | 已授权账号全盘 | OAuth Token 有效 |
| 分享链接转存、分享链接下载 | `bdpan-storage` / WSL | `/apps/bdpan/` | WSL 内安装并登录 `bdpan` |

“检查连接”会分别显示百度 OAuth、LLM、官方 MCP 全盘分享、`bdpan` 转存/分享下载四项状态。某一可选后端不可用时，不影响其他后端已经支持的功能。

### 全盘分享是如何实现的

旧版分享通过 `bdpan share` 执行，因此路径被官方 Skill 限制在 `/apps/bdpan/`。现在的全盘分享改用百度官方 MCP 仓库提供的 `file_sharelink_set` 工具，处理流程如下：

```text
用户选择全盘任意文件或文件夹
  -> OperationPlan 二次确认
  -> OpenAPI 列出父目录并按完整路径匹配文件
  -> 将路径解析为百度网盘 fs_id
  -> 官方 MCP file_sharelink_set
  -> 返回分享链接、提取码和有效期
  -> 操作页展示结果并提供一键复制
```

1. 工作台或 AI 问答只生成 `backend="mcp"` 的分享计划，不会直接创建公开链接。
2. 用户确认后，`BaiduNetdiskClient.create_share()` 对路径做绝对路径、去重和根目录保护，再从 OpenAPI 列表结果中取得对应 `fs_id`。
3. `BaiduMcpClient` 使用现有 OAuth Token 连接百度官方托管 MCP 服务，调用 `file_sharelink_set`。`fsid_list` 按官方要求编码为字符串形式的 JSON 数组，并传入 1 天、7 天、30 天或永久有效期以及随机四位提取码。
4. 返回结果经过错误码和链接字段校验后才显示到操作页。成功后“复制分享信息”按钮一次复制分享链接、提取码和有效期。
5. 这条链路不读取 Windows 百度网盘客户端登录态，不使用 Cookie、BDUSS 或未公开接口，也不依赖 WSL 内的 `bdpan`。

因此，连接检测把“全盘分享”和“分享链接转存/下载”分开显示：前者由官方 MCP 提供；后者才是可选 `bdpan` 后端。未安装 `bdpan` 不会影响全盘分享。

## 环境要求

- Windows 10 或 Windows 11
- Python 3.12-3.14
- [uv](https://docs.astral.sh/uv/)
- 百度网盘 OAuth Access Token，作用域包含 `basic` 和 `netdisk`
- 可选：WSL 中安装并登录 `bdpan`，用于转存和分享链接下载；创建全盘分享只需要百度 OAuth 授权

## 安装与启动

```powershell
git clone <repository-url>
cd panfetch-ai
uv sync --python 3.12 --system-certs
uv run pytest
uv run panfetch-ai
```

Windows 日常使用可双击 `启动PanFetch AI.vbs`。它直接调用 `pythonw.exe`，不会出现控制台黑框。首次安装依赖或排查启动错误时，运行 `诊断启动PanFetch AI.bat`；诊断入口会保留控制台并显示错误。

## 百度网盘授权

打开“设置”，在“百度网盘”页点击“打开百度授权页”。完成登录授权后，将成功页中的 Access Token 粘贴到设置中并保存。Token 会被当前 Windows 用户的 DPAPI 加密并写入 `.secrets/baidu-token.dpapi`，密文只能由同一 Windows 用户在本机解密。账号卡片可随时重新授权或退出；退出只删除本机授权，不修改任何网盘文件。

默认 OAuth Client ID 来自百度官方 MCP 项目的个人用户限时体验配置，可能由百度不定期调整；正式开源部署应在设置中填写自己在百度网盘开放平台创建应用后获得的 Client ID。

PanFetch AI 使用的用户基础接口与百度官方 MCP 项目一致：

- 已鉴权用户信息：`/rest/2.0/xpan/nas?method=uinfo&openapi=xpansdk`
- 网盘容量：`/api/quota?openapi=xpansdk`
- 全盘分享：官方 MCP 工具 `file_sharelink_set`，执行前由全盘路径解析为文件 ID

官方参考：[baidu-netdisk/mcp](https://github.com/baidu-netdisk/mcp)

也可以临时通过环境变量提供 Token：

```powershell
$env:BAIDU_NETDISK_ACCESS_TOKEN = "<access-token>"
uv run panfetch-ai
```

不要将 Token、OAuth 成功页完整 URL 或带 `access_token` 的请求日志提交到 Git。

## LLM 配置

LLM 是可选能力。未配置 LLM 时，程序仍能使用本地规则处理路径、扩展名、常见排除项和整理方式。

| 配置项 | 说明 |
|---|---|
| 服务预设 | OpenAI、DeepSeek、硅基流动、Ollama、自定义 |
| Base URL | 服务的 API 根地址，通常以 `/v1` 结尾 |
| 接口模式 | `chat/completions` 或 `responses` |
| 模型 | 服务实际支持的模型 ID |
| API Key | DPAPI 加密保存，也可由 `PANFETCH_LLM_API_KEY` 提供 |
| Key 请求头 | 默认 `Authorization`，也支持 `x-api-key`、`api-key` 等 |
| Key 前缀 | 默认 `Bearer`，需要裸 Key 时可留空 |
| 自定义请求头 | 非敏感 JSON 对象，例如组织 ID 或网关路由信息 |

设置页“检测连接”会使用当前表单中的未保存值发起一次最小对话请求，因此可以在保存前验证 Base URL、接口模式、模型和 API Key 是否匹配。检测不会打印请求头或 API Key。

主工具栏“检查连接”会分别检查百度网盘授权、当前 LLM 对话接口、官方 MCP 全盘分享服务，以及可选的 `bdpan` 分享链接转存/下载后端。未安装 `bdpan` 会显示“未配置（可选）”，不会再被表述为分享功能异常。默认下载目录只在设置页维护；工作台手动下载时会弹出目录选择，AI 下载计划则在独立详情页选择保存位置。

LLM 的返回值必须能解析为 `SelectionPlan`，否则程序拒绝执行下载。

## 使用方式

1. 在 AI 问答页面选择全局网盘、当前目录或指定路径，再用自然语言查找位置、识别资料或提出下载要求；按 `Enter` 发送，按 `Shift+Enter` 换行。
2. 在同一会话中连续追问；需要时从左侧历史恢复之前的请求、回答和运行日志。
3. 目录或搜索结果点击“查看工作台结果”；下载或写操作请求点击对应计划按钮进入独立详情页。
4. 在工作台浏览目录，也可用“常用网盘操作”上传、新建文件夹、移动、复制、重命名或分享选中内容。
5. 在计划详情页检查来源、目标、执行后端、影响范围和风险提示。
6. 明确确认后才开始执行；下载任务可随时暂停、继续或取消。

可选整理方式包括保留原目录、按来源目录、按年份和按文件类型。

## CLI

桌面端和 CLI 共用同一份加密授权与本地配置：

```powershell
uv run panfetch-ai-cli status
uv run panfetch-ai-cli list "/示例目录"
uv run panfetch-ai-cli tree "/示例目录" --depth 3 --limit 2000
uv run panfetch-ai-cli search "关键词" "/示例目录" --limit 100
uv run panfetch-ai-cli chapters "/示例目录"
uv run panfetch-ai-cli export "/示例目录" --depth -1 --limit 0 --format csv --output "目录清单.csv"
```

完整参数见 [命令参考](docs/COMMANDS.md)。

## 项目结构

```text
panfetch_ai/
  app.py                 Qt 应用入口和全局异常处理
  cli.py                 命令行入口
  logging_setup.py       按日期写入的脱敏日志
  core/
    config.py            配置、DPAPI 凭据和路径约定
    netdisk.py           百度网盘 OpenAPI 客户端
    baidu_mcp.py         百度官方托管 MCP 全盘分享适配器
    bdpan.py             bdpan 原生/WSL 检测、路径隔离和命令适配
    cancellation.py      对话、扫描和网络请求的协作式中断
    operations.py        写操作计划、校验和受控执行器
    agent.py             Agent 意图、白名单工具和安全执行
    assistant_workflow.py LangGraph 状态图、LangChain 节点和 LangSmith tracing
    history.py           本地 JSONL 会话、回答与工具日志
    models.py            远程文件与下载计划模型
    planner.py           LLM 协议适配与本地解析
    rules.py             确定性筛选与计划预览
    structure.py         目录树、章节和 CSV 输出
    catalog.py           SQLite 本地索引
    downloader.py        并发、重试、校验与原子落盘
  ui/
    main_window.py       AI 问答、网盘工作台和计划详情页面
    settings_dialog.py   百度授权、下载和 LLM 设置
    workers.py           Qt 线程池任务封装
    styles.py            界面样式
tests/                   核心逻辑与 UI 冒烟测试
scripts/                 构建与界面渲染脚本
docs/                    架构和命令文档
```

更详细的边界说明见 [架构文档](docs/ARCHITECTURE.md)。

## 本地数据

以下目录和文件都已加入 `.gitignore`：

| 路径 | 内容 |
|---|---|
| `.secrets/` | DPAPI 加密的百度 Token 和 LLM API Key |
| `local_settings.json` | 下载目录、并发数和非敏感 LLM 配置 |
| `.panfetch-ai/` | SQLite 目录索引与 AI 会话历史 |
| `downloads/` | 默认下载目录 |
| `exports/` | 导出的目录清单 |
| `logs/` | 脱敏运行日志 |
| `build/`、`dist/` | PyInstaller 构建产物 |
| `artifacts/` | 本地 UI 验证截图 |

凭据、下载内容、个人目录结构、清单和本机配置不属于开源仓库。安全要求见 [SECURITY.md](SECURITY.md)。

## 开发与测试

```powershell
uv sync --python 3.12 --system-certs
uv run pytest
uv run python -m panfetch_ai
```

测试覆盖配置序列化、DPAPI 边界、网盘响应解析、用户信息与容量接口、官方 MCP 分享载荷、分片上传、文件管理载荷、写操作确认边界、路径隔离、规则筛选、文件夹递归展开、下载结构、LangGraph 编排、UTF-8 流式协议、历史乱码修复和多页面 UI 构造。

## 构建 Windows EXE

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

构建配置位于 `panfetch-ai.spec`，设置 `console=False`，输出 `dist\PanFetch AI.exe`。EXE 可直接双击启动且不会创建控制台窗口。开发仓库中的 `dist` 构建会复用仓库根目录的本地配置；单独分发 EXE 时，配置和加密凭据保存在 EXE 同级目录。发布时不要打包 `.secrets/`、`local_settings.json`、日志或任何已下载文件。

## 参与贡献

提交前运行：

```powershell
uv run pytest
git status --short --ignored
git diff --check
```

贡献约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 开源协议

[MIT License](LICENSE)。PySide6 由 Qt for Python 提供，分发二进制版本时还需遵守其 LGPL/GPL/商业许可条款。
