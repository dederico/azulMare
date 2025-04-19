# app/util/rate_limiter.py
import asyncio
import time
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Implements a token bucket rate limiter for API requests.
    """
    def __init__(self, rate=5, max_tokens=10):
        """
        Initialize the rate limiter.
        
        Args:
            rate (float): Number of tokens refilled per second
            max_tokens (int): Maximum number of tokens in the bucket
        """
        self.rate = rate  # tokens per second
        self.max_tokens = max_tokens
        self.tokens = max_tokens  # start with a full bucket
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
        
    async def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.rate
        
        self.tokens = min(self.tokens + new_tokens, self.max_tokens)
        self.last_refill = now
        
    async def acquire(self, tokens=1, timeout=None):
        """
        Acquire tokens from the bucket or wait until they're available.
        
        Args:
            tokens (int): Number of tokens to acquire
            timeout (float, optional): Max time to wait in seconds
            
        Returns:
            bool: True if tokens were acquired, False if timed out
        """
        if tokens > self.max_tokens:
            logger.warning(f"Requested {tokens} tokens exceeds max capacity of {self.max_tokens}")
            return False
            
        start_time = time.time()
        
        async with self.lock:
            while self.tokens < tokens:
                await self._refill()
                
                # Check if we can acquire tokens now
                if self.tokens >= tokens:
                    break
                    
                # Check for timeout
                if timeout is not None:
                    if time.time() - start_time > timeout:
                        logger.warning(f"Rate limit timeout after waiting {timeout}s")
                        return False
                
                # Wait a bit before checking again
                refill_time = (tokens - self.tokens) / self.rate
                wait_time = min(refill_time, 1.0)  # Wait at most 1 second
                
                logger.debug(f"Waiting {wait_time:.2f}s for rate limit tokens to refill")
                await asyncio.sleep(wait_time)
            
            # Acquire tokens
            self.tokens -= tokens
            return True

class ImageProcessingQueue:
    """
    Queue for managing image processing tasks.
    """
    def __init__(self, max_concurrent=3, rate_limit_per_minute=30):
        """
        Initialize the image processing queue.
        
        Args:
            max_concurrent (int): Maximum number of concurrent processing tasks
            rate_limit_per_minute (int): Maximum requests to OpenAI per minute
        """
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rate_limiter = RateLimiter(rate=rate_limit_per_minute/60, max_tokens=max_concurrent)
        self.queue = []
        
    async def add_task(self, task_func, *args, **kwargs):
        """
        Add an image processing task to the queue.
        
        Args:
            task_func: Async function to execute
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            result: Result of the task function
        """
        # Wait for a semaphore slot to be available
        async with self.semaphore:
            # Wait for rate limiting
            await self.rate_limiter.acquire()
            
            # Execute the task
            start_time = time.time()
            logger.debug(f"Starting image processing task at {datetime.now().strftime('%H:%M:%S.%f')}")
            
            try:
                result = await task_func(*args, **kwargs)
                logger.debug(f"Image processing completed in {time.time() - start_time:.2f}s")
                return result
            except Exception as e:
                logger.error(f"Error in image processing task: {str(e)}")
                raise

# Create a global instance to be used across the application
image_processing_queue = ImageProcessingQueue(max_concurrent=3, rate_limit_per_minute=30)