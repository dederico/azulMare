import os
import json
import logging
import asyncio
import threading
import traceback
import base64
import requests
import httpx
import pytz
import psycopg2
import tiktoken
import zlib
import aioredis
import random
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request, Response, HTTPException, APIRouter, Depends
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager, contextmanager
from typing import Dict, List, Optional, Any, Union, TypeVar, Generic, Callable
from pydantic import BaseModel, Field
from copy import deepcopy
from functools import lru_cache
import time
from prometheus_client import Counter, Gauge, Histogram

# Import from the original routes
from app.api.routes import router as original_router
from app.api.routes import whatsapp as original_whatsapp
from app.util.database import LocalStorage
from app.models.Config import Config
from app.models.Message import Message
from app.util.logger import logger

# Constants for token and context management
MAX_TOKENS_PER_CONVERSATION = 4000  # Maximum tokens allowed per conversation
MAX_TOKENS_PER_MESSAGE = 1000  # Maximum tokens allowed per message
TOKEN_COUNTING_MODEL = "gpt-3.5-turbo"  # Model to use for token counting
TOKEN_COMPRESSION_THRESHOLD = 3000  # Token threshold before compressing context
MESSAGE_COMPRESSION_THRESHOLD = 15  # Message count threshold before compressing context
CONTEXT_VALIDATION_INTERVAL = 300  # Time in seconds between context validations (5 minutes)
RATE_LIMIT_WINDOW = 60  # 1 minute
RATE_LIMIT_MESSAGES = 20  # Max messages per minute
BATCH_SIZE = 10  # Number of messages to process in a batch for pruning
MAX_RECOVERY_ATTEMPTS = 3  # Maximum number of recovery attempts for a context
MAX_CONTEXT_AGE = 24 * 60 * 60  # 24 hours in seconds
MAX_CONTEXTS = 1000  # Maximum number of contexts to keep in memory
BACKUP_TTL = 300  # 5 minutes for context backups

# Setup the router
router = APIRouter()

# Define metrics for monitoring
CONTEXT_COUNT = Gauge('whatsapp_context_count', 'Number of active WhatsApp contexts')
TOKEN_USAGE = Histogram('whatsapp_token_usage', 'Token usage per message', buckets=[0, 100, 250, 500, 750, 1000, 2000, 4000])
COMPRESSION_COUNT = Counter('whatsapp_compression_count', 'Number of context compressions performed')
RATE_LIMIT_COUNT = Counter('whatsapp_rate_limit_count', 'Number of rate limits applied')
CONTEXT_RECOVERY_COUNT = Counter('whatsapp_context_recovery_count', 'Number of context recoveries performed')
MESSAGE_PROCESSING_TIME = Histogram('whatsapp_message_processing_time', 'Time to process a WhatsApp message', buckets=[0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30])
VALIDATION_ERRORS = Counter('whatsapp_validation_errors', 'Number of context validation errors detected')
CLEANUP_OPERATIONS = Counter('whatsapp_cleanup_operations', 'Number of cleanup operations performed', ['type'])
BACKUP_COUNT = Gauge('whatsapp_backup_count', 'Number of context backups stored')

# Global dictionary to store all enhanced contexts by phone number
enhanced_contexts: Dict[str, EnhancedContext] = {}

# =======================================
# Context and Token Management Utilities
# =======================================
class EnhancedContext(BaseModel):
    """Wrapper around the original context with enhanced features"""
    original_context: Any  # The original context object
    compressed_history: Optional[bytes] = None
    version: int = 1  # Version for tracking context changes
    token_count: int = 0  # Track token count for this conversation
    rate_limit_count: int = 0  # Track messages for rate limiting
    rate_limit_start_time: Optional[float] = None
    last_validation_time: Optional[float] = None  # Last time context was validated
    compression_count: int = 0  # Number of times this context has been compressed
    recovery_count: int = 0  # Number of times this context has been recovered
    created_at: float = Field(default_factory=time.time)  # Creation timestamp
    
    class Config:
        arbitrary_types_allowed = True  # Allow Any type for original_context
    def compress_history(self, history_text: str):
        """
        Compress and store conversation history when it gets too long.
        
        Args:
            history_text (str): The conversation history text to compress
        """
        self.compressed_history = zlib.compress(history_text.encode('utf-8'))
        
    def decompress_history(self) -> Optional[str]:
        """
        Decompress stored conversation history.
        
        Returns:
            Optional[str]: The decompressed history text, or None if decompression fails
        """
        if self.compressed_history:
            try:
                return zlib.decompress(self.compressed_history).decode('utf-8')
            except Exception as e:
                logger.error(f"Error decompressing history: {str(e)}")
                return None
        return None
    
    def backup(self) -> dict:
        """
        Create a backup of the context state.
        
        Returns:
            dict: A dictionary containing the critical context state
        """
        return {
            "version": self.version,
            "token_count": self.token_count,
            "rate_limit_count": self.rate_limit_count,
            "rate_limit_start_time": self.rate_limit_start_time,
            "has_compressed_history": self.compressed_history is not None
        }
    
    def restore(self, backup_data: dict):
        """
        Restore context from a backup.
        
        Args:
            backup_data (dict): The backup data to restore from
        """
        for key, value in backup_data.items():
            if hasattr(self, key) and key != "has_compressed_history":
                setattr(self, key, value)
        
        # Increment recovery counter
        self.recovery_count += 1
        
    def is_valid(self) -> bool:
        """
        Validates that the context is in a consistent state.
        
        Returns:
            bool: True if the context is valid, False otherwise
        """
        # Check for required attributes
        if self.version < 1:
            logger.error(f"Invalid context version: {self.version}")
            return False
        
        # Validate token count is reasonable
        if self.token_count < 0 or self.token_count > MAX_TOKENS_PER_CONVERSATION * 2:
            logger.error(f"Suspicious token count: {self.token_count}")
            return False
            
        # Check for timestamp consistency
        current_time = time.time()
        if self.rate_limit_start_time and self.rate_limit_start_time > current_time:
            logger.error(f"Future timestamp detected in rate limit: {self.rate_limit_start_time}")
            return False
            
        return True
        
    def update_validation_time(self):
        """Update the last validation timestamp to the current time."""
        self.last_validation_time = time.time()
