"""
UTP Server Implementation
File: utp_server.py
Date: 2026-08-25

UDP-based server implementation with UTP protocol support for multi-client
chatroom communication with RSA encryption.
"""

import socket
import threading
import time
import rsa
from typing import Dict, Optional, Tuple
from utp_protocol import UTPFrame
from utp_connection import UTPConnection, UTPState
from constants import MessageType, Flags, Timeouts


class UTPServer:
    """
    UTP Protocol server for handling multiple UDP-based connections.
    
    Manages connection state machines, message routing, retransmission,
    and graceful shutdown.
    """
    
    def __init__(self, host: str, port: int):
        """
        Initialize UTP server.
        
        Args:
            host: Server IP address to bind to
            port: Server port to bind to
        """
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        
        # Connection management
        self.connections: Dict[Tuple[str, int], UTPConnection] = {}
        self.client_names: Dict[Tuple[str, int], str] = {}
        self.public_keys: Dict[Tuple[str, int], bytes] = {}
        
        # Server encryption keys
        self.server_public_key, self.server_private_key = rsa.newkeys(1024)
        
        # Lock for thread-safe access to shared state
        self.lock = threading.Lock()
    
    def start(self) -> None:
        """Start the UTP server and receive loop."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.host, self.port))
        self.running = True
        
        print(f"UTP Server started on {self.host}:{self.port}")
        
        # Start receive loop in main thread
        try:
            self.receive_loop()
        except KeyboardInterrupt:
            self.shutdown()
    
    def receive_loop(self) -> None:
        """
        Main receive loop - continuously receives frames from all clients.
        
        Non-blocking processing of incoming datagrams.
        """
        # Set socket timeout for periodic cleanup
        self.socket.settimeout(1.0)
        
        while self.running:
            try:
                data, addr = self.socket.recvfrom(65536)
                
                # Parse UTP frame
                frame = UTPFrame.deserialize(data)
                if frame is None:
                    # Malformed frame - silently drop
                    continue
                
                # Route to appropriate handler
                self._handle_frame(frame, addr)
                
            except socket.timeout:
                # Periodic cleanup of idle/dead connections
                self._cleanup_connections()
                continue
            except Exception as e:
                print(f"Error in receive loop: {e}")
                continue
    
    def _handle_frame(self, frame: UTPFrame, addr: Tuple[str, int]) -> None:
        """
        Route frame to appropriate handler based on message type.
        
        Args:
            frame: Received UTP frame
            addr: Sender address (host, port)
        """
        with self.lock:
            if frame.message_type == MessageType.HANDSHAKE_INIT:
                self._handle_handshake_init(frame, addr)
            elif frame.message_type == MessageType.HANDSHAKE_RESP:
                self._handle_handshake_resp(frame, addr)
            elif frame.message_type == MessageType.DATA:
                self._handle_data(frame, addr)
            elif frame.message_type == MessageType.ACK:
                self._handle_ack(frame, addr)
            elif frame.message_type == MessageType.CLOSE:
                self._handle_close(frame, addr)
    
    def _handle_handshake_init(self, frame: UTPFrame, addr: Tuple[str, int]) -> None:
        """
        Handle HANDSHAKE_INIT from client.
        
        Args:
            frame: Handshake init frame
            addr: Client address
        """
        # Create new connection for this client
        if addr not in self.connections:
            conn = UTPConnection(addr, is_server=True)
            conn.initiate_handshake()  # Server-side: move to handshaking
            self.connections[addr] = conn
        
        conn = self.connections[addr]
        
        # Send HANDSHAKE_RESP with server's public key
        response = UTPFrame(
            message_type=MessageType.HANDSHAKE_RESP,
            sequence=conn.increment_send_seq(),
            data=self.server_public_key.save_pkcs1("PEM")
        )
        response.set_flag(Flags.ACK_REQUIRED)
        
        self.socket.sendto(response.serialize(), addr)
        # Don't queue during handshake - just send
    
    def _handle_handshake_resp(self, frame: UTPFrame, addr: Tuple[str, int]) -> None:
        """
        Handle HANDSHAKE_RESP from client (contains client's public key).
        
        Args:
            frame: Handshake response frame with public key
            addr: Client address
        """
        if addr not in self.connections:
            # Unexpected response without init
            return
        
        conn = self.connections[addr]
        
        if conn.state == UTPState.HANDSHAKING:
            try:
                # Extract client's public key from frame data
                client_public_key = rsa.PublicKey.load_pkcs1(frame.data)
                self.public_keys[addr] = client_public_key
                
                # Transition connection to CONNECTED
                conn.accept_handshake()
                
                # Send ACK for handshake response
                ack = UTPFrame(
                    message_type=MessageType.ACK,
                    sequence=conn.increment_send_seq()
                )
                self.socket.sendto(ack.serialize(), addr)
                
                print(f"Client connected: {addr}")
            except Exception as e:
                print(f"Error processing handshake response from {addr}: {e}")
    
    def _handle_data(self, frame: UTPFrame, addr: Tuple[str, int]) -> None:
        """
        Handle DATA frame - decrypt and broadcast to all clients.
        
        Args:
            frame: Data frame
            addr: Sender address
        """
        if addr not in self.connections:
            # Unknown connection
            return
        
        conn = self.connections[addr]
        
        if conn.state != UTPState.CONNECTED:
            # Not ready for data
            return
        
        try:
            # Decrypt message using server's private key
            decrypted_data = rsa.decrypt(frame.data, self.server_private_key)
            message = decrypted_data.decode("utf-8")
            
            # Send ACK if required
            if frame.has_flag(Flags.ACK_REQUIRED):
                ack = UTPFrame(
                    message_type=MessageType.ACK,
                    sequence=frame.sequence
                )
                ack.set_flag(Flags.IS_ACK)
                self.socket.sendto(ack.serialize(), addr)
                conn.acknowledge(frame.sequence)
            
            # Broadcast to other clients
            self._broadcast(message.encode("utf-8"), addr)
            
            # Update activity
            conn.update_activity()
            
        except Exception as e:
            print(f"Error processing data from {addr}: {e}")
    
    def _handle_ack(self, frame: UTPFrame, addr: Tuple[str, int]) -> None:
        """
        Handle ACK frame - mark frame as acknowledged.
        
        Args:
            frame: ACK frame
            addr: Sender address
        """
        if addr not in self.connections:
            return
        
        conn = self.connections[addr]
        
        # Remove from pending if it was waiting for ACK
        if conn.acknowledge(frame.sequence):
            conn.update_activity()
    
    def _handle_close(self, frame: UTPFrame, addr: Tuple[str, int]) -> None:
        """
        Handle CLOSE frame - gracefully close connection.
        
        Args:
            frame: Close frame
            addr: Sender address
        """
        if addr not in self.connections:
            return
        
        conn = self.connections[addr]
        
        # Send CLOSE ACK
        close_ack = UTPFrame(
            message_type=MessageType.CLOSE,
            sequence=conn.increment_send_seq()
        )
        close_ack.set_flag(Flags.IS_ACK)
        self.socket.sendto(close_ack.serialize(), addr)
        
        # Mark connection as closed
        conn.mark_closed()
    
    def _broadcast(self, message: bytes, sender_addr: Tuple[str, int]) -> None:
        """
        Broadcast message to all connected clients except sender.
        
        Args:
            message: Message to broadcast
            sender_addr: Sender address (to exclude)
        """
        sender_name = self.client_names.get(sender_addr, "Unknown")
        
        for addr, conn in list(self.connections.items()):
            if addr == sender_addr or conn.state != UTPState.CONNECTED:
                continue
            
            if addr not in self.public_keys:
                continue
            
            try:
                # Encrypt message with client's public key
                encrypted_msg = rsa.encrypt(message, self.public_keys[addr])
                
                # Send DATA frame with encryption flag
                frame = UTPFrame(
                    message_type=MessageType.DATA,
                    sequence=conn.send_seq,
                    data=encrypted_msg
                )
                frame.set_flag(Flags.ACK_REQUIRED)
                
                self.socket.sendto(frame.serialize(), addr)
                conn.queue_frame(frame)
                
            except Exception as e:
                print(f"Error broadcasting to {addr}: {e}")
    
    def _cleanup_connections(self) -> None:
        """
        Clean up idle and dead connections.
        
        Removes connections that have exceeded idle timeout or max retries.
        """
        with self.lock:
            to_remove = []
            
            for addr, conn in list(self.connections.items()):
                # Check for idle timeout
                if conn.is_idle():
                    print(f"Closing idle connection: {addr}")
                    to_remove.append(addr)
                
                # Check for dead connection (max retries exceeded)
                elif conn.is_dead():
                    print(f"Closing dead connection (max retries): {addr}")
                    to_remove.append(addr)
                
                # Handle retransmissions
                else:
                    retransmits = conn.get_pending_retransmits()
                    for seq, frame, _ in retransmits:
                        if not conn.mark_retry(seq):
                            # Max retries exceeded
                            to_remove.append(addr)
                            break
                        else:
                            # Retransmit frame
                            try:
                                self.socket.sendto(frame.serialize(), addr)
                            except Exception as e:
                                print(f"Error retransmitting to {addr}: {e}")
            
            # Remove dead connections
            for addr in to_remove:
                if addr in self.connections:
                    del self.connections[addr]
                if addr in self.client_names:
                    del self.client_names[addr]
                if addr in self.public_keys:
                    del self.public_keys[addr]
    
    def shutdown(self) -> None:
        """Gracefully shutdown the server."""
        print("Shutting down UTP server...")
        self.running = False
        
        with self.lock:
            # Close all connections
            for addr in list(self.connections.keys()):
                try:
                    close_frame = UTPFrame(
                        message_type=MessageType.CLOSE,
                        sequence=0
                    )
                    self.socket.sendto(close_frame.serialize(), addr)
                except Exception as e:
                    print(f"Error closing connection {addr}: {e}")
        
        if self.socket:
            self.socket.close()
        
        print("UTP server shutdown complete")
    
    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"UTPServer(host={self.host}, port={self.port}, "
            f"connections={len(self.connections)})"
        )


def main():
    """Main entry point for UTP server."""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python utp_server.py <host> <port>")
        sys.exit(1)
    
    host = sys.argv[1]
    port = int(sys.argv[2])
    
    server = UTPServer(host, port)
    server.start()


if __name__ == "__main__":
    main()
