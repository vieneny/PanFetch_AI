from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _resolve_project_root() -> Path:
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parents[2]
    executable_dir = Path(sys.executable).resolve().parent
    checkout_root = executable_dir.parent
    if (
        executable_dir.name.casefold() == "dist"
        and (checkout_root / "pyproject.toml").is_file()
        and (checkout_root / "panfetch_ai").is_dir()
    ):
        return checkout_root
    return executable_dir


PROJECT_ROOT = _resolve_project_root()
SETTINGS_FILE = PROJECT_ROOT / "local_settings.json"
SECRETS_DIR = PROJECT_ROOT / ".secrets"
BAIDU_TOKEN_FILE = SECRETS_DIR / "baidu-token.dpapi"
LLM_KEY_FILE = SECRETS_DIR / "llm-api-key.dpapi"
DEFAULT_BAIDU_OAUTH_CLIENT_ID = "QHOuRXiepJBMjtk0esLhrPoNlQyYd0mF"


LLM_PRESETS: dict[str, dict[str, str]] = {
    "OpenAI": {"base_url": "https://api.openai.com/v1", "api_mode": "responses", "model": "gpt-5-mini"},
    "DeepSeek": {"base_url": "https://api.deepseek.com/v1", "api_mode": "chat_completions", "model": "deepseek-chat"},
    "硅基流动": {"base_url": "https://api.siliconflow.cn/v1", "api_mode": "chat_completions", "model": "Qwen/Qwen3-8B"},
    "Ollama": {"base_url": "http://127.0.0.1:11434/v1", "api_mode": "chat_completions", "model": "qwen3:8b"},
    "自定义": {"base_url": "", "api_mode": "chat_completions", "model": ""},
}


@dataclass(slots=True)
class LLMConfig:
    provider: str = "自定义"
    base_url: str = ""
    api_mode: str = "chat_completions"
    model: str = ""
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer"
    custom_headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 90


@dataclass(slots=True)
class AppConfig:
    download_root: str = str((PROJECT_ROOT / "downloads").resolve())
    concurrency: int = 5
    baidu_oauth_client_id: str = DEFAULT_BAIDU_OAUTH_CLIENT_ID
    llm: LLMConfig = field(default_factory=LLMConfig)


class ConfigStore:
    def __init__(self, settings_file: Path = SETTINGS_FILE, secrets_dir: Path = SECRETS_DIR) -> None:
        self.settings_file = settings_file
        self.secrets_dir = secrets_dir
        self.baidu_token_file = secrets_dir / BAIDU_TOKEN_FILE.name
        self.llm_key_file = secrets_dir / LLM_KEY_FILE.name

    def load(self) -> AppConfig:
        if not self.settings_file.is_file():
            return AppConfig()
        try:
            payload = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return AppConfig()
        llm_payload = payload.get("llm") if isinstance(payload.get("llm"), dict) else {}
        headers = llm_payload.get("custom_headers") if isinstance(llm_payload.get("custom_headers"), dict) else {}
        return AppConfig(
            download_root=str(payload.get("download_root") or AppConfig().download_root),
            concurrency=max(1, min(int(payload.get("concurrency") or 5), 10)),
            baidu_oauth_client_id=str(payload.get("baidu_oauth_client_id") or DEFAULT_BAIDU_OAUTH_CLIENT_ID),
            llm=LLMConfig(
                provider=str(llm_payload.get("provider") or "自定义"),
                base_url=str(llm_payload.get("base_url") or ""),
                api_mode=str(llm_payload.get("api_mode") or "chat_completions"),
                model=str(llm_payload.get("model") or ""),
                api_key_header=str(llm_payload.get("api_key_header") or "Authorization"),
                api_key_prefix=str(llm_payload.get("api_key_prefix") if llm_payload.get("api_key_prefix") is not None else "Bearer"),
                custom_headers={str(k): str(v) for k, v in headers.items()},
                timeout_seconds=max(10, int(llm_payload.get("timeout_seconds") or 90)),
            ),
        )

    def save(self, config: AppConfig) -> None:
        root = Path(config.download_root).expanduser()
        if not root.is_absolute():
            raise ValueError("下载根目录必须是绝对路径")
        root.mkdir(parents=True, exist_ok=True)
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.settings_file, json.dumps(asdict(config), ensure_ascii=False, indent=2).encode("utf-8"))

    def has_baidu_token(self) -> bool:
        return bool(os.getenv("BAIDU_NETDISK_ACCESS_TOKEN", "").strip()) or self.baidu_token_file.is_file()

    def read_baidu_token(self) -> str:
        from_environment = os.getenv("BAIDU_NETDISK_ACCESS_TOKEN", "").strip()
        if from_environment:
            return from_environment
        return self._read_secret(self.baidu_token_file, "百度网盘授权尚未配置")

    def write_baidu_token(self, token: str) -> None:
        self._write_secret(self.baidu_token_file, token, "PanFetch AI Baidu Netdisk token")

    def delete_baidu_token(self) -> bool:
        used_environment = bool(os.getenv("BAIDU_NETDISK_ACCESS_TOKEN", "").strip())
        os.environ.pop("BAIDU_NETDISK_ACCESS_TOKEN", None)
        self.baidu_token_file.unlink(missing_ok=True)
        return used_environment

    def read_llm_key(self) -> str:
        from_environment = os.getenv("PANFETCH_LLM_API_KEY", "").strip()
        if from_environment:
            return from_environment
        if not self.llm_key_file.is_file():
            return ""
        return self._read_secret(self.llm_key_file, "")

    def write_llm_key(self, api_key: str) -> None:
        if api_key.strip():
            self._write_secret(self.llm_key_file, api_key, "PanFetch AI LLM API key")

    @staticmethod
    def _read_secret(path: Path, missing_message: str) -> str:
        if not path.is_file():
            raise ValueError(missing_message)
        try:
            import win32crypt

            return win32crypt.CryptUnprotectData(path.read_bytes(), None, None, None, 0)[1].decode("utf-8").strip()
        except (ImportError, OSError, UnicodeError) as exc:
            raise ValueError("本机无法解密已保存的凭据") from exc

    def _write_secret(self, path: Path, value: str, description: str) -> None:
        secret = value.strip()
        if not secret:
            raise ValueError("凭据不能为空")
        try:
            import win32crypt

            encrypted = win32crypt.CryptProtectData(secret.encode("utf-8"), description, None, None, None, 0)
        except ImportError as exc:
            raise RuntimeError("DPAPI 仅支持 Windows") from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, encrypted)


def _atomic_write(path: Path, data: bytes) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:10]}.tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def parse_headers(value: str) -> dict[str, str]:
    if not value.strip():
        return {}
    payload: Any = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("自定义请求头必须是 JSON 对象")
    headers = {str(key): str(item) for key, item in payload.items()}
    secret_headers = {"authorization", "proxy-authorization", "x-api-key", "api-key"}
    if any(key.casefold() in secret_headers for key in headers):
        raise ValueError("API Key 请使用独立的加密字段，不要写入自定义请求头")
    return headers
