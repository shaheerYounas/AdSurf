import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

def setup_logging():
    # Define the separate folder for logs
    # Moving up from apps/api/app/core to the root of the project, then /logs
    base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
    logs_dir = base_dir / "logs"
    
    # Ensure the logs directory exists
    os.makedirs(logs_dir, exist_ok=True)
    
    log_file = logs_dir / "app_activity.txt"
    
    # We want a detailed log every 5 minutes. 
    # TimedRotatingFileHandler rotates the log file.
    # when="M", interval=5 means every 5 minutes, it saves the current file and starts a new one 
    # with a timestamp suffix.
    handler = TimedRotatingFileHandler(
        filename=log_file,
        when="M",
        interval=5,
        backupCount=100,  # Keep up to 100 rotated log files
        encoding="utf-8"
    )
    
    # Create a detailed format
    formatter = logging.Formatter(
        fmt="[%(asctime)s.%(msecs)03d] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Prevent adding multiple handlers if setup_logging is called multiple times
    if not any(isinstance(h, TimedRotatingFileHandler) for h in root_logger.handlers):
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        
    logging.info("Application detailed logging initialized. Rotating every 5 minutes.")
