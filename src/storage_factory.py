from __future__ import annotations

from typing import Any, Dict

from csv_adapter import CSVAdapter
from rest_api_adapter import RESTAPIAdapter
from sqlserver_adapter import SQLServerAdapter
from sqlite_adapter import SQLiteAdapter
from storage_adapter import StorageAdapter


def create_storage_adapter(storage_config: Dict[str, Any]) -> StorageAdapter:
    adapter_type = str(storage_config.get("type", "sqlite")).strip().lower()

    if adapter_type == "sqlite":
        database_path = storage_config.get("database_path", "./data/rfid_events.db")
        schema_path = storage_config.get("schema_path", "./sql/schema.sql")
        return SQLiteAdapter(database_path=database_path, schema_path=schema_path)

    if adapter_type == "csv":
        file_path = str(storage_config.get("csv_path", "./data/rfid_events.csv"))
        return CSVAdapter(file_path=file_path)

    if adapter_type == "sqlserver":
        return SQLServerAdapter(
            connection_string=(
                str(storage_config.get("connection_string")).strip()
                if storage_config.get("connection_string")
                else None
            ),
            server=(str(storage_config.get("server")).strip() if storage_config.get("server") else None),
            database=(
                str(storage_config.get("database")).strip() if storage_config.get("database") else None
            ),
            username=(
                str(storage_config.get("username")).strip() if storage_config.get("username") else None
            ),
            password=(str(storage_config.get("password")) if storage_config.get("password") is not None else None),
            driver=str(storage_config.get("driver", "ODBC Driver 18 for SQL Server")),
            trusted_connection=bool(storage_config.get("trusted_connection", False)),
            table_name=str(storage_config.get("table_name", "rfid_events")),
            connect_timeout_seconds=int(storage_config.get("connect_timeout_seconds", 5)),
            create_table_if_missing=bool(storage_config.get("create_table_if_missing", True)),
        )

    if adapter_type == "postgresql":
        raise NotImplementedError("PostgreSQL adapter is planned but not implemented yet")

    if adapter_type == "mqtt":
        raise NotImplementedError("MQTT adapter is planned but not implemented yet")

    if adapter_type == "rest_api":
        endpoint_url = str(storage_config.get("endpoint_url", "")).strip()
        timeout_seconds = float(storage_config.get("timeout_seconds", 5.0))
        method = str(storage_config.get("method", "POST"))
        headers = storage_config.get("headers", {})
        bearer_token = storage_config.get("bearer_token")
        payload_key = storage_config.get("payload_key")
        return RESTAPIAdapter(
            endpoint_url=endpoint_url,
            timeout_seconds=timeout_seconds,
            method=method,
            headers=headers if isinstance(headers, dict) else {},
            bearer_token=str(bearer_token) if bearer_token is not None else None,
            payload_key=str(payload_key) if payload_key is not None else None,
        )

    raise ValueError(f"Unsupported storage adapter type: {adapter_type}")
