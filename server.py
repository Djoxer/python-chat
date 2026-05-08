import socket
import struct
import threading
from datetime import datetime
import pymysql
from database import PythonChatDB

# ─── Konfiguration ───────────────────────────────────────────────────────────
HOST = '0.0.0.0'    # lauscht auf allen Interfaces — für LAN-Betrieb geeignet
PORT = 55555
ADMINS = {"admin"}   # Usernames mit /shutdown-Berechtigung — erweiterbar

db = PythonChatDB()  # DB-Verbindung beim Start — Credentials via .env

# Globale Dicts: client-Socket als Key, Werte als Value
# Bewusst als Dict statt Klasse gehalten — einfach, lesbar, für diesen Scope ausreichend
clients      = []        # alle aktiven Sockets
usernames    = {}        # socket → username
addresses    = {}        # socket → (ip, port)
user_ids     = {}        # socket → DB-user_id (für leave_user / send_message)
chat_id      = None      # wird in main() gesetzt, eine Session = ein Chat
owner_socket = None      # erster eingeloggter Client = Server-Owner
clients_lock = threading.Lock()  # schützt alle globalen Dicts/Listen inkl. owner_socket

# ─── TCP-Framing ─────────────────────────────────────────────────────────────

def _recv_exact(sock, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError
        buf += chunk
    return bytes(buf)

def send_msg(sock, data: bytes):
    sock.sendall(struct.pack('>I', len(data)) + data)

def recv_msg(sock) -> bytes:
    length = struct.unpack('>I', _recv_exact(sock, 4))[0]
    return _recv_exact(sock, length)

# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

def get_datetime():
    return datetime.now().strftime('%d.%m.%Y %H:%M:%S')

def get_time():
    return datetime.now().strftime('%H:%M:%S')

def broadcast(message: bytes):
    """Sendet eine Nachricht an alle verbundenen Clients."""
    with clients_lock:
        targets = clients[:]
    for c in targets:
        try:
            send_msg(c, message)
        except:
            cleanup_client(c)

def cleanup_client(client):
    """
    Entfernt einen Client aus allen globalen Dicts und setzt left_at in der DB.
    Wird bei /quit, Disconnect und /shutdown aufgerufen.
    """
    global owner_socket
    with clients_lock:
        if client in clients:
            clients.remove(client)
        usernames.pop(client, None)
        addresses.pop(client, None)
        uid = user_ids.pop(client, None)
        if client is owner_socket:
            owner_socket = None
    if uid:
        db.leave_user(uid)  # Abmeldezeit in DB persistieren — außerhalb des Locks (I/O)

# ─── Client Handler ──────────────────────────────────────────────────────────

def handle_client(client):
    """Läuft als eigener Thread pro verbundenem Client."""
    username = usernames.get(client, "???")
    uid = user_ids.get(client)  # DB-ID aus globalem Dict — kein DB-Lookup nötig

    while True:
        try:
            raw = recv_msg(client)
            msg = raw.decode('utf-8', errors='replace').strip()

            if msg.lower() == "/quit":
                broadcast(f"[{get_time()}] {username} hat den Chat verlassen\n".encode('utf-8'))
                cleanup_client(client)
                client.close()
                print(f"[{get_datetime()}] {username} /quit")
                break

            elif msg.lower() == "/shutdown":
                with clients_lock:
                    is_owner = (client is owner_socket)
                if not is_owner and username not in ADMINS:
                    send_msg(client, "⛔ Nur Admins oder der Server-Owner dürfen den Server herunterfahren.\n".encode('utf-8'))
                else:
                    broadcast("🔴 SERVER WIRD HERUNTERGEFAHREN...\n".encode('utf-8'))
                    print(f"[{get_datetime()}] SHUTDOWN durch {username}")
                    if chat_id is not None:
                        db.close_chat(chat_id)
                    cleanup_client(client)
                    client.close()
                    # In eigenem Thread damit der Handler sauber returnen kann
                    threading.Thread(target=shutdown_server, daemon=True).start()
                    return

            elif msg:
                if uid:
                    db.send_message(chat_id, uid, msg)
                broadcast(f"[{get_time()}] {username}: {msg}\n".encode('utf-8'))

        except:
            # Unerwarteter Disconnect (z.B. Fenster geschlossen ohne /quit)
            print(f"[{get_datetime()}] {username} unerwartet disconnected")
            if uid:
                db.leave_user(uid)
            cleanup_client(client)
            client.close()
            break

def shutdown_server():
    """Benachrichtigt alle Clients und beendet den Prozess."""
    print("Server wird beendet...")
    with clients_lock:
        targets = clients[:]
    for c in targets:
        try:
            send_msg(c, "🔴 Server wurde vom Administrator heruntergefahren.\n".encode('utf-8'))
            c.close()
        except:
            pass
    import sys
    sys.exit(0)

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    global chat_id, owner_socket

    # Neuen Chat-Datensatz in DB anlegen — jeder Server-Start = neue Session
    chat_id = db.create_chat()
    print(f"[{get_datetime()}] Neuer Chat angelegt → ID {chat_id}")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(20)
    print(f"[{get_datetime()}] Server läuft auf {HOST}:{PORT} | Chat-ID: {chat_id}")

    while True:
        client, addr = server.accept()
        print(f"[{get_datetime()}] Verbindung von {addr}")

        # Username direkt empfangen — Client sendet ihn als erstes nach Connect
        try:
            username = recv_msg(client).decode('utf-8').strip()
            if not username:
                send_msg(client, b"ERROR:Kein Username angegeben")
                client.close()
                continue
        except:
            client.close()
            continue

        # Eindeutigkeit prüfen, dann mit OK/ERROR antworten
        with clients_lock:
            taken = username in usernames.values()
            is_first = (owner_socket is None)

        if taken:
            send_msg(client, b"ERROR:Username bereits vergeben")
            client.close()
            print(f"[{get_datetime()}] Abgewiesen (Username vergeben): {username}")
            continue

        send_msg(client, b"OK")

        # User in DB registrieren, ID cachen
        uid = db.join_user(chat_id, username, addr[0])
        with clients_lock:
            user_ids[client]  = uid
            usernames[client] = username
            addresses[client] = addr
            clients.append(client)
            if is_first:
                owner_socket = client

        print(f"User {username} → DB-ID {uid}")

        join_msg = f"[{get_time()}] {username} ist dem Chat beigetreten\n".encode('utf-8')
        broadcast(join_msg)

        # Jeder Client bekommt seinen eigenen Handler-Thread
        t = threading.Thread(target=handle_client, args=(client,), daemon=True)
        t.start()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nServer wurde per STRG+C beendet")
        db.close_chat(chat_id)
    finally:
        db.close()
