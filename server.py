# [2026-08-25] Async chat server with transport abstraction layer
# Supports both TCP and UTP protocols with automatic fallback and metrics collection

import asyncio
import rsa
import os
import sys
import struct
from typing import Dict, Optional, Tuple
from transport_adapter import Connection, TransportProtocol
from protocol_factory import create_transport, get_primary_protocol, DualStackTransport
from metrics import get_metrics, setup_logging, logger

# Configuration
HOST = os.getenv("CHATROOM_HOST", "0.0.0.0")
PORT = int(os.getenv("CHATROOM_PORT", "5000"))
PROTOCOL = os.getenv("CHATROOM_PRIMARY_PROTOCOL", "auto")
DUAL_STACK = os.getenv("CHATROOM_DUAL_STACK", "true").lower() in ("true", "1", "yes")

# Server state
clients: Dict[str, Connection] = {}  # conn_id -> Connection
client_names: Dict[str, str] = {}  # conn_id -> client_name
public_keys: Dict[str, rsa.PublicKey] = {}  # conn_id -> PublicKey
transport: Optional[TransportProtocol] = None
metrics = get_metrics()

# Generate server RSA keys
public_key, private_key = rsa.newkeys(1024)
server_conn_id_counter = 0


def get_next_conn_id() -> str:
    """Get next unique connection ID."""
    global server_conn_id_counter
    server_conn_id_counter += 1
    return f"conn_{server_conn_id_counter}"


async def recv_exact(conn: Connection, nbytes: int) -> bytes:
    """Receive exactly nbytes from connection.
    
    Handles TCP stream framing by reading until we have enough bytes.
    
    Args:
        conn: Connection object
        nbytes: Exact number of bytes to receive
        
    Returns:
        Bytes data (exactly nbytes)
        
    Raises:
        ConnectionError: If connection closes before nbytes received
    """
    data = bytearray()
    while len(data) < nbytes:
        chunk = await conn.recv(nbytes - len(data))
        if not chunk:
            raise ConnectionError(f"Connection closed, got {len(data)}/{nbytes} bytes")
        data.extend(chunk)
    return bytes(data)


async def send_message(conn: Connection, data: bytes) -> None:
    """Send a message with length prefix.
    
    Prepends a 4-byte big-endian length prefix for framing.
    
    Args:
        conn: Connection object
        data: Message bytes to send
    """
    length_prefix = struct.pack("!I", len(data))
    await conn.sendall(length_prefix + data)


async def recv_message(conn: Connection, max_size: int = 65536) -> bytes:
    """Receive a message with length prefix.
    
    Reads 4-byte big-endian length prefix then reads exact message bytes.
    
    Args:
        conn: Connection object
        max_size: Maximum message size to prevent DoS
        
    Returns:
        Message bytes (without length prefix)
        
    Raises:
        ConnectionError: If length invalid or connection closes
    """
    length_data = await recv_exact(conn, 4)
    msg_len = struct.unpack("!I", length_data)[0]
    
    if msg_len > max_size:
        raise ConnectionError(f"Message too large: {msg_len} > {max_size}")
    
    if msg_len == 0:
        return b""
    
    return await recv_exact(conn, msg_len)


async def broadcast(message: bytes, sender_conn_id: str) -> None:
    """Broadcast message to all clients except sender.
    
    Args:
        message: Message bytes (already encrypted)
        sender_conn_id: Connection ID of sender (not included in broadcast)
    """
    disconnected = []
    for conn_id, client_conn in clients.items():
        if conn_id != sender_conn_id:
            try:
                # Message is already encrypted, just forward it
                await send_message(client_conn, message)
                metrics.record_send(conn_id, len(message))
            except Exception as e:
                logger.warning(f"Failed to send message to {conn_id}: {e}")
                metrics.record_error(conn_id)
                disconnected.append(conn_id)
    
    # Remove disconnected clients
    for conn_id in disconnected:
        await disconnect_client(conn_id)


async def disconnect_client(conn_id: str) -> None:
    """Disconnect and clean up a client.
    
    Args:
        conn_id: Connection ID to disconnect
    """
    if conn_id in clients:
        try:
            await clients[conn_id].close()
        except Exception:
            pass
        
        del clients[conn_id]
        
        if conn_id in client_names:
            client_name = client_names[conn_id]
            logger.info(f"Client disconnected: {client_name} ({conn_id})")
            del client_names[conn_id]
        
        if conn_id in public_keys:
            del public_keys[conn_id]
        
        metrics.unregister_connection(conn_id)


