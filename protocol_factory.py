# [2026-08-25] Protocol factory for creating and managing transport protocols
# Handles protocol selection, configuration, and fallback logic

import asyncio
import os
from typing import Optional, List, Type
from transport_adapter import TransportProtocol
from tcp_handler import TCPTransport
from utp_handler import UTPTransport


def get_primary_protocol() -> str:
    """Get primary protocol from environment or default.
    
    Returns:
        Protocol name: 'tcp', 'utp', or 'auto'
    """
    protocol = os.getenv("CHATROOM_PRIMARY_PROTOCOL", "tcp").lower()
    if protocol not in ("tcp", "utp", "auto"):
        protocol = "tcp"
    return protocol


def get_fallback_timeout() -> float:
    """Get fallback timeout from environment or default.
    
    Returns:
        Timeout in seconds
    """
    try:
        return float(os.getenv("CHATROOM_FALLBACK_TIMEOUT", "5"))
    except ValueError:
        return 5.0


def is_utp_enabled() -> bool:
    """Check if UTP is explicitly enabled.
    
    Returns:
        True if UTP is enabled
    """
    return os.getenv("CHATROOM_ENABLE_UTP", "true").lower() in ("true", "1", "yes")


def is_tcp_enabled() -> bool:
    """Check if TCP is explicitly enabled.
    
    Returns:
        True if TCP is enabled (defaults to true)
    """
    return os.getenv("CHATROOM_ENABLE_TCP", "true").lower() in ("true", "1", "yes")


def create_transport(
    protocol: str = "auto",
    host: str = "0.0.0.0",
    port: int = 5000,
    config: Optional[dict] = None
) -> TransportProtocol:
    """Factory function to create transport protocol instances.
    
    Args:
        protocol: Protocol name ('tcp', 'utp', 'auto')
        host: Bind address for server-side
        port: Bind port for server-side
        config: Optional configuration dictionary
        
    Returns:
        TransportProtocol instance
        
    Raises:
        ValueError: If protocol is invalid or no suitable protocol available
    """
    config = config or {}
    
    # Handle explicit protocol selection
    if protocol == "tcp":
        if not is_tcp_enabled():
            raise ValueError("TCP is disabled")
        return TCPTransport(host, port)
    
    elif protocol == "utp":
        if not is_utp_enabled():
            raise ValueError("UTP is disabled")
        return UTPTransport(host, port)
    
    elif protocol == "auto":
        # Auto mode: prefer primary, fall back as needed
        primary = get_primary_protocol()
        
        if primary == "utp" and is_utp_enabled():
            return UTPTransport(host, port)
        elif primary == "tcp" and is_tcp_enabled():
            return TCPTransport(host, port)
        else:
            # Default fallback chain: try each in order
            if is_tcp_enabled():
                return TCPTransport(host, port)
            elif is_utp_enabled():
                return UTPTransport(host, port)
            else:
                raise ValueError("No protocols enabled")
    
    else:
        raise ValueError(f"Unknown protocol: {protocol}")


