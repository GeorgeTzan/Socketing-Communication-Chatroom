import socket
import threading

HOST = "127.0.0.1"
PORT = 65

clients = []
client_names = {}


def broadcast(message, sender_conn):
    for client in clients:
        if client != sender_conn:
            try:
                client.sendall(message)
            except ConnectionResetError:
                clients.remove(client)


def handle_client(conn, addr):
    global client_names
    print(f"Connected by {addr}")
    client_name = conn.recv(1024).decode("utf-8")  # Receive the client's name
    client_names[conn] = client_name
    while True:
        try:
            data = conn.recv(1024)
            if not data:
                break
            message = f"{data.decode('utf-8')}"
            broadcast(message.encode("utf-8"), conn)
        except ConnectionResetError:
            break
    conn.close()
    clients.remove(conn)
    del client_names[conn]


with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen()
    try:
        while True:
            conn, addr = s.accept()
            clients.append(conn)
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.start()
    except KeyboardInterrupt:
        print("Shutting down the server...")
        for client in clients:
            client.close()
        s.close()
