import socket
import threading
from typing import Optional

HOST = "0.0.0.0"
PORT = 5058

clients = {}
clients_lock = threading.Lock()


def register_client(conn: socket.socket, role: str) -> None:
    role_name = (role or "").strip().lower()
    if not role_name:
        return
    with clients_lock:
        clients[conn] = role_name


def unregister_client(conn: socket.socket) -> None:
    with clients_lock:
        clients.pop(conn, None)


def snapshot_clients():
    with clients_lock:
        return list(clients.items())


def broadcast_line(line: str, target_role: Optional[str] = "android") -> None:
    encoded = f"{line}\n".encode("utf-8")
    dead = []
    for conn, role in snapshot_clients():
        if target_role is not None and role != target_role:
            continue
        try:
            conn.sendall(encoded)
        except OSError:
            dead.append(conn)
    for conn in dead:
        unregister_client(conn)


def console_input_loop() -> None:
    while True:
        try:
            text = input("Text for Buddy> ").strip()
        except EOFError:
            break
        if not text:
            continue
        message = f"SAY:{text}"
        print(f"[>] Broadcasting {message}")
        broadcast_line(message, target_role="android")


def handle_client(conn: socket.socket, addr):
    print(f"[+] Connected: {addr}")
    role: Optional[str] = None
    buffer = ""
    try:
        with conn:
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    msg = line.strip()
                    if not msg:
                        continue
                    if msg.startswith("ROLE:"):
                        role = msg.split(":", 1)[1].strip().lower() or None
                        if role:
                            register_client(conn, role)
                            print(f"[*] {addr} identified as {role}")
                        continue
                    if role is None:
                        role = "android"
                        register_client(conn, role)
                    print(f"[>] from {addr} ({role}): {msg}")
                    if role == "app":
                        broadcast_line(msg, target_role="android")
                    elif role == "android":
                        broadcast_line(msg, target_role="app")
                    else:
                        broadcast_line(msg)
            tail = buffer.strip()
            if tail:
                if tail.startswith("ROLE:"):
                    role = tail.split(":", 1)[1].strip().lower() or role
                    if role:
                        register_client(conn, role)
                        print(f"[*] {addr} identified as {role}")
                else:
                    if role is None:
                        role = "android"
                        register_client(conn, role)
                    print(f"[>] from {addr} ({role}): {tail}")
                    if role == "app":
                        broadcast_line(tail, target_role="android")
                    elif role == "android":
                        broadcast_line(tail, target_role="app")
                    else:
                        broadcast_line(tail)
    finally:
        unregister_client(conn)
        print(f"[-] Disconnected: {addr}")


def main():
    threading.Thread(target=console_input_loop, daemon=True).start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, PORT))
        sock.listen()
        print(f"Server listening on {HOST}:{PORT}")
        while True:
            conn, addr = sock.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
