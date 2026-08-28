from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from panfetch_ai.core.config import ConfigStore
from panfetch_ai.core.netdisk import BaiduNetdiskClient, NetdiskError
from panfetch_ai.core.structure import chapter_lines, items_to_csv, tree_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="panfetch-ai-cli", description="PanFetch AI 百度网盘只读快捷命令")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="查看授权账号和配置状态")

    listing = commands.add_parser("list", help="查看目录的直接子项")
    listing.add_argument("path", nargs="?", default="/")
    listing.add_argument("--limit", type=int, default=0, help="最多显示数量，0 表示不限")

    tree = commands.add_parser("tree", help="递归查看目录结构")
    tree.add_argument("path", nargs="?", default="/")
    tree.add_argument("--depth", type=int, default=3, help="递归深度，-1 表示不限")
    tree.add_argument("--limit", type=int, default=2000, help="最多显示数量，0 表示不限")

    search = commands.add_parser("search", help="按文件名搜索")
    search.add_argument("keyword")
    search.add_argument("path", nargs="?", default="/")
    search.add_argument("--limit", type=int, default=100)

    chapters = commands.add_parser("chapters", help="识别当前层级章节目录")
    chapters.add_argument("path", nargs="?", default="/")

    export = commands.add_parser("export", help="递归导出目录清单")
    export.add_argument("path", nargs="?", default="/")
    export.add_argument("--depth", type=int, default=-1)
    export.add_argument("--limit", type=int, default=0)
    export.add_argument("--format", choices=("csv", "json"), default="csv")
    export.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        store = ConfigStore()
        client = BaiduNetdiskClient(config_store=store)
        if args.command == "status":
            account = client.account_info()
            quota = client.quota_info()
            config = store.load()
            name = account.get("netdisk_name") or account.get("baidu_name") or account.get("uk")
            vip_type = int(account.get("vip_type") or 0)
            membership = "SVIP" if vip_type == 2 else "VIP" if vip_type == 1 else "普通用户"
            total = max(0, int(quota.get("total") or 0))
            used = max(0, int(quota.get("used") or 0))
            print(f"账号：{name}")
            print(f"UID：{account.get('uk', '-')}")
            print(f"会员类型：{membership}")
            print(f"网盘容量：已用 {_size(used)} / {_size(total)}，剩余 {_size(max(0, total - used))}")
            print(f"下载根目录：{config.download_root}")
            print(f"LLM：{config.llm.provider} / {config.llm.model or '未配置'}")
            return 0
        if args.command == "list":
            items = client.list_directory(args.path, args.limit)
            print(_table(items))
            return 0
        if args.command == "tree":
            items = client.walk(args.path, args.depth, args.limit)
            print(tree_text(args.path, items, limit=args.limit or len(items)))
            return 0
        if args.command == "search":
            print(_table(client.search(args.keyword, args.path, True, args.limit)))
            return 0
        if args.command == "chapters":
            print("\n".join(chapter_lines(args.path, client.list_directory(args.path))))
            return 0
        items = client.walk(args.path, args.depth, args.limit)
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        if args.format == "json":
            content = json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2)
            output.write_text(content, encoding="utf-8")
        else:
            output.write_text(items_to_csv(items), encoding="utf-8-sig")
        print(f"已导出 {len(items)} 项：{output}")
        return 0
    except (NetdiskError, OSError, ValueError) as exc:
        print(f"操作失败：{exc}", file=sys.stderr)
        return 2


def _table(items: list) -> str:
    lines = ["TYPE\tSIZE\tMODIFIED\tPATH"]
    for item in items:
        kind = "DIR" if item.is_dir else "FILE"
        size = "-" if item.is_dir else _size(item.size)
        modified = datetime.fromtimestamp(item.modified).strftime("%Y-%m-%d %H:%M:%S") if item.modified else "-"
        lines.append(f"{kind}\t{size}\t{modified}\t{item.path}")
    return "\n".join(lines)


def _size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"
