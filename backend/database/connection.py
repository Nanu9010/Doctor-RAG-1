"""
database/connection.py
Thread-safe MySQL connection pool using PyMySQL.
"""
import os
import threading
import pymysql
from pymysql.cursors import DictCursor
from contextlib import contextmanager


_pool_lock = threading.Lock()
_connection_pool: list[pymysql.connections.Connection] = []
_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))


def _create_connection() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        db=os.getenv("DB_NAME", "medrag"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=10,
    )


def _get_connection() -> pymysql.connections.Connection:
    with _pool_lock:
        if _connection_pool:
            conn = _connection_pool.pop()
            try:
                conn.ping(reconnect=True)
                return conn
            except Exception:
                pass  # dead connection — create fresh
        return _create_connection()


def _release_connection(conn: pymysql.connections.Connection) -> None:
    with _pool_lock:
        if len(_connection_pool) < _POOL_SIZE:
            _connection_pool.append(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass


@contextmanager
def get_db():
    """
    Usage:
        with get_db() as (conn, cursor):
            cursor.execute("SELECT ...")
            conn.commit()
    """
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        _release_connection(conn)
