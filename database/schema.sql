-- MedRAG Database Schema
-- Run: mysql -u root -p < schema.sql

CREATE DATABASE IF NOT EXISTS doctor_rag_1 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE doctor_rag_1;

-- ─────────────────────────────────────────
-- USERS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          VARCHAR(36)  NOT NULL PRIMARY KEY,  -- UUID
    email       VARCHAR(255) NOT NULL UNIQUE,
    name        VARCHAR(255) NOT NULL,
    password    VARCHAR(255) NOT NULL,              -- bcrypt hash
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ─────────────────────────────────────────
-- DOCUMENTS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id              VARCHAR(36)   NOT NULL PRIMARY KEY,  -- UUID
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
) ENGINE=InnoDB;

-- ─────────────────────────────────────────
-- CHAT SESSIONS
-- ─────────────────────────────────────────
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
) ENGINE=InnoDB;

-- ─────────────────────────────────────────
-- CHAT MESSAGES
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_messages (
    id              VARCHAR(36)   NOT NULL PRIMARY KEY,
    session_id      VARCHAR(36)   NOT NULL,
    user_id         VARCHAR(36)   NOT NULL,
    role            ENUM('user','assistant') NOT NULL,
    content         TEXT          NOT NULL,
    source_chunks   JSON          NULL,   -- [{chunk_text, score, page}]
    confidence      FLOAT         NULL,   -- avg similarity score 0–1
    tokens_used     INT           NULL,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_msg_session FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_msg_user    FOREIGN KEY (user_id)    REFERENCES users(id)         ON DELETE CASCADE,
    INDEX idx_msg_session (session_id),
    INDEX idx_msg_created (created_at)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────
-- PROCESSING JOBS (async task tracking)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS processing_jobs (
    id           VARCHAR(36)  NOT NULL PRIMARY KEY,
    document_id  VARCHAR(36)  NOT NULL,
    attempts     INT          NOT NULL DEFAULT 0,
    max_attempts INT          NOT NULL DEFAULT 3,
    last_error   TEXT         NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_job_doc FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
) ENGINE=InnoDB;
