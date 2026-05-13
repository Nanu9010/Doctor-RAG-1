"""
import_schema.py - Run this to initialize the database schema
Usage: python import_schema.py
"""
import os
import sys
import pymysql
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "doctor_rag_1")
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASSWORD", "")

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql')

print(f"Connecting to MySQL: {DB_USER}@{DB_HOST}:{DB_PORT}")

try:
    # Connect without specifying DB to create it if needed
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASS,
        charset='utf8mb4', autocommit=True
    )
    cursor = conn.cursor()

    # Create database
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    print(f"[OK] Database '{DB_NAME}' ready")

    # Switch to DB
    cursor.execute(f"USE `{DB_NAME}`")

    # Read schema
    with open(SCHEMA_FILE, 'r') as f:
        sql = f.read()

    # Execute statements
    for stmt in sql.split(';'):
        stmt = stmt.strip()
        if not stmt or stmt.startswith('--') or stmt.upper().startswith('CREATE DATABASE') or stmt.upper().startswith('USE '):
            continue
        try:
            cursor.execute(stmt)
            print(f"  [OK] {stmt[:60]}...")
        except pymysql.err.OperationalError as e:
            if e.args[0] in (1050,):  # table exists
                print(f"  [SKIP] Already exists: {stmt[:50]}")
            else:
                print(f"  [ERR] Error: {e}")

    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\n[OK] Tables in '{DB_NAME}': {tables}")

    conn.close()
    print("\n[DONE] Schema import complete!")

except Exception as e:
    print(f"\n[FAIL] Failed: {e}")
    sys.exit(1)
