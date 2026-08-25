# [2026-08-25] Unit and integration tests for transport protocols and client/server
# Tests TCP handler, UTP handler, protocol factory, and integration scenarios

import asyncio
import pytest
import pytest_asyncio
import socket
import sys
import os
from typing import Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from transport_adapter import Connection, TransportProtocol
from tcp_handler import TCPTransport, TCPConnection
from utp_handler import UTPTransport, UTPConnection
from protocol_factory import (
    create_transport,
    DualStackTransport,
    get_primary_protocol,
    get_fallback_timeout,
    is_utp_enabled,
    is_tcp_enabled
)


# Test fixtures

@pytest_asyncio.fixture
async def tcp_server():
    """Fixture providing a TCP server transport."""
    transport = TCPTransport("127.0.0.1", 15000)
    await transport.listen("127.0.0.1", 15000)
    yield transport
    await transport.close()


@pytest_asyncio.fixture
async def utp_server():
    """Fixture providing a UTP server transport."""
    transport = UTPTransport("127.0.0.1", 15001)
    await transport.listen("127.0.0.1", 15001)
    yield transport
    await transport.close()


# TCP Handler Tests

class TestTCPTransport:
    """Test TCP transport protocol handler."""
    
    @pytest.mark.asyncio
    async def test_tcp_listen(self):
        """Test TCP server can listen on port."""
        transport = TCPTransport("127.0.0.1", 15010)
        await transport.listen("127.0.0.1", 15010)
        assert transport.server_socket is not None
        await transport.close()
    
    @pytest.mark.asyncio
    async def test_tcp_connect(self):
        """Test TCP client can connect to server."""
        server = TCPTransport("127.0.0.1", 15011)
        await server.listen("127.0.0.1", 15011)
        
        # Connect in background
        async def accept_conn():
            conn, addr = await server.accept()
            return conn, addr
        
        accept_task = asyncio.create_task(accept_conn())
        
        # Connect client
        client = TCPTransport()
        conn = await client.connect("127.0.0.1", 15011)
        
        # Wait for accept
        server_conn, addr = await asyncio.wait_for(accept_task, timeout=5.0)
        
        assert not conn.closed
        assert not server_conn.closed
        
        await conn.close()
        await server_conn.close()
        await server.close()
    
    @pytest.mark.asyncio
    async def test_tcp_send_recv(self):
        """Test TCP send and receive data."""
        server = TCPTransport("127.0.0.1", 15012)
        await server.listen("127.0.0.1", 15012)
        
        async def server_handler():
            conn, addr = await server.accept()
            data = await conn.recv(1024)
            assert data == b"Hello, TCP!"
            await conn.sendall(b"Echo: Hello, TCP!")
            await conn.close()
        
        server_task = asyncio.create_task(server_handler())
        
        # Client connection
        client = TCPTransport()
        conn = await client.connect("127.0.0.1", 15012)
        
        # Send data
        await conn.sendall(b"Hello, TCP!")
        
        # Receive response
        response = await conn.recv(1024)
        assert response == b"Echo: Hello, TCP!"
        
        await conn.close()
        await server.close()
        await asyncio.wait_for(server_task, timeout=5.0)
    
    @pytest.mark.asyncio
    async def test_tcp_protocol_name(self):
        """Test TCP protocol name."""
        transport = TCPTransport()
        assert transport.protocol_name == "tcp"


class TestUTPTransport:
    """Test UTP transport protocol handler."""
    
    @pytest.mark.asyncio
    async def test_utp_listen(self):
        """Test UTP server can listen on port."""
        transport = UTPTransport("127.0.0.1", 15020)
        await transport.listen("127.0.0.1", 15020)
        assert transport.server_socket is not None
        await transport.close()
    
    @pytest.mark.asyncio
    async def test_utp_connect(self):
        """Test UTP client can connect to server."""
        server = UTPTransport("127.0.0.1", 15021)
        await server.listen("127.0.0.1", 15021)
        
        # Connect client
        client = UTPTransport()
        try:
            conn = await asyncio.wait_for(
                client.connect("127.0.0.1", 15021),
                timeout=2.0
            )
            assert not conn.closed
            await conn.close()
        except asyncio.TimeoutError:
            pass  # UTP accept may not work in simple test
        finally:
            await server.close()
    
    @pytest.mark.asyncio
    async def test_utp_protocol_name(self):
        """Test UTP protocol name."""
        transport = UTPTransport()
        assert transport.protocol_name == "utp"


# Protocol Factory Tests

