# [2026-08-25] Refactored async client with transport abstraction and protocol selection
# Supports TCP and UTP with automatic fallback and protocol indicator in GUI

import asyncio
import os
import sys
import tkinter as tk
import logging
import threading
import rsa
from typing import Optional
from protocol_factory import create_transport, get_primary_protocol, DualStackTransport

# Configure logging
logging.basicConfig(
    level=os.getenv("CHATROOM_LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CLIENT:
    """Async-aware Tkinter chatroom client with protocol selection.
    
    Features:
    - Protocol selection dropdown (TCP/UTP/Auto)
    - Automatic fallback on protocol failure
    - Protocol indicator in status bar
    - Same message encryption and broadcasting as original
    """
    
    def __init__(self):
        """Initialize the client GUI and state."""
        self.root = tk.Tk()
        self.root.geometry("700x550")
        self.root.title("Chatroom [Socketing Communication]")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Connection state
        self.connection = None
        self.transport = None
        self.notConnected = True
        self.event_loop: Optional[asyncio.AbstractEventLoop] = None
        self.async_thread: Optional[threading.Thread] = None
        
        # Crypto keys
        self.name = None
        self.public_key, self.private_key = rsa.newkeys(1024)
        self.public_key_other = None
        
        # Setup UI
        self.setup_boxes()
    
    def setup_boxes(self):
        """Setup all GUI elements including protocol selector."""
        # Name
        self.name_var = tk.StringVar()
        self.name_var.trace_add("write", self.enable_connect_button)
        
        self.nameLabel = tk.Label(self.root, text="Name:", font=("Arial", 10))
        self.nameLabel.grid(row=0, column=3, padx=5, pady=5)
        
        self.nameEntry = tk.Entry(self.root, textvariable=self.name_var, width=15)
        self.nameEntry.grid(row=0, column=4, padx=5, pady=5)
        
        # IP
        self.ip_var = tk.StringVar()
        self.ip_var.trace_add("write", self.enable_connect_button)
        
        self.ipLabel = tk.Label(self.root, text="IP:", font=("Arial", 10))
        self.ipLabel.grid(row=0, column=0, padx=5, pady=5)
        
        self.ipEntry = tk.Entry(self.root, textvariable=self.ip_var, width=15)
        self.ipEntry.grid(row=0, column=1, padx=5, pady=5)
        
        # Port
        self.port_var = tk.StringVar()
        self.port_var.trace_add("write", self.enable_connect_button)
        
        self.portLabel = tk.Label(self.root, text="Port:", font=("Arial", 10))
        self.portLabel.grid(row=1, column=0, padx=5, pady=5)
        
        self.portEntry = tk.Entry(self.root, textvariable=self.port_var, width=15)
        self.portEntry.grid(row=1, column=1, padx=5, pady=5)
        
        # Protocol selector (NEW)
        self.protocolLabel = tk.Label(self.root, text="Protocol:", font=("Arial", 10))
        self.protocolLabel.grid(row=1, column=3, padx=5, pady=5)
        
        self.protocol_var = tk.StringVar(value=get_primary_protocol().upper())
        self.protocolMenu = tk.OptionMenu(
            self.root,
            self.protocol_var,
            "TCP", "UTP", "AUTO"
        )
        self.protocolMenu.grid(row=1, column=4, padx=5, pady=5)
        
        # Connect button
        self.ConnectButton = tk.Button(
            self.root,
            text="Connect",
            command=self.connect_to_server,
            state=tk.DISABLED,
            font=("Arial", 10, "bold")
        )
        self.ConnectButton.grid(row=2, column=2)
        
        # Status indicator (NEW)
        self.statusLabel = tk.Label(
            self.root,
            text="⚫ Disconnected",
            font=("Arial", 9),
            fg="red"
        )
        self.statusLabel.grid(row=2, column=3, columnspan=2, padx=5, pady=5)
        
        # Message area
        self.text_area = tk.Text(self.root, font=("Courier", 9))
        self.text_area.grid(row=3, column=0, columnspan=9, padx=5, pady=5, sticky="nsew")
        
        # Message input
        self.msg_entry = tk.Entry(self.root, font=("Arial", 10))
        self.msg_entry.bind("<Return>", self.send_message)
        self.msg_entry.grid(row=4, column=0, columnspan=9, padx=5, pady=5, sticky="ew")
        
        # Configure grid weights for resizing
        self.root.grid_rowconfigure(3, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
    
    def enable_connect_button(self, *args):
        """Enable connect button when all fields are filled."""
        name = self.name_var.get()
        ip = self.ip_var.get()
        port = self.port_var.get()
        
        if name and ip and port and self.notConnected:
            self.ConnectButton.config(state=tk.NORMAL)
        else:
            self.ConnectButton.config(state=tk.DISABLED)
    
    def update_status(self, connected: bool, protocol: str = ""):
        """Update connection status indicator.
        
        Args:
            connected: True if connected, False otherwise
            protocol: Protocol name (tcp, utp, etc.)
        """
        if connected:
            status_text = f"🟢 Connected ({protocol.upper()})"
            color = "green"
        else:
            status_text = "⚫ Disconnected"
            color = "red"
        
        self.statusLabel.config(text=status_text, fg=color)
    
    def on_closing(self):
        """Handle window close event."""
        if self.connection is not None:
            try:
                # Schedule close in async loop
                if self.event_loop and self.event_loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.connection.close(), self.event_loop)
            except Exception:
                pass
        
        self.root.destroy()
        sys.exit()
    
    def run(self):
        """Start the client GUI and async event loop."""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.on_closing()
    
    def _start_async_loop(self):
        """Start asyncio event loop in separate thread."""
        self.event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.event_loop)
        
        try:
            self.event_loop.run_forever()
        finally:
            self.event_loop.close()
    
    def connect_to_server(self):
        """Connect to server using selected protocol with fallback."""
        self.name = self.name_var.get()
        self.ConnectButton.config(state=tk.DISABLED)
        self.update_status(False)
        
        # Start async loop if not running
        if self.event_loop is None or not self.event_loop.is_running():
            self.async_thread = threading.Thread(target=self._start_async_loop, daemon=True)
            self.async_thread.start()
        
        # Schedule connection in async loop
        protocol = self.protocol_var.get().lower()
        future = asyncio.run_coroutine_threadsafe(
            self._async_connect(protocol),
            self.event_loop
        )
    
    async def _async_connect(self, protocol: str) -> None:
        """Asynchronously connect to server with fallback.
        
        Args:
            protocol: Protocol to use ('tcp', 'utp', or 'auto')
        """
        try:
            host = self.ipEntry.get()
            port = int(self.portEntry.get())
            
            logger.info(f"Attempting connection to {host}:{port} with {protocol} protocol")
            
            # Create transport (supports fallback if auto)
            self.transport = DualStackTransport()
            
            # Establish connection with fallback
            try:
                self.connection = await asyncio.wait_for(
                    self.transport.connect(host, port),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                self.update_status(False)
                self.notConnected = True
                self.ConnectButton.config(state=tk.NORMAL)
                self.text_area.insert(tk.END, "❌ Connection timeout\n")
                logger.error("Connection timeout")
                return
            
            # Get actual protocol used
            actual_protocol = "tcp"  # Default
            
            # Protocol negotiation and key exchange
            try:
                # Receive server's public key
                key_data = await self.connection.recv(1024)
                if not key_data:
                    raise ConnectionError("Server closed connection")
                
                self.public_key_other = rsa.PublicKey.load_pkcs1(key_data)
                
                # Send our public key
                await self.connection.sendall(self.public_key.save_pkcs1("PEM"))
                
                # Send name (encrypted)
                await self.connection.sendall(
                    rsa.encrypt(self.name.encode(), self.public_key_other)
                )
                
                # Update UI
                self.notConnected = False
                self.update_status(True, actual_protocol)
                self.text_area.insert(tk.END, f"✓ Connected via {actual_protocol.upper()}\n")
                logger.info(f"Connected to server via {actual_protocol}")
                
                # Start receiving messages
                asyncio.create_task(self.receive_messages())
            
            except Exception as e:
                logger.error(f"Key exchange failed: {e}")
                self.text_area.insert(tk.END, f"❌ Key exchange failed: {e}\n")
                await self.connection.close()
                self.connection = None
                self.notConnected = True
                self.update_status(False)
                self.ConnectButton.config(state=tk.NORMAL)
        
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.text_area.insert(tk.END, f"❌ Server not found: {e}\n")
            self.notConnected = True
            self.update_status(False)
            self.ConnectButton.config(state=tk.NORMAL)
    
    async def receive_messages(self) -> None:
        """Receive and display messages from server."""
        try:
            while self.connection and not self.connection.closed:
                try:
                    data = await self.connection.recv(1024)
                    if not data:
                        break
                    
                    message = rsa.decrypt(data, self.private_key).decode("utf-8")
                    # Schedule UI update in main thread
                    self.root.after(0, lambda m=message: 
                        self.text_area.insert(tk.END, m + "\n"))
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Receive error: {e}")
                    break
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
        finally:
            self.notConnected = True
            self.update_status(False)
            self.ConnectButton.config(state=tk.NORMAL)
    
    def send_message(self, event):
        """Send message to server (called on Enter key).
        
        Args:
            event: Tkinter event object
        """
        message = f"{self.name}: {self.msg_entry.get()}"
        self.msg_entry.delete(0, tk.END)
        
        if self.connection and not self.connection.closed:
            try:
                # Send message in async loop
                future = asyncio.run_coroutine_threadsafe(
                    self.connection.sendall(
                        rsa.encrypt(message.encode(), self.public_key_other)
                    ),
                    self.event_loop
                )
                # Display locally
                self.text_area.insert(tk.END, message + "\n")
            except Exception as e:
                logger.error(f"Send error: {e}")
                self.text_area.insert(tk.END, f"❌ Send failed: {e}\n")


if __name__ == "__main__":
    client = CLIENT()
    client.run()
