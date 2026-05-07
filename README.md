# python-chat

A TCP chat application with GUI client, multi-threaded server, and MySQL message logging.

Built with Python's standard library (`socket`, `threading`, `tkinter`) and `pymysql`.

## Features

- Multi-client TCP server — handles simultaneous connections via threads
- Tkinter GUI client with login window and scrollable chat area
- MySQL logging — every message, join, and leave event is persisted
- `/quit` — graceful disconnect, sets `left_at` timestamp in DB
- `/shutdown` — admin command, closes all connections and ends the server process

## Architecture

```
server.py      — TCP server, client handler threads, broadcast logic
client.py      — Tkinter GUI, login flow, receive thread
database.py    — pymysql CRUD wrapper (chats, users, messages)
database.sql   — schema with FK constraints and utf8mb4 encoding
```

## Setup

### 1. Database

```bash
mysql -u root -p < database.sql
```

### 2. Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```env
DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=pythonchat
```

Load the `.env` before starting the server (Linux/macOS):

```bash
export $(cat .env | xargs)
python server.py
```

On Windows (PowerShell):

```powershell
Get-Content .env | ForEach-Object { $k, $v = $_ -split '=', 2; [System.Environment]::SetEnvironmentVariable($k, $v) }
python server.py
```

### 3. Start

```bash
# Terminal 1 — Server
python server.py

# Terminal 2+ — Client (one per user)
python client.py
```

## Requirements

```
pymysql
```

```bash
pip install pymysql
```

Python 3.x, Tkinter (included in standard Python installation)

## Author

Djoxer — built during Python fundamentals training