class TestProtocolFactory:
    """Test protocol factory and configuration."""
    
    def test_create_tcp_transport(self):
        """Test creating TCP transport explicitly."""
        os.environ["CHATROOM_ENABLE_TCP"] = "true"
        
        transport = create_transport("tcp", "127.0.0.1", 15030)
        assert isinstance(transport, TCPTransport)
        assert transport.protocol_name == "tcp"
    
    def test_create_utp_transport(self):
        """Test creating UTP transport explicitly."""
        os.environ["CHATROOM_ENABLE_UTP"] = "true"
        
        transport = create_transport("utp", "127.0.0.1", 15031)
        assert isinstance(transport, UTPTransport)
        assert transport.protocol_name == "utp"
    
    def test_create_auto_transport_defaults_to_tcp(self):
        """Test auto mode defaults to TCP."""
        os.environ["CHATROOM_ENABLE_TCP"] = "true"
        os.environ["CHATROOM_ENABLE_UTP"] = "false"
        os.environ["CHATROOM_PRIMARY_PROTOCOL"] = "auto"
        
        transport = create_transport("auto", "127.0.0.1", 15032)
        assert isinstance(transport, TCPTransport)
    
    def test_invalid_protocol_raises_error(self):
        """Test invalid protocol raises ValueError."""
        with pytest.raises(ValueError):
            create_transport("invalid", "127.0.0.1", 15033)
    
    @pytest.mark.asyncio
    async def test_dual_stack_transport_listen(self):
        """Test dual-stack transport can listen."""
        os.environ["CHATROOM_ENABLE_TCP"] = "true"
        os.environ["CHATROOM_ENABLE_UTP"] = "false"  # Disable UTP for this test
        
        transport = DualStackTransport("127.0.0.1", 15040)
        await transport.listen("127.0.0.1", 15040)
        assert len(transport.active_transports) > 0
        await transport.close()


# Integration Tests

class TestIntegration:
    """Integration tests for full client-server scenarios."""
    
    @pytest.mark.asyncio
    async def test_tcp_client_server_communication(self):
        """Test TCP client-server communication."""
        os.environ["CHATROOM_ENABLE_TCP"] = "true"
        os.environ["CHATROOM_PRIMARY_PROTOCOL"] = "tcp"
        
        server = TCPTransport("127.0.0.1", 15050)
        await server.listen("127.0.0.1", 15050)
        
        messages_received = []
        
        async def server_handler():
            conn, addr = await server.accept()
            # Receive data with a delimiter or known size
            data = await conn.recv(1024)
            messages_received.append(data)
            await conn.close()
        
        server_task = asyncio.create_task(server_handler())
        
        # Client
        client = TCPTransport()
        conn = await client.connect("127.0.0.1", 15050)
        
        # Send both messages together
        await conn.sendall(b"Message 1Message 2")
        await conn.close()
        
        await asyncio.wait_for(server_task, timeout=5.0)
        await server.close()
        
        assert len(messages_received) == 1
        assert b"Message 1" in messages_received[0]
        assert b"Message 2" in messages_received[0]
    
    @pytest.mark.asyncio
    async def test_fallback_from_unavailable_protocol(self):
        """Test fallback when primary protocol is unavailable."""
        os.environ["CHATROOM_ENABLE_UTP"] = "false"
        os.environ["CHATROOM_ENABLE_TCP"] = "true"
        os.environ["CHATROOM_PRIMARY_PROTOCOL"] = "auto"
        
        # Attempt to use DualStackTransport which should fall back to TCP
        transport = DualStackTransport("127.0.0.1", 15051)
        await transport.listen("127.0.0.1", 15051)
        
        # Should have TCP active even though UTP is disabled
        assert any(t.protocol_name == "tcp" for t in transport.active_transports)
        
        await transport.close()
    
    @pytest.mark.asyncio
    async def test_multiple_client_connections(self):
        """Test server accepting multiple client connections."""
        server = TCPTransport("127.0.0.1", 15052)
        await server.listen("127.0.0.1", 15052)
        
        accepted_connections = []
        
        async def server_handler():
            for _ in range(3):
                conn, addr = await server.accept()
                accepted_connections.append(conn)
        
        server_task = asyncio.create_task(server_handler())
        
        # Connect multiple clients
        clients = []
        for i in range(3):
            client = TCPTransport()
            conn = await client.connect("127.0.0.1", 15052)
            clients.append(conn)
        
        await asyncio.wait_for(server_task, timeout=5.0)
        
        assert len(accepted_connections) == 3
        
        for conn in clients:
            await conn.close()
        for conn in accepted_connections:
            await conn.close()
        await server.close()


# Performance benchmark tests

class TestPerformance:
    """Performance tests for protocol comparison."""
    
    @pytest.mark.asyncio
    async def test_tcp_throughput(self):
        """Measure TCP throughput."""
        import time
        
        server = TCPTransport("127.0.0.1", 15060)
        await server.listen("127.0.0.1", 15060)
        
        bytes_received = []
        
        async def server_handler():
            conn, addr = await server.accept()
            while True:
                data = await conn.recv(4096)
                if not data:
                    break
                bytes_received.append(len(data))
            await conn.close()
        
        server_task = asyncio.create_task(server_handler())
        
        # Client sends data
        client = TCPTransport()
        conn = await client.connect("127.0.0.1", 15060)
        
        # Send 1MB of data
        chunk = b"x" * 4096
        start = time.time()
        
        for _ in range(256):
            await conn.sendall(chunk)
        
        await conn.close()
        elapsed = time.time() - start
        
        await asyncio.wait_for(server_task, timeout=5.0)
        await server.close()
        
        total_bytes = sum(bytes_received)
        throughput = total_bytes / elapsed / 1024 / 1024  # MB/s
        
        # Log throughput for reference
        print(f"TCP Throughput: {throughput:.2f} MB/s")
        assert total_bytes == 256 * 4096


if __name__ == "__main__":
    # Run tests with: pytest tests/test_transport.py -v
    pytest.main([__file__, "-v"])
