# [2026-08-25] Async chat client with protocol selection and fallback support
# Supports TCP and UTP protocols with automatic fallback and metrics collection

import asyncio
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import rsa
import os
import sys
from typing import Optional
from transport_adapter import Connection
from protocol_factory import create_transport, get_primary_protocol
from metrics import get_metrics, setup_logging, logger


class AsyncClientThread(threading.Thread):
    """Separate thread for running the async event loop."""
    
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = None
    
    def run(self):
        """Run the async event loop."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
    
    def submit(self, coro):
        """Submit a coroutine to run in the event loop."""
        if self.loop:
            return asyncio.run_coroutine_threadsafe(coro, self.loop)
        return None


class CLIENT:
    """Async chat client with protocol selection."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.geometry("600x550")
        self.root.title("Chat Application - Protocol Agnostic")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Connection state
        self.server_connection: Optional[Connection] = None
        self.not_connected = True
        self.name: Optional[str] = None
        self.public_key, self.private_key = rsa.newkeys(1024)
        self.public_key_other: Optional[rsa.PublicKey] = None
        
        # Protocol and async support
        self.protocol: str = get_primary_protocol()
        self.async_thread = AsyncClientThread()
        self.async_thread.start()
        
        # Metrics
        self.metrics = get_metrics()
        self.conn_id = "client"
        
        # UI setup
        self.setup_boxes()
    
    def setup_boxes(self):
        """Set up GUI elements."""
        # Connection frame
        conn_frame = ttk.LabelFrame(self.root, text="Connection Settings", padding=10)
        conn_frame.grid(row=0, column=0, columnspan=9, sticky="ew", padx=5, pady=5)
        
        # Name
        ttk.Label(conn_frame, text="Name:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.name_var = tk.StringVar()
        self.nameEntry = ttk.Entry(conn_frame, textvariable=self.name_var, width=20)
        self.nameEntry.grid(row=0, column=1, padx=5, pady=5)
        self.name_var.trace_add("write", self.enable_connect_button)
        
        # IP
        ttk.Label(conn_frame, text="Server IP:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.ip_var = tk.StringVar()
        self.ipEntry = ttk.Entry(conn_frame, textvariable=self.ip_var, width=20)
        self.ipEntry.grid(row=0, column=3, padx=5, pady=5)
        self.ip_var.trace_add("write", self.enable_connect_button)
        
        # Port
        ttk.Label(conn_frame, text="Port:").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.port_var = tk.StringVar(value="5000")
        self.portEntry = ttk.Entry(conn_frame, textvariable=self.port_var, width=10)
        self.portEntry.grid(row=0, column=5, padx=5, pady=5)
        self.port_var.trace_add("write", self.enable_connect_button)
        
        # Protocol selection
        ttk.Label(conn_frame, text="Protocol:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.protocol_var = tk.StringVar(value=self.protocol)
        protocol_combo = ttk.Combobox(
            conn_frame, 
            textvariable=self.protocol_var, 
            values=["auto", "tcp", "utp"],
            state="readonly",
            width=10
        )
        protocol_combo.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        # Connect button
        self.ConnectButton = ttk.Button(
            conn_frame, text="Connect", command=self.on_connect_clicked, state=tk.DISABLED
        )
        self.ConnectButton.grid(row=1, column=2, padx=5, pady=5)
        
        # Status label
        self.status_var = tk.StringVar(value="Not connected")
        ttk.Label(conn_frame, textvariable=self.status_var, foreground="red").grid(
            row=1, column=3, columnspan=2, padx=5, pady=5, sticky="w"
        )
        
        # Disconnect button
        self.DisconnectButton = ttk.Button(
            conn_frame, text="Disconnect", command=self.on_disconnect_clicked, state=tk.DISABLED
        )
        self.DisconnectButton.grid(row=1, column=5, padx=5, pady=5)
        
        # Chat display
        self.text_area = tk.Text(self.root, height=20, width=70)
        self.text_area.grid(row=2, column=0, columnspan=9, padx=5, pady=5)
        self.text_area.config(state=tk.DISABLED)
        
        # Message input
        self.msg_entry = ttk.Entry(self.root, width=70)
        self.msg_entry.bind("<Return>", self.send_message)
        self.msg_entry.grid(row=3, column=0, columnspan=9, padx=5, pady=5)
        self.msg_entry.config(state=tk.DISABLED)
        
        # Send button
        self.SendButton = ttk.Button(
            self.root, text="Send", command=lambda: self.send_message(None), state=tk.DISABLED
        )
        self.SendButton.grid(row=4, column=0, columnspan=9, padx=5, pady=5)
    
    def enable_connect_button(self, *args):
        """Enable/disable connect button based on input fields."""
        name = self.name_var.get()
        ip = self.ip_var.get()
        port = self.port_var.get()
        if name and ip and port and self.not_connected:
            self.ConnectButton.config(state=tk.NORMAL)
        else:
            self.ConnectButton.config(state=tk.DISABLED)
    
    def log_message(self, message: str) -> None:
        """Add a message to the chat display."""
        self.text_area.config(state=tk.NORMAL)
        self.text_area.insert(tk.END, message + "\n")
        self.text_area.see(tk.END)
        self.text_area.config(state=tk.DISABLED)
    
    def on_closing(self):
        """Handle window close event."""
        if self.server_connection is not None:
            self.async_thread.submit(self._close_connection())
        self.root.destroy()
    
    async def _close_connection(self):
        """Async close connection."""
        if self.server_connection is not None:
            try:
                await self.server_connection.close()
            except Exception:
                pass
            self.server_connection = None
    
    def on_disconnect_clicked(self):
        """Handle disconnect button click."""
        self.async_thread.submit(self._close_connection())
        self.server_connection = None
        self.not_connected = True
        self.status_var.set("Disconnected")
        self.status_var.config(foreground="red")
        self.ConnectButton.config(state=tk.NORMAL)
        self.DisconnectButton.config(state=tk.DISABLED)
        self.msg_entry.config(state=tk.DISABLED)
        self.SendButton.config(state=tk.DISABLED)
        self.log_message("--- Disconnected from server ---")
    
    def on_connect_clicked(self):
        """Handle connect button click."""
        self.name = self.name_var.get()
        self.protocol = self.protocol_var.get()
        self.ConnectButton.config(state=tk.DISABLED)
        
        # Submit async connection
        future = self.async_thread.submit(self.connect_to_server())
    
    async def connect_to_server(self):
        """Async connection to server."""
        try:
            ip = self.ip_var.get()
            port = int(self.port_var.get())
            
            self.log_message(f"Connecting via {self.protocol.upper()} to {ip}:{port}...")
            self.root.update()
            
            # Create transport with fallback
            transport = create_transport(
                protocol=self.protocol,
                config={"fallback_timeout": 5}
            )
            
            # Connect
            self.server_connection = await transport.connect(ip, port)
            self.metrics.register_connection(self.conn_id, self.protocol, f"{ip}:{port}")
            
            # Receive server public key
            key_data = await self.server_connection.recv(1024)
            self.public_key_other = rsa.PublicKey.load_pkcs1(key_data)
            self.metrics.record_receive(self.conn_id, len(key_data))
            
            # Send our public key
            await self.server_connection.sendall(self.public_key.save_pkcs1("PEM"))
            self.metrics.record_send(self.conn_id, len(self.public_key.save_pkcs1("PEM")))
            
            # Send encrypted name
            encrypted_name = rsa.encrypt(self.name.encode(), self.public_key_other)
            await self.server_connection.sendall(encrypted_name)
            self.metrics.record_send(self.conn_id, len(encrypted_name))
            self.metrics.record_message_sent(self.conn_id)
            
            self.not_connected = False
            self.log_message(f"Connected via {self.protocol.upper()}!")
            self.status_var.set(f"Connected via {self.protocol.upper()}")
            self.status_var.config(foreground="green")
            self.DisconnectButton.config(state=tk.NORMAL)
            self.msg_entry.config(state=tk.NORMAL)
            self.SendButton.config(state=tk.NORMAL)
            
            # Start receiving messages
            self.async_thread.submit(self.receive_messages())
        
        except asyncio.TimeoutError:
            self.log_message("Connection timeout! Could not connect to server.")
            self.status_var.set("Connection failed (timeout)")
            self.status_var.config(foreground="red")
            self.not_connected = True
            self.ConnectButton.config(state=tk.NORMAL)
            self.metrics.record_error(self.conn_id)
        
        except Exception as e:
            self.log_message(f"Failed to connect: {e}")
            self.status_var.set(f"Connection failed: {type(e).__name__}")
            self.status_var.config(foreground="red")
            self.not_connected = True
            self.ConnectButton.config(state=tk.NORMAL)
            self.metrics.record_error(self.conn_id)
            logger.error(f"Connection failed: {e}")
    
    async def receive_messages(self):
        """Async receive messages from server."""
        try:
            while self.server_connection is not None and not self.server_connection.closed:
                try:
                    data = await asyncio.wait_for(
                        self.server_connection.recv(1024),
                        timeout=30.0
                    )
                    
                    if not data:
                        logger.info("Server closed connection")
                        break
                    
                    self.metrics.record_receive(self.conn_id, len(data))
                    self.metrics.record_message_received(self.conn_id)
                    
                    # Decrypt and display message
                    message = rsa.decrypt(data, self.private_key).decode("utf-8")
                    self.log_message(message)
                
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    self.metrics.record_error(self.conn_id)
                    break
        finally:
            self.not_connected = True
            if self.server_connection:
                try:
                    await self.server_connection.close()
                except Exception:
                    pass
            self.server_connection = None
    
    def send_message(self, event):
        """Send a message to the server."""
        message_text = self.msg_entry.get()
        if not message_text:
            return
        
        self.msg_entry.delete(0, tk.END)
        
        if self.server_connection is None:
            self.log_message("Not connected to server!")
            return
        
        try:
            # Format and encrypt message
            message = f"{self.name}: {message_text}"
            encrypted_msg = rsa.encrypt(message.encode(), self.public_key_other)
            
            # Send in async context
            self.async_thread.submit(self._send_message_async(encrypted_msg, message))
        
        except Exception as e:
            self.log_message(f"Error preparing message: {e}")
            logger.error(f"Error sending message: {e}")
    
    async def _send_message_async(self, encrypted_msg: bytes, message: str):
        """Async send message."""
        try:
            if self.server_connection is not None:
                await self.server_connection.sendall(encrypted_msg)
                self.metrics.record_send(self.conn_id, len(encrypted_msg))
                self.metrics.record_message_sent(self.conn_id)
                self.log_message(message)
        except Exception as e:
            self.log_message(f"Failed to send message: {e}")
            self.metrics.record_error(self.conn_id)
            logger.error(f"Send failed: {e}")
    
    def run(self):
        """Run the GUI."""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.on_closing()


def main():
    """Main entry point."""
    setup_logging("INFO")
    logger.info("Chat Client starting...")
    client = CLIENT()
    client.run()


if __name__ == "__main__":
    main()
