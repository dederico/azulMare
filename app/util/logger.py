import os
import logging
import colorlog
from io import StringIO
from threading import local
from dotenv import load_dotenv

load_dotenv()
thread_local = local()

console_handler = colorlog.StreamHandler()
console_formatter = colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

console_handler.setFormatter(console_formatter)
logger = colorlog.getLogger()
logger.addHandler(console_handler)
logger.setLevel(os.getenv('CONSOLE_LOG_LEVEL', 'DEBUG'))

if os.getenv('LOG_TO_FILE', '').lower() == 'true':
    log_file = os.getenv('LOG_FILE', 'log_file.log')
    file_handler = logging.FileHandler(log_file)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

file_log_level = os.getenv('LOG_FILE_LOG_LEVEL')
if file_log_level:
    file_handler.setLevel(file_log_level)

def get_thread_log_handler():
    if not hasattr(thread_local, 'log_stream'):
        thread_local.log_stream = StringIO()
        handler = logging.StreamHandler(thread_local.log_stream)
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        thread_local.handler = handler

    return thread_local.handler

def cleanup_call_logger():
    if hasattr(thread_local, 'handler'):
        logger.removeHandler(get_thread_log_handler())
        del thread_local.handler
        del thread_local.log_stream
