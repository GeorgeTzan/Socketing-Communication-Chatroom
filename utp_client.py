"""
UTP Client Connection Manager
File: utp_client.py
Date: 2026-08-25

Client-side UTP protocol implementation with handshake, message sending/receiving,
and automatic retransmission.
"""

import socket
import threading
import time
import rsa
from typing import Optional, Callable, Tuple
from utp_protocol import UTPFrame
from utp_connection import UTPConnection, UTPState
from constants import MessageType, Flags, Timeouts


class UTPConnectionManager:
    """
    Manages UTP client connection with handshake, messaging, and retransmission.
    
    Provides a simple interface for connecting, sending messages, and receiving
    responses from a UTP server.
    """
    
    def __init__(
        self,
        server_host: str,
        server_port: int,
        client_name: str,
        callback_on_message: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize UTP connection manager.
        
        Args:
            server_host: Server IP address
            server_port: Server port
            client_name: Name to display for this client
            callback_on_message: Optional callback when message received
        """
        self.server_host = server_host
        self.server_port = server_port
        self.client_name = client_name
        self.callback_on_message = callback_on_message
        
        # Socket and connection
        self.socket: Optional[socket.socket] = None
        self.connection: Optional[UTPConnection] = None
        self.running = False
        
        # Encryption keys
        self.client_public_key: Optional[bytes] = None
        self.client_private_key: Optional[bytes] = None
        self.server_public_key: Optional[rsa.PublicKey] = None
        
        # Threads
        self.receive_thread: Optional[threading.Thread] = None
        self.retransmit_thread: Optional[threading.Thread] = None
    
    def connect(self) -> None:
        """
        Establish connection with handshake.
        
        Raises:
            RuntimeError: If connection fails or times out
        """
        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(2.0)
            
            # Initialize client connection state
            self.connection = UTPConnection(
                (self.server_host, self.server_port),
                is_server=False
            )
            self.connection.initiate_handshake()
            
            # Generate RSA key pair
            self.client_public_key, self.client_private_key = rsa.newkeys(1024)
            
            # Send HANDSHAKE_INIT
            init_frame = UTPFrame(
                message_type=MessageType.HANDSHAKE_INIT,
                sequence=self.connection.increment_send_seq()
            )
            self.socket.sendto(
                init_frame.serialize(),
                (self.server_host, self.server_port)
            )
            
            # Receive HANDSHAKE_RESP
            response_data, _ = self.socket.recvfrom(65536)
            response = UTPFrame.deserialize(response_data)
            
            if response is None or response.message_type != MessageType.HANDSHAKE_RESP:
                raise RuntimeError("Invalid handshake response")
            
            # Parse server's public key
            self.server_public_key = rsa.PublicKey.load_pkcs1(response.data)
            self.connection.accept_handshake()
            
            # Send DATA frame with client info (name + public key)
            client_info = (self.client_name.encode("utf-8") + b"|" +
                          self.client_public_key.save_pkcs1("PEM"))
            encrypted_info = rsa.encrypt(client_info, self.server_public_key)
            
            data_frame = UTPFrame(
                message_type=MessageType.DATA,
                sequence=self.connection.increment_send_seq(),
                data=encrypted_info
            )
            data_frame.set_flag(Flags.ACK_REQUIRED)
            
            self.socket.sendto(
                data_frame.serialize(),
                (self.server_host, self.server_port)
            )
            self.connection.queue_frame(data_frame)
            
            # Wait for ACK
            ack_received = False
            for _ in range(3):  # Wait up to 3 seconds
                try:
                    ack_data, _ = self.socket.recvfrom(65536)
                    ack_frame = UTPFrame.deserialize(ack_data)
                    
                    if (ack_frame is not None and
                        ack_frame.message_type == MessageType.ACK and
                        ack_frame.sequence == data_frame.sequence):
                        self.connection.acknowledge(data_frame.sequence)
                        ack_received = True
                        break
                except socket.timeout:
                    continue
            
            if not ack_received:
                raise RuntimeError("Handshake ACK timeout")
            
            # Connection established
            self.running = True
            
            # Start background threads
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            self.retransmit_thread = threading.Thread(target=self._retransmit_loop, daemon=True)
            self.retransmit_thread.start()
            
        except Exception as e:
            self.close()
            raise RuntimeError(f"Connection failed: {e}")
    
    def send_message(self, message: str) -> None:
        """
        Send a message to the server.
        
        Args:
            message: Message to send
            
        Raises:
            RuntimeError: If not connected
        """
        if not self.running or self.connection.state != UTPState.CONNECTED:
            raise RuntimeError("Not connected")
        
        try:
            # Format message
            formatted_msg = f"{self.client_name}: {message}".encode("utf-8")
            
            # Encrypt with server's public key
            encrypted_msg = rsa.encrypt(formatted_msg, self.server_public_key)
            
            # Create DATA frame
            frame = UTPFrame(
                message_type=MessageType.DATA,
                sequence=self.connection.increment_send_seq(),
                data=encrypted_msg
            )
            frame.set_flag(Flags.ACK_REQUIRED)
            
            # Send frame
            self.socket.sendto(frame.serialize(), (self.server_host, self.server_port))
            self.connection.queue_frame(frame)
            
        except Exception as e:
            print(f"Error sending message: {e}")
    
    def close(self) -> None:
        """Gracefully close connection."""
        self.running = False
        
        if self.connection and self.connection.state != UTPState.CLOSED:
            try:
                close_frame = UTPFrame(
                    message_type=MessageType.CLOSE,
                    sequence=self.connection.increment_send_seq()
                )
                self.socket.sendto(
                    close_frame.serialize(),
                    (self.server_host, self.server_port)
                )
                self.connection.mark_closed()
            except Exception as e:
                print(f"Error closing connection: {e}")
        
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
    
    def _receive_loop(self) -> None:
        """Background thread for receiving messages."""
        while self.running:
            try:
                if self.socket is None:
                    break
                
                data, _ = self.socket.recvfrom(65536)
                frame = UTPFrame.deserialize(data)
                
                if frame is None:
                    continue
                
                # Handle different frame types
                if frame.message_type == MessageType.DATA:
                    self._handle_data_frame(frame)
                elif frame.message_type == MessageType.ACK:
                    self.connection.acknowledge(frame.sequence)
                elif frame.message_type == MessageType.CLOSE:
                    self.connection.mark_closed()
                    self.running = False
                
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error in receive loop: {e}")
                break
    
    def _handle_data_frame(self, frame: UTPFrame) -> None:
        """
        Handle incoming DATA frame.
        
        Args:
            frame: Received data frame
        """
        try:
            # Decrypt message
            decrypted = rsa.decrypt(frame.data, self.client_private_key)
            message = decrypted.decode("utf-8")
            
            # Send ACK if required
            if frame.has_flag(Flags.ACK_REQUIRED):
                ack = UTPFrame(
                    message_type=MessageType.ACK,
                    sequence=frame.sequence
                )
                ack.set_flag(Flags.IS_ACK)
                self.socket.sendto(
                    ack.serialize(),
                    (self.server_host, self.server_port)
                )
            
            # Call callback if registered
            if self.callback_on_message:
                self.callback_on_message(message)
            
            self.connection.update_activity()
            
        except Exception as e:
            print(f"Error handling data frame: {e}")
    
    def _retransmit_loop(self) -> None:
        """Background thread for handling retransmissions."""
        while self.running:
            try:
                if self.connection is None:
                    break
                
                # Check for frames needing retransmission
                retransmits = self.connection.get_pending_retransmits()
                
                for seq, frame, _ in retransmits:
                    if not self.connection.mark_retry(seq):
                        # Max retries exceeded
                        self.running = False
                        break
                    
                    try:
                        self.socket.sendto(
                            frame.serialize(),
                            (self.server_host, self.server_port)
                        )
                    except Exception as e:
                        print(f"Error retransmitting: {e}")
                
                time.sleep(0.1)  # Check every 100ms
                
            except Exception as e:
                print(f"Error in retransmit loop: {e}")
                break
    
    def __repr__(self) -> str:
        """Return string representation."""
        state = self.connection.state.name if self.connection else "DISCONNECTED"
        return (
            f"UTPConnectionManager(host={self.server_host}, port={self.server_port}, "
            f"name={self.client_name}, state={state})"
        )


# Adapter for abstract connection interface
class TCPConnection:
    """Adapter for TCP connections to match UTPConnectionManager interface."""
    
    def __init__(self, host: str, port: int, name: str):
        """Initialize TCP connection."""
        self.host = host
        self.port = port
        self.name = name
        self.socket = None
    
    def connect(self) -> None:
        """Establish TCP connection."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
    
    def send(self, data: bytes) -> None:
        """Send data."""
        self.socket.sendall(data)
    
    def receive(self, buffer_size: int = 1024) -> bytes:
        """Receive data."""
        return self.socket.recv(buffer_size)
    
    def close(self) -> None:
        """Close connection."""
        if self.socket:
            self.socket.close()