# Create a separate backup store with TTL
class ContextBackupStore:
    def __init__(self):
        self.backups = {}
        self.timestamps = {}
        
    def store(self, number: str, backup: dict):
        """Store a context backup with timestamp"""
        self.backups[number] = backup
        self.timestamps[number] = time.time()
        BACKUP_COUNT.set(len(self.backups))
        
    def get(self, number: str) -> Optional[dict]:
        """Get a backup if it exists and hasn't expired"""
        if number not in self.backups:
            return None
            
        # Check TTL
        if time.time() - self.timestamps[number] > BACKUP_TTL:
            self.remove(number)
            return None
            
        return self.backups[number]
        
    def remove(self, number: str):
        """Remove a backup and update metrics"""
        self.backups.pop(number, None)
        self.timestamps.pop(number, None)
        BACKUP_COUNT.set(len(self.backups))
        CLEANUP_OPERATIONS.labels(type='backup').inc()
        
    async def cleanup(self):
        """Remove expired backups periodically"""
        cleanup_interval = 60  # Run cleanup every minute
        
        while True:
            try:
                # Get current time once for all operations
                current_time = time.time()
                
                # Use a list comprehension for better performance
                expired = [
                    number for number, timestamp in self.timestamps.items()
                    if current_time - timestamp > BACKUP_TTL
                ]
                
                # Batch remove expired backups
                if expired:
                    logger.info(f"Removing {len(expired)} expired backups")
                    for number in expired:
                        self.remove(number)
                    
            except Exception as e:
                logger.error(f"Error in backup cleanup: {str(e)}")
                
            try:
                # Use wait_for to make the sleep cancellable
                await asyncio.wait_for(
                    asyncio.sleep(cleanup_interval),
                    timeout=cleanup_interval + 5  # Add small buffer to timeout
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info("Backup cleanup task cancelled")
                # Perform final cleanup before exiting
                try:
                    # Clear all expired backups one last time
                    current_time = time.time()
                    expired = [
                        number for number, timestamp in self.timestamps.items()
                        if current_time - timestamp > BACKUP_TTL
                    ]
                    for number in expired:
                        self.remove(number)
                except Exception as e:
                    logger.error(f"Error in final backup cleanup: {str(e)}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in backup cleanup: {str(e)}")
                # Add a small delay before retrying on unexpected errors
                await asyncio.sleep(1)
# Initialize the backup store
backup_store = ContextBackupStore()
# LRU cache for frequently accessed contexts
@lru_cache(maxsize=100)
def get_cached_context(phone_number: str):
    """Get a context from LRU cache if available, otherwise return None"""
    return enhanced_contexts.get(phone_number)

# Token counting utility
@lru_cache(maxsize=128)
def get_tokenizer(model_name: str = TOKEN_COUNTING_MODEL):
    """Get a tokenizer for the specified model"""
    try:
        encoding = tiktoken.encoding_for_model(model_name)
        return encoding
    except KeyError:
        # Fallback to cl100k_base if model not found
        return tiktoken.get_encoding("cl100k_base")
def count_tokens(text: str, model_name: str = TOKEN_COUNTING_MODEL) -> int:
    """Count tokens in text using the specified model's tokenizer"""
    encoding = get_tokenizer(model_name)
    return len(encoding.encode(text))

class TokenBatcher:
    """Batches token counting operations for efficiency"""
    def __init__(self):
        self.batch = []
        self.batch_size = 0
        self.max_batch_size = 1000
        self.error_count = 0
        self.max_errors = 3
        
    async def add_text(self, text: str) -> int:
        """Add text to batch and return token count"""
        try:
            if self.batch_size >= self.max_batch_size:
                await self.process_batch()
                
            tokens = count_tokens(text)
            self.batch.append((text, tokens))
            self.batch_size += 1
            return tokens
        except Exception as e:
            self.error_count += 1
            logger.error(f"Error in token batcher (count {self.error_count}): {str(e)}")
            if self.error_count >= self.max_errors:
                logger.critical("Token batcher exceeded max errors, clearing batch")
                self.batch = []
                self.batch_size = 0
                self.error_count = 0
            return len(text) // 4  # Fallback approximation
        
    async def process_batch(self):
        """Process accumulated token counting operations with error handling"""
        if not self.batch:
            return
            
        try:
            # Process any accumulated tokens
            for text, token_count in self.batch:
                TOKEN_USAGE.observe(token_count)
                
            # Clear the processed batch
            self.batch = []
            self.batch_size = 0
            self.error_count = 0  # Reset error count on successful processing
            
        except Exception as e:
            logger.error(f"Error processing token batch: {str(e)}")
            # Clear batch on error to prevent cascading failures
            self.batch = []
            self.batch_size = 0

# Initialize the batcher
token_batcher = TokenBatcher()

async def periodic_batch_processing():
    """Process token batches periodically to ensure timely metric updates"""
    while True:
        try:
            await token_batcher.process_batch()
        except Exception as e:
            logger.error(f"Error in periodic batch processing: {str(e)}")
        await asyncio.sleep(60)  # Process every minute
async def truncate_message(message_text: str, max_tokens: int) -> str:
    """Truncate a message to fit within max_tokens"""
    try:
        encoding = get_tokenizer()
        tokens = encoding.encode(message_text)
        
        # Leave margin for warning message
        truncated_tokens = tokens[:max_tokens - 50]
        truncated_message = encoding.decode(truncated_tokens)
        
        logger.warning(f"Message truncated from {len(tokens)} to {len(truncated_tokens)} tokens")
        return truncated_message + "\n\n[Message truncated due to length limits]"
    except Exception as e:
        logger.error(f"Error truncating message: {str(e)}")
        # If truncation fails, return a safe fixed message
        return "Message too long and couldn't be truncated properly. Please send a shorter message."

@contextmanager
def get_db_connection(db):
    """Context manager for database connections with proper transaction management"""
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=db.dbName, 
            user=db.user, 
            password=db.password, 
            host=db.host, 
            port=db.port
        )
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

