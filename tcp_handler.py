# [2026-08-25] TCP transport handler implementation
# Wraps socket.socket to provide the TransportProtocol interface
# Maintains full backwards compatibility with existing TCP functionality

import socket
import asyncio
from typing import Tuple, Optional
from transport_adapter import Connection, TransportProtocol


class TCPConnection(Connection):
    """TCP connection wrapper implementing the Connection interface."""
    
    def __init__(self, sock: socket.socket):
        """Initialize TCP connection with a socket.
        
        Args:
            sock: An active socket.socket object
        """
        self.sock = sock
        self._closed = False
    
    async def send(self, data: bytes) -> int:
        """Send data over TCP connection.
        
        Args:
            data: Bytes to send
            
        Returns:
            Number of bytes sent
            
        Raises:
            ConnectionError: If send fails
        """
        if self._closed:
            raise ConnectionError("Connection is closed")
        
        try:
            # Use asyncio to avoid blocking
            loop = asyncio.get_event_loop()
            sent = await loop.sock_sendall(self.sock, data)
            return len(data)
        except Exception as e:
            self._closed = True
            raise ConnectionError(f"TCP send failed: {e}")
    
    async def recv(self, bufsize: int) -> bytes:
        """Receive data from TCP connection.
        
        Args:
            bufsize: Maximum bytes to receive
            
        Returns:
            Received data (empty bytes if connection closed by peer)
            
        Raises:
            ConnectionError: If recv fails
        """
        if self._closed:
            raise ConnectionError("Connection is closed")
        
        try:
            loop = asyncio.get_event_loop()
            data = await loop.sock_recv(self.sock, bufsize)
            if not data:
                self._closed = True
            return data
        except Exception as e:
            self._closed = True
            raise ConnectionError(f"TCP recv failed: {e}")
    
    async def sendall(self, data: bytes) -> None:
        """Send all data over TCP connection.
        
        Args:
            data: Bytes to send
            
        Raises:
            ConnectionError: If send fails
        """
        if self._closed:
            raise ConnectionError("Connection is closed")
        
        try:
            loop = asyncio.get_event_loop()
            await loop.sock_sendall(self.sock, data)
        except Exception as e:
            self._closed = True
            raise ConnectionError(f"TCP sendall failed: {e}")
    
    async def close(self) -> None:
        """Close the TCP connection."""
        if not self._closed:
            try:
                self.sock.close()
            except Exception:
                pass
            finally:
                self._closed = True
    
    @property
    def closed(self) -> bool:
        """Check if connection is closed."""
        return self._closed


class TCPTransport(TransportProtocol):
    """TCP transport protocol implementation.
    
    Provides TCP socket handling following the TransportProtocol interface.
    This is a wrapper around Python's socket module for TCP connections.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 5000):
        """Initialize TCP transport.
        
        Args:
            host: Bind address
            port: Bind port
        """
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
    
    async def listen(self, host: str, port: int) -> None:
        """Start listening for TCP connections.
        
        Args:
            host: Address to bind to
            port: Port to listen on
            
        Raises:
            OSError: If bind or listen fails
        """
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((host, port))
            self.server_socket.listen()
            self.server_socket.setblocking(False)
            print(f"[TCP] Listening on {host}:{port}")
        except OSError as e:
            raise OSError(f"TCP listen failed: {e}")
    
    async def accept(self) -> Tuple[Connection, Tuple[str, int]]:
        """Accept an incoming TCP connection.
        
        Returns:
            Tuple of (TCPConnection, (remote_host, remote_port))
            
        Raises:
            ConnectionError: If accept fails
        """
        if self.server_socket is None:
            raise ConnectionError("Transport not listening")
        
        try:
            loop = asyncio.get_event_loop()
            conn, addr = await loop.sock_accept(self.server_socket)
            return TCPConnection(conn), addr
        except Exception as e:
            raise ConnectionError(f"TCP accept failed: {e}")
    
    async def connect(self, host: str, port: int) -> Connection:
        """Establish an outgoing TCP connection.
        
        Args:
            host: Remote host
            port: Remote port
            
        Returns:
            TCPConnection object
            
        Raises:
            ConnectionError: If connection fails
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setblocking(False)
            loop = asyncio.get_event_loop()
            await loop.sock_connect(sock, (host, port))
            print(f"[TCP] Connected to {host}:{port}")
            return TCPConnection(sock)
        except Exception as e:
            raise ConnectionError(f"TCP connect failed: {e}")
    
    async def close(self) -> None:
        """Close the TCP transport."""
        if self.server_socket is not None:
            try:
                self.server_socket.close()
            except Exception:
                pass
            finally:
                self.server_socket = None
    
    @property
    def protocol_name(self) -> str:
        """Return protocol name."""
        return "tcp"
