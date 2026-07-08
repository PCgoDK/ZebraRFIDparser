from __future__ import annotations

from sqlserver_adapter import SQLServerAdapter


def test_build_connection_string_with_username_password() -> None:
    adapter = SQLServerAdapter(
        server="sql-host,1433",
        database="RFIDEvents",
        username="user1",
        password="secret",
        trusted_connection=False,
    )

    conn_str = adapter._build_connection_string()
    assert "SERVER=sql-host,1433" in conn_str
    assert "DATABASE=RFIDEvents" in conn_str
    assert "UID=user1" in conn_str
    assert "PWD=secret" in conn_str


def test_build_connection_string_with_trusted_connection() -> None:
    adapter = SQLServerAdapter(
        server="sql-host,1433",
        database="RFIDEvents",
        trusted_connection=True,
    )

    conn_str = adapter._build_connection_string()
    assert "Trusted_Connection=yes" in conn_str


def test_invalid_table_name_rejected() -> None:
    adapter = SQLServerAdapter(connection_string="DRIVER={x};SERVER=s;DATABASE=d", table_name="bad-name")
    try:
        adapter._safe_table_name()
        assert False, "Expected ValueError for invalid table name"
    except ValueError as exc:
        assert "Invalid" in str(exc)
