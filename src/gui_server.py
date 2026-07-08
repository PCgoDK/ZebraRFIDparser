from __future__ import annotations

import html
import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from parser import parse_event
from status_tracker import StatusTracker


def _load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


def _save_config(config_path: Path, config: Dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _as_bool(form: Dict[str, Any], key: str, default: bool) -> bool:
    value = form.get(key)
    if value is None:
        return default
    if isinstance(value, list):
        value = value[0]
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _render_page(
    config: Dict[str, Any],
    status_snapshot: Dict[str, Any],
    message: str = "",
    restart_prompt: bool = False,
) -> str:
    input_cfg = config.get("input", {})
    parser_cfg = config.get("parser_setup", {})
    storage_cfg = config.get("storage", {})

    rows = []
    for row in status_snapshot.get("latest_senders", []):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('sender_id', '')))}</td>"
            f"<td>{html.escape(str(row.get('protocol', '')))}</td>"
            f"<td>{html.escape(str(row.get('last_seen', '')))}</td>"
            f"<td>{html.escape(str(row.get('raw_messages', 0)))}</td>"
            f"<td>{html.escape(str(row.get('events', 0)))}</td>"
            f"<td>{html.escape(str(row.get('parse_errors', 0)))}</td>"
            f"<td>{html.escape(str(row.get('storage_errors', 0)))}</td>"
            f"<td>{html.escape(str(row.get('last_tag_id', '')))}</td>"
            f"<td>{html.escape(str(row.get('last_error', '')))}</td>"
            "</tr>"
        )
    latest_rows = "\n".join(rows)
    selected_protocol = str(input_cfg.get("protocol", "text_tcp"))
    restart_banner = (
        "<div class=\"restart-box\"><strong>Konfigurationen er gemt.</strong>"
        "<div class=\"subtle\">Vil du genstarte tjenesten nu, så ændringerne træder i kraft med det samme?</div>"
        "<div class=\"restart-actions\">"
        "<form method=\"post\" action=\"/restart-service\"><button type=\"submit\">Ja, genstart tjeneste</button></form>"
        "<form method=\"get\" action=\"/\"><button type=\"submit\" class=\"secondary\">Nej, senere</button></form>"
        "</div></div>"
        if restart_prompt
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>RFID Event Collector</title>
<style>
body {{ font-family: Segoe UI, sans-serif; margin: 18px; background: #f8f8f8; color: #222; }}
.card {{ background: #fff; border: 1px solid #ddd; border-radius: 10px; padding: 14px; margin-bottom: 14px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(320px,1fr)); gap: 12px; }}
label {{ display: block; font-size: 0.9rem; margin-top: 8px; color: #555; }}
input,select,textarea {{ width: 100%; box-sizing: border-box; padding: 8px; border: 1px solid #ccc; border-radius: 6px; }}
textarea {{ min-height: 84px; }}
button {{ margin-top: 10px; background: #086f4d; color: #fff; border: 0; padding: 8px 12px; border-radius: 6px; cursor: pointer; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 7px; text-align: left; }}
.msg {{ color: #086f4d; font-weight: 600; }}
.subtle {{ color: #666; font-size: 0.9rem; margin-top: 2px; }}
.field-group {{ margin-top: 6px; padding: 8px 10px 2px; border: 1px solid transparent; border-radius: 8px; transition: opacity 0.2s ease, background 0.2s ease; }}
.field-group.is-disabled {{ opacity: 0.55; background: #f4f4f4; border-color: #e0e0e0; }}
.restart-box {{ margin: 0 0 14px; padding: 12px 14px; border: 1px solid #d7c27a; background: #fff8df; border-radius: 10px; }}
.restart-actions {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }}
.restart-actions form {{ margin: 0; }}
.secondary {{ background: #6b7280; }}
</style>
</head>
<body>
<h1>RFID Event Collector GUI</h1>
{f'<p class="msg">{html.escape(message)}</p>' if message else ''}
{restart_banner}

<div class="grid">
<section class="card">
<h2>Input + Storage</h2>
<div class="subtle">Vælg input-protokol først, og tilpas derefter storage til det miljø du vil gemme events i.</div>
<form method="post" action="/save-config">
<h3>Input protocol</h3>
<div class="subtle">De viste felter skifter automatisk efter protokolvalget.</div>
<label>Input protocol</label>
<select name="input_protocol" id="input-protocol" onchange="updateProtocolVisibility()">
    <option value="text_tcp" {'selected' if selected_protocol == 'text_tcp' else ''}>text_tcp</option>
    <option value="llrp_client" {'selected' if selected_protocol == 'llrp_client' else ''}>llrp_client</option>
    <option value="llrp_server" {'selected' if selected_protocol == 'llrp_server' else ''}>llrp_server</option>
</select>
<div class="subtle" id="protocol-help"></div>

<div id="host-port-group" class="field-group">
    <label>Host</label><input name="input_host" id="input-host" value="{html.escape(str(input_cfg.get('host', '0.0.0.0')))}"/>
    <label>Port</label><input name="input_port" id="input-port" value="{html.escape(str(input_cfg.get('port', 9002)))}"/>
</div>

<div id="reader-group" class="field-group">
    <label>Reader host</label><input name="reader_host" id="reader-host" value="{html.escape(str(input_cfg.get('reader_host', '192.168.1.100')))}"/>
    <label>Reader port</label><input name="reader_port" id="reader-port" value="{html.escape(str(input_cfg.get('reader_port', 5084)))}"/>
</div>

<label>Reader id / afsender-id</label><input name="reader_id" value="{html.escape(str(input_cfg.get('reader_id', 'fx7500')))}"/>
<div class="subtle">Bruges som identitet på readeren ved LLRP server, hvis afsenderen ikke sender sit eget id.</div>

<h3>Storage settings</h3>
<label>Storage type</label>
<select name="storage_type">
    <option value="sqlite" {'selected' if storage_cfg.get('type') == 'sqlite' else ''}>SQLite</option>
    <option value="sqlserver" {'selected' if storage_cfg.get('type') == 'sqlserver' else ''}>SQL Server</option>
    <option value="postgresql" {'selected' if storage_cfg.get('type') == 'postgresql' else ''}>PostgreSQL (planned)</option>
    <option value="mysql" {'selected' if storage_cfg.get('type') == 'mysql' else ''}>MySQL (planned)</option>
    <option value="rest_api" {'selected' if storage_cfg.get('type') == 'rest_api' else ''}>REST API</option>
    <option value="mqtt" {'selected' if storage_cfg.get('type') == 'mqtt' else ''}>MQTT (planned)</option>
</select>

<label>SQL Server connection string</label>
<input name="sqlserver_connection_string" value="{html.escape(str(storage_cfg.get('connection_string', '')))}"/>

<button type="submit">Save config</button>
</form>
</section>

<section class="card">
<h2>Parser Setup + Preview</h2>
<div class="subtle">Her definerer du hvordan rå data skal oversættes til et event, og tester resultatet direkte.</div>
<form method="post" action="/save-config">
<h3>Parser setup</h3>
<div class="subtle">Bruges til standardfelter, alias-mapping for fx tag_id, reader_id, antenna, rssi og timestamp samt fallback-adfærd.</div>
<label>Default event type</label>
<input name="parser_default_event_type" value="{html.escape(str(parser_cfg.get('default_event_type', 'scan')))}"/>
<label>Required tag field</label>
<input name="parser_required_tag_field" value="{html.escape(str(parser_cfg.get('required_tag_field', 'tag_id')))}"/>
<label>Key aliases (JSON)</label>
<textarea name="parser_key_aliases">{html.escape(json.dumps(parser_cfg.get('key_aliases', {}), indent=2))}</textarea>
<div class="subtle">Eksempel: <code>"epc": "tag_id"</code> betyder at <code>epc</code> kommer fra afsenderen, og <code>tag_id</code> er navnet på databasefeltet. Andre eksempler: <code>"reader": "reader_id"</code>, <code>"antenna_index": "antenna"</code>, <code>"signal_strength": "rssi"</code>, <code>"timestamp": "event_time"</code>.</div>
<label style="display:flex; align-items:flex-start; gap:8px; margin-top:8px;">
    <input type="checkbox" name="parser_allow_plain_tag_id" {'checked' if bool(parser_cfg.get('allow_plain_tag_id', True)) else ''} style="margin-top:2px; width:auto;"/>
    <span>Allow plain tag id <span class="subtle" style="display:inline; margin-left:6px;">Eksempel: <code>"epc": "tag_id"</code> betyder at <code>epc</code> kommer fra afsenderen, og <code>tag_id</code> er navnet på databasefeltet. Andre eksempler: <code>"reader": "reader_id"</code>, <code>"antenna_index": "antenna"</code>, <code>"signal_strength": "rssi"</code>, <code>"timestamp": "event_time"</code>.</span></span>
</label>
<button type="submit">Save parser setup</button>
</form>

<h3>Preview</h3>
<div class="subtle">Indsæt et eksempel og se det normaliserede output før du gemmer eller tester live data.</div>
<label>Sample payload</label>
<textarea id="preview-input">{{"epc":"E2000017221101441890ABCD","reader":"R1"}}</textarea>
<button type="button" onclick="runPreview()">Run preview</button>
<label>Preview output</label>
<textarea id="preview-output" readonly></textarea>
</section>
</div>

<section class="card">
<h2>Latest Senders</h2>
<p>Total senders: <strong id="total-senders">{status_snapshot.get('total_senders', 0)}</strong> |
Raw: <strong id="total-raw">{status_snapshot.get('total_raw_messages', 0)}</strong> |
Events: <strong id="total-events">{status_snapshot.get('total_events', 0)}</strong> |
Errors: <strong id="total-errors">{status_snapshot.get('total_errors', 0)}</strong></p>
<table>
    <thead>
        <tr>
            <th>Sender</th><th>Protocol</th><th>Last Seen</th><th>Raw</th><th>Events</th><th>Parse Err</th><th>Storage Err</th><th>Last EPC</th><th>Last Error</th>
        </tr>
    </thead>
    <tbody id="status-body">{latest_rows}</tbody>
</table>
</section>

<script>
function updateProtocolVisibility() {{
    const protocol = document.getElementById('input-protocol').value;
    const hostPortGroup = document.getElementById('host-port-group');
    const readerGroup = document.getElementById('reader-group');
    const help = document.getElementById('protocol-help');

    const hostInput = document.getElementById('input-host');
    const portInput = document.getElementById('input-port');
    const readerHostInput = document.getElementById('reader-host');
    const readerPortInput = document.getElementById('reader-port');

    const showHostPort = protocol === 'text_tcp' || protocol === 'llrp_server';
    const showReader = protocol === 'llrp_client';

    hostPortGroup.style.display = showHostPort ? 'block' : 'none';
    readerGroup.style.display = showReader ? 'block' : 'none';
    hostPortGroup.classList.toggle('is-disabled', !showHostPort);
    readerGroup.classList.toggle('is-disabled', !showReader);

    hostInput.disabled = !showHostPort;
    portInput.disabled = !showHostPort;
    readerHostInput.disabled = !showReader;
    readerPortInput.disabled = !showReader;

    if (protocol === 'llrp_client') {{
        help.textContent = 'llrp_client: tjenesten forbinder ud til readerens LLRP-port.';
    }} else if (protocol === 'llrp_server') {{
        help.textContent = 'llrp_server: readeren sender til denne servers host og port.';
    }} else {{
        help.textContent = 'text_tcp: lokale events modtages på host og port.';
    }}
}}

async function refreshStatus() {{
    const r = await fetch('/api/status');
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById('total-senders').textContent = d.total_senders || 0;
    document.getElementById('total-raw').textContent = d.total_raw_messages || 0;
    document.getElementById('total-events').textContent = d.total_events || 0;
    document.getElementById('total-errors').textContent = d.total_errors || 0;
    const rows = (d.latest_senders || []).map(row =>
        `<tr><td>${{row.sender_id || ''}}</td><td>${{row.protocol || ''}}</td><td>${{row.last_seen || ''}}</td><td>${{row.raw_messages || 0}}</td><td>${{row.events || 0}}</td><td>${{row.parse_errors || 0}}</td><td>${{row.storage_errors || 0}}</td><td>${{row.last_tag_id || ''}}</td><td>${{row.last_error || ''}}</td></tr>`
    ).join('');
    document.getElementById('status-body').innerHTML = rows;
}}

async function runPreview() {{
    const payload = document.getElementById('preview-input').value || '';
    const r = await fetch('/api/parser-preview', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ payload }})
    }});
    const d = await r.json();
    document.getElementById('preview-output').value = JSON.stringify(d, null, 2);
}}

updateProtocolVisibility();
setInterval(refreshStatus, 5000);
</script>
</body>
</html>"""


class _GUIHandler(BaseHTTPRequestHandler):
    config_path: Path
    status_tracker: StatusTracker
    logger: logging.Logger

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            payload = json.dumps(self.status_tracker.snapshot()).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        config = _load_config(self.config_path)
        page = _render_page(config, self.status_tracker.snapshot())
        payload = page.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/parser-preview":
            self._handle_parser_preview()
            return
        if parsed.path == "/restart-service":
            config = _load_config(self.config_path)
            page = _render_page(
                config,
                self.status_tracker.snapshot(),
                message="Genstart tjenesten manuelt for at aktivere ændringerne.",
                restart_prompt=False,
            )
            payload = page.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if parsed.path != "/save-config":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        form = parse_qs(body)
        config = _load_config(self.config_path)
        input_cfg = config.setdefault("input", {})
        parser_cfg = config.setdefault("parser_setup", {})
        storage_cfg = config.setdefault("storage", {})

        input_cfg["protocol"] = str(form.get("input_protocol", [input_cfg.get("protocol", "text_tcp")])[0])
        input_cfg["host"] = str(form.get("input_host", [input_cfg.get("host", "0.0.0.0")])[0])
        input_cfg["port"] = int(str(form.get("input_port", [input_cfg.get("port", 9002)])[0]))
        input_cfg["reader_host"] = str(form.get("reader_host", [input_cfg.get("reader_host", "")])[0])
        input_cfg["reader_port"] = int(str(form.get("reader_port", [input_cfg.get("reader_port", 5084)])[0]))
        input_cfg["reader_id"] = str(form.get("reader_id", [input_cfg.get("reader_id", "fx7500")])[0])

        parser_cfg["default_event_type"] = str(
            form.get("parser_default_event_type", [parser_cfg.get("default_event_type", "scan")])[0]
        )
        parser_cfg["required_tag_field"] = str(
            form.get("parser_required_tag_field", [parser_cfg.get("required_tag_field", "tag_id")])[0]
        )
        parser_cfg["allow_plain_tag_id"] = _as_bool(
            form, "parser_allow_plain_tag_id", bool(parser_cfg.get("allow_plain_tag_id", True))
        )

        aliases_text = str(form.get("parser_key_aliases", [json.dumps(parser_cfg.get("key_aliases", {}))])[0])
        try:
            aliases = json.loads(aliases_text)
            parser_cfg["key_aliases"] = aliases if isinstance(aliases, dict) else {}
            parser_message = "Saved"
        except Exception:
            parser_message = "Saved with parser alias warning"

        storage_cfg["type"] = str(form.get("storage_type", [storage_cfg.get("type", "sqlite")])[0]).lower()
        storage_cfg["connection_string"] = str(
            form.get("sqlserver_connection_string", [storage_cfg.get("connection_string", "")])[0]
        )

        _save_config(self.config_path, config)
        page = _render_page(config, self.status_tracker.snapshot(), message=parser_message, restart_prompt=True)
        payload = page.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_parser_preview(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        payload_text = ""
        try:
            req = json.loads(body) if body else {}
            payload_text = str(req.get("payload", ""))
        except Exception:
            payload_text = body

        config = _load_config(self.config_path)
        parser_cfg = config.get("parser_setup", {})
        input_cfg = config.get("input", {})
        reader_id = str(input_cfg.get("reader_id", "fx7500"))
        try:
            event = parse_event(payload_text, parser_config=parser_cfg, default_reader_id=reader_id)
            result = {"ok": True, "event": event}
            status = HTTPStatus.OK
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
            status = HTTPStatus.BAD_REQUEST

        payload = json.dumps(result).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: Any) -> None:
        self.logger.debug("GUI %s - %s", self.client_address[0], fmt % args)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        payload_text = ""
        try:
            req = json.loads(body) if body else {}
            payload_text = str(req.get("payload", ""))
        except Exception:
            payload_text = body

        parser_cfg = _load_config(self.config_path).get("parser_setup", {})
        try:
            event = parse_event(payload_text, parser_config=parser_cfg)
            result = {"ok": True, "event": event}
            status = HTTPStatus.OK
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
            status = HTTPStatus.BAD_REQUEST

        payload = json.dumps(result).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: Any) -> None:
        self.logger.debug("GUI %s - %s", self.client_address[0], fmt % args)


class GUIService:
    def __init__(self, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        self._server = server
        self._thread = thread

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=3)


def start_gui_server(
    config_path: str,
    status_tracker: StatusTracker,
    logger: logging.Logger,
    host: str = "127.0.0.1",
    port: int = 8088,
) -> GUIService:
    handler = type("RuntimeGUIHandler", (_GUIHandler,), {})
    handler.config_path = Path(config_path)
    handler.status_tracker = status_tracker
    handler.logger = logger

    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("GUI server started at http://%s:%s", host, port)
    return GUIService(server=server, thread=thread)
