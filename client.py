import socket
import sys
import tkinter as tk
import threading


class CLIENT:
    def __init__(self):
        self.root = tk.Tk()
        self.root.geometry("600x500")
        self.root.title("Communication app title [Placeholder]")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.server_socket = None
        self.notConnected = True
        self.setup_boxes()
        self.name = None

    def setup_boxes(self):
        self.name_var = tk.StringVar()
        self.ip_var = tk.StringVar()
        self.port_var = tk.StringVar()

        self.name_var.trace_add("write", self.enable_connect_button)
        self.ip_var.trace_add("write", self.enable_connect_button)
        self.port_var.trace_add("write", self.enable_connect_button)

        self.nameLabel = tk.Label(self.root, text="Name:")
        self.nameLabel.grid(row=0, column=3, padx=5, pady=5)

        self.nameEntry = tk.Entry(self.root, textvariable=self.name_var)
        self.nameEntry.grid(row=0, column=4, padx=5, pady=5)

        self.text_area = tk.Text(self.root)
        self.text_area.grid(row=3, column=0, columnspan=9)

        self.msg_entry = tk.Entry(self.root)
        self.msg_entry.bind("<Return>", self.send_message)
        self.msg_entry.grid(row=4, column=0, columnspan=9)

        self.ipLabel = tk.Label(self.root, text="IP:")
        self.ipLabel.grid(row=0, column=0, padx=5, pady=5)

        self.ipEntry = tk.Entry(self.root, textvariable=self.ip_var)
        self.ipEntry.grid(row=0, column=1, padx=5, pady=5)

        self.portLabel = tk.Label(self.root, text="Port:")
        self.portLabel.grid(row=1, column=0, padx=5, pady=5)

        self.portEntry = tk.Entry(self.root, textvariable=self.port_var)
        self.portEntry.grid(row=1, column=1, padx=5, pady=5)

        self.ConnectButton = tk.Button(
            self.root, text="Connect", command=self.connect_to_server, state=tk.DISABLED
        )
        self.ConnectButton.grid(row=2, column=2)

    def enable_connect_button(self, *args):
        name = self.name_var.get()
        ip = self.ip_var.get()
        port = self.port_var.get()
        # print(name, ip, port)
        if name and ip and port and self.notConnected:
            self.ConnectButton.config(state=tk.NORMAL)
        else:
            self.ConnectButton.config(state=tk.DISABLED)

    def on_closing(self):
        if self.server_socket is not None:
            self.server_socket.close()
            print("Socket connection closed.")

        self.root.destroy()
        sys.exit()

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.on_closing()

    def connect_to_server(self):
        self.notConnected = False
        self.name = self.name_var.get()
        self.ConnectButton.config(state=tk.DISABLED)
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.connect((self.ipEntry.get(), int(self.portEntry.get())))
            self.server_socket.sendall(self.name.encode())  # Send the client's name
            threading.Thread(target=self.receive_messages).start()
        except Exception:
            print("Server not Found!")

    def receive_messages(self):
        while True:
            try:
                data = self.server_socket.recv(1024)
                self.text_area.insert(tk.END, data.decode("utf-8") + "\n")
            except Exception:
                pass

    def send_message(self, event):
        message = f"{self.name}: {self.msg_entry.get()}"
        self.msg_entry.delete(0, tk.END)
        if self.server_socket is not None:
            try:
                self.server_socket.sendall(str.encode(message))
                self.text_area.insert(tk.END, message + "\n")
            except Exception:
                pass


client = CLIENT()
client.run()
