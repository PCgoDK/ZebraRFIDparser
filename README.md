# Zebra RFID Parser

Zebra RFID Parser is a Python 3 receiver service that ingests RFID events (text TCP or LLRP) and stores them via a storage adapter interface.

## Features

- Python 3 implementation
- Built-in web GUI for configuration and runtime monitoring
- TCP text server for incoming RFID events
- LLRP adapter server for RO_ACCESS_REPORT messages (for readers such as Zebra FX7500)
- Storage adapter interface for pluggable backends
- SQLite adapter included as default backend
- CSV file adapter included
- SQL Server adapter implementation included
- REST API adapter implementation included
- Future adapter support prepared in the factory:
  - PostgreSQL
  - MQTT
- Linux systemd service unit included

## Project Structure

```text
src/
    main.py
  gui_server.py
  status_tracker.py
    tcp_server.py
    llrp_adapter.py
    dedup_storage_adapter.py
    sqlserver_adapter.py
    rest_api_adapter.py
    parser.py
    storage_adapter.py
    sqlite_adapter.py
    storage_factory.py

sql/
    schema.sql

systemd/
  zebra-rfid-parser.service

config/
    config.json.example

install.sh
uninstall.sh
README.md
```

## Configuration

Copy `config/config.json.example` to your runtime config path and adjust as needed:

```json
{
  "log_level": "INFO",
  "gui": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 8088
  },
  "input": {
    "protocol": "llrp_server",
    "host": "0.0.0.0",
    "port": 9000,
    "reader_host": "192.168.1.100",
    "reader_port": 5084,
    "reader_id": "fx7500",
    "reconnect_delay_seconds": 2.0,
    "socket_timeout_seconds": 5.0
  },
  "parser_setup": {
    "default_event_type": "scan",
    "required_tag_field": "tag_id",
    "allow_plain_tag_id": true,
    "key_aliases": {
      "epc": "tag_id",
      "reader": "reader_id"
    }
  },
  "storage": {
    "type": "sqlite",
    "database_path": "/var/lib/zebra-rfid-parser/rfid_events.db",
    "schema_path": "/opt/zebra-rfid-parser/sql/schema.sql",
    "csv_path": "/home/pcgo/Documents/data.csv",
    "endpoint_url": "https://example.local/rfid/events",
    "timeout_seconds": 5.0,
    "method": "POST",
    "headers": {
      "X-Source": "zebra-rfid-parser"
    },
    "bearer_token": "",
    "payload_key": "event"
  },
  "duplicate_filter": {
    "enabled": true,
    "window_seconds": 2.0,
    "key_fields": ["tag_id", "reader_id", "antenna"],
    "metrics_log_interval_seconds": 30.0
  }
}
```

`gui` settings:

- `gui.enabled`: starter GUI-serveren sammen med parser-servicen
- `gui.host`: bind-adresse for GUI
- `gui.port`: port for GUI (default `8088`)

`parser_setup` settings:

- `default_event_type`: fallback event type
- `required_tag_field`: obligatorisk felt i parsed event
- `allow_plain_tag_id`: tillad plain EPC-linje som fallback
- `key_aliases`: map input-nogler til interne feltnavne

`storage.type` values:

- `sqlite`: writes events to local SQLite
- `csv`: appends events to a local CSV file (`storage.csv_path`)
- `sqlserver`: writes events to SQL Server via ODBC (`pyodbc`)
- `rest_api`: posts each event as JSON to `storage.endpoint_url`

When `storage.type` is `csv`, configure:

- `csv_path`: destination CSV file path (default `/home/pcgo/Documents/data.csv`)

When `storage.type` is `sqlserver`, configure either:

- `connection_string` directly, or
- `server` + `database` + auth settings (`trusted_connection` or `username`/`password`)

Additional SQL Server settings:

- `driver` (default `ODBC Driver 18 for SQL Server`)
- `table_name` (default `rfid_events`)
- `connect_timeout_seconds`
- `create_table_if_missing`

Install requirement for SQL Server adapter:

```bash
python -m pip install pyodbc
```

When `storage.type` is `rest_api`, configure:

- `endpoint_url`: target HTTP(S) endpoint
- `timeout_seconds`: request timeout
- `method`: HTTP method (typically `POST`)
- `headers`: additional HTTP headers
- `bearer_token`: optional bearer token
- `payload_key`: optional wrapper key for payload body

`input.protocol` values:

- `text_tcp`: newline-delimited text events (JSON, key=value, or plain tag)
- `llrp_client`: connects to the reader LLRP endpoint (default `reader_port: 5084`)
- `llrp_server`: listens for inbound LLRP frames (default mode)

## Supported Incoming Event Formats

Each event must be sent as one line terminated by `\n`.

