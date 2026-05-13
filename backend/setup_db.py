"""
setup_db.py — Direct database setup without shell escaping issues
Run: python setup_db.py
"""
import sys
import os

# Load env from current dir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pymysql

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "doctor_rag_1")
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASSWORD", "")

print(f"Setting up database: {DB_NAME} on {DB_USER}@{DB_HOST}:{DB_PORT}")

try:
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASS,
        charset="utf8mb4", autocommit=True
    )
    cursor = conn.cursor()

    # Create DB
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cursor.execute(f"USE `{DB_NAME}`")
    print(f"[OK] Database '{DB_NAME}' selected")

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          VARCHAR(36)  NOT NULL PRIMARY KEY,
            email       VARCHAR(255) NOT NULL UNIQUE,
            name        VARCHAR(255) NOT NULL,
            password    VARCHAR(255) NOT NULL,
            created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
    """)
    print("[OK] Table: users")

    # Documents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id              VARCHAR(36)   NOT NULL PRIMARY KEY,
            user_id         VARCHAR(36)   NOT NULL,
            filename        VARCHAR(512)  NOT NULL,
            original_name   VARCHAR(512)  NOT NULL,
            file_path       VARCHAR(1024) NOT NULL,
            file_size       BIGINT        NOT NULL DEFAULT 0,
            mime_type       VARCHAR(128)  NOT NULL DEFAULT 'application/pdf',
            status          ENUM('UPLOADED','PROCESSING','READY','FAILED') NOT NULL DEFAULT 'UPLOADED',
            error_message   TEXT          NULL,
            page_count      INT           NULL,
            chunk_count     INT           NULL,
            ocr_used        BOOLEAN       NOT NULL DEFAULT FALSE,
            pinecone_namespace VARCHAR(128) NULL,
            created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_doc_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_doc_user   (user_id),
            INDEX idx_doc_status (status)
        ) ENGINE=InnoDB
    """)
    print("[OK] Table: documents")

    # Chat sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id          VARCHAR(36)  NOT NULL PRIMARY KEY,
            user_id     VARCHAR(36)  NOT NULL,
            document_id VARCHAR(36)  NOT NULL,
            title       VARCHAR(512) NOT NULL DEFAULT 'New Chat',
            created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_session_user FOREIGN KEY (user_id)     REFERENCES users(id)     ON DELETE CASCADE,
            CONSTRAINT fk_session_doc  FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            INDEX idx_session_user (user_id),
            INDEX idx_session_doc  (document_id)
        ) ENGINE=InnoDB
    """)
    print("[OK] Table: chat_sessions")

    # Chat messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id              VARCHAR(36)   NOT NULL PRIMARY KEY,
            session_id      VARCHAR(36)   NOT NULL,
            user_id         VARCHAR(36)   NOT NULL,
            role            ENUM('user','assistant') NOT NULL,
            content         TEXT          NOT NULL,
            source_chunks   JSON          NULL,
            confidence      FLOAT         NULL,
            tokens_used     INT           NULL,
            created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_msg_session FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
            CONSTRAINT fk_msg_user    FOREIGN KEY (user_id)    REFERENCES users(id)         ON DELETE CASCADE,
            INDEX idx_msg_session (session_id),
            INDEX idx_msg_created (created_at)
        ) ENGINE=InnoDB
    """)
    print("[OK] Table: chat_messages")

    # Processing jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_jobs (
            id           VARCHAR(36)  NOT NULL PRIMARY KEY,
            document_id  VARCHAR(36)  NOT NULL,
            attempts     INT          NOT NULL DEFAULT 0,
            max_attempts INT          NOT NULL DEFAULT 3,
            last_error   TEXT         NULL,
            created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_job_doc FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        ) ENGINE=InnoDB
    """)
    print("[OK] Table: processing_jobs")

    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\n[DONE] All tables in '{DB_NAME}': {tables}")

    conn.close()
    print("[DONE] Database setup complete! You can now start the Flask server.")

except Exception as e:
    print(f"[FAIL] Setup failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
