from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from panfetch_ai.core.config import PROJECT_ROOT


DEFAULT_HISTORY_FILE = PROJECT_ROOT / ".panfetch-ai" / "assistant_history.jsonl"


@dataclass(slots=True)
class ConversationTurn:
    session_id: str
    timestamp: str
    request: str
    response: str
    scope: str
    path: str
    action: str
    logs: list[str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ConversationTurn":
        return cls(
            session_id=str(payload.get("session_id") or ""),
            timestamp=str(payload.get("timestamp") or ""),
            request=repair_mojibake(str(payload.get("request") or "")),
            response=repair_mojibake(str(payload.get("response") or "")),
            scope=str(payload.get("scope") or "global"),
            path=repair_mojibake(str(payload.get("path") or "/")),
            action=str(payload.get("action") or "help"),
            logs=[repair_mojibake(str(item)) for item in payload.get("logs") or []],
        )


class ConversationStore:
    def __init__(self, path: Path = DEFAULT_HISTORY_FILE) -> None:
        self.path = path

    @staticmethod
    def new_session_id() -> str:
        return uuid.uuid4().hex

    def append(
        self,
        session_id: str,
        request: str,
        response: str,
        scope: str,
        path: str,
        action: str,
        logs: list[str],
    ) -> ConversationTurn:
        turn = ConversationTurn(
            session_id=session_id,
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            request=request,
            response=response,
            scope=scope,
            path=path,
            action=action,
            logs=logs,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(asdict(turn), ensure_ascii=False, separators=(",", ":")) + "\n")
        return turn

    def turns(self, session_id: str | None = None) -> list[ConversationTurn]:
        if not self.path.is_file():
            return []
        turns: list[ConversationTurn] = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-5000:]:
            try:
                payload = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            turn = ConversationTurn.from_dict(payload)
            if turn.session_id and (session_id is None or turn.session_id == session_id):
                turns.append(turn)
        return turns

    def sessions(self) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for turn in self.turns():
            entry = grouped.setdefault(
                turn.session_id,
                {"session_id": turn.session_id, "title": turn.request[:36], "updated": turn.timestamp, "count": 0},
            )
            entry["updated"] = turn.timestamp
            entry["count"] = int(entry["count"]) + 1
        return sorted(grouped.values(), key=lambda item: str(item["updated"]), reverse=True)

    def delete_session(self, session_id: str) -> int:
        normalized = session_id.strip()
        if not normalized or not self.path.is_file():
            return 0
        retained: list[str] = []
        removed = 0
        for line in self.path.read_text(encoding="utf-8").splitlines(keepends=True):
            try:
                payload = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                retained.append(line)
                continue
            if isinstance(payload, dict) and str(payload.get("session_id") or "") == normalized:
                removed += 1
            else:
                retained.append(line)
        if not removed:
            return 0
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex[:10]}.tmp")
        try:
            temporary.write_text("".join(retained), encoding="utf-8", newline="")
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return removed

    def repair_encoding(self) -> int:
        if not self.path.is_file():
            return 0
        original_lines = self.path.read_text(encoding="utf-8").splitlines()
        output_lines: list[str] = []
        repaired_count = 0
        for line in original_lines:
            try:
                payload = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                output_lines.append(line)
                continue
            if not isinstance(payload, dict):
                output_lines.append(line)
                continue
            for key in ("request", "response", "path"):
                if isinstance(payload.get(key), str):
                    repaired = repair_mojibake(payload[key])
                    if repaired != payload[key]:
                        payload[key] = repaired
                        repaired_count += 1
            if isinstance(payload.get("logs"), list):
                repaired_logs = [repair_mojibake(str(item)) for item in payload["logs"]]
                if repaired_logs != payload["logs"]:
                    payload["logs"] = repaired_logs
                    repaired_count += 1
            output_lines.append(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        if repaired_count:
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text("\n".join(output_lines) + "\n", encoding="utf-8", newline="\n")
            temporary.replace(self.path)
        return repaired_count


def repair_mojibake(text: str) -> str:
    if not text or _mojibake_score(text) == 0:
        return text
    try:
        candidate = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return candidate if _mojibake_score(candidate) < _mojibake_score(text) else text


def _mojibake_score(text: str) -> int:
    markers = ("Ã", "Â", "ä", "å", "æ", "ç", "è", "é", "ï", "ð", "�")
    control_count = sum(1 for char in text if 0x80 <= ord(char) <= 0x9F)
    return sum(text.count(marker) for marker in markers) + control_count
