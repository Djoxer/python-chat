import socket
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# ─── Konfiguration ───────────────────────────────────────────────────────────
HOST = '127.0.0.1'   # Server-IP — für LAN ändern, z.B. '192.168.1.x'
PORT = 55555

# Globale Socket- und Username-Referenz
client   = None
username = None

# ─── Hauptfenster (wird erst nach erfolgreichem Login sichtbar) ──────────────
root = tk.Tk()
root.title("Python Chat")
root.geometry("600x500")
root.withdraw()   # erstmal versteckt — wird in try_connect() aufgedeckt

# Chat-Textbereich mit Scrollbar
text_area = tk.Text(root, wrap="word", state="disabled", font=("Consolas", 11))
scrollbar = ttk.Scrollbar(root, orient="vertical", command=text_area.yview)
text_area.configure(yscrollcommand=scrollbar.set)

# Eingabezeile unten
frame_bottom = ttk.Frame(root)
entry        = ttk.Entry(frame_bottom, font=("Consolas", 11))
send_btn     = ttk.Button(frame_bottom, text="Send", width=10)

# ─── Login-Fenster ───────────────────────────────────────────────────────────
login = tk.Toplevel()
login.title("Chat beitreten")
login.geometry("380x220")
login.resizable(False, False)

tk.Label(login, text="Benutzername:", font=("Arial", 12)).pack(pady=(30, 10))

username_entry = ttk.Entry(login, width=35, font=("Consolas", 12))
username_entry.pack(pady=10)
username_entry.focus()

status_label = tk.Label(login, text="", fg="red", font=("Arial", 10))
status_label.pack(pady=5)

def try_connect():
    """
    Verbindet zum Server, sendet den Username als erstes Paket.
    Bei Erfolg: Login-Fenster schließen, Chat-Fenster aufbauen, Receive-Thread starten.
    """
    global client, username

    name = username_entry.get().strip()
    if not name:
        status_label.config(text="Bitte einen Namen eingeben")
        return

    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((HOST, PORT))
        client.send(name.encode('utf-8'))   # Server erwartet Username als erstes Paket

        username = name
        status_label.config(text="Verbunden!", fg="green")

        # Login nach kurzer Verzögerung schließen (damit "Verbunden!" kurz sichtbar ist)
        login.after(800, login.destroy)

        # Chat-Fenster aufbauen und sichtbar machen
        root.deiconify()
        root.title(f"Chat - {username}")

        text_area.pack(side="top", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        frame_bottom.pack(side="bottom", fill="x", padx=10, pady=10)
        entry.pack(side="left", fill="x", expand=True)
        send_btn.pack(side="right", padx=(10, 0))

        # Receive-Thread läuft als Daemon — stirbt automatisch wenn Hauptfenster geschlossen wird
        threading.Thread(target=receive_messages, daemon=True).start()

        entry.focus()
        entry.bind("<Return>", lambda e: send_message())

    except Exception as e:
        status_label.config(text=f"Verbindung fehlgeschlagen: {e}")

def send_message():
    """Sendet die aktuelle Eingabe an den Server. /quit beendet den Client."""
    msg = entry.get().strip()
    if not msg:
        return

    if msg.lower() == "/quit":
        try:
            client.send("/quit".encode('utf-8'))
        except:
            pass
        root.quit()
        return

    try:
        client.send((msg + "\n").encode('utf-8'))
        entry.delete(0, tk.END)
    except:
        # Sendefehler = Verbindung wahrscheinlich unterbrochen
        text_area.config(state="normal")
        text_area.insert("end", ">>> Sendefehler – Verbindung unterbrochen?\n")
        text_area.config(state="disabled")
        text_area.see("end")

def receive_messages():
    """
    Läuft in eigenem Thread. Empfängt Nachrichten vom Server und fügt sie
    in den Text-Bereich ein. Thread-safe via text_area state toggle.
    """
    while True:
        try:
            data = client.recv(1024)
            if not data:
                break   # Server hat Verbindung getrennt

            msg = data.decode('utf-8', errors='replace').rstrip()

            text_area.config(state="normal")
            text_area.insert("end", msg + "\n")
            text_area.config(state="disabled")
            text_area.see("end")   # automatisch nach unten scrollen

        except:
            text_area.config(state="normal")
            text_area.insert("end", "\n>>> Verbindung verloren\n")
            text_area.config(state="disabled")
            text_area.see("end")
            break

    # Nach Verbindungsverlust Fenster sauber beenden (im Main-Thread)
    root.after(0, lambda: root.quit())

# ─── Login-Fenster finalisieren ──────────────────────────────────────────────
ttk.Button(login, text="Beitreten", command=try_connect).pack(pady=20)
username_entry.bind("<Return>", lambda e: try_connect())
send_btn.config(command=send_message)

login.protocol("WM_DELETE_WINDOW", root.quit)
root.protocol("WM_DELETE_WINDOW", root.quit)

# ─── Start ───────────────────────────────────────────────────────────────────
root.mainloop()

# Cleanup nach Fenster-Schließen
if client:
    try:
        client.close()
    except:
        pass
