import os
import threading
import pymysql
from datetime import datetime
from typing import Optional, List, Dict

# ──────────────────────────────────────────────────────────────────────────────
#  PythonChatDB — CRUD-Wrapper für die pythonchat-Datenbank
#
#  Konfiguration via Umgebungsvariablen (siehe .env.example):
#    DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
#  Fallback auf localhost/root wenn keine Vars gesetzt sind.
# ──────────────────────────────────────────────────────────────────────────────

class PythonChatDB:
    def __init__(
        self,
        host:     str = os.getenv("DB_HOST",     "127.0.0.1"),
        user:     str = os.getenv("DB_USER",     "root"),
        password: str = os.getenv("DB_PASSWORD", ""),
        db:       str = os.getenv("DB_NAME",     "pythonchat"),
    ):
        self._cfg = dict(
            host=host,
            user=user,
            password=password,
            database=db,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        self._local = threading.local()

    @property
    def db(self):
        """Gibt die Verbindung des aufrufenden Threads zurück; legt sie bei Bedarf an."""
        if not hasattr(self._local, 'conn'):
            self._local.conn = pymysql.connect(**self._cfg)
        return self._local.conn

    def close(self):
        if hasattr(self._local, 'conn'):
            self._local.conn.close()

    # ─── Chats ────────────────────────────────────────────────────────────────

    def create_chat(self) -> int:
        """Legt einen neuen Chat-Raum an und gibt die DB-ID zurück."""
        with self.db.cursor() as cur:
            cur.execute("INSERT INTO chats (created) VALUES (NOW())")
            self.db.commit()
            return cur.lastrowid

    def get_chat(self, chat_id: int) -> Optional[dict]:
        """Gibt einen Chat-Datensatz anhand der ID zurück."""
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM chats WHERE id = %s", (chat_id,))
            return cur.fetchone()

    def close_chat(self, chat_id: int) -> bool:
        """Setzt den closed-Timestamp — wird bei /shutdown oder STRG+C aufgerufen."""
        with self.db.cursor() as cur:
            cur.execute("UPDATE chats SET closed = NOW() WHERE id = %s", (chat_id,))
            self.db.commit()
            return cur.rowcount > 0

    # ─── Users ────────────────────────────────────────────────────────────────

    def join_user(self, chat_id: int, username: str, ip: Optional[str] = None) -> int:
        """
        Trägt einen neuen User in die DB ein.
        IP wird als VARBINARY(4) gespeichert (IPv4 → 4 Bytes).
        Gibt die DB-ID zurück — wird in user_ids{} im Server gecacht.
        """
        ip_bin = None
        if ip:
            parts = ip.split(".")
            if len(parts) == 4:
                ip_bin = bytes(int(p) for p in parts)

        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id_chat, ip, username, joined_at)
                VALUES (%s, %s, %s, NOW())
                """,
                (chat_id, ip_bin, username),
            )
            self.db.commit()
            return cur.lastrowid

    def get_user(self, user_id: int) -> Optional[dict]:
        """Gibt einen User-Datensatz anhand der DB-ID zurück."""
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cur.fetchone()

    def leave_user(self, user_id: int) -> bool:
        """
        Setzt left_at auf NOW() — wird bei /quit, Disconnect und /shutdown
        für jeden verbundenen User aufgerufen.
        """
        with self.db.cursor() as cur:
            cur.execute("UPDATE users SET left_at = NOW() WHERE id = %s", (user_id,))
            self.db.commit()
            return cur.rowcount > 0

    # ─── Messages ─────────────────────────────────────────────────────────────

    def send_message(self, chat_id: int, user_id: int, text: str) -> int:
        """Persistiert eine Nachricht in der DB. Wird für jede Broadcast-Message aufgerufen."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (id_chat, id_user, message_text, sent_at)
                VALUES (%s, %s, %s, NOW())
                """,
                (chat_id, user_id, text),
            )
            self.db.commit()
            return cur.lastrowid

    def get_messages(self, chat_id: int, limit: int = 50) -> List[dict]:
        """
        Gibt die letzten `limit` Nachrichten eines Chats zurück (neueste zuerst).
        JOIN auf users für den Usernamen direkt im Result-Dict.
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    m.id, m.message_text, m.sent_at,
                    u.username, u.id AS user_id
                FROM messages m
                JOIN users u ON m.id_user = u.id
                WHERE m.id_chat = %s
                ORDER BY m.sent_at DESC
                LIMIT %s
                """,
                (chat_id, limit),
            )
            return cur.fetchall()
