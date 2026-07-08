from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from storage_adapter import StorageAdapter


class SQLServerAdapter(StorageAdapter):
    def __init__(
        self,
        connection_string: Optional[str] = None,
        server: Optional[str] = None,
        database: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        driver: str = "ODBC Driver 18 for SQL Server",
        trusted_connection: bool = False,
        table_name: str = "rfid_events",
        connect_timeout_seconds: int = 5,
        create_table_if_missing: bool = True,
    ) -> None:
        self.connection_string = connection_string
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.driver = driver
        self.trusted_connection = trusted_connection
        self.table_name = table_name
        self.connect_timeout_seconds = int(connect_timeout_seconds)
        self.create_table_if_missing = bool(create_table_if_missing)
        self._conn: Any = None

    def connect(self) -> None:
        try:
            import pyodbc  # type: ignore
        except Exception as exc:
            raise RuntimeError("SQL Server adapter requires pyodbc. Install with: pip install pyodbc") from exc

        conn_str = self._build_connection_string()
        self._conn = pyodbc.connect(conn_str, timeout=self.connect_timeout_seconds)
        if self.create_table_if_missing:
            self._ensure_table()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def store_event(self, event: Dict[str, Any]) -> None:
        if self._conn is None:
            raise RuntimeError("SQL Server adapter is not connected")

        table = self._safe_table_name()
        payload = json.dumps(event, ensure_ascii=True)
        cursor = self._conn.cursor()
        cursor.execute(
            f"""
            INSERT INTO {table} (tag_id, reader_id, antenna, event_type, event_time, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("tag_id"),
                event.get("reader_id"),
                event.get("antenna"),
                event.get("event_type"),
                event.get("event_time"),
                payload,
            ),
        )
        self._conn.commit()

    def _build_connection_string(self) -> str:
        if self.connection_string:
            return self.connection_string

        if not self.server or not self.database:
            raise ValueError("SQL Server adapter requires either connection_string or server + database")

        parts = [
            f"DRIVER={{{self.driver}}}",
            f"SERVER={self.server}",
            f"DATABASE={self.database}",
            "Encrypt=yes",
            "TrustServerCertificate=yes",
        ]

        if self.trusted_connection:
            parts.append("Trusted_Connection=yes")
        else:
            if not self.username or self.password is None:
                raise ValueError(
                    "SQL Server adapter requires username/password unless trusted_connection is enabled"
                )
            parts.append(f"UID={self.username}")
            parts.append(f"PWD={self.password}")

        return ";".join(parts)

    def _safe_table_name(self) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.table_name):
            raise ValueError("Invalid SQL Server table_name")
        return f"[{self.table_name}]"

    def _ensure_table(self) -> None:
        if self._conn is None:
            raise RuntimeError("SQL Server adapter is not connected")

        table_raw = self.table_name
        table = self._safe_table_name()
        cursor = self._conn.cursor()
        cursor.execute(
            f"""
            IF OBJECT_ID(N'dbo.{table_raw}', N'U') IS NULL
            BEGIN
                CREATE TABLE {table} (
                    id BIGINT IDENTITY(1,1) PRIMARY KEY,
                    tag_id NVARCHAR(128) NULL,
                    reader_id NVARCHAR(128) NULL,
                    antenna NVARCHAR(64) NULL,
                    event_type NVARCHAR(64) NULL,
                    event_time NVARCHAR(64) NOT NULL,
                    raw_payload NVARCHAR(MAX) NOT NULL,
                    received_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
                );
                CREATE INDEX IX_{table_raw}_event_time ON {table}(event_time);
                CREATE INDEX IX_{table_raw}_tag_id ON {table}(tag_id);
            END
            """
        )
        self._conn.commit()