class DualStackTransport(TransportProtocol):
    """Dual-stack transport supporting both TCP and UTP simultaneously.
    
    Allows accepting connections from both TCP and UTP clients on the same port
    (or port+1 for UDP if necessary). Routes incoming connections appropriately.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 5000):
        """Initialize dual-stack transport.
        
        Args:
            host: Bind address
            port: Base port (TCP uses this, UTP uses port+1)
        """
        self.host = host
        self.port = port
        self.tcp_transport: Optional[TCPTransport] = None
        self.utp_transport: Optional[UTPTransport] = None
        self.active_transports: List[TransportProtocol] = []
    
    async def listen(self, host: str, port: int) -> None:
        """Start listening for both TCP and UTP connections.
        
        Args:
            host: Address to bind to
            port: Base port number
            
        Raises:
            OSError: If both protocols fail to listen
        """
        errors = []
        
        # Try TCP
        if is_tcp_enabled():
            try:
                self.tcp_transport = TCPTransport(host, port)
                await self.tcp_transport.listen(host, port)
                self.active_transports.append(self.tcp_transport)
                print(f"[DualStack] TCP listener started")
            except OSError as e:
                errors.append(f"TCP: {e}")
                self.tcp_transport = None
        
        # Try UTP on port+1 (to avoid address already in use)
        if is_utp_enabled():
            try:
                utp_port = port + 1
                self.utp_transport = UTPTransport(host, utp_port)
                await self.utp_transport.listen(host, utp_port)
                self.active_transports.append(self.utp_transport)
                print(f"[DualStack] UTP listener started on port {utp_port}")
            except OSError as e:
                errors.append(f"UTP: {e}")
                self.utp_transport = None
        
        # Require at least one protocol to succeed
        if not self.active_transports:
            raise OSError(f"Failed to start any transport: {'; '.join(errors)}")
    
    async def accept(self):
        """Accept connections from any active transport.
        
        Uses asyncio.wait to accept from whichever transport has a connection ready.
        
        Returns:
            Tuple of (Connection, (remote_host, remote_port))
            
        Raises:
            ConnectionError: If no transports are active
        """
        if not self.active_transports:
            raise ConnectionError("No active transports")
        
        # Create accept tasks for all active transports
        accept_tasks = []
        for transport in self.active_transports:
            task = asyncio.create_task(transport.accept())
            accept_tasks.append(task)
        
        try:
            # Wait for the first transport to accept a connection
            wait_fn = asyncio.wait
            first_completed = asyncio.FIRST_COMPLETED
            done, pending = await wait_fn(accept_tasks, return_when=first_completed)
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
            
            # Return result from completed task
            result = done.pop().result()
            return result
        except Exception as e:
            raise ConnectionError(f"Dual-stack accept failed: {e}")
    
    async def connect(self, host: str, port: int):
        """Establish connection using available protocols.
        
        Tries protocols in priority order with fallback.
        
        Args:
            host: Remote host
            port: Remote port
            
        Returns:
            Connection object
            
        Raises:
            ConnectionError: If all protocols fail
        """
        primary = get_primary_protocol()
        fallback_timeout = get_fallback_timeout()
        
        # Build protocol list in priority order
        protocols: List[TransportProtocol] = []
        if primary == "utp" and is_utp_enabled():
            protocols.append(UTPTransport())
            if is_tcp_enabled():
                protocols.append(TCPTransport())
        else:
            if is_tcp_enabled():
                protocols.append(TCPTransport())
            if is_utp_enabled():
                protocols.append(UTPTransport())
        
        if not protocols:
            raise ConnectionError("No protocols enabled")
        
        last_error = None
        for i, transport in enumerate(protocols):
            try:
                print(f"[DualStack] Attempting {transport.protocol_name} connection to {host}:{port}")
                
                # Use timeout for non-primary protocols
                timeout = fallback_timeout if i > 0 else 10
                conn = await asyncio.wait_for(
                    transport.connect(host, port),
                    timeout=timeout
                )
                print(f"[DualStack] Connected via {transport.protocol_name}")
                return conn
            except asyncio.TimeoutError as e:
                last_error = f"{transport.protocol_name} timeout"
                print(f"[DualStack] {transport.protocol_name} timeout, trying fallback...")
            except Exception as e:
                last_error = f"{transport.protocol_name}: {e}"
                print(f"[DualStack] {transport.protocol_name} failed: {e}")
        
        raise ConnectionError(f"All protocols failed. Last error: {last_error}")
    
    async def close(self) -> None:
        """Close all active transports."""
        for transport in self.active_transports:
            try:
                await transport.close()
            except Exception:
                pass
        self.active_transports.clear()
    
    @property
    def protocol_name(self) -> str:
        """Return protocol name."""
        return "dual-stack"
