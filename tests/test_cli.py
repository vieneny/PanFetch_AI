from panfetch_ai.cli import build_parser


def test_cli_common_commands_parse() -> None:
    assert build_parser().parse_args(["list", "/学习资料"]).path == "/学习资料"
    tree = build_parser().parse_args(["tree", "/项目文档", "--depth", "2"])
    assert tree.depth == 2
    assert build_parser().parse_args(["chapters", "/学习资料"]).command == "chapters"