# =======================================
# Enhanced Database Operations
# =======================================
async def batch_process_message_history(db, number, max_messages=20):
    """
    Optimized batch processing with better transaction management
    Uses window functions to identify messages to delete more efficiently
    """
    try:
        with get_db_connection(db) as conn:
            cursor = conn.cursor()
            
            # Use window functions to identify messages to delete more efficiently
            cursor.execute("""
                WITH ranked_messages AS (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY number 
                               ORDER BY time DESC
                           ) as rn
                    FROM messages
                    WHERE number = %s
                )
                SELECT COUNT(*)
                FROM ranked_messages
                WHERE rn > %s
            """, [number, max_messages])
            
            to_delete = cursor.fetchone()[0]
            
            if to_delete > 0:
                deleted_total = 0
                while deleted_total < to_delete:
                    # Delete in smaller batches for better performance
                    cursor.execute("""
                        WITH ranked_messages AS (
                            SELECT id,
                                   ROW_NUMBER() OVER (
                                       PARTITION BY number 
                                       ORDER BY time DESC
                                   ) as rn
                            FROM messages
                            WHERE number = %s
                        )
                        DELETE FROM messages
                        WHERE id IN (
                            SELECT id 
                            FROM ranked_messages
                            WHERE rn > %s
                            LIMIT %s
                        )
                        RETURNING id
                    """, [number, max_messages, BATCH_SIZE])
                    
                    deleted_count = cursor.rowcount
                    deleted_total += deleted_count
                    
                    if deleted_count < BATCH_SIZE:
                        break
                        
                    conn.commit()  # Commit each batch to release locks
                    
                logger.debug(f"Efficiently removed {deleted_total} old messages for {number}")
            
            conn.commit()
    except Exception as e:
        logger.error(f"Error in optimized batch message processing: {str(e)}")