1. JSON (preferred)

```json
{"tag_id":"E2000017221101441890ABCD","reader_id":"R1","antenna":"1","event_type":"scan"}
```

2. Key-value pairs

```text
tag_id=E2000017221101441890ABCD,reader_id=R1,antenna=1,event_type=scan
```

3. Plain tag id (fallback)

```text
E2000017221101441890ABCD
```

The parser ensures `event_time` is present (UTC ISO-8601), defaulting when missing.

## LLRP Adapter Notes

When `input.protocol` is set to `llrp_client`, the service opens a TCP connection to the configured reader host/port and consumes binary LLRP messages.

Current LLRP support includes:

- `RO_ACCESS_REPORT` message decoding
- `TagReportData` extraction
- EPC from `EPCData` (parameter 241) or `EPC-96` (TV parameter 13)
- Optional fields when present: antenna, RSSI, seen count, timestamp
- `KEEPALIVE` handling with `KEEPALIVE_ACK` response
- Automatic reconnect when the reader connection drops

Unsupported or non-tag LLRP messages are ignored.

## Duplicate EPC Filtering

Duplicate suppression is enabled by default and is applied before writes, while still using the `StorageAdapter` interface for all persistence.

- `duplicate_filter.enabled`: turn filtering on/off
- `duplicate_filter.window_seconds`: duplicate suppression window
- `duplicate_filter.key_fields`: event fields used to identify a duplicate
- `duplicate_filter.metrics_log_interval_seconds`: log dedupe counters every N seconds

With defaults, repeated reads of the same EPC from the same reader/antenna within 2 seconds are dropped.

Example dedupe metric log entry:

```text
Dedup metrics: received=1200 stored=640 dropped_duplicates=560 active_keys=87 window_seconds=2.0
```

## GUI

GUI bruges til:

- Konfiguration af server-protokol, host/port og reader settings
- Opsaetning af parser (required field, default type, key aliases)
- Visning af aktuel status for seneste afsendere af data
- Valg af mappe til CSV-output via knappen `Vaelg mappe` (saetter automatisk filnavn til `data.csv`)

Bemark om mappevalg i browser:

- GUI bruger en server-side mappebrowser, ikke en native OS-dialog
- Browser-sikkerhed tillader ikke en rigtig server-filvaelger dialogboks

Naar service er startet med `gui.enabled=true`, aabn:

```text
http://127.0.0.1:8088
```

Hvis du tilgaar enheden eksternt, brug SSH tunnel:

```bash
ssh -L 8088:127.0.0.1:8088 pcgo@<enhed-ip>
```

og aabn derefter `http://127.0.0.1:8088` lokalt.

Status-panelet viser blandt andet:

- Seneste afsendere
- Sidst set tidspunkt
- Antal raw beskeder
- Antal parse/store events
- Seneste EPC pr. afsender

Example LLRP client input configuration:

```json
{
  "input": {
    "protocol": "llrp_client",
    "reader_host": "192.168.1.100",
    "reader_port": 5084,
    "reader_id": "fx7500"
  }
}
```

## Run Locally

From project root:

```bash
cp config/config.json.example config/config.json
python3 src/main.py --config config/config.json
```

Send a test event:

```bash
echo '{"tag_id":"E2000017221101441890ABCD","reader_id":"R1"}' | nc 127.0.0.1 9000
```

Note: Kommandoen ovenfor gaelder for `text_tcp`. Standard er `llrp_server`.

## Testing

Run the automated tests:

```bash
python -m pytest -q
```

## Install As systemd Service

```bash
sudo chmod +x install.sh uninstall.sh
sudo ./install.sh
```

Check service status:

```bash
sudo systemctl status zebra-rfid-parser.service
```

View logs:

```bash
journalctl -u zebra-rfid-parser.service -f
```

Post-install verification:

```bash
sudo systemctl is-enabled zebra-rfid-parser.service
sudo systemctl is-active zebra-rfid-parser.service
ss -ltn | grep 8088
curl -s -o /tmp/gui.html -w "%{http_code}\n" http://127.0.0.1:8088/
```

Note: `curl -I` (HEAD) can return `501 Unsupported method` on the built-in GUI handler.
Use a normal GET request for verification as shown above.

If the service fails with missing config (`/etc/zebra-rfid-parser/config.json`):

```bash
sudo mkdir -p /etc/zebra-rfid-parser
sudo cp config/config.json.example /etc/zebra-rfid-parser/config.json
sudo chown root:rfidcollector /etc/zebra-rfid-parser/config.json
sudo chmod 640 /etc/zebra-rfid-parser/config.json
sudo systemctl restart zebra-rfid-parser.service
```

## Uninstall

```bash
sudo ./uninstall.sh
```
