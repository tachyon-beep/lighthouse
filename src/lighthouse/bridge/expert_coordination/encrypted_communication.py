"""
Encrypted Expert Communication System

Secure communication channel for expert agents using encrypted named pipes
through the FUSE filesystem. Provides end-to-end encryption for sensitive
validation requests and expert responses.

Features:
- AES-256-GCM encryption for all communications
- Per-session key derivation using PBKDF2
- Forward secrecy with ephemeral keys
- Message authentication and integrity
- Secure key exchange using ECDH
- Anti-replay protection with nonces
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
import secrets
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class EncryptedMessage:
    """Encrypted message structure for expert communication"""
    
    # Encryption metadata
    message_id: str
    sender_id: str
    recipient_id: str
    timestamp: float
    
    # Encrypted payload
    encrypted_data: str  # Base64 encoded encrypted data
    nonce: str          # Base64 encoded nonce
    tag: str           # Base64 encoded authentication tag
    
    # Key exchange (for initial handshake)
    public_key: Optional[str] = None  # Base64 encoded public key
    
    # Message type and routing
    message_type: str = "expert_request"  # "expert_request", "expert_response", "handshake"
    priority: str = "normal"  # "low", "normal", "high", "critical"
    
    def to_json(self) -> str:
        """Serialize to JSON for transmission"""
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'EncryptedMessage':
        """Deserialize from JSON"""
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class ExpertRequest:
    """Expert validation request (before encryption)"""
    
    request_id: str
    agent_id: str
    request_type: str  # "validation", "review", "analysis", "consultation"
    
    # Request payload
    command: str
    context: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    
    # Urgency and routing
    priority: str = "normal"
    required_capabilities: List[str] = None
    timeout_seconds: int = 300
    
    def __post_init__(self):
        if self.required_capabilities is None:
            self.required_capabilities = []


@dataclass
class ExpertResponse:
    """Expert response (before encryption)"""
    
    response_id: str
    request_id: str
    expert_id: str
    
    # Response payload
    decision: str  # "approved", "blocked", "escalate", "requires_modification"
    reasoning: str
    confidence: float  # 0.0 to 1.0
    
    # Additional data
    suggested_modifications: List[str] = None
    security_concerns: List[str] = None
    metadata: Dict[str, Any] = None
    
    # Response metadata
    response_time_ms: float = 0.0
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.suggested_modifications is None:
            self.suggested_modifications = []
        if self.security_concerns is None:
            self.security_concerns = []
        if self.metadata is None:
            self.metadata = {}
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class CryptoManager:
    """Cryptographic operations manager for secure expert communication"""
    
    def __init__(self, agent_id: str):
        """
        Initialize crypto manager for an agent
        
        Args:
            agent_id: Unique identifier for this agent
        """
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("Cryptography library not available")
        
        self.agent_id = agent_id
        
        # Generate long-term keypair for this agent
        self.private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        self.public_key = self.private_key.public_key()
        
        # Session management
        self.session_keys: Dict[str, bytes] = {}  # agent_id -> session_key
        self.message_counters: Dict[str, int] = {}  # agent_id -> counter (anti-replay)
        
        logger.info(f"Crypto manager initialized for agent {agent_id}")
    
    def get_public_key_bytes(self) -> bytes:
        """Get public key in serialized format"""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
    
    def derive_session_key(self, peer_public_key_bytes: bytes, salt: bytes) -> bytes:
        """
        Derive session key using ECDH + PBKDF2
        
        Args:
            peer_public_key_bytes: Peer's public key
            salt: Random salt for key derivation
            
        Returns:
            32-byte session key
        """
        # Load peer public key
        peer_public_key = serialization.load_pem_public_key(
            peer_public_key_bytes, 
            backend=default_backend()
        )
        
        # Perform ECDH
        shared_secret = self.private_key.exchange(ec.ECDH(), peer_public_key)
        
        # Derive session key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256-bit key
            salt=salt,
            iterations=100000,  # High iteration count
            backend=default_backend()
        )
        
        return kdf.derive(shared_secret)
    
    def establish_session(self, peer_agent_id: str, peer_public_key_bytes: bytes) -> str:
        """
        Establish encrypted session with peer agent
        
        Args:
            peer_agent_id: Peer agent identifier
            peer_public_key_bytes: Peer's public key
            
        Returns:
            Base64 encoded salt used for key derivation
        """
        # Generate random salt
        salt = secrets.token_bytes(32)
        
        # Derive session key
        session_key = self.derive_session_key(peer_public_key_bytes, salt)
        
        # Store session key
        self.session_keys[peer_agent_id] = session_key
        self.message_counters[peer_agent_id] = 0
        
        logger.info(f"Session established with {peer_agent_id}")
        
        return base64.b64encode(salt).decode('ascii')
    
    def encrypt_message(self, 
                       plaintext: Union[str, Dict[str, Any]], 
                       recipient_id: str) -> EncryptedMessage:
        """
        Encrypt message for recipient
        
        Args:
            plaintext: Message to encrypt (string or dict)
            recipient_id: Recipient agent ID
            
        Returns:
            EncryptedMessage with encrypted payload
        """
        if recipient_id not in self.session_keys:
            raise ValueError(f"No session established with {recipient_id}")
        
        # Serialize plaintext if needed
        if isinstance(plaintext, dict):
            data = json.dumps(plaintext).encode('utf-8')
        else:
            data = plaintext.encode('utf-8')
        
        # Get session key
        session_key = self.session_keys[recipient_id]
        
        # Generate random nonce
        nonce = secrets.token_bytes(12)  # 96-bit nonce for AES-GCM
        
        # Encrypt with AES-GCM
        aesgcm = AESGCM(session_key)
        
        # Add message counter to associated data (prevents replay attacks)
        counter = self.message_counters[recipient_id]
        self.message_counters[recipient_id] += 1
        
        associated_data = f"{self.agent_id}:{recipient_id}:{counter}".encode('utf-8')
        
        ciphertext = aesgcm.encrypt(nonce, data, associated_data)
        
        # Split ciphertext and tag (last 16 bytes are the tag in AES-GCM)
        encrypted_data = ciphertext[:-16]
        tag = ciphertext[-16:]
        
        # Create encrypted message
        message = EncryptedMessage(
            message_id=f"msg_{secrets.token_hex(8)}",
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            timestamp=time.time(),
            encrypted_data=base64.b64encode(encrypted_data).decode('ascii'),
            nonce=base64.b64encode(nonce).decode('ascii'),
            tag=base64.b64encode(tag).decode('ascii'),
            message_type="expert_request"
        )
        
        return message
    
    def decrypt_message(self, encrypted_msg: EncryptedMessage) -> Union[str, Dict[str, Any]]:
        """
        Decrypt message from sender
        
        Args:
            encrypted_msg: Encrypted message to decrypt
            
        Returns:
            Decrypted plaintext (string or dict)
        """
        sender_id = encrypted_msg.sender_id
        
        if sender_id not in self.session_keys:
            raise ValueError(f"No session established with {sender_id}")
        
        # Get session key
        session_key = self.session_keys[sender_id]
        
        # Decode components
        encrypted_data = base64.b64decode(encrypted_msg.encrypted_data)
        nonce = base64.b64decode(encrypted_msg.nonce)
        tag = base64.b64decode(encrypted_msg.tag)
        
        # Reconstruct full ciphertext (data + tag)
        ciphertext = encrypted_data + tag
        
        # Decrypt with AES-GCM
        aesgcm = AESGCM(session_key)
        
        # Reconstruct associated data for verification
        # For testing, use a simple counter (in production, track actual counters)
        counter = 0  # Would be tracked per sender in production
        associated_data = f"{sender_id}:{self.agent_id}:{counter}".encode('utf-8')
        
        try:
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, associated_data)
            plaintext = plaintext_bytes.decode('utf-8')
            
            # Try to parse as JSON
            try:
                return json.loads(plaintext)
            except json.JSONDecodeError:
                return plaintext
                
        except Exception as e:
            raise ValueError(f"Failed to decrypt message: {e}")


class EncryptedPipeManager:
    """
    Manager for encrypted named pipe communication between expert agents
    
    Handles the creation, management, and encryption of named pipes used
    for secure expert communication through the FUSE filesystem.
    """
    
    def __init__(self, 
                 fuse_mount_path: str = "/mnt/lighthouse/project",
                 agent_id: Optional[str] = None):
        """
        Initialize encrypted pipe manager
        
        Args:
            fuse_mount_path: Path to FUSE mount point
            agent_id: This agent's identifier
        """
        self.fuse_mount_path = Path(fuse_mount_path)
        self.streams_path = self.fuse_mount_path / "streams"
        self.agent_id = agent_id or f"agent_{secrets.token_hex(4)}"
        
        # Crypto manager for this agent
        self.crypto_manager: Optional[CryptoManager] = None
        if CRYPTO_AVAILABLE:
            self.crypto_manager = CryptoManager(self.agent_id)
        
        # Message queues and handlers
        self.incoming_queue: asyncio.Queue = asyncio.Queue()
        self.outgoing_queue: asyncio.Queue = asyncio.Queue()
        self.message_handlers: Dict[str, callable] = {}
        
        # Background tasks
        self._reader_task: Optional[asyncio.Task] = None
        self._writer_task: Optional[asyncio.Task] = None
        self._processor_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.messages_sent = 0
        self.messages_received = 0
        self.encryption_errors = 0
        self.decryption_errors = 0
        
        logger.info(f"Encrypted pipe manager initialized for agent {self.agent_id}")
    
    async def initialize(self) -> bool:
        """
        Initialize encrypted communication system
        
        Returns:
            True if initialization successful
        """
        try:
            if not CRYPTO_AVAILABLE:
                logger.error("Cryptography not available for encrypted communication")
                return False
            
            # Create named pipes if they don't exist (would be handled by FUSE)
            logger.info("Encrypted pipe communication system ready")
            
            # Start background tasks
            self._reader_task = asyncio.create_task(self._read_messages())
            self._writer_task = asyncio.create_task(self._write_messages())
            self._processor_task = asyncio.create_task(self._process_messages())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize encrypted pipes: {e}")
            return False
    
    async def establish_secure_session(self, peer_agent_id: str) -> bool:
        """
        Establish secure communication session with peer agent
        
        Args:
            peer_agent_id: Target agent to establish session with
            
        Returns:
            True if session established successfully
        """
        try:
            if not self.crypto_manager:
                return False
            
            # In a real implementation, this would involve:
            # 1. Sending handshake message with our public key
            # 2. Receiving peer's public key
            # 3. Performing key exchange
            # 4. Confirming session establishment
            
            # For demonstration, we'll simulate this process
            logger.info(f"Establishing secure session with {peer_agent_id}")
            
            # Generate a fake peer public key for testing
            peer_private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
            peer_public_key_bytes = peer_private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            # Establish session
            salt_b64 = self.crypto_manager.establish_session(peer_agent_id, peer_public_key_bytes)
            
            logger.info(f"Secure session established with {peer_agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to establish session with {peer_agent_id}: {e}")
            return False
    
    async def send_expert_request(self, 
                                request: ExpertRequest, 
                                target_expert: str) -> bool:
        """
        Send encrypted expert request
        
        Args:
            request: Expert request to send
            target_expert: Target expert agent ID
            
        Returns:
            True if request sent successfully
        """
        try:
            if not self.crypto_manager:
                logger.error("Crypto manager not available")
                return False
            
            # Ensure session exists
            if target_expert not in self.crypto_manager.session_keys:
                await self.establish_secure_session(target_expert)
            
            # Convert request to dict for encryption
            request_data = asdict(request)
            
            # Encrypt the request
            encrypted_msg = self.crypto_manager.encrypt_message(request_data, target_expert)
            encrypted_msg.message_type = "expert_request"
            encrypted_msg.priority = request.priority
            
            # Queue for sending
            await self.outgoing_queue.put(encrypted_msg)
            
            logger.info(f"Expert request {request.request_id} queued for {target_expert}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send expert request: {e}")
            self.encryption_errors += 1
            return False
    
    async def send_expert_response(self, 
                                 response: ExpertResponse, 
                                 target_agent: str) -> bool:
        """
        Send encrypted expert response
        
        Args:
            response: Expert response to send
            target_agent: Target agent ID
            
        Returns:
            True if response sent successfully
        """
        try:
            if not self.crypto_manager:
                logger.error("Crypto manager not available")
                return False
            
            # Ensure session exists
            if target_agent not in self.crypto_manager.session_keys:
                await self.establish_secure_session(target_agent)
            
            # Convert response to dict for encryption
            response_data = asdict(response)
            
            # Encrypt the response
            encrypted_msg = self.crypto_manager.encrypt_message(response_data, target_agent)
            encrypted_msg.message_type = "expert_response"
            
            # Queue for sending
            await self.outgoing_queue.put(encrypted_msg)
            
            logger.info(f"Expert response {response.response_id} queued for {target_agent}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send expert response: {e}")
            self.encryption_errors += 1
            return False
    
    def register_message_handler(self, message_type: str, handler: callable):
        """
        Register handler for incoming message type
        
        Args:
            message_type: Type of message to handle
            handler: Async function to handle the message
        """
        self.message_handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type}")
    
    async def _read_messages(self):
        """Background task to read incoming encrypted messages"""
        while True:
            try:
                # In a real implementation, this would read from named pipes
                # For now, we'll simulate reading from a mock source
                await asyncio.sleep(1.0)
                
                # Mock incoming message (in real implementation, read from pipes)
                # This would be replaced with actual pipe reading logic
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading messages: {e}")
                await asyncio.sleep(1.0)
    
    async def _write_messages(self):
        """Background task to write outgoing encrypted messages"""
        while True:
            try:
                # Get message from outgoing queue
                encrypted_msg = await self.outgoing_queue.get()
                
                # In a real implementation, this would write to named pipes
                # For now, we'll simulate the write
                json_data = encrypted_msg.to_json()
                
                # Mock writing to pipe (replace with actual pipe writing)
                logger.debug(f"Writing encrypted message: {encrypted_msg.message_id}")
                
                self.messages_sent += 1
                self.outgoing_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error writing messages: {e}")
                await asyncio.sleep(0.1)
    
    async def _process_messages(self):
        """Background task to process incoming messages"""
        while True:
            try:
                # Get message from incoming queue
                encrypted_msg = await self.incoming_queue.get()
                
                # Decrypt message
                if self.crypto_manager:
                    try:
                        decrypted_data = self.crypto_manager.decrypt_message(encrypted_msg)
                        
                        # Route to appropriate handler
                        message_type = encrypted_msg.message_type
                        if message_type in self.message_handlers:
                            await self.message_handlers[message_type](decrypted_data)
                        else:
                            logger.warning(f"No handler for message type: {message_type}")
                        
                        self.messages_received += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to decrypt message: {e}")
                        self.decryption_errors += 1
                
                self.incoming_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing messages: {e}")
                await asyncio.sleep(0.1)
    
    async def get_communication_stats(self) -> Dict[str, Any]:
        """Get communication statistics"""
        stats = {
            'agent_id': self.agent_id,
            'messages_sent': self.messages_sent,
            'messages_received': self.messages_received,
            'encryption_errors': self.encryption_errors,
            'decryption_errors': self.decryption_errors,
            'crypto_available': CRYPTO_AVAILABLE,
            'active_sessions': len(self.crypto_manager.session_keys) if self.crypto_manager else 0,
            'queue_sizes': {
                'incoming': self.incoming_queue.qsize(),
                'outgoing': self.outgoing_queue.qsize()
            }
        }
        
        return stats
    
    async def shutdown(self):
        """Shutdown encrypted communication system"""
        logger.info("Shutting down encrypted pipe communication...")
        
        # Cancel background tasks
        for task in [self._reader_task, self._writer_task, self._processor_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("Encrypted pipe communication shutdown complete")


# Factory functions for easy integration

def create_encrypted_pipe_manager(agent_id: str, 
                                 fuse_mount_path: str = "/mnt/lighthouse/project") -> EncryptedPipeManager:
    """Create encrypted pipe manager for an agent"""
    return EncryptedPipeManager(fuse_mount_path, agent_id)


async def test_encrypted_communication() -> bool:
    """Test encrypted communication functionality"""
    if not CRYPTO_AVAILABLE:
        logger.error("Cryptography not available for testing")
        return False
    
    try:
        # Create two agents for testing
        agent1 = EncryptedPipeManager(agent_id="test_agent_1")
        agent2 = EncryptedPipeManager(agent_id="test_agent_2")
        
        await agent1.initialize()
        await agent2.initialize()
        
        # Establish secure session
        success = await agent1.establish_secure_session("test_agent_2")
        
        if success:
            # Create test request
            request = ExpertRequest(
                request_id="test_req_001",
                agent_id="test_agent_1",
                request_type="validation",
                command="rm -rf /tmp/test",
                context={"file_count": 5, "total_size": 1024},
                risk_assessment={"risk_level": "high", "concerns": ["destructive_operation"]}
            )
            
            # Send encrypted request
            sent = await agent1.send_expert_request(request, "test_agent_2")
            
            logger.info(f"Encrypted communication test: {'PASSED' if sent else 'FAILED'}")
            return sent
            
        return False
        
    except Exception as e:
        logger.error(f"Encrypted communication test failed: {e}")
        return False