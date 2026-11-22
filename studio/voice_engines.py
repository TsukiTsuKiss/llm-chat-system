"""VOICEVOX ENGINE の管理（名前・URL・有効/無効）。ルートの voicevox_engines.json を読む。"""

from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from studio.schema_validate import validate_schema_document

ENGINES_FILE = "voicevox_engines.json"
_RESOLVE_TTL_SECONDS = 60.0
# ホスト名 → (IPv4 または None, 有効期限)。DHCP で IP が替わっても、一定時間ごとに引き直す
_resolved: dict[str, tuple[str | None, float]] = {}


class EngineConfigError(ValueError):
    """voicevox_engines.json の誤り、または指定した ENGINE 名が無い。"""


@dataclass(frozen=True)
class Engine:
    name: str
    url: str
    device: str = "cpu"
    parallel: int = 1
    enabled: bool = True
    note: str = ""


def load_engines(root: Path) -> list[Engine]:
    """管理対象の ENGINE を、ファイルの順に返す。ファイルが無ければ空。"""
    path = Path(root) / ENGINES_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EngineConfigError(f"{ENGINES_FILE} を読めません: {exc}") from exc
    report = validate_schema_document(data, "voicevox_engines", ENGINES_FILE)
    if report.errors:
        raise EngineConfigError(f"{ENGINES_FILE} が不正です: " + "; ".join(e.format() for e in report.errors))

    engines: list[Engine] = []
    seen: set[str] = set()
    for item in data["engines"]:
        key = item["name"].lower()
        if key in seen:
            raise EngineConfigError(f"{ENGINES_FILE}: 名前が重複しています: {item['name']}")
        seen.add(key)
        engines.append(
            Engine(
                name=item["name"],
                url=item["url"].rstrip("/"),
                device=item.get("device", "cpu"),
                parallel=item.get("parallel", 1),
                enabled=item.get("enabled", True),
                note=item.get("note", ""),
            )
        )
    return engines


def expand_engine_spec(value: str | None, root: Path | None, fallback: str) -> str:
    """--voicevox-url などの指定を、URL のカンマ区切りにする。

    優先順位: 明示した値（登録名も書ける）> voicevox_engines.json の有効な ENGINE > fallback（環境変数・既定）。
    明示した値は、ファイルの enabled に関わらず、そのまま使う（管理対象とは混ぜない）。
    """
    engines = load_engines(root) if root is not None else []
    if value is None or not value.strip():
        enabled = [engine.url for engine in engines if engine.enabled]
        return ",".join(enabled) if enabled else fallback

    by_name = {engine.name.lower(): engine for engine in engines}
    urls: list[str] = []
    for token in (item.strip() for item in value.split(",")):
        if not token:
            continue
        engine = by_name.get(token.lower())
        if engine is not None:
            urls.append(engine.url)
        elif "://" in token:
            urls.append(token)
        else:
            names = ", ".join(e.name for e in engines) or "なし"
            raise EngineConfigError(f"ENGINE '{token}' が見つかりません（URL か、登録名を指定してください。登録名: {names}）")
    return ",".join(urls) if urls else fallback


def engine_names_by_url(root: Path | None) -> dict[str, str]:
    """URL → 登録名。ホスト名の URL は、IPv4 に引いた URL でも引けるようにする。ファイルが無い・不正なら空。"""
    if root is None:
        return {}
    try:
        engines = load_engines(root)
    except EngineConfigError:
        return {}
    names: dict[str, str] = {}
    for engine in engines:
        names[engine.url] = engine.name
        names[prefer_ipv4(engine.url).rstrip("/")] = engine.name
    return names


def _resolve_ipv4(host: str) -> str | None:
    now = time.monotonic()
    cached = _resolved.get(host)
    if cached is not None and cached[1] > now:
        return cached[0]
    try:
        ip = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    except (OSError, IndexError):
        ip = None
    _resolved[host] = (ip, now + _RESOLVE_TTL_SECONDS)
    return ip


def prefer_ipv4(url: str) -> str:
    """ホスト名の URL を IPv4 の URL にする（引けなければそのまま）。

    ホスト名は IPv6 を先に試すので、IPv4 だけで待ち受ける ENGINE には、毎回数秒の遅れが出る。
    """
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname
    if not host:
        return url
    try:
        ipaddress.ip_address(host)
        return url
    except ValueError:
        pass
    ip = _resolve_ipv4(host)
    if ip is None:
        return url
    netloc = ip if parts.port is None else f"{ip}:{parts.port}"
    return urllib.parse.urlunsplit(parts._replace(netloc=netloc))
