"""Configuration settings and utility functions"""
import logging
import os
import json
import re
from pathlib import Path
from uuid import uuid4

class CrunchyrollConfig:
    """Configuration settings for Crunchyroll API"""

    # API URLs
    AUTH_URL = 'https://beta-api.crunchyroll.com/auth/v1/token'
    PROFILE_URL = 'https://beta-api.crunchyroll.com/accounts/v1/me/profile'
    ACCOUNTS_URL = 'https://beta-api.crunchyroll.com/accounts/v1/me'
    DRM_AUTH_URL = 'https://beta-api.crunchyroll.com/drm/v1/auth'

    # Device details
    DEVICE_ID = "2b58e6c0-14df-4c62-85ed-ca0076af08ea"  # Can be randomized with str(uuid4())
    DEVICE_TYPE = 'Xiaomi Redmi Note 7'
    DEVICE_NAME = 'Redmi Note 7'

    # Headers
    #
    # This was inspired by https://github.com/anidl/multi-downloader-nx
    # https://github.com/anidl/multi-downloader-nx/commit/36cff8b4961256748ba8e5b9adeee3d9dfa883a2
    #
    # the android tv basic token, its whitelisted on every endpoint

    # AUTHORIZATION = 'Basic eHVuaWh2ZWRidDNtYmlzdWhldnQ6MWtJUzVkeVR2akUwX3JxYUEzWWVBaDBiVVhVbXhXMTE='

    AUTHORIZATION = 'Basic Ym1icmt4eXgzZDd1NmpzZnlsYTQ6QUlONEQ1VkVfY3Awd1Z6Zk5vUDBZcUhVcllGcDloU2c='
    USER_AGENT = 'Crunchyroll/3.81.8 Android/15 okhttp/4.12.0'
    USER_AGENT_PC = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'

    
    # License URL
    LICENSE_URL = 'https://cr-license-proxy.prd.crunchyrollsvc.com/v1/license/widevine'
    
    # Base config directory in user's home folder
    CONFIG_BASE = os.path.join(os.path.expanduser("~"), ".config", "crdl")
    
    # Default paths - use user's home directory with proper path joining for cross-platform compatibility
    DEFAULT_CONFIG_DIR = Path(CONFIG_BASE)
    DEFAULT_JSON_DIR = Path(os.path.join(CONFIG_BASE, "json"))
    DEFAULT_WIDEVINE_DIR = Path(os.path.join(CONFIG_BASE, "widevine"))
    DEFAULT_LOG_DIR = Path(os.path.join(CONFIG_BASE, "logs"))
    DEFAULT_OUTPUT_DIR = Path('downloads')  # Keep default downloads in current dir
    
    def __init__(self, config_dirs=None):
        """
        Initialize configuration with optional custom directories
        
        Args:
            config_dirs: Dictionary containing custom directory paths
        """
        if config_dirs:
            self.json_dir = config_dirs.get("json_dir", self.DEFAULT_JSON_DIR)
            self.widevine_dir = config_dirs.get("widevine_dir", self.DEFAULT_WIDEVINE_DIR)
            self.log_dir = config_dirs.get("logs_dir", self.DEFAULT_LOG_DIR)
            self.output_dir = config_dirs.get("output_dir", self.DEFAULT_OUTPUT_DIR)
        else:
            self.json_dir = self.DEFAULT_JSON_DIR
            self.widevine_dir = self.DEFAULT_WIDEVINE_DIR
            self.log_dir = self.DEFAULT_LOG_DIR
            self.output_dir = self.DEFAULT_OUTPUT_DIR
        
        # Create directories if they don't exist
        os.makedirs(self.json_dir, exist_ok=True)
        os.makedirs(self.widevine_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

def setup_logging(log_dir=None):
    """
    Set up logging configuration and return logger
    
    Args:
        log_dir: Optional custom log directory
        
    Returns:
        Logger: Configured logger instance
    """
    # Use provided log_dir or default
    if log_dir is None:
        log_dir = CrunchyrollConfig.DEFAULT_LOG_DIR
    
    # Create log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure logging with proper path joining
    log_file = os.path.join(log_dir, "crunchyroll_downloader.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger("CrunchyrollDownloader")
    
    return logger

def save_json(data, filename, directory=None):
    """
    Save JSON data to a file
    
    Args:
        data: Data to save
        filename: Name of the file
        directory: Directory to save the file (defaults to json/)
    """
    if directory is None:
        directory = CrunchyrollConfig.DEFAULT_JSON_DIR
    
    # Create directory if it doesn't exist
    os.makedirs(directory, exist_ok=True)
    
    filepath = directory / filename
    try:
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return filepath
    except Exception as e:
        logging.getLogger("CrunchyrollDownloader").error(f"Error saving JSON to {filepath}: {str(e)}")
        return None

def sanitize_filename(filename):
    """
    Remove problematic characters from a filename
    
    Args:
        filename: Original filename
        
    Returns:
        str: Sanitized filename
    """
    
    # Replace special characters
    sanitized = re.sub(r'[\\/*?:"<>|]', '-', filename)
    sanitized = sanitized.replace(' ', '.').replace(':', '').replace('/', '-')
    # Remove apostrophes and other problematic characters
    sanitized = sanitized.replace("'", "").replace("`", "")
    return sanitized 