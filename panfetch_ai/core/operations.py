from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Callable

from panfetch_ai.core.bdpan import BdpanBackend, bdpan_relative_path, normalize_bdpan_path, validate_share_url
from panfetch_ai.core.models import OperationPlan, OperationResult
from panfetch_ai.core.netdisk import BaiduNetdiskClient, normalize_remote_path


WRITE_ACTIONS = {"upload", "move", "copy", "rename", "mkdir", "share", "transfer", "share_download"}


def build_operation_plan(action: str, arguments: dict[str, Any], request: str = "") -> OperationPlan:
    action = str(action).removeprefix("prepare_").strip().lower()
    if action not in WRITE_ACTIONS:
        raise ValueError("不支持的网盘操作")
    if action == "upload":
        local = Path(str(arguments.get("local_path") or "").strip()).expanduser().resolve()
        if not local.exists():
            raise ValueError(f"本地路径不存在：{local}")
        remote = normalize_remote_path(str(arguments.get("remote_path") or "/来自：PanFetch AI"))
        target = f"{remote.rstrip('/')}/{local.name}" if remote == "/" or not _looks_like_file_target(remote, local) else remote
        count = sum(1 for item in local.rglob("*") if item.is_file()) if local.is_dir() else 1
        return OperationPlan(
            action,
            "上传到百度网盘",
            f"从本地上传 {count} 个文件\n本地：{local}\n网盘：{target}",
            {"local_path": str(local), "remote_path": target, "request": request},
            warnings=["同名内容可能由百度网盘按服务端规则处理，请先核对目标路径。"],
        )
    if action in {"move", "copy"}:
        raw_source = str(arguments.get("source") or arguments.get("path") or "").strip()
        raw_destination = str(arguments.get("destination") or "").strip()
        if not raw_source or not raw_destination:
            raise ValueError("请同时指定源路径和目标目录")
        source = normalize_remote_path(raw_source)
        destination = normalize_remote_path(raw_destination)
        if source == "/" or source == destination or destination.startswith(f"{source.rstrip('/')}/"):
            raise ValueError("不能移动或复制网盘根目录，也不能把目录放入自身")
        verb = "移动" if action == "move" else "复制"
        return OperationPlan(
            action,
            f"{verb}网盘内容",
            f"{verb}：{source}\n目标目录：{destination}",
            {"source": source, "destination": destination, "request": request},
            warnings=["此操作会修改网盘目录结构。"] if action == "move" else [],
        )
    if action == "rename":
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise ValueError("请指定需要重命名的路径")
        path = normalize_remote_path(raw_path)
        if path == "/":
            raise ValueError("不能重命名网盘根目录")
        new_name = _safe_name(str(arguments.get("new_name") or ""))
        return OperationPlan(
            action,
            "重命名网盘内容",
            f"原路径：{path}\n新名称：{new_name}",
            {"path": path, "new_name": new_name, "request": request},
            warnings=["重命名会改变原网盘路径。"],
        )
    if action == "mkdir":
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise ValueError("请指定需要创建的文件夹路径")
        path = normalize_remote_path(raw_path)
        if path == "/":
            raise ValueError("不能创建网盘根目录")
        return OperationPlan(action, "创建网盘文件夹", f"新文件夹：{path}", {"path": path, "request": request})
    if action == "share":
        raw_paths = arguments.get("paths") or [arguments.get("path")]
        paths = list(dict.fromkeys(normalize_remote_path(str(path)) for path in raw_paths if path))
        if not paths:
            raise ValueError("请指定需要分享的文件或文件夹")
        if "/" in paths:
            raise ValueError("不能直接分享整个网盘根目录，请选择需要分享的文件或文件夹")
        period = _period(arguments.get("period"))
        label = "永久" if period == 0 else f"{period} 天"
        return OperationPlan(
            action,
            "生成百度网盘分享链接",
            f"分享内容：\n" + "\n".join(f"- {path}" for path in paths) + f"\n有效期：{label}",
            {"paths": paths, "period": period, "request": request},
            backend="mcp",
            warnings=["分享链接会允许持有链接和提取码的人访问所选内容。"] + (["永久链接不会自动过期。"] if period == 0 else []),
        )
    if action in {"transfer", "share_download"}:
        url = validate_share_url(str(arguments.get("share_url") or ""))
        code = str(arguments.get("extraction_code") or arguments.get("pwd") or "").strip()[:16]
        if action == "transfer":
            destination = normalize_bdpan_path(str(arguments.get("destination") or "/apps/bdpan"))
            summary = f"分享链接：{url}\n转存到：{destination}"
            args = {"share_url": url, "extraction_code": code, "destination": destination, "request": request}
            title = "转存分享内容"
        else:
            destination = Path(str(arguments.get("destination") or "").strip()).expanduser().resolve()
            if not destination.is_absolute():
                raise ValueError("分享链接下载需要绝对本地目录")
            transfer_dir = normalize_bdpan_path(str(arguments.get("transfer_dir") or "/apps/bdpan"))
            summary = f"分享链接：{url}\n保存到本地：{destination}\n临时转存目录：{transfer_dir}"
            args = {
                "share_url": url,
                "extraction_code": code,
                "destination": str(destination),
                "transfer_dir": transfer_dir,
                "request": request,
            }
            title = "下载百度网盘分享链接"
        if code:
            summary += f"\n提取码：{'*' * len(code)}"
        return OperationPlan(action, title, summary, args, backend="bdpan", warnings=["执行后会向自己的网盘写入内容。"])
    raise ValueError("无法生成操作计划")


