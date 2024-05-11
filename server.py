import socket
import threading
import rsa

HOST = None  # YOUR IP. Must be str
PORT = None  # YOUR PORT. Must be int

clients = []
client_names = {}
public_keys = {}

public_key, private_key = rsa.newkeys(1024)


def broadcast(message, sender_conn):
    for client in clients:
        if client != sender_conn:
            try:
                encrypted_message = rsa.encrypt(message, public_keys[client])
                client.sendall(encrypted_message)
            except ConnectionResetError:
                clients.remove(client)


def handle_client(conn, addr):
    global client_names
    print(f"Connected by {addr}")
    client_name = rsa.decrypt(conn.recv(1024), private_key).decode("utf-8")
    client_names[conn] = client_name
    while True:
        try:
            data = conn.recv(1024)
            if not data:
                break
            message = rsa.decrypt(data, private_key).decode("utf-8")
            broadcast(message.encode("utf-8"), conn)
        except ConnectionResetError:
            break
    conn.close()
    clients.remove(conn)
    del client_names[conn]
    del public_keys[conn]


with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen()
    try:
        while True:
            conn, addr = s.accept()
            conn.send(public_key.save_pkcs1("PEM"))
            public_keys[conn] = rsa.PublicKey.load_pkcs1(conn.recv(1024))
            clients.append(conn)
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.start()
    except KeyboardInterrupt:
        print("Shutting down the server...")
        for client in clients:
            client.close()
        s.close()
