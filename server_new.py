# [2026-08-25] Refactored async server using transport abstraction layer
# Supports both TCP and UTP protocols while maintaining existing business logic

import asyncio
import os
import logging
import rsa
from typing import Dict, Optional
from protocol_factory import create_transport, get_primary_protocol

# Configure logging
logging.basicConfig(
    level=os.getenv("CHATROOM_LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
HOST = os.getenv("CHATROOM_HOST", "0.0.0.0")
PORT = int(os.getenv("CHATROOM_PORT", "5000"))
PRIMARY_PROTOCOL = get_primary_protocol()

# Global state (same as original)
clients = []
client_names: Dict = {}
public_keys: Dict = {}

# Generate RSA keys for server
public_key, private_key = rsa.newkeys(1024)


async def broadcast(message: bytes, sender_conn, sender_name: str = None) -> None:
    """Broadcast encrypted message to all clients except sender.
    
    Args:
        message: Raw message bytes to encrypt and send
        sender_conn: Connection object of sender (to exclude)
        sender_name: Name of sender (for logging)
    """
    disconnected_clients = []
    
    for client in clients:
        if client != sender_conn:
            try:
                encrypted_message = rsa.encrypt(message, public_keys[client])
                await client.sendall(encrypted_message)
            except Exception as e:
                logger.warning(f"Failed to send message to {client}: {e}")
                disconnected_clients.append(client)
    
    # Clean up disconnected clients
    for client in disconnected_clients:
        try:
            clients.remove(client)
            if client in client_names:
                logger.info(f"Removed disconnected client: {client_names[client]}")
                del client_names[client]
            if client in public_keys:
                del public_keys[client]
        except ValueError:
            pass


async def handle_client(conn, addr: tuple) -> None:
    """Handle individual client connection.
    
    Receives encrypted messages and broadcasts them to other clients.
    This function's business logic is unchanged from the original implementation.
    
    Args:
        conn: Connection object from transport layer
        addr: (host, port) tuple of client address
    """
    client_name = None
    
    try:
        logger.info(f"Client connected from {addr}")
        
        # Receive and decrypt client name
        name_data = await conn.recv(1024)
        if not name_data:
            logger.warning(f"Client {addr} sent no name")
            return
        
        client_name = rsa.decrypt(name_data, private_key).decode("utf-8")
        client_names[conn] = client_name
        logger.info(f"Client identified as: {client_name}")
        
        # Main message loop
        while True:
            data = await conn.recv(1024)
            if not data:
                logger.info(f"Client {client_name} disconnected")
                break
            
            try:
                message = rsa.decrypt(data, private_key).decode("utf-8")
                logger.debug(f"Message from {client_name}: {message[:50]}...")
                # Broadcast to all other clients
                await broadcast(message.encode("utf-8"), conn, client_name)
            except Exception as e:
                logger.error(f"Failed to process message from {client_name}: {e}")
                break
    
    except Exception as e:
        logger.error(f"Error handling client {addr}: {e}")
    
    finally:
        # Cleanup
        try:
            await conn.close()
        except Exception:
            pass
        
        if conn in clients:
            clients.remove(conn)
        
        if conn in client_names:
            client_name = client_names[conn]
            logger.info(f"Client disconnected: {client_name}")
            del client_names[conn]
        
        if conn in public_keys:
            del public_keys[conn]


async def accept_and_negotiate(conn, addr: tuple) -> bool:
    """Handle protocol negotiation with connecting client.
    
    Exchanges RSA public keys to establish encrypted communication.
    
    Args:
        conn: Connection object
        addr: Client address
        
    Returns:
        True if negotiation successful, False otherwise
    """
    try:
        # Send server's public key
        await conn.sendall(public_key.save_pkcs1("PEM"))
        
        # Receive client's public key
        client_key_data = await conn.recv(1024)
        if not client_key_data:
            logger.warning(f"No public key from {addr}")
            return False
        
        public_keys[conn] = rsa.PublicKey.load_pkcs1(client_key_data)
        clients.append(conn)
        logger.debug(f"Negotiation complete with {addr}")
        return True
    except Exception as e:
        logger.error(f"Negotiation failed with {addr}: {e}")
        return False


async def main() -> None:
    """Main server loop.
    
    Creates transport listener, accepts connections, and handles clients.
    """
    transport = None
    
    try:
        logger.info(f"Starting chatroom server on {HOST}:{PORT} with {PRIMARY_PROTOCOL.upper()} protocol")
        
        # Create and start transport
        transport = create_transport(PRIMARY_PROTOCOL, HOST, PORT)
        await transport.listen(HOST, PORT)
        
        logger.info("Server listening for connections...")
        
        # Accept connections
        while True:
            try:
                conn, addr = await transport.accept()
                logger.debug(f"Accepted connection from {addr}")
                
                # Negotiate protocol (exchange keys)
                if await accept_and_negotiate(conn, addr):
                    # Handle client in background task
                    asyncio.create_task(handle_client(conn, addr))
                else:
                    # Negotiation failed, close connection
                    try:
                        await conn.close()
                    except Exception:
                        pass
            
            except Exception as e:
                logger.error(f"Error accepting connection: {e}")
                await asyncio.sleep(0.1)
    
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
    
    finally:
        logger.info("Shutting down server...")
        
        # Close all client connections
        for client in clients[:]:
            try:
                await client.close()
            except Exception:
                pass
        
        # Close transport
        if transport:
            try:
                await transport.close()
            except Exception:
                pass
        
        logger.info("Server shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
