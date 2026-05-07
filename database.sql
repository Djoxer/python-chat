-- Datenbank mit UTF8MB4 für Emojis und Unicode
CREATE DATABASE pythonchat CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE pythonchat;

-- Tabelle: Chats
CREATE TABLE chats (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    created DATETIME DEFAULT CURRENT_TIMESTAMP,
    closed DATETIME
);

-- Tabelle: Benutzer
CREATE TABLE users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_chat BIGINT UNSIGNED NOT NULL,
    ip VARBINARY(16),
    username VARCHAR(64) NOT NULL,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    left_at DATETIME,
    FOREIGN KEY (id_chat) REFERENCES chats(id) ON DELETE CASCADE
);

-- Tabelle: Nachrichtenverlauf
CREATE TABLE messages (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_chat BIGINT UNSIGNED NOT NULL,
    id_user BIGINT UNSIGNED NOT NULL,
    message_text TEXT,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_chat) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (id_user) REFERENCES users(id) ON DELETE CASCADE
);