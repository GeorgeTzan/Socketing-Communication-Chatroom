# [2026-08-25] Transport abstraction layer defining protocol-agnostic interfaces
# This module provides abstract base classes for transport protocols (TCP, UTP, etc.)
# allowing the server and client to work with any protocol interchangeably.

from abc import ABC, abstractmethod
from typing import Tuple


class Connection(ABC):
    """Abstract base class for connection objects.
    
    Represents a connection-oriented communication channel between client and server.
    Implementations must provide send/recv operations and cleanup.
    """
    
    @abstractmethod
    async def send(self, data: bytes) -> int:
        """Send data over the connection.
        
        Args:
            data: Bytes to send
            
        Returns:
            Number of bytes sent
            
        Raises:
            ConnectionError: If connection is closed or send fails
        """
        pass
    
    @abstractmethod
    async def recv(self, bufsize: int) -> bytes:
        """Receive data from the connection.
        
        Args:
            bufsize: Maximum bytes to receive
            
        Returns:
            Received data (empty bytes if connection closed)
            
        Raises:
            ConnectionError: If connection is closed or recv fails
        """
        pass
    
    @abstractmethod
    async def sendall(self, data: bytes) -> None:
        """Send all data over the connection.
        
        Ensures all data is sent even if multiple sends are required.
        
        Args:
            data: Bytes to send
            
        Raises:
            ConnectionError: If connection is closed or send fails
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the connection gracefully.
        
        Raises:
            ConnectionError: If close fails
        """
        pass
    
    @property
    @abstractmethod
    def closed(self) -> bool:
        """Check if connection is closed."""
        pass


class TransportProtocol(ABC):
    """Abstract base class for transport protocol implementations.
    
    Defines the interface for connection-oriented transport protocols
    like TCP and UTP. Each implementation handles protocol-specific
    socket management, connection negotiation, and data transfer.
    """
    
    @abstractmethod
    async def listen(self, host: str, port: int) -> None:
        """Start listening for incoming connections.
        
        Binds to the specified host and port and prepares to accept connections.
        This is typically called on the server side.
        
        Args:
            host: Address to bind to (e.g., "0.0.0.0")
            port: Port number to listen on
            
        Raises:
            OSError: If binding or listen setup fails
        """
        pass
    
    @abstractmethod
    async def accept(self) -> Tuple[Connection, Tuple[str, int]]:
        """Accept an incoming connection.
        
        Blocks until a client connects. This is called after listen().
        
        Returns:
            Tuple of (Connection object, (remote_host, remote_port))
            
        Raises:
            OSError: If accept fails
            ConnectionError: If listener is not active
        """
        pass
    
    @abstractmethod
    async def connect(self, host: str, port: int) -> Connection:
        """Establish an outgoing connection to a remote host.
        
        This is typically called on the client side.
        
        Args:
            host: Remote host address
            port: Remote port number
            
        Returns:
            Connection object for communication
            
        Raises:
            ConnectionError: If connection fails
            OSError: If socket operation fails
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the transport and clean up resources.
        
        Closes listening sockets or active connections.
        
        Raises:
            OSError: If close fails
        """
        pass
    
    @property
    @abstractmethod
    def protocol_name(self) -> str:
        """Return the name of this protocol (e.g., 'tcp', 'utp')."""
        pass