class NetdiskOperationExecutor:
    def __init__(self, client: BaiduNetdiskClient, bdpan: BdpanBackend | None = None) -> None:
        self.client = client
        self.bdpan = bdpan or BdpanBackend()

    def execute(self, plan: OperationPlan, progress: Callable[[dict[str, Any]], None] | None = None) -> OperationResult:
        report = progress or (lambda _: None)
        args = plan.arguments
        if plan.action == "upload":
            uploaded = self.client.upload_path(args["local_path"], args["remote_path"], report)
            return OperationResult("upload", f"上传完成，共 {len(uploaded)} 个文件。", {"items": uploaded})
        if plan.action == "move":
            self.client.move(args["source"], args["destination"])
            return OperationResult("move", f"已移动到：{args['destination']}")
        if plan.action == "copy":
            self.client.copy(args["source"], args["destination"])
            return OperationResult("copy", f"已复制到：{args['destination']}")
        if plan.action == "rename":
            self.client.rename(args["path"], args["new_name"])
            return OperationResult("rename", f"已重命名为：{args['new_name']}")
        if plan.action == "mkdir":
            self.client.create_directory(args["path"])
            return OperationResult("mkdir", f"已创建文件夹：{args['path']}")
        session_input = str(args.get("request") or plan.title)
        if plan.action == "share":
            payload = self.client.create_share(args["paths"], args["period"])
            link = payload.get("link") or payload.get("short_url") or payload.get("url") or ""
            pwd = payload.get("pwd") or payload.get("password") or ""
            message = f"分享链接已生成：{link}" + (f"\n提取码：{pwd}" if pwd else "")
            return OperationResult("share", message, payload)
        if plan.action == "transfer":
            command = [args["share_url"]]
            destination = bdpan_relative_path(args["destination"])
            if destination:
                command.extend(["-d", destination])
            if args.get("extraction_code"):
                command.extend(["-p", args["extraction_code"]])
            payload = self.bdpan.run("transfer", command, session_input)
            status = payload.get("status")
            message = "转存任务已提交。" if status == "submitted" else "分享内容已转存到网盘。"
            return OperationResult("transfer", message, payload)
        if plan.action == "share_download":
            local_destination = self.bdpan.local_path_argument(args["destination"])
            command = [args["share_url"], local_destination]
            transfer_dir = bdpan_relative_path(args["transfer_dir"])
            if transfer_dir:
                command.extend(["-t", transfer_dir])
            if args.get("extraction_code"):
                command.extend(["-p", args["extraction_code"]])
            payload = self.bdpan.run("download", command, session_input)
            return OperationResult("share_download", f"分享内容已下载到：{args['destination']}", payload)
        raise ValueError("不支持的操作计划")


def _safe_name(value: str) -> str:
    name = value.strip()
    if not name or name in {".", ".."} or any(char in name for char in "/\\"):
        raise ValueError("新名称只能是单个文件名或文件夹名")
    return name


def _period(value: Any) -> int:
    try:
        requested = int(value)
    except (TypeError, ValueError):
        return 7
    return min((0, 1, 7, 30), key=lambda option: abs(option - requested))


def _looks_like_file_target(remote: str, local: Path) -> bool:
    if local.is_dir():
        return PurePosixPath(remote).name == local.name
    return PurePosixPath(remote).suffix != ""
