import socket
import threading
from datetime import datetime
import pymysql
from database import PythonChatDB

# ─── Konfiguration ───────────────────────────────────────────────────────────
HOST = '0.0.0.0'    # lauscht auf allen Interfaces — für LAN-Betrieb geeignet
PORT = 55555

db = PythonChatDB()  # DB-Verbindung beim Start — Credentials via .env

# Globale Dicts: client-Socket als Key, Werte als Value
# Bewusst als Dict statt Klasse gehalten — einfach, lesbar, für diesen Scope ausreichend
clients   = []        # alle aktiven Sockets
usernames = {}        # socket → username
addresses = {}        # socket → (ip, port)
user_ids  = {}        # socket → DB-user_id (für leave_user / send_message)
chat_id   = None      # wird in main() gesetzt, eine Session = ein Chat
clients_lock = threading.Lock()  # schützt alle vier globalen Dicts/Listen

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
            c.send(message)
        except:
            cleanup_client(c)

def cleanup_client(client):
    """
    Entfernt einen Client aus allen globalen Dicts und setzt left_at in der DB.
    Wird bei /quit, Disconnect und /shutdown aufgerufen.
    """
    with clients_lock:
        if client in clients:
            clients.remove(client)
        usernames.pop(client, None)
        addresses.pop(client, None)
        uid = user_ids.pop(client, None)
    if uid:
        db.leave_user(uid)  # Abmeldezeit in DB persistieren — außerhalb des Locks (I/O)

# ─── Client Handler ──────────────────────────────────────────────────────────

def handle_client(client):
    """Läuft als eigener Thread pro verbundenem Client."""
    username = usernames.get(client, "???")
    uid = user_ids.get(client)  # DB-ID aus globalem Dict — kein DB-Lookup nötig

    while True:
        try:
            raw = client.recv(4096)
            if not raw:
                raise ConnectionError   # leeres Paket = Client hat Verbindung getrennt

            msg = raw.decode('utf-8', errors='replace').strip()

            if msg.lower() == "/quit":
                # Sauberes Verlassen: Broadcast → DB → Cleanup → Socket schließen
                broadcast(f"[{get_time()}] {username} hat den Chat verlassen\n".encode('utf-8'))
                if uid:
                    db.leave_user(uid)
                cleanup_client(client)
                client.close()
                print(f"[{get_datetime()}] {username} /quit")
                break

            elif msg.lower() == "/shutdown":
                # Nur für Admin-Zwecke — fährt den gesamten Server herunter
                broadcast("🔴 SERVER WIRD HERUNTERGEFAHREN...\n".encode('utf-8'))
                print(f"[{get_datetime()}] SHUTDOWN durch {username}")
                db.close_chat(chat_id)
                cleanup_client(client)
                client.close()
                # In eigenem Thread damit der Handler sauber returnen kann
                threading.Thread(target=shutdown_server, daemon=True).start()
                return

            else:
                # Normale Nachricht: in DB persistieren + an alle broadcasten
                if uid and msg:
                    db.send_message(chat_id, uid, msg)
                formatted = f"[{get_time()}] {username}: {msg}\n"
                broadcast(formatted.encode('utf-8'))

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
            c.send("🔴 Server wurde vom Administrator heruntergefahren.\n".encode('utf-8'))
            c.close()
        except:
            pass
    import sys
    sys.exit(0)

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    global chat_id

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
            username = client.recv(1024).decode('utf-8').strip()
            if not username:
                client.close()
                continue
        except:
            client.close()
            continue

        # User in DB registrieren, ID cachen
        uid = db.join_user(chat_id, username, addr[0])
        with clients_lock:
            user_ids[client]  = uid
            usernames[client] = username
            addresses[client] = addr
            clients.append(client)

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