async def compress_conversation_if_needed(
    db: LocalStorage,
    context: Optional[EnhancedContext], 
    number: str
) -> None:
    """
    Compresses the conversation history if it exceeds threshold
    Now uses enhanced compression decision logic
    
    Args:
        db (LocalStorage): Database connection object
        context (Optional[EnhancedContext]): The context to check for compression
        number (str): The phone number associated with the context
    """
    try:
        # Only compress if context exists and has enhanced features
        if number not in enhanced_contexts:
            return
            
        context_obj = enhanced_contexts[number]
            
        with get_db_connection(db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM messages WHERE number = %s", [number])
            count = cursor.fetchone()[0]
            
            # Use enhanced compression decision logic with validation
            if should_compress_context(context_obj, count):
                # Validate message count before compression
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM messages 
                    WHERE number = %s 
                    AND time > NOW() - INTERVAL '1 hour'
                """, [number])
                recent_count = cursor.fetchone()[0]
                
                # Only compress if we have enough recent messages
                if recent_count >= 5:
                    cursor.execute("""
                        SELECT message, direction, time
                        FROM messages
                        WHERE number = %s
                        ORDER BY time ASC
                    """, [number])
                messages = cursor.fetchall()
                
                # Format messages for compression
                formatted_history = "\n\n".join([
                    f"[{row[2]}] {'User' if row[1] == 'inbound' else 'Bot'}: {row[0]}"
                    for row in messages
                ])
                
                # Compress the history
                enhanced_contexts[number].compress_history(formatted_history)
                enhanced_contexts[number].version += 1
                
                # Keep only recent messages (last 5)
                cursor.execute("""
                    DELETE FROM messages
                    WHERE id IN (
                        SELECT id FROM messages
                        WHERE number = %s
                        ORDER BY time ASC
                        LIMIT %s
                    )
                """, [number, max(0, count - 5)])
                
                conn.commit()
                
                logger.debug(f"Compressed history for {number}: {count} messages -> 5 messages")
                
                # Update compression metrics
                context_obj.compression_count += 1
                COMPRESSION_COUNT.inc()
                
                # Reset token count to account for the compression
                context_obj.token_count = min(500, context_obj.token_count)
    except Exception as e:
        logger.error(f"Error compressing conversation: {str(e)}")
        
        # Try to recover the context if it exists
        await recover_context(number)
async def check_token_limit(number: str, message_text: str) -> str:
    """
    Checks and manages token limits using the token batcher
    Returns the original message or a truncated version if it exceeds the limit
    """
    # If context doesn't exist yet, just return the original message
    if number not in enhanced_contexts:
        return message_text
        
    context = enhanced_contexts[number]
    
    # Count tokens in the message using the batcher
    try:
        message_tokens = await token_batcher.add_text(message_text)
        
        # If the message exceeds the per-message limit
        if message_tokens > MAX_TOKENS_PER_MESSAGE:
            return await truncate_message(message_text, MAX_TOKENS_PER_MESSAGE)
        
        # If the entire conversation exceeds the limit
        if context.token_count + message_tokens > MAX_TOKENS_PER_CONVERSATION:
            # Update token counter but allow the message
            context.token_count = message_tokens  # Reset counter with just this message
            logger.warning(f"Token limit exceeded for {number}. Resetting counter.")
            return message_text
        
        # Update token counter
        context.token_count += message_tokens
        return message_text
    except Exception as e:
        logger.error(f"Error checking token limits: {str(e)}")
        return message_text  # In case of error, return original message
class EnhancedRateLimiter:
    """Enhanced rate limiter with Redis connection pooling and robust error handling"""
    def __init__(self, redis_url: Optional[str] = None):
        self.redis = None
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.local_cache = {}
        self.cache_lock = asyncio.Lock()
        self.connection_retries = 0
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
        self._pool = None
        
    async def initialize(self):
        """Initialize Redis connection pool if URL is available"""
        if self.redis_url:
            try:
                # Create connection pool with reasonable defaults
                self._pool = aioredis.ConnectionPool.from_url(
                    self.redis_url,
                    max_connections=20,  # Adjust based on your needs
                    timeout=1.0,  # Connection timeout
                    retry_on_timeout=True
                )
                self.redis = aioredis.Redis(connection_pool=self._pool)
                logger.info("Enhanced rate limiter initialized with Redis connection pool")
            except Exception as e:
                logger.error(f"Failed to initialize Redis pool: {str(e)}")
                
    async def _ensure_connection(self) -> bool:
        """
        Ensure Redis connection is available, with improved retry logic
        to prevent infinite recursion and handle edge cases better.
        
        Returns:
            bool: True if connection is available, False otherwise
        """
        if not self.redis:
            return False
            
        retry_count = 0
        max_retries = self.max_retries
        base_delay = self.retry_delay
        
        while retry_count <= max_retries:
            try:
                # Test connection
                await self.redis.ping()
                self.connection_retries = 0  # Reset on successful connection
                return True
                
            except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
                retry_count += 1
                if retry_count <= max_retries:
                    # Use exponential backoff with jitter
                    delay = base_delay * (2 ** (retry_count - 1)) * (0.5 + random.random())
                    logger.warning(
                        f"Redis connection attempt {retry_count}/{max_retries} "
                        f"failed: {str(e)}. Retrying in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("Redis connection failed after max retries")
                    return False
                    
            except Exception as e:
                logger.error(f"Unexpected Redis error: {str(e)}")
                return False
                
        return False  # Fallback return, should not reach here
    
    async def check_rate_limit(self, number: str) -> bool:
        """
        Hierarchical rate limiting:
        1. Check local cache first (fastest)
        2. Try Redis if available (distributed)
        3. Fall back to in-memory context if both fail
        
        Args:
            number (str): The phone number to check
            
        Returns:
            bool: True if rate limited, False otherwise
        """
        try:
            # Quick local cache check first
            async with self.cache_lock:
                if number in self.local_cache:
                    entry = self.local_cache[number]
                    if time.time() - entry['timestamp'] < RATE_LIMIT_WINDOW:
                        if entry['count'] > RATE_LIMIT_MESSAGES:
                            return True
                        entry['count'] += 1
                        return False
                    else:
                        # Reset expired entry
                        self.local_cache[number] = {
                            'count': 1,
                            'timestamp': time.time()
                        }
                        return False
                        
            # Try Redis if available
            if self.redis:
                try:
                    if await self._ensure_connection():
                        result = await self._check_redis_rate_limit(number)
                        # Cache the result locally
                        async with self.cache_lock:
                            self.local_cache[number] = {
                                'count': 1 if not result else RATE_LIMIT_MESSAGES + 1,
                                'timestamp': time.time()
                            }
                        return result
                    else:
                        logger.warning("Redis connection unavailable, falling back to local rate limiting")
                except Exception as e:
                    logger.error(f"Redis rate limit error: {str(e)}")
                    
            # Fall back to context-based rate limiting
            try:
                result = await local_check_rate_limit(number)
                
                # Cache the result
                async with self.cache_lock:
                    self.local_cache[number] = {
                        'count': 1 if not result else RATE_LIMIT_MESSAGES + 1,
                        'timestamp': time.time()
                    }
                return result
            except Exception as e:
                logger.error(f"Local rate limit check failed: {str(e)}")
                return False  # Fail open on error
                
        except Exception as e:
            logger.error(f"Rate limit error: {str(e)}")
            return False  # Fail open on errors
            
    async def _check_redis_rate_limit(self, number: str) -> bool:
        """
        Enhanced Redis rate limit check with optimized pipeline usage.
        Removes redundant GET operation since INCR returns the new value.
        
        Args:
            number (str): The phone number to check
            
        Returns:
            bool: True if rate limited, False otherwise
            
        Raises:
            Exception: If Redis operation fails
        """
        key = f"rate_limit:{number}"
        try:
            # Use Redis pipeline with explicit transaction
            async with self.redis.pipeline(transaction=True) as pipe:
                # Execute all commands in a single transaction
                pipe.multi()
                # INCR returns the new value, no need for separate GET
                pipe.incr(key)
                pipe.expire(key, RATE_LIMIT_WINDOW)
                
                try:
                    results = await pipe.execute()
                    current_count = int(results[0])  # New count from INCR
                    expire_set = bool(results[1])  # From EXPIRE
                    
                    if not expire_set:
                        logger.warning(f"Failed to set expiry for rate limit key: {key}")
                    
                    if current_count > RATE_LIMIT_MESSAGES:
                        logger.warning(
                            f"Redis rate limit exceeded for {number}: "
                            f"{current_count} messages in {RATE_LIMIT_WINDOW} seconds"
                        )
                        return True
                    
                    return False
                    
                except aioredis.WatchError:
                    logger.warning(f"Concurrent modification detected for {key}")
                    await asyncio.sleep(0.1)  # Short delay before retry
                    return await self._check_redis_rate_limit(number)  # Single retry
                
        except Exception as e:
            logger.error(f"Redis rate limit check failed: {str(e)}")
            raise  # Re-raise to be handled by the caller
# Initialize the enhanced rate limiter
rate_limiter = EnhancedRateLimiter()

# Lock for thread-safe context creation
context_lock = asyncio.Lock()
async def local_check_rate_limit(number: str) -> bool:
    """
    Local rate limiting implementation (fallback when Redis is not available)
    Returns True if rate limited, False otherwise
    """
    if number not in enhanced_contexts:
        return False
        
    context = enhanced_contexts[number]
    current_time = datetime.now().timestamp()
    
    # Initialize rate limiting if not yet set
    if context.rate_limit_start_time is None:
        context.rate_limit_start_time = current_time
        context.rate_limit_count = 1
        return False
    
    # Check if we're still in the same time window
    if current_time - context.rate_limit_start_time > RATE_LIMIT_WINDOW:
        # Reset for new window
        context.rate_limit_start_time = current_time
        context.rate_limit_count = 1
        return False
    
    # Increment count and check if limit exceeded
    context.rate_limit_count += 1
    if context.rate_limit_count > RATE_LIMIT_MESSAGES:
        logger.warning(f"Local rate limit exceeded for {number}: {context.rate_limit_count} messages in {RATE_LIMIT_WINDOW} seconds")
        return True
    
    return False

# For compatibility with existing code
async def check_rate_limit(number: str) -> bool:
    """
    Main rate limit check function that uses distributed limiter if available
    """
    return await rate_limiter.check_rate_limit(number)
async def reconstruct_from_database(context: EnhancedContext, number: str) -> bool:
    """Reconstruct context from database history"""
    db = LocalStorage()
    try:
        with get_db_connection(db) as conn:
            cursor = conn.cursor()
            # Get recent messages
            cursor.execute("""
                SELECT message, direction, time
                FROM messages 
                WHERE number = %s 
                ORDER BY time DESC 
                LIMIT 10
            """, [number])
            
            messages = cursor.fetchall()
            
            # Reset context state
            context.token_count = 0
            context.rate_limit_count = 0
            context.rate_limit_start_time = time.time()
            context.version += 1
            context.compressed_history = None
            
            # Rebuild conversation history
            total_tokens = 0
            for message, direction, msg_time in messages:
                total_tokens += count_tokens(message)
                if total_tokens > MAX_TOKENS_PER_CONVERSATION:
                    break
            
            context.token_count = total_tokens
            return True
            
    except Exception as e:
        logger.error(f"Database reconstruction error: {str(e)}")
        return False

async def recover_context(number: str) -> bool:
    """
    Optimized context recovery with better failure handling and efficiency
    
    Args:
        number (str): Phone number associated with the context
        
    Returns:
        bool: True if recovery was successful, False otherwise
    """
    try:
        # Quick validation check first
        if number not in enhanced_contexts:
            logger.warning(f"No context found for {number} during recovery")
            return False
            
        context = enhanced_contexts[number]
        
        # Update recovery metrics first to ensure accurate tracking
        context.recovery_count += 1
        CONTEXT_RECOVERY_COUNT.inc()
        
        # Check recovery attempts early to fail fast
        if context.recovery_count > MAX_RECOVERY_ATTEMPTS:
            logger.error(f"Max recovery attempts ({MAX_RECOVERY_ATTEMPTS}) exceeded for {number}")
            del enhanced_contexts[number]
            return False
            
        # Try backup restoration first - most efficient as it's in memory
        backup = backup_store.get(number)
        if backup:
            try:
                if await restore_with_degradation(context, backup):
                    if context.is_valid():  # Validate restored context
                        logger.info(f"Context restored from backup for {number}")
                        return True
                    else:
                        logger.warning(f"Restored context failed validation for {number}")
                        # Don't delete yet, try database reconstruction
            except Exception as e:
                logger.error(f"Backup restore failed for {number}: {str(e)}")
        
        # Try database reconstruction if backup failed
        try:
            if await reconstruct_from_database(context, number):
                if context.is_valid():  # Validate reconstructed context
                    logger.info(f"Context reconstructed from database for {number}")
                    return True
                else:
                    logger.warning(f"Reconstructed context failed validation for {number}")
            else:
                logger.warning(f"Database reconstruction failed for {number}")
        except Exception as e:
            logger.error(f"Database reconstruction failed for {number}: {str(e)}")
        
        # If all recovery attempts failed, create new context
        enhanced_contexts[number] = EnhancedContext(
            original_context=None,
            version=1,
            token_count=0,
            rate_limit_count=0,
            rate_limit_start_time=time.time()
        )
        logger.info(f"Created new context for {number} after recovery failure")
        return True
        
    except Exception as e:
        logger.error(f"Unexpected error during context recovery for {number}: {str(e)}")
        # Remove the context in case of unexpected errors
        enhanced_contexts.pop(number, None)
        return False
async def restore_with_degradation(context: EnhancedContext, backup_data: dict) -> bool:
    """
    Attempts to restore context with gradual degradation if full restore fails.
    
    This is an enhancement to the original implementation that allows for partial
    context restoration when full restoration fails. It prioritizes critical fields
    like token counts and rate limiting information while safely discarding
    non-critical data that might be corrupted.
    
    Args:
        context (EnhancedContext): The context to restore
        backup_data (dict): The backup data to restore from
        
    Returns:
        bool: True if restoration was successful (even partially), False otherwise
    """
    try:
        # Try full restore first
        context.restore(backup_data)
        return True
    except Exception as e:
        logger.error(f"Full context restore failed: {str(e)}")
        
        try:
            # Attempt partial restore of critical fields
            critical_fields = ['token_count', 'rate_limit_count', 'version']
            for field in critical_fields:
                if field in backup_data:
                    setattr(context, field, backup_data[field])
            
            # Reset non-critical fields to defaults
            context.compressed_history = None
            context.rate_limit_start_time = time.time()
            context.recovery_count += 1
            logger.warning("Performed partial context restore with degradation")
            return True
        except Exception as e2:
            logger.error(f"Partial restore failed: {str(e2)}")
            return False
def should_compress_context(
    context: EnhancedContext,
    message_count: int
) -> bool:
    """
    Enhanced compression decision logic with improved validation
    
    Args:
        context (EnhancedContext): The context to check
        message_count (int): Current number of messages
        
    Returns:
        bool: True if the context should be compressed, False otherwise
    """
    try:
        # Check basic thresholds
        if message_count > MESSAGE_COMPRESSION_THRESHOLD:
            return True
            
        if context.token_count > TOKEN_COMPRESSION_THRESHOLD:
            return True
            
        # Check compression efficiency
        if context.compressed_history:
            try:
                # If context has an original_context with messages
                if context.original_context and hasattr(context.original_context, 'messages'):
                    original_size = sum(len(str(msg).encode()) for msg in context.original_context.messages)
                    compressed_size = len(context.compressed_history)
                    if compressed_size < original_size * 0.5:  # If compression saves > 50%
                        return True
            except Exception as e:
                # If error checking efficiency, fall back to basic checks
                logger.error(f"Error checking compression efficiency: {str(e)}")
                
        # Check conversation velocity
        if context.rate_limit_start_time and RATE_LIMIT_WINDOW > 0:
            message_rate = context.rate_limit_count / RATE_LIMIT_WINDOW
            if message_rate > (RATE_LIMIT_MESSAGES * 0.8):
                return True
            
        return False
    except Exception as e:
        logger.error(f"Error in compression decision: {str(e)}")
        return message_count > MESSAGE_COMPRESSION_THRESHOLD  # Fallback to basic check
async def validate_all_contexts():
    """
    Validates all contexts periodically and attempts recovery if needed
    """
    while True:
        try:
            current_time = time.time()
            invalid_contexts = []
            
            # Check each context
            for number, context in list(enhanced_contexts.items()):
                # Skip if recently validated
                if (context.last_validation_time and 
                    current_time - context.last_validation_time < CONTEXT_VALIDATION_INTERVAL):
                    continue
                    
                # Validate context integrity
                if not context.is_valid():
                    VALIDATION_ERRORS.inc()
                    logger.warning(f"Invalid context detected for {number}")
                    
                    # Try recovery if we haven't exceeded max attempts
                    if context.recovery_count < MAX_RECOVERY_ATTEMPTS:
                        success = await recover_context(number)
                        if not success:
                            invalid_contexts.append(number)
                    else:
                        invalid_contexts.append(number)
                        
                # Check for stale rate limit windows
                if (context.rate_limit_start_time and 
                    current_time - context.rate_limit_start_time > RATE_LIMIT_WINDOW * 2):
                    context.rate_limit_count = 0
                    context.rate_limit_start_time = None
                    
                # Check compression state
                if context.compression_count > 0 and not context.compressed_history:
                    logger.warning(f"Inconsistent compression state for {number}")
                    invalid_contexts.append(number)
                    
                # Update validation timestamp
                context.update_validation_time()
            
            # Remove invalid contexts
            for number in invalid_contexts:
                logger.error(f"Removing invalid context for {number}")
                if number in enhanced_contexts:
                    del enhanced_contexts[number]
            
            # Update metrics
            CONTEXT_COUNT.set(len(enhanced_contexts))
            
        except Exception as e:
            logger.error(f"Error in context validation: {str(e)}")
        # Wait before next validation cycle
        await asyncio.sleep(CONTEXT_VALIDATION_INTERVAL)

async def cleanup_old_contexts():
    """Periodically clean up old contexts to prevent memory leaks"""
    while True:
        try:
            current_time = time.time()
            contexts_to_remove = []
            
            # Check for old contexts
            for number, context in enhanced_contexts.items():
                # Remove contexts older than MAX_CONTEXT_AGE
                if current_time - context.created_at > MAX_CONTEXT_AGE:
                    contexts_to_remove.append(number)
                    
            # If we're over the limit, remove oldest contexts first
            if len(enhanced_contexts) > MAX_CONTEXTS:
                sorted_contexts = sorted(
                    enhanced_contexts.items(),
                    key=lambda x: x[1].created_at
                )
                # Keep the newest MAX_CONTEXTS contexts
                contexts_to_remove.extend(
                    number for number, _ in sorted_contexts[:-MAX_CONTEXTS]
                )
            
            # Remove the contexts
            for number in contexts_to_remove:
                logger.info(f"Cleaning up old context for {number}")
                if number in enhanced_contexts:
                    del enhanced_contexts[number]
                    CLEANUP_OPERATIONS.labels(type='context').inc()
            
            # Update metrics
            CONTEXT_COUNT.set(len(enhanced_contexts))
            
        except Exception as e:
            logger.error(f"Error in context cleanup: {str(e)}")
        await asyncio.sleep(300)  # Run every 5 minutes

@router.post("/whatsapp")
async def whatsapp_wrapper(request: Request):
    """
    Enhanced wrapper for the WhatsApp endpoint that adds:
    - Token counting and limiting
    - LRU caching for frequently accessed contexts
    - Context compression for long conversations
    - Batch processing for message history
    - Rate limiting
    - Robust context recovery mechanism
    - Context validation
    - Comprehensive monitoring metrics
    """
    start_time = time.time()
    from_number = None
    
    try:
        # Safely parse the request data
        try:
            request_data = await request.json()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request: {str(e)}")
            return JSONResponse(
                content={"error": "Invalid JSON request"},
                status_code=400
            )
            
        # Extract basic information
        message_type = request_data.get('type', '')
        if message_type != 'from_client':
            # Pass through to original handler for non-client messages
            return await original_whatsapp(request)
            
        from_number = request_data.get('client', {}).get('phone')
        if not from_number:
            return JSONResponse(
                content={"error": "Missing phone number"},
                status_code=400
            )
            
        body = request_data.get('text', '')
        client_id = request_data.get('client_id')
        channel_id = request_data.get('channel_id')
        
        # Check rate limiting first
        is_rate_limited = await rate_limiter.check_rate_limit(from_number)
        if is_rate_limited:
            RATE_LIMIT_COUNT.inc()
            # Send rate limit message via Chat2Desk
            try:
                rate_limit_message = "Has enviado demasiados mensajes en un corto periodo de tiempo. Por favor, espera un momento antes de enviar más mensajes."
                
                api_token = os.getenv("CHAT2DESK_API_TOKEN")
                chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
                
                headers = {
                    "Authorization": api_token,
                    "Content-Type": "application/json"
                }
                
                message_data = {
                    "client_id": client_id,
                    "channel_id": channel_id,
                    "transport": "wa_direct",
                    "text": rate_limit_message
                }
                
                async with httpx.AsyncClient() as client:
                    await client.post(chat2desk_url, json=message_data, headers=headers)
                    
                return JSONResponse(content={"status": True, "message": "Rate limit applied"})
            except Exception as e:
                logger.error(f"Error sending rate limit message: {str(e)}")
                return JSONResponse(
                    content={"error": "Rate limit exceeded"},
                    status_code=429
                )
        
        # Optimized context creation and backup with proper locking
        async with context_lock:
            # Check if context exists first
            context_exists = from_number in enhanced_contexts
            if context_exists:
                # Create backup while holding lock to prevent race conditions
                context_backup = enhanced_contexts[from_number].backup()
                backup_store.store(from_number, context_backup)
            else:
                # Create new context while holding lock
                new_context = EnhancedContext(
                    original_context=None,
                    version=1,
                    token_count=count_tokens(body),
                    rate_limit_count=1,
                    rate_limit_start_time=datetime.now().timestamp()
                )
                enhanced_contexts[from_number] = new_context
                # Create initial backup
                backup_store.store(from_number, new_context.backup())
                
        # Process message through token limiter - now outside the lock
        body = await check_token_limit(from_number, body)
        
        # Update request data with modified text
        request_data['text'] = body
        # Create a new request with modified data - more efficient implementation
        async def receive():
            return {
                "type": "http.request",
                "body": json.dumps(request_data).encode('utf-8'),
                "more_body": False
            }
        modified_request = Request(
            scope=request.scope,
            receive=receive,
            send=request._send
        )
        # Process with original handler
        response = await original_whatsapp(modified_request)
        # After processing, check if we need to compress the conversation
        db = LocalStorage()
        await compress_conversation_if_needed(db, enhanced_contexts.get(from_number), from_number)
        
        # Record metrics
        processing_time = time.time() - start_time
        MESSAGE_PROCESSING_TIME.observe(processing_time)
        
        # Update token usage metrics
        if from_number in enhanced_contexts:
            TOKEN_USAGE.observe(enhanced_contexts[from_number].token_count)
        
        return response
        
    except Exception as e:
        # Attempt context recovery on error
        if from_number and from_number in enhanced_contexts:
            await recover_context(from_number)
            
        logger.error(f"Error in WhatsApp wrapper: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": "Internal server error", "details": str(e)},
            status_code=500
        )
    finally:
        # Only record processing time if not already recorded in the try block
        if start_time and from_number not in enhanced_contexts:
            processing_time = time.time() - start_time
            MESSAGE_PROCESSING_TIME.observe(processing_time)

# =======================================
# FastAPI Lifecycle
# =======================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager for the FastAPI application.
    Handles startup and shutdown of background tasks and resources.
    """
    # Initialize tasks list
    tasks = []
    try:
        # Initialize rate limiter
        await rate_limiter.initialize()
        
        # Initialize token batcher and process any existing batch
        await token_batcher.process_batch()
        
        # Start background tasks
        validation_task = asyncio.create_task(validate_all_contexts())
        cleanup_task = asyncio.create_task(cleanup_old_contexts())
        backup_cleanup_task = asyncio.create_task(backup_store.cleanup())
        token_batch_task = asyncio.create_task(periodic_batch_processing())
        
        tasks.extend([
            validation_task,
            cleanup_task,
            backup_cleanup_task,
            token_batch_task
        ])
        logger.info("WhatsApp wrapper started with enhanced context management")
        
        yield
        
    finally:
        # Cancel all background tasks
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            
        # Cleanup resources
        try:
            # Process any remaining tokens
            await token_batcher.process_batch()
            
            # Clear all contexts and ensure they're properly cleaned up
            for number in list(enhanced_contexts.keys()):
                try:
                    context = enhanced_contexts[number]
                    # Compress one final time if needed
                    db = LocalStorage()
                    await compress_conversation_if_needed(db, context, number)
                except Exception as e:
                    logger.error(f"Error during final compression for {number}: {str(e)}")
            
            # Clear all caches and contexts
            context_count = len(enhanced_contexts)
            enhanced_contexts.clear()
            get_cached_context.cache_clear()
            get_tokenizer.cache_clear()
            CLEANUP_OPERATIONS.labels(type='shutdown').inc(context_count)
            
            # Clear backup store
            backup_store.backups.clear()
            backup_store.timestamps.clear()
            
            # Close Redis connection if exists
            if hasattr(rate_limiter, 'redis') and rate_limiter.redis:
                try:
                    await rate_limiter.close()
                except Exception as e:
                    logger.error(f"Error closing Redis connection: {str(e)}")
            
            logger.info("WhatsApp wrapper cleanup completed successfully")
            
        except Exception as e:
            logger.error(f"Error during final cleanup: {str(e)}")
            
        finally:
            # Reset metrics
            CONTEXT_COUNT.set(0)
            logger.info("WhatsApp wrapper shutdown completed")

app = FastAPI(lifespan=lifespan)
# Include our router
app.include_router(router)

logger.info("WhatsApp Context Management Wrapper initialized with token tracking and recovery mechanisms")
# Implementation complete - WhatsApp wrapper with comprehensive token and context management
