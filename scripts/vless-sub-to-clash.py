#!/usr/bin/env python3
"""Конвертация VLESS-подписки (base64 или plain vless://) в Clash Meta YAML."""

from __future__ import annotations

import argparse
import base64
import sys
import urllib.parse
from pathlib import Path


def _load_vless_lines(raw: str) -> list[str]:
    text = raw.strip()
    if not text:
        return []
    if text.startswith("dmx") or text.startswith("dmxs") or not text.startswith("vless://"):
        try:
            decoded = base64.b64decode(text, validate=False).decode("utf-8", errors="ignore")
            lines = [line.strip() for line in decoded.splitlines() if line.strip().startswith("vless://")]
            if lines:
                return lines
        except Exception:
            pass
    return [line.strip() for line in text.splitlines() if line.strip().startswith("vless://")]


def _parse_vless(url: str) -> dict | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "vless":
        return None

    name = urllib.parse.unquote(parsed.fragment or "vless-node")
    params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    server = parsed.hostname
    port = parsed.port or 443
    uuid = parsed.username

    if not server or not uuid:
        return None

    security = params.get("security", "none")
    network = params.get("type", "tcp")
    flow = params.get("flow", "")

    proxy: dict = {
        "name": name,
        "type": "vless",
        "server": server,
        "port": port,
        "uuid": uuid,
        "network": network,
        "udp": True,
    }

    if flow:
        proxy["flow"] = flow

    if security in {"reality", "tls"}:
        proxy["tls"] = True
        sni = params.get("sni") or server
        proxy["servername"] = sni
        fp = params.get("fp")
        if fp:
            proxy["client-fingerprint"] = fp
        if security == "reality":
            pbk = params.get("pbk")
            sid = params.get("sid")
            if pbk and sid:
                proxy["reality-opts"] = {"public-key": pbk, "short-id": sid}

    if network == "grpc":
        proxy["grpc-opts"] = {"grpc-service-name": params.get("serviceName", params.get("path", ""))}
    elif network == "xhttp":
        return None  # xhttp — пропускаем; для Telegram достаточно tcp/reality
    elif network in {"ws", "http", "h2"}:
        proxy["ws-opts"] = {"path": params.get("path", "/"), "headers": {}}

    return proxy


def convert(raw: str, *, exclude_auto: bool = True) -> str:
    lines = _load_vless_lines(raw)
    proxies: list[dict] = []

    for line in lines:
        if exclude_auto and ("web.max.ru" in line or "AUTO" in urllib.parse.unquote(line)):
            continue
        item = _parse_vless(line)
        if item:
            proxies.append(item)

    if not proxies:
        raise SystemExit("Не найдено ни одного vless-узла после разбора подписки.")

    yaml_lines = ["proxies:"]
    for p in proxies:
        yaml_lines.append(f"  - name: {p['name']!r}")
        yaml_lines.append(f"    type: {p['type']}")
        yaml_lines.append(f"    server: {p['server']}")
        yaml_lines.append(f"    port: {p['port']}")
        yaml_lines.append(f"    uuid: {p['uuid']}")
        yaml_lines.append(f"    network: {p['network']}")
        yaml_lines.append("    udp: true")
        if "flow" in p:
            yaml_lines.append(f"    flow: {p['flow']}")
        if p.get("tls"):
            yaml_lines.append("    tls: true")
            yaml_lines.append(f"    servername: {p['servername']}")
            if "client-fingerprint" in p:
                yaml_lines.append(f"    client-fingerprint: {p['client-fingerprint']}")
            if "reality-opts" in p:
                yaml_lines.append("    reality-opts:")
                yaml_lines.append(f"      public-key: {p['reality-opts']['public-key']}")
                yaml_lines.append(f"      short-id: {p['reality-opts']['short-id']}")
        if "grpc-opts" in p:
            yaml_lines.append("    grpc-opts:")
            yaml_lines.append(f"      grpc-service-name: {p['grpc-opts']['grpc-service-name']!r}")

    return "\n".join(yaml_lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="Файл подписки или stdin")
    parser.add_argument("-o", "--output", help="Куда записать YAML")
    parser.add_argument("--include-auto", action="store_true", help="Не фильтровать AUTO/web.max.ru")
    args = parser.parse_args()

    if args.input:
        raw = Path(args.input).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()

    result = convert(raw, exclude_auto=not args.include_auto)

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"OK: {args.output} ({result.count('name:')} nodes)", file=sys.stderr)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