async def handle_client(conn: Connection, addr: Tuple[str, int], protocol: str) -> None:
    """Handle a client connection.
    
    Args:
        conn: Connection object
        addr: Remote address (host, port)
        protocol: Protocol name (tcp or utp)
    """
    conn_id = get_next_conn_id()
    
    try:
        metrics.register_connection(conn_id, protocol, f"{addr[0]}:{addr[1]}")
        logger.info(f"Client connected via {protocol.upper()}: {addr} ({conn_id})")
        
        # Send server public key
        await send_message(conn, public_key.save_pkcs1("PEM"))
        
        # Receive client public key
        key_data = await recv_message(conn, max_size=8192)
        if not key_data:
            logger.warning(f"Client {conn_id} disconnected without sending public key")
            return
        
        public_keys[conn_id] = rsa.PublicKey.load_pkcs1(key_data)
        metrics.record_receive(conn_id, len(key_data))
        
        # Receive encrypted client name
        name_data = await recv_message(conn, max_size=8192)
        if not name_data:
            logger.warning(f"Client {conn_id} disconnected without sending name")
            return
        
        client_name = rsa.decrypt(name_data, private_key).decode("utf-8")
        client_names[conn_id] = client_name
        clients[conn_id] = conn
        metrics.record_receive(conn_id, len(name_data))
        
        logger.info(f"Client authenticated: {client_name} ({conn_id})")
        
        # Message receive loop
        while not conn.closed:
            try:
                data = await asyncio.wait_for(recv_message(conn, max_size=65536), timeout=30.0)
                
                if not data:
                    logger.debug(f"Client {conn_id} sent empty data (connection closing)")
                    break
                
                metrics.record_receive(conn_id, len(data))
                metrics.record_message_received(conn_id)
                
                # Decrypt message
                message = rsa.decrypt(data, private_key).decode("utf-8")
                logger.debug(f"Message from {client_name}: {message[:50]}...")
                
                # Re-encrypt and broadcast to other clients
                for other_id in list(clients.keys()):
                    if other_id != conn_id:
                        try:
                            encrypted_msg = rsa.encrypt(message.encode(), public_keys[other_id])
                            metrics.record_send(other_id, len(encrypted_msg))
                            metrics.record_message_sent(other_id)
                        except Exception:
                            pass
                
                # Broadcast to all except sender
                await broadcast(data, conn_id)
                
            except asyncio.TimeoutError:
                logger.debug(f"Read timeout for client {conn_id}, continuing...")
            except Exception as e:
                logger.error(f"Error receiving from client {conn_id}: {e}")
                metrics.record_error(conn_id)
                break
    
    except Exception as e:
        logger.error(f"Error handling client {conn_id}: {e}")
        metrics.record_error(conn_id)
    
    finally:
        await disconnect_client(conn_id)


async def run_server() -> None:
    """Start the chat server."""
    global transport
    
    try:
        # Create transport
        if DUAL_STACK:
            logger.info("Starting server in dual-stack mode (TCP + UTP)")
            transport = DualStackTransport(HOST, PORT)
        else:
            logger.info(f"Starting server with {PROTOCOL} protocol")
            transport = create_transport(PROTOCOL, HOST, PORT)
        
        # Start listening
        await transport.listen(HOST, PORT)
        logger.info(f"Server listening on {HOST}:{PORT}")
        
        # Accept connections
        logger.info("Server started. Waiting for connections...")
        while True:
            try:
                conn, addr = await asyncio.wait_for(transport.accept(), timeout=None)
                
                # Determine protocol
                protocol = transport.protocol_name
                
                # Handle client in a task
                asyncio.create_task(handle_client(conn, addr, protocol))
                
            except Exception as e:
                logger.error(f"Error accepting connection: {e}")
    
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        await shutdown_server()


async def shutdown_server() -> None:
    """Gracefully shutdown the server."""
    logger.info("Shutting down server...")
    
    # Close all client connections
    for conn_id in list(clients.keys()):
        await disconnect_client(conn_id)
    
    # Close transport
    if transport:
        try:
            await transport.close()
        except Exception as e:
            logger.error(f"Error closing transport: {e}")
    
    # Log final metrics
    summary = metrics.get_summary()
    logger.info(f"Server shutdown. Final metrics: {summary}")


def main() -> None:
    """Main entry point."""
    logger.info("Chat Server starting...")
    
    # Run async server
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Server interrupted")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

