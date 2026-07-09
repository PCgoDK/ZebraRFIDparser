from __future__ import annotations

from csv_adapter import CSVAdapter
from rest_api_adapter import RESTAPIAdapter
from sqlserver_adapter import SQLServerAdapter
from storage_factory import create_storage_adapter
from sqlite_adapter import SQLiteAdapter


def test_create_sqlite_adapter_default() -> None:
    adapter = create_storage_adapter({"type": "sqlite"})
    assert isinstance(adapter, SQLiteAdapter)


def test_create_sqlite_adapter_custom_config() -> None:
    adapter = create_storage_adapter(
        {
            "type": "sqlite",
            "database_path": "./tmp/custom.db",
            "schema_path": "./sql/schema.sql",
        }
    )
    assert isinstance(adapter, SQLiteAdapter)
    assert adapter.database_path == "./tmp/custom.db"
    assert adapter.schema_path == "./sql/schema.sql"


def test_create_csv_adapter_custom_config() -> None:
    adapter = create_storage_adapter(
        {
            "type": "csv",
            "csv_path": "./tmp/events.csv",
        }
    )
    assert isinstance(adapter, CSVAdapter)
    assert adapter.file_path == "./tmp/events.csv"


def test_future_backends_not_implemented() -> None:
    for backend in ["postgresql", "mqtt"]:
        try:
            create_storage_adapter({"type": backend})
            assert False, f"Expected NotImplementedError for {backend}"
        except NotImplementedError:
            pass


def test_create_sqlserver_adapter() -> None:
    adapter = create_storage_adapter(
        {
            "type": "sqlserver",
            "server": "sql-host,1433",
            "database": "RFIDEvents",
            "username": "sa",
            "password": "secret",
            "driver": "ODBC Driver 18 for SQL Server",
            "table_name": "rfid_events",
        }
    )
    assert isinstance(adapter, SQLServerAdapter)
    assert adapter.server == "sql-host,1433"
    assert adapter.database == "RFIDEvents"
    assert adapter.username == "sa"
    assert adapter.table_name == "rfid_events"


def test_create_rest_api_adapter() -> None:
    adapter = create_storage_adapter(
        {
            "type": "rest_api",
            "endpoint_url": "https://example.local/events",
            "timeout_seconds": 7.5,
            "method": "POST",
            "headers": {"X-App": "rfid"},
            "bearer_token": "abc",
            "payload_key": "event",
        }
    )
    assert isinstance(adapter, RESTAPIAdapter)
    assert adapter.endpoint_url == "https://example.local/events"
    assert adapter.timeout_seconds == 7.5
    assert adapter.method == "POST"
    assert adapter.headers == {"X-App": "rfid"}
    assert adapter.bearer_token == "abc"
    assert adapter.payload_key == "event"


def test_unsupported_backend_raises() -> None:
    try:
        create_storage_adapter({"type": "unknown_backend"})
        assert False, "Expected ValueError for unsupported backend"
    except ValueError as exc:
        assert "Unsupported" in str(exc)
