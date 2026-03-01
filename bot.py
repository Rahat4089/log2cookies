#!/usr/bin/env python3
# bot.py - RUTE Cookie Extractor Bot (ULTRA-FAST WITH LIBARCHIVE)

import os
import sys
import re
import zipfile
import shutil
import hashlib
import time
import random
import string
import asyncio
import aiohttp
import aiofiles
import tempfile
from datetime import datetime
from typing import List, Set, Dict, Optional, Tuple, Any
import threading
import platform
import uuid
from pathlib import Path
import math
from concurrent.futures import ThreadPoolExecutor
import traceback
import logging
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass
from enum import Enum
import queue
from collections import deque
import html
import json
from urllib.parse import urlparse

# Pyrofork imports
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, MessageNotModified, RPCError, MessageIdInvalid
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.enums import ParseMode

# Third-party imports
try:
    from tqdm import tqdm
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)
except ImportError:
    os.system("pip install -q tqdm colorama")
    from tqdm import tqdm
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)

# Try to import libarchive
try:
    import libarchive
    import libarchive.public
    import libarchive.constants
    HAS_LIBARCHIVE = True
except ImportError:
    HAS_LIBARCHIVE = False
    try:
        os.system("pip install -q libarchive-c")
        import libarchive
        import libarchive.public
        import libarchive.constants
        HAS_LIBARCHIVE = True
    except:
        HAS_LIBARCHIVE = False

# Try to import psutil for stats
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    try:
        os.system("pip install -q psutil")
        import psutil
        HAS_PSUTIL = True
    except:
        HAS_PSUTIL = False

# ==============================================================================
#                            CONFIGURATION
# ==============================================================================

API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8640428737:AAHBUkPVT333xnDjLmiDTcRLzWJxXIHTKnU"
LOG_CHANNEL = -1003747061396
SEND_LOGS = False
ADMINS = [7125341830]

# ULTIMATE SPEED SETTINGS
MAX_WORKERS = 200
BUFFER_SIZE = 100 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024 * 60
DOWNLOAD_CHUNK_SIZE = 100 * 1024 * 1024
PROGRESS_UPDATE_INTERVAL = 3

# QUEUE SETTINGS
MAX_CONCURRENT_USERS = 10
MAX_USER_TASKS = 1
ACTIVE_TASK_TIMEOUT = 3600
QUEUE_TIMEOUT = 0

SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.cab', '.iso', '.lha', '.lzh'}
ARCHIVE_MAGIC = {
    b'PK\x03\x04': 'zip',
    b'PK\x05\x06': 'zip',
    b'PK\x07\x08': 'zip',
    b'Rar!\x1a\x07': 'rar',
    b'Rar!\x1a\x07\x00': 'rar',
    b'7z\xbc\xaf\x27\x1c': '7z',
    b'\x1f\x8b': 'gz',
    b'\x42\x5a\x68': 'bz2',
    b'\xfd\x37\x7a\x58\x5a\x00': 'xz',
    b'\x75\x73\x74\x61\x72': 'tar',
    b'\x75\x73\x74\x61\x72\x20': 'tar',
    b'MSCF': 'cab',
    b'CD001': 'iso',
    b'-lh': 'lha',
    b'-lz': 'lzh',
}

# Content-Type mapping
CONTENT_TYPE_MAP = {
    'application/zip': '.zip',
    'application/x-zip-compressed': '.zip',
    'application/vnd.rar': '.rar',
    'application/x-rar-compressed': '.rar',
    'application/x-7z-compressed': '.7z',
    'application/gzip': '.gz',
    'application/x-gzip': '.gz',
    'application/x-bzip2': '.bz2',
    'application/x-xz': '.xz',
    'application/x-tar': '.tar',
    'application/vnd.ms-cab-compressed': '.cab',
    'application/x-iso9660-image': '.iso',
    'application/x-lha': '.lha',
    'application/x-lzh': '.lzh',
}

# Folders to scan for data
TARGET_FOLDERS = {
    'cookies': {'cookies', 'cookie', 'cookiess', 'cookies_', 'cookies-', 'cookies data'},
    'credit_cards': {'credit cards', 'creditcards', 'cc', 'cards', 'card', 'credit', 'autofill', 'payment'}
}

# Files to always scan
ALWAYS_SCAN_EXTENSIONS = {'.txt', '.log', '.csv', '.data', '.bak', '.old'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file max

# Credit card patterns (pre-compiled for speed)
CC_PATTERN_WITH_NAME = re.compile(r'(.+?)\s*\|\s*(\d{16})\s*\|\s*(\d{1,2}/\d{4})\s*\|\s*(\d{3,4})')
CC_PATTERN_NO_NAME = re.compile(r'(\d{16})\s*\|\s*(\d{1,2}/\d{4})\s*\|\s*(\d{3,4})')

# Cookie patterns (simple domain matching)
COOKIE_DOMAIN_PATTERN = re.compile(r'\.([a-zA-Z0-9-]+\.[a-zA-Z]{2,})')

# Detect system
SYSTEM = platform.system().lower()

# Create required directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

for directory in [DOWNLOADS_DIR, LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            os.path.join(LOGS_DIR, 'bot.log'),
            maxBytes=10*1024*1024,
            backupCount=5
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global start time
BOT_START_TIME = time.time()

# ==============================================================================
#                            FILE TYPE DETECTION
# ==============================================================================

async def detect_file_type_from_url(url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Detect file type from URL using HEAD request"""
    try:
        timeout = aiohttp.ClientTimeout(total=10, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.head(url, allow_redirects=True) as response:
                content_type = response.headers.get('Content-Type', '').lower()
                content_disposition = response.headers.get('Content-Disposition', '')
                
                # Extract filename from Content-Disposition
                filename = None
                if content_disposition:
                    filename_match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', content_disposition, re.IGNORECASE)
                    if filename_match:
                        filename = filename_match.group(1).strip('"\'')
                
                # Determine extension from content-type
                extension = None
                if content_type:
                    for ct, ext in CONTENT_TYPE_MAP.items():
                        if ct in content_type:
                            extension = ext
                            break
                
                # If no extension from content-type, try from filename
                if not extension and filename:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in SUPPORTED_ARCHIVES:
                        extension = ext
                
                # If still no extension, try from URL
                if not extension:
                    parsed = urlparse(url)
                    path = parsed.path.lower()
                    for ext in SUPPORTED_ARCHIVES:
                        if path.endswith(ext):
                            extension = ext
                            break
                
                return extension, filename, content_type
                
    except Exception as e:
        logger.error(f"Error detecting file type from URL: {e}")
        return None, None, None

def detect_file_type_from_content(file_path: str) -> Optional[str]:
    """Detect file type by reading magic bytes"""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(1024)
        
        # Check against known signatures
        for signature, file_type in ARCHIVE_MAGIC.items():
            if header.startswith(signature):
                return file_type
        
        # Check for tar variants
        if header[257:262] in [b'ustar', b'ustar\x00']:
            return 'tar'
        
        return None
    except Exception as e:
        logger.error(f"Error detecting file type: {e}")
        return None

def get_extension_from_type(file_type: str) -> str:
    """Convert file type to extension"""
    if not file_type:
        return '.zip'
    if file_type.startswith('.'):
        return file_type
    return f'.{file_type}'

# ==============================================================================
#                            ENUMS & DATACLASSES
# ==============================================================================

class TaskStage(Enum):
    INIT = "init"
    AWAITING_OPTIONS = "awaiting_options"
    AWAITING_DOMAINS = "awaiting_domains"
    AWAITING_PASSWORD = "awaiting_password"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"

class SourceType(Enum):
    TELEGRAM = "telegram"
    URL = "url"

class ExtractionType(Enum):
    COOKIES = "cookies"
    CREDIT_CARDS = "credit_cards"
    BOTH = "both"

@dataclass
class ExtractedData:
    """Container for all extracted data in one pass"""
    cookies: Dict[str, List[str]]  # domain -> list of cookie lines
    credit_cards: List[str]  # list of formatted credit cards
    files_processed: int = 0
    total_entries: int = 0
    
    def __post_init__(self):
        if self.cookies is None:
            self.cookies = {}
        if self.credit_cards is None:
            self.credit_cards = []
        self.seen_cards = set()
        self.seen_cookie_entries = set()
        self.lock = threading.Lock()
    
    def add_cookie(self, domain: str, line: str):
        """Add a cookie entry with deduplication"""
        with self.lock:
            if domain not in self.cookies:
                self.cookies[domain] = []
            
            # Simple deduplication using hash
            entry_hash = hashlib.md5(f"{domain}:{line}".encode()).hexdigest()
            if entry_hash not in self.seen_cookie_entries:
                self.seen_cookie_entries.add(entry_hash)
                self.cookies[domain].append(line)
                self.total_entries += 1
    
    def add_credit_card(self, card_str: str):
        """Add a credit card with deduplication"""
        with self.lock:
            # Extract card number for deduplication
            card_num = card_str.split('|')[0]
            if card_num not in self.seen_cards:
                self.seen_cards.add(card_num)
                self.credit_cards.append(card_str)
                self.total_entries += 1

@dataclass
class TaskData:
    """Task data structure"""
    task_id: str
    user_id: int
    chat_id: int
    message_id: int
    source_type: SourceType
    source_data: Any
    extraction_type: ExtractionType = ExtractionType.BOTH  # Default to both
    domains: List[str] = None
    password: Optional[str] = None
    stage: TaskStage = TaskStage.INIT
    created_at: float = None
    queued_at: float = None
    started_at: float = None
    completed_at: float = None
    error: Optional[str] = None
    paths: Dict[str, str] = None
    stats: Dict[str, Any] = None
    bot: Any = None
    status_message_id: int = None
    file_name: str = None
    file_size: int = 0
    forwarded: bool = False
    forwarded_message_id: int = None
    detected_type: str = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.paths is None:
            self.paths = {}
        if self.stats is None:
            self.stats = {
                'files_processed': 0,
                'total_entries': 0,
                'archives_extracted': 0,
                'zips_created': 0,
                'download_size': 0,
                'extracted_size': 0,
                'credit_cards_found': 0,
                'cookies_found': 0
            }
    
    def get_user_folder(self) -> str:
        """Get user-specific folder path"""
        return os.path.join(DOWNLOADS_DIR, str(self.user_id))
    
    def get_download_path(self) -> str:
        """Get download path for this task"""
        user_folder = self.get_user_folder()
        os.makedirs(user_folder, exist_ok=True)
        return os.path.join(user_folder, f"{self.task_id}_{self.file_name}")
    
    def get_extract_path(self) -> str:
        """Get extract path for this task"""
        user_folder = self.get_user_folder()
        return os.path.join(user_folder, f"extracted_{self.task_id}")
    
    def get_results_path(self) -> str:
        """Get results path for this task"""
        user_folder = self.get_user_folder()
        return os.path.join(user_folder, f"results_{self.task_id}")

# ==============================================================================
#                            LIBARCHIVE EXTRACTOR
# ==============================================================================

class LibArchiveExtractor:
    """Universal extractor using libarchive"""
    
    def __init__(self, password: str = None, task_id: str = None):
        self.password = password
        self.task_id = task_id
        self.stop_processing = False
        self.has_libarchive = HAS_LIBARCHIVE
        
        if not self.has_libarchive:
            logger.error("libarchive-c not available! Using fallback extraction.")
    
    async def extract_archive(self, archive_path: str, extract_to: str) -> bool:
        """Extract any archive using libarchive"""
        if not self.has_libarchive:
            return await self._fallback_extract(archive_path, extract_to)
        
        try:
            # Use libarchive for extraction
            def extract_with_libarchive():
                try:
                    with libarchive.public.file_reader(archive_path) as archive:
                        for entry in archive:
                            if self.stop_processing:
                                return False
                            
                            # Skip directories, they'll be created automatically
                            if entry.isdir:
                                continue
                            
                            # Build output path
                            out_path = os.path.join(extract_to, entry.pathname)
                            os.makedirs(os.path.dirname(out_path), exist_ok=True)
                            
                            # Extract file
                            with open(out_path, 'wb') as f:
                                for block in entry.get_blocks():
                                    f.write(block)
                    return True
                except Exception as e:
                    logger.error(f"Libarchive extraction error: {e}")
                    return False
            
            return await asyncio.to_thread(extract_with_libarchive)
            
        except Exception as e:
            logger.error(f"Libarchive error: {e}")
            return await self._fallback_extract(archive_path, extract_to)
    
    async def _fallback_extract(self, archive_path: str, extract_to: str) -> bool:
        """Fallback extraction for unsupported formats"""
        ext = os.path.splitext(archive_path)[1].lower()
        
        # Try Python's built-in modules as fallback
        try:
            if ext == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    if self.password:
                        zf.setpassword(self.password.encode())
                    await asyncio.to_thread(zf.extractall, extract_to)
                return True
            
            elif ext in ['.tar', '.gz', '.bz2', '.xz']:
                import tarfile
                mode = 'r'
                if ext == '.gz':
                    mode = 'r:gz'
                elif ext == '.bz2':
                    mode = 'r:bz2'
                elif ext == '.xz':
                    mode = 'r:xz'
                
                with tarfile.open(archive_path, mode) as tar:
                    await asyncio.to_thread(tar.extractall, extract_to)
                return True
            
            else:
                logger.error(f"No fallback for {ext}")
                return False
                
        except Exception as e:
            logger.error(f"Fallback extraction error: {e}")
            return False
    
    async def find_archives(self, directory: str) -> List[str]:
        """Find all archives in directory recursively"""
        archives = []
        
        def scan():
            local_archives = []
            for root, _, files in os.walk(directory):
                for file in files:
                    # Check by extension
                    ext = os.path.splitext(file)[1].lower()
                    if ext in SUPPORTED_ARCHIVES:
                        local_archives.append(os.path.join(root, file))
                    else:
                        # Check by magic bytes
                        file_path = os.path.join(root, file)
                        try:
                            if detect_file_type_from_content(file_path):
                                local_archives.append(file_path)
                        except:
                            pass
            return local_archives
        
        return await asyncio.to_thread(scan)
    
    async def extract_all_nested(self, archive_path: str, extract_dir: str, progress_callback=None) -> Tuple[str, int]:
        """Extract all nested archives recursively"""
        # First extraction
        success = await self.extract_archive(archive_path, extract_dir)
        if not success:
            raise Exception("Archive extraction failed - wrong password or corrupted file")
        
        extracted_count = 1
        
        if progress_callback:
            await progress_callback(f"📦 Extracted main archive")
        
        # Find and extract nested archives
        iteration = 1
        while True:
            if self.stop_processing:
                break
            
            archives = await self.find_archives(extract_dir)
            if not archives:
                break
            
            if progress_callback:
                await progress_callback(f"📦 Found {len(archives)} nested archives...")
            
            new_extractions = 0
            
            for arc_path in archives:
                if self.stop_processing:
                    break
                
                # Extract to same directory (flatten)
                try:
                    success = await self.extract_archive(arc_path, extract_dir)
                    if success:
                        new_extractions += 1
                        extracted_count += 1
                        
                        # Remove archive after extraction
                        try:
                            os.remove(arc_path)
                        except:
                            pass
                except Exception as e:
                    logger.error(f"Failed to extract nested {arc_path}: {e}")
            
            if new_extractions == 0:
                break
            
            iteration += 1
        
        if progress_callback:
            await progress_callback(f"✅ Extraction complete! {extracted_count} archives processed")
        
        return extract_dir, extracted_count

# ==============================================================================
#                            COOKIE & CREDIT CARD EXTRACTOR (SINGLE PASS)
# ==============================================================================

class DataExtractor:
    """Extract both cookies and credit cards in a single pass"""
    
    def __init__(self, target_domains: List[str] = None):
        self.target_domains = [d.strip().lower() for d in target_domains] if target_domains else []
        self.stop_processing = False
        self.extracted_data = ExtractedData()
        
        # Pre-compile domain patterns for speed
        self.domain_patterns = {}
        if self.target_domains:
            for domain in self.target_domains:
                escaped = re.escape(domain).replace(r'\*', '.*')
                self.domain_patterns[domain] = re.compile(escaped.encode() if isinstance(escaped, str) else escaped)
    
    def should_process_file(self, file_path: str) -> bool:
        """Check if file should be processed"""
        # Check file size first (fast check)
        try:
            size = os.path.getsize(file_path)
            if size > MAX_FILE_SIZE or size == 0:
                return False
        except:
            return False
        
        # Check extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ALWAYS_SCAN_EXTENSIONS:
            return False
        
        # Check if in relevant folders (fast path)
        path_lower = file_path.lower()
        for category, folders in TARGET_FOLDERS.items():
            for folder in folders:
                if folder in path_lower:
                    return True
        
        # Always scan small files for credit cards
        if size < 1024 * 1024:  # Under 1MB
            return True
        
        return False
    
    def process_file_content(self, content: str, file_path: str):
        """Process file content for both cookies and credit cards"""
        content_bytes = content.encode('utf-8', errors='ignore')
        content_lower = content.lower()
        
        # 1. Extract credit cards (fast regex)
        for match in CC_PATTERN_WITH_NAME.finditer(content):
            name, card, expiry, cvv = match.groups()
            if self._validate_card(card, expiry):
                formatted = f"{card}|{expiry}|{cvv}|{name.strip()}"
                self.extracted_data.add_credit_card(formatted)
        
        for match in CC_PATTERN_NO_NAME.finditer(content):
            card, expiry, cvv = match.groups()
            if self._validate_card(card, expiry):
                formatted = f"{card}|{expiry}|{cvv}"
                self.extracted_data.add_credit_card(formatted)
        
        # 2. Extract cookies if domains specified
        if self.target_domains:
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                line_lower = line.lower()
                for domain in self.target_domains:
                    if domain in line_lower:
                        # Try to extract domain from line
                        cookie_domain = self._extract_domain(line)
                        if cookie_domain and any(d in cookie_domain for d in self.target_domains):
                            self.extracted_data.add_cookie(cookie_domain, line)
                        else:
                            # Just use the target domain
                            self.extracted_data.add_cookie(domain, line)
    
    def _validate_card(self, card: str, expiry: str) -> bool:
        """Quick card validation"""
        try:
            month, year = expiry.split('/')
            year_int = int(year)
            return 2020 <= year_int <= 2035 and len(card) == 16 and card.isdigit()
        except:
            return False
    
    def _extract_domain(self, line: str) -> Optional[str]:
        """Extract domain from cookie line"""
        # Simple domain extraction from common cookie formats
        match = COOKIE_DOMAIN_PATTERN.search(line)
        if match:
            return match.group(1)
        
        # Look for domain-like patterns
        parts = re.findall(r'[a-zA-Z0-9-]+\.[a-zA-Z]{2,}', line)
        return parts[0] if parts else None
    
    async def process_file(self, file_path: str) -> bool:
        """Process a single file"""
        if self.stop_processing:
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            self.process_file_content(content, file_path)
            self.extracted_data.files_processed += 1
            return True
            
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return False
    
    def find_files_to_scan(self, extract_dir: str) -> List[str]:
        """Find all files that should be scanned"""
        files_to_scan = []
        
        def scan_worker(start_dir):
            local_files = []
            try:
                for root, _, files in os.walk(start_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if self.should_process_file(file_path):
                            local_files.append(file_path)
            except Exception as e:
                logger.error(f"Scan error: {e}")
            return local_files
        
        return scan_worker(extract_dir)
    
    async def process_all(self, extract_dir: str, progress_callback=None) -> ExtractedData:
        """Process all files in a single pass"""
        if progress_callback:
            await progress_callback("🔍 Scanning for files to process...")
        
        # Find all files in thread pool
        files_to_scan = await asyncio.to_thread(self.find_files_to_scan, extract_dir)
        
        if not files_to_scan:
            if progress_callback:
                await progress_callback("❌ No processable files found!")
            return self.extracted_data
        
        if progress_callback:
            await progress_callback(f"📄 Found {len(files_to_scan)} files to scan")
        
        processed = 0
        total = len(files_to_scan)
        
        # Process in batches
        batch_size = 20
        for i in range(0, total, batch_size):
            if self.stop_processing:
                break
            
            batch = files_to_scan[i:i+batch_size]
            
            # Process batch in thread pool
            def process_batch():
                for file_path in batch:
                    if self.stop_processing:
                        break
                    asyncio.run(self.process_file(file_path))
            
            await asyncio.to_thread(process_batch)
            
            processed += len(batch)
            
            if progress_callback and processed % 10 == 0:
                progress_text = f"🔍 Scanning files...\n"
                progress_text += f"📊 Files: {processed}/{total}\n"
                
                if self.extracted_data.cookies:
                    progress_text += f"🍪 Cookies: {sum(len(v) for v in self.extracted_data.cookies.values())}\n"
                if self.extracted_data.credit_cards:
                    progress_text += f"💳 Cards: {len(self.extracted_data.credit_cards)}\n"
                
                await progress_callback(progress_text)
        
        if progress_callback:
            await progress_callback(f"✅ Scan complete! Found {self.extracted_data.total_entries} total entries")
        
        return self.extracted_data
    
    def create_result_files(self, result_folder: str) -> Dict[str, str]:
        """Create all result files (cookies per domain + credit cards)"""
        created_files = {}
        
        # Create cookie files per domain
        for domain, lines in self.extracted_data.cookies.items():
            if not lines:
                continue
            
            # Sanitize domain for filename
            safe_domain = re.sub(r'[^\w\-.]', '_', domain)
            timestamp = datetime.now().strftime('%H%M%S')
            file_name = f"{safe_domain}_{timestamp}.txt"
            file_path = os.path.join(result_folder, file_name)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            created_files[domain] = file_path
        
        # Create credit card file
        if self.extracted_data.credit_cards:
            timestamp = datetime.now().strftime('%H%M%S')
            file_name = f"credit_cards_{timestamp}.txt"
            file_path = os.path.join(result_folder, file_name)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.extracted_data.credit_cards))
            
            created_files['credit_cards'] = file_path
        
        return created_files

# ==============================================================================
#                            DOWNLOAD MANAGER
# ==============================================================================

class DownloadManager:
    """Handle file downloads with progress"""
    
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.stop_download = False
    
    async def download_file(self, url: str, file_path: str, progress_callback=None) -> Tuple[bool, Optional[str]]:
        """Download file from URL with progress"""
        try:
            timeout = aiohttp.ClientTimeout(total=3600, connect=30)
            connector = aiohttp.TCPConnector(limit=100)
            
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status != 200:
                        return False, f"HTTP {resp.status}"
                    
                    total_size = int(resp.headers.get('content-length', 0))
                    downloaded = 0
                    start_time = time.time()
                    
                    if progress_callback:
                        await progress_callback(f"📥 Downloading... 0%")
                    
                    # Download to temporary file first
                    temp_path = file_path + ".tmp"
                    
                    async with aiofiles.open(temp_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(DOWNLOAD_CHUNK_SIZE):
                            if self.stop_download:
                                return False, "Cancelled"
                            
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            if progress_callback and total_size > 0:
                                percentage = (downloaded / total_size) * 100
                                elapsed = time.time() - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                eta = (total_size - downloaded) / speed if speed > 0 else 0
                                
                                text = f"📥 Downloading... {percentage:.1f}%\n"
                                text += f"📦 {format_size(downloaded)} / {format_size(total_size)}\n"
                                text += f"⚡ {format_size(speed)}/s\n"
                                text += f"⏱️ ETA: {format_time(eta)}"
                                await progress_callback(text)
                    
                    # Detect file type from content
                    file_type = await asyncio.to_thread(detect_file_type_from_content, temp_path)
                    
                    if file_type:
                        new_file_path = os.path.splitext(file_path)[0] + get_extension_from_type(file_type)
                        os.rename(temp_path, new_file_path)
                        file_path = new_file_path
                    else:
                        os.rename(temp_path, file_path)
                    
                    if progress_callback:
                        await progress_callback(f"✅ Download complete!")
                    
                    return True, file_path
                    
        except asyncio.TimeoutError:
            return False, "Connection timeout"
        except aiohttp.ClientError as e:
            return False, f"Network error: {str(e)}"
        except Exception as e:
            return False, str(e)
    
    async def download_from_telegram(self, message: Message, file_path: str, progress_callback=None) -> Tuple[bool, Optional[str]]:
        """Download file from Telegram with progress"""
        try:
            if progress_callback:
                await progress_callback(f"📥 Downloading from Telegram... 0%")
            
            start_time = time.time()
            
            async def progress(current, total):
                if self.stop_download:
                    raise Exception("Download cancelled")
                
                if progress_callback:
                    percentage = (current / total) * 100
                    elapsed = time.time() - start_time
                    speed = current / elapsed if elapsed > 0 else 0
                    eta = (total - current) / speed if speed > 0 else 0
                    
                    text = f"📥 Downloading from Telegram... {percentage:.1f}%\n"
                    text += f"📦 {format_size(current)} / {format_size(total)}\n"
                    text += f"⚡ {format_size(speed)}/s\n"
                    text += f"⏱️ ETA: {format_time(eta)}"
                    await progress_callback(text)
            
            # Download to temporary file first
            temp_path = file_path + ".tmp"
            
            # Download in thread pool
            if message.document:
                await asyncio.to_thread(
                    lambda: message.download(temp_path, progress=progress)
                )
            elif message.photo:
                await asyncio.to_thread(
                    lambda: message.photo.download(temp_path, progress=progress)
                )
            else:
                return False, "Unsupported media type"
            
            # Detect file type from content
            file_type = await asyncio.to_thread(detect_file_type_from_content, temp_path)
            
            if file_type:
                new_file_path = os.path.splitext(file_path)[0] + get_extension_from_type(file_type)
                os.rename(temp_path, new_file_path)
                file_path = new_file_path
            else:
                os.rename(temp_path, file_path)
            
            if progress_callback:
                await progress_callback(f"✅ Download complete!")
            
            return True, file_path
            
        except Exception as e:
            return False, str(e)

# ==============================================================================
#                            QUEUE MANAGER
# ==============================================================================

class QueueManager:
    """Manage user and global queues"""
    
    def __init__(self, max_concurrent: int = MAX_CONCURRENT_USERS):
        self.max_concurrent = max_concurrent
        self.queue = asyncio.Queue()
        self.active_tasks: Dict[int, TaskData] = {}
        self.processing = False
        self.lock = asyncio.Lock()
        self._processor_task = None
        self._timeout_check_task = None
    
    async def start(self):
        """Start queue processor"""
        self.processing = True
        self._processor_task = asyncio.create_task(self._process_queue())
        self._timeout_check_task = asyncio.create_task(self._check_timeouts())
        logger.info("Queue processor started")
    
    async def stop(self):
        """Stop queue processor"""
        self.processing = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        if self._timeout_check_task:
            self._timeout_check_task.cancel()
            try:
                await self._timeout_check_task
            except asyncio.CancelledError:
                pass
        logger.info("Queue processor stopped")
    
    async def add_to_queue(self, task: TaskData) -> Tuple[int, str]:
        """Add task to queue"""
        async with self.lock:
            if task.user_id in self.active_tasks:
                raise Exception("You already have an active task")
            
            task.stage = TaskStage.QUEUED
            task.queued_at = time.time()
            
            await self.queue.put(task)
            
            position = self.queue.qsize()
            
            if position <= self.max_concurrent - len(self.active_tasks):
                estimated_time = 0
            else:
                tasks_ahead = position - (self.max_concurrent - len(self.active_tasks))
                estimated_time = tasks_ahead * 300
            
            # Trigger processing if slots available
            if len(self.active_tasks) < self.max_concurrent:
                asyncio.create_task(self._process_next_task())
            
            return position, self._format_eta(estimated_time)
    
    async def _process_next_task(self):
        """Process the next task in queue"""
        async with self.lock:
            if len(self.active_tasks) >= self.max_concurrent:
                return
            
            if self.queue.empty():
                return
            
            try:
                task = self.queue.get_nowait()
                
                if task.stage == TaskStage.CANCELLED:
                    return
                
                self.active_tasks[task.user_id] = task
                task.started_at = time.time()
                
                logger.info(f"Task {task.task_id} started processing")
                
                # Process in background
                asyncio.create_task(task.bot.process_task(task))
                
            except asyncio.QueueEmpty:
                pass
            except Exception as e:
                logger.error(f"Error processing next task: {e}")
    
    async def _process_queue(self):
        """Process queue continuously"""
        while self.processing:
            try:
                if len(self.active_tasks) < self.max_concurrent:
                    await self._process_next_task()
                
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue processor error: {e}")
                await asyncio.sleep(2)
    
    async def _check_timeouts(self):
        """Check for timed out active tasks"""
        while self.processing:
            try:
                await asyncio.sleep(30)
                
                async with self.lock:
                    current_time = time.time()
                    timed_out_tasks = []
                    
                    for user_id, task in list(self.active_tasks.items()):
                        if task.started_at and (current_time - task.started_at) > ACTIVE_TASK_TIMEOUT:
                            timed_out_tasks.append((user_id, task))
                    
                    for user_id, task in timed_out_tasks:
                        logger.warning(f"Task {task.task_id} timed out")
                        del self.active_tasks[user_id]
                        
                        task.stage = TaskStage.FAILED
                        task.error = "Task timeout"
                        
                        try:
                            await task.bot.app.send_message(
                                task.chat_id,
                                f"⏰ <b>Task Timeout</b>\n\n"
                                f"Your task was cancelled after {ACTIVE_TASK_TIMEOUT//60} minutes."
                            )
                            await self._cleanup_user_folder(task.user_id)
                        except:
                            pass
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Timeout check error: {e}")
    
    async def remove_task(self, user_id: int):
        """Remove task from active tasks"""
        async with self.lock:
            if user_id in self.active_tasks:
                task = self.active_tasks[user_id]
                del self.active_tasks[user_id]
                await self._cleanup_user_folder(user_id)
    
    async def _cleanup_user_folder(self, user_id: int):
        """Clean up user's folder"""
        try:
            user_folder = os.path.join(DOWNLOADS_DIR, str(user_id))
            if os.path.exists(user_folder):
                await asyncio.to_thread(shutil.rmtree, user_folder, ignore_errors=True)
        except Exception as e:
            logger.error(f"Error cleaning up user folder {user_id}: {e}")
    
    def get_queue_position(self, user_id: int) -> Optional[int]:
        """Get user's queue position"""
        try:
            position = 1
            for task in list(self.queue._queue):
                if task.user_id == user_id:
                    return position
                position += 1
            return None
        except:
            return None
    
    def get_active_count(self) -> int:
        """Get number of active tasks"""
        return len(self.active_tasks)
    
    def get_queue_count(self) -> int:
        """Get number of queued tasks"""
        return self.queue.qsize()
    
    def _format_eta(self, seconds: int) -> str:
        """Format ETA"""
        if seconds <= 0:
            return "immediately"
        elif seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds//60}m {seconds%60}s"
        else:
            return f"{seconds//3600}h {(seconds%3600)//60}m"

# ==============================================================================
#                            ERROR HANDLER
# ==============================================================================

class ErrorHandler:
    """Comprehensive error handler"""
    
    @staticmethod
    async def handle_error(error: Exception, context: Dict[str, Any] = None) -> str:
        """Handle error and return user-friendly message"""
        
        logger.error(f"Error: {error}", exc_info=True)
        if context:
            logger.error(f"Context: {context}")
        
        if isinstance(error, FloodWait):
            wait_time = error.value
            return f"⚠️ Telegram rate limit. Please wait {wait_time} seconds."
        
        elif isinstance(error, MessageNotModified):
            return None
        
        elif isinstance(error, MessageIdInvalid):
            return "⚠️ Message expired. Please start over."
        
        elif isinstance(error, RPCError):
            return f"❌ Telegram API error: {str(error)}"
        
        elif isinstance(error, asyncio.TimeoutError):
            return "⏰ Operation timed out. Please try again."
        
        elif isinstance(error, ConnectionError):
            return "🌐 Network connection error. Please check your internet."
        
        elif "password" in str(error).lower() or "Wrong password" in str(error).lower():
            return "🔑 Wrong password or archive is password protected."
        
        elif "disk" in str(error).lower() or "space" in str(error).lower():
            return "💿 Insufficient disk space. Free up space and try again."
        
        else:
            return f"❌ Unexpected error: {str(error)}"

# ==============================================================================
#                            UTILITY FUNCTIONS
# ==============================================================================

def sanitize_filename(filename: str) -> str:
    """Quick sanitize for filenames"""
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)

def generate_random_string(length: int = 6) -> str:
    """Generate random string"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def format_size(size_bytes: int) -> str:
    """Quick size formatting"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"

def format_time(seconds: float) -> str:
    """Format seconds to human readable"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"

def create_progress_bar(percentage: float, width: int = 10) -> str:
    """Create a text progress bar"""
    filled = int(width * percentage / 100)
    return '█' * filled + '░' * (width - filled)

def escape_html(text: str) -> str:
    """Escape HTML special characters"""
    return html.escape(str(text))

async def delete_user_folder(user_id: int) -> bool:
    """Delete user's entire folder"""
    user_folder = os.path.join(DOWNLOADS_DIR, str(user_id))
    if not os.path.exists(user_folder):
        return True
    
    try:
        await asyncio.to_thread(shutil.rmtree, user_folder, ignore_errors=True)
        return True
    except Exception as e:
        logger.error(f"Error deleting user folder {user_folder}: {e}")
        return False

# ==============================================================================
#                            STATS COLLECTOR
# ==============================================================================

class StatsCollector:
    """Collect bot and server statistics"""
    
    @staticmethod
    def get_server_stats() -> Dict[str, Any]:
        """Get server statistics"""
        stats = {
            'system': platform.system(),
            'release': platform.release(),
            'python_version': platform.python_version(),
            'hostname': platform.node(),
            'architecture': platform.machine(),
            'libarchive': '✅' if HAS_LIBARCHIVE else '❌'
        }
        
        try:
            if HAS_PSUTIL:
                stats['cpu_percent'] = psutil.cpu_percent(interval=1)
                stats['cpu_count'] = psutil.cpu_count()
                
                mem = psutil.virtual_memory()
                stats['memory_total'] = mem.total
                stats['memory_available'] = mem.available
                stats['memory_used'] = mem.used
                stats['memory_percent'] = mem.percent
                
                disk = psutil.disk_usage('/')
                stats['disk_total'] = disk.total
                stats['disk_used'] = disk.used
                stats['disk_free'] = disk.free
                stats['disk_percent'] = disk.percent
                
                process = psutil.Process()
                stats['process_memory'] = process.memory_info().rss
                stats['process_threads'] = process.num_threads()
            
        except Exception as e:
            logger.error(f"Error getting server stats: {e}")
        
        return stats
    
    @staticmethod
    def get_bot_stats(task_manager, queue_manager) -> Dict[str, Any]:
        """Get bot statistics"""
        stats = {
            'total_tasks': len(task_manager.tasks),
            'active_tasks': queue_manager.get_active_count(),
            'queued_tasks': queue_manager.get_queue_count(),
            'max_concurrent': MAX_CONCURRENT_USERS,
            'libarchive': '✅' if HAS_LIBARCHIVE else '❌',
            'uptime': time.time() - BOT_START_TIME,
            'workers': MAX_WORKERS
        }
        
        # Count tasks by stage
        completed_count = 0
        failed_count = 0
        total_cookies = 0
        total_cc = 0
        
        for task in task_manager.tasks.values():
            if task.stage == TaskStage.COMPLETE:
                completed_count += 1
            elif task.stage == TaskStage.FAILED:
                failed_count += 1
            
            if task.stats:
                total_cookies += task.stats.get('cookies_found', 0)
                total_cc += task.stats.get('credit_cards_found', 0)
        
        stats['completed_tasks'] = completed_count
        stats['failed_tasks'] = failed_count
        stats['total_cookies'] = total_cookies
        stats['total_credit_cards'] = total_cc
        
        return stats
    
    @staticmethod
    def format_bytes(bytes_num: int) -> str:
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_num < 1024.0:
                return f"{bytes_num:.2f} {unit}"
            bytes_num /= 1024.0
        return f"{bytes_num:.2f} PB"
    
    @staticmethod
    def format_time(seconds: float) -> str:
        """Format seconds to human readable"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        else:
            return f"{seconds/3600:.1f}h"

# ==============================================================================
#                            TASK MANAGER
# ==============================================================================

class TaskManager:
    """Manage tasks"""
    
    def __init__(self):
        self.tasks: Dict[str, TaskData] = {}
        self.user_tasks: Dict[int, str] = {}
        self.lock = asyncio.Lock()
    
    async def create_task(self, task_data: TaskData) -> str:
        """Create new task"""
        async with self.lock:
            if task_data.user_id in self.user_tasks:
                old_task_id = self.user_tasks[task_data.user_id]
                if old_task_id in self.tasks:
                    task = self.tasks[old_task_id]
                    if task.stage not in [TaskStage.COMPLETE, TaskStage.CANCELLED, TaskStage.FAILED]:
                        raise Exception("You already have an active task")
            
            self.tasks[task_data.task_id] = task_data
            self.user_tasks[task_data.user_id] = task_data.task_id
            return task_data.task_id
    
    async def get_task(self, task_id: str) -> Optional[TaskData]:
        """Get task by ID"""
        async with self.lock:
            return self.tasks.get(task_id)
    
    async def get_user_task(self, user_id: int) -> Optional[TaskData]:
        """Get user's current task"""
        async with self.lock:
            task_id = self.user_tasks.get(user_id)
            if task_id:
                return self.tasks.get(task_id)
            return None
    
    async def update_task(self, task_id: str, **kwargs):
        """Update task fields"""
        async with self.lock:
            if task_id in self.tasks:
                for key, value in kwargs.items():
                    if hasattr(self.tasks[task_id], key):
                        setattr(self.tasks[task_id], key, value)
    
    async def remove_task(self, task_id: str):
        """Remove task"""
        async with self.lock:
            if task_id in self.tasks:
                user_id = self.tasks[task_id].user_id
                if user_id in self.user_tasks and self.user_tasks[user_id] == task_id:
                    del self.user_tasks[user_id]
                del self.tasks[task_id]
    
    async def delete_user_data(self, user_id: int):
        """Delete user's sensitive data from memory"""
        async with self.lock:
            task_id = self.user_tasks.get(user_id)
            if task_id and task_id in self.tasks:
                task = self.tasks[task_id]
                task.domains = None
                task.password = None

# ==============================================================================
#                            BOT CLASS
# ==============================================================================

class RUTEBot:
    """Main bot class"""
    
    def __init__(self):
        self.app = Client(
            "rute_cookie_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            parse_mode=ParseMode.HTML
        )
        self.task_manager = TaskManager()
        self.queue_manager = QueueManager()
        self.user_states: Dict[int, Dict] = {}
        self.bot = self.app
        self._running = False
        
        logger.info("Bot initialized")
        logger.info(f"Libarchive: {'✅' if HAS_LIBARCHIVE else '❌'}")
    
    async def start(self):
        """Start the bot"""
        try:
            self._running = True
            await self.app.start()
            await self.queue_manager.start()
            
            logger.info("Bot started successfully")
            
            if SEND_LOGS:
                try:
                    await self.app.send_message(
                        LOG_CHANNEL,
                        f"<b>🚀 Bot Started</b>\n\n"
                        f"📊 Libarchive: {'✅' if HAS_LIBARCHIVE else '❌'}\n"
                        f"⚡ Max concurrent: {MAX_CONCURRENT_USERS}"
                    )
                except Exception as e:
                    logger.error(f"Failed to send startup notification: {e}")
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise
    
    async def stop(self):
        """Stop the bot"""
        try:
            self._running = False
            await self.queue_manager.stop()
            await self.app.stop()
            logger.info("Bot stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
    
    async def safe_edit_message(self, message: Message, text: str, reply_markup: InlineKeyboardMarkup = None):
        """Safely edit a message"""
        try:
            await message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            return message
        except MessageIdInvalid:
            new_msg = await message.reply(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            return new_msg
        except MessageNotModified:
            return message
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            return message
    
    async def progress_callback_factory(self, message: Message):
        """Create a progress callback for a message"""
        last_update = 0
        
        async def callback(text: str):
            nonlocal last_update
            now = time.time()
            if now - last_update > PROGRESS_UPDATE_INTERVAL:
                try:
                    await message.edit_text(text, parse_mode=ParseMode.HTML)
                    last_update = now
                except:
                    pass
        
        return callback
    
    async def get_start_text(self) -> str:
        """Get formatted start text"""
        active = self.queue_manager.get_active_count()
        queued = self.queue_manager.get_queue_count()
        
        return f"""
<b>🚀 LOGS Extractor Bot</b>

<b>Extraction Engine:</b> {'✅ libarchive' if HAS_LIBARCHIVE else '❌ libarchive (using fallbacks)'}

<b>Queue Status:</b>
• Active: {active}/{MAX_CONCURRENT_USERS}
• Queued: {queued}
• Active timeout: {ACTIVE_TASK_TIMEOUT//60} minutes

<b>Commands:</b>
• Send any archive file (ZIP/RAR/7z/TAR/GZ/BZ2/XZ/CAB/ISO)
• Or use <code>/link &lt;url&gt;</code>
• <code>/status</code> - Check your queue position
• <code>/cancel</code> - Cancel current task
• <code>/queue</code> - Show queue status
• <code>/stats</code> - Show bot statistics

<b>Features:</b>
✅ Single-pass extraction (cookies + credit cards at once)
✅ Libarchive for all archive types
✅ Credit card format: cc|mm/yyyy|cvv|name or cc|mm/yyyy|cvv
✅ Auto-delete user data after completion
        """
    
    async def handle_start(self, client: Client, message: Message):
        """Handle /start command"""
        try:
            start_text = await self.get_start_text()
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📊 Queue", callback_data="show_queue"),
                    InlineKeyboardButton("📈 Stats", callback_data="stats_refresh")
                ],
                [
                    InlineKeyboardButton("ℹ️ About", callback_data="show_about"),
                    InlineKeyboardButton("🆘 Help", callback_data="show_help")
                ]
            ])
            
            await message.reply(start_text, reply_markup=keyboard)
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'start'})
            if error_msg:
                await message.reply(error_msg)
    
    async def handle_stats(self, client: Client, message: Message):
        """Handle /stats command"""
        try:
            status_msg = await message.reply("<b>📊 Collecting statistics...</b>")
            
            server_stats = StatsCollector.get_server_stats()
            bot_stats = StatsCollector.get_bot_stats(self.task_manager, self.queue_manager)
            
            # Format server stats
            server_text = "<b>🖥️ Server Statistics</b>\n\n"
            
            server_text += f"<b>System:</b> {server_stats['system']}\n"
            server_text += f"<b>Libarchive:</b> {server_stats['libarchive']}\n"
            
            if HAS_PSUTIL:
                server_text += f"\n<b>CPU:</b> {server_stats.get('cpu_percent', 0):.1f}% ({server_stats.get('cpu_count', 0)} cores)\n"
                server_text += f"<b>Memory:</b> {StatsCollector.format_bytes(server_stats.get('memory_used', 0))} / {StatsCollector.format_bytes(server_stats.get('memory_total', 0))} ({server_stats.get('memory_percent', 0):.1f}%)\n"
                server_text += f"<b>Disk:</b> {StatsCollector.format_bytes(server_stats.get('disk_used', 0))} / {StatsCollector.format_bytes(server_stats.get('disk_total', 0))} ({server_stats.get('disk_percent', 0):.1f}%)"
            
            # Format bot stats
            bot_text = f"\n<b>🤖 Bot Statistics</b>\n\n"
            bot_text += f"• Uptime: {StatsCollector.format_time(bot_stats['uptime'])}\n"
            bot_text += f"• Total tasks: {bot_stats['total_tasks']}\n"
            bot_text += f"• Active: {bot_stats['active_tasks']}/{bot_stats['max_concurrent']}\n"
            bot_text += f"• Queued: {bot_stats['queued_tasks']}\n"
            bot_text += f"• Completed: {bot_stats.get('completed_tasks', 0)}\n"
            bot_text += f"• Cookies found: {bot_stats.get('total_cookies', 0)}\n"
            bot_text += f"• Credit cards: {bot_stats.get('total_credit_cards', 0)}"
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 Refresh", callback_data="stats_refresh"),
                    InlineKeyboardButton("📊 Queue", callback_data="show_queue")
                ],
                [InlineKeyboardButton("🏠 Home", callback_data="show_start")]
            ])
            
            await status_msg.edit_text(server_text + "\n\n" + bot_text, reply_markup=keyboard)
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'stats'})
            if error_msg:
                await message.reply(error_msg)
    
    async def handle_status(self, client: Client, message: Message):
        """Handle /status command"""
        try:
            user_id = message.from_user.id
            task = await self.task_manager.get_user_task(user_id)
            
            if not task:
                await message.reply("❌ You don't have any active task.")
                return
            
            if task.stage == TaskStage.QUEUED:
                position = self.queue_manager.get_queue_position(user_id)
                if position:
                    queue_text = f"""
<b>⏳ Queue Status</b>

<b>Your Position:</b> {position}
<b>Active Tasks:</b> {self.queue_manager.get_active_count()}/{MAX_CONCURRENT_USERS}
<b>Total Queued:</b> {self.queue_manager.get_queue_count()}
<b>File:</b> {escape_html(task.file_name or 'Unknown')}
<b>Size:</b> {format_size(task.file_size) if task.file_size else 'Unknown'}

<b>Wait time:</b> ~{position * 5} minutes
                    """
                    await message.reply(queue_text)
                else:
                    await message.reply("⏳ You are in queue. Please wait...")
            
            elif task.stage in [TaskStage.DOWNLOADING, TaskStage.PROCESSING]:
                elapsed = time.time() - (task.started_at or task.created_at)
                status_text = f"""
<b>⚙️ Processing...</b>

<b>Stage:</b> {task.stage.value}
<b>Elapsed:</b> {format_time(elapsed)}
<b>File:</b> {escape_html(task.file_name or 'Unknown')}
                """
                await message.reply(status_text)
            
            elif task.stage == TaskStage.COMPLETE:
                await message.reply("✅ Your last task completed successfully!")
            
            elif task.stage == TaskStage.FAILED:
                await message.reply(f"❌ Your last task failed: {escape_html(task.error)}")
            
            else:
                await message.reply(f"<b>Task status:</b> {task.stage.value}")
                
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'status'})
            if error_msg:
                await message.reply(error_msg)
    
    async def handle_queue(self, client: Client, message: Message):
        """Handle /queue command"""
        try:
            active = self.queue_manager.get_active_count()
            queued = self.queue_manager.get_queue_count()
            
            status_text = f"<b>📊 Queue Status</b>\n\n"
            status_text += f"• Active: {active}/{MAX_CONCURRENT_USERS}\n"
            status_text += f"• Queued: {queued}\n\n"
            
            if active > 0:
                status_text += "<b>🔄 Active Tasks:</b>\n"
                for i, (user_id, task) in enumerate(list(self.queue_manager.active_tasks.items())[:5], 1):
                    elapsed = time.time() - task.started_at if task.started_at else 0
                    status_text += f"{i}. User: <code>{user_id}</code>\n"
                    status_text += f"   📦 {escape_html(task.file_name)} ({format_size(task.file_size)})\n"
                    status_text += f"   ⏱️ {format_time(elapsed)}\n"
                if len(self.queue_manager.active_tasks) > 5:
                    status_text += f"   ... and {len(self.queue_manager.active_tasks) - 5} more\n"
                status_text += "\n"
            
            if queued > 0:
                status_text += "<b>⏳ Queued Tasks:</b>\n"
                queue_list = list(self.queue_manager.queue._queue)
                for i, task in enumerate(queue_list[:5], 1):
                    status_text += f"{i}. User: <code>{task.user_id}</code>\n"
                    status_text += f"   📦 {escape_html(task.file_name)} ({format_size(task.file_size)})\n"
                if len(queue_list) > 5:
                    status_text += f"   ... and {len(queue_list) - 5} more\n"
                status_text += "\n"
            
            if queued > 0:
                status_text += f"Estimated wait for new tasks: ~{queued * 5} minutes"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="show_queue")],
                [InlineKeyboardButton("🏠 Home", callback_data="show_start")]
            ])
            
            await message.reply(status_text, reply_markup=keyboard)
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'queue'})
            if error_msg:
                await message.reply(error_msg)
    
    async def handle_cancel(self, client: Client, message: Message):
        """Handle /cancel command"""
        try:
            user_id = message.from_user.id
            task = await self.task_manager.get_user_task(user_id)
            
            if not task:
                await message.reply("❌ No active task found.")
                return
            
            await self.task_manager.remove_task(task.task_id)
            await self.queue_manager.remove_task(user_id)
            await delete_user_folder(user_id)
            
            await message.reply("✅ Task cancelled and user data cleaned up!")
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'cancel'})
            if error_msg:
                await message.reply(error_msg)
    
    async def handle_link(self, client: Client, message: Message):
        """Handle /link command"""
        try:
            user_id = message.from_user.id
            
            # Check if user has active task
            existing_task = await self.task_manager.get_user_task(user_id)
            if existing_task and existing_task.stage not in [TaskStage.COMPLETE, TaskStage.CANCELLED, TaskStage.FAILED]:
                await message.reply(
                    "❌ You already have an active task.\n"
                    "Use /status to check or /cancel to cancel."
                )
                return
            
            # Extract URL
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2:
                await message.reply("❌ Please provide a URL: <code>/link &lt;url&gt;</code>")
                return
            
            url = parts[1].strip()
            
            # Validate URL
            if not url.startswith(('http://', 'https://')):
                await message.reply("❌ Invalid URL. Must start with http:// or https://")
                return
            
            # Send "detecting" message
            detecting_msg = await message.reply("🔍 Detecting file type from URL...")
            
            # Detect file type from URL
            extension, filename, content_type = await detect_file_type_from_url(url)
            
            if extension:
                await detecting_msg.edit_text(f"✅ Detected: {extension} archive")
            else:
                await detecting_msg.edit_text("⚠️ Could not detect file type, will try after download")
            
            # Create task
            task_id = str(uuid.uuid4())[:8]
            
            if filename:
                file_name = filename
            else:
                file_name = f"archive_{task_id}{extension or '.zip'}"
            
            task = TaskData(
                task_id=task_id,
                user_id=user_id,
                chat_id=message.chat.id,
                message_id=message.id,
                source_type=SourceType.URL,
                source_data=url,
                bot=self,
                file_name=file_name,
                file_size=0,
                detected_type=extension
            )
            
            await self.task_manager.create_task(task)
            
            # Ask for domains (optional)
            status_msg = await message.reply(
                f"<b>📦 File:</b> <code>{escape_html(file_name)}</code>\n"
                f"<b>🔍 Detected:</b> {extension or 'Unknown'}\n\n"
                f"<b>Enter target domains (optional):</b>\n"
                f"Send comma-separated domains to filter cookies.\n"
                f"Leave empty to only extract credit cards.\n\n"
                f"Example: <code>google.com, facebook.com</code>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏭️ Skip (cards only)", callback_data=f"skip_domains_{task_id}")],
                    [InlineKeyboardButton("🚫 Cancel", callback_data=f"cancel_{task_id}")]
                ])
            )
            
            self.user_states[user_id] = {
                'task_id': task_id,
                'stage': TaskStage.AWAITING_DOMAINS,
                'status_message_id': status_msg.id
            }
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'link'})
            if error_msg:
                await message.reply(error_msg)
    
    async def handle_document(self, client: Client, message: Message):
        """Handle document (archive file)"""
        try:
            user_id = message.from_user.id
            
            # Check if user has active task
            existing_task = await self.task_manager.get_user_task(user_id)
            if existing_task and existing_task.stage not in [TaskStage.COMPLETE, TaskStage.CANCELLED, TaskStage.FAILED]:
                await message.reply(
                    "❌ You already have an active task.\n"
                    "Use /status to check or /cancel to cancel."
                )
                return
            
            # Check if it's an archive
            doc = message.document
            if not doc:
                return
            
            file_name = doc.file_name or "unknown"
            ext = os.path.splitext(file_name)[1].lower()
            
            if ext not in SUPPORTED_ARCHIVES:
                await message.reply(
                    f"❌ Unsupported file type: {ext}\n"
                    f"Supported: {', '.join(SUPPORTED_ARCHIVES)}"
                )
                return
            
            # Create task
            task_id = str(uuid.uuid4())[:8]
            task = TaskData(
                task_id=task_id,
                user_id=user_id,
                chat_id=message.chat.id,
                message_id=message.id,
                source_type=SourceType.TELEGRAM,
                source_data={
                    'message': message,
                    'file_name': file_name,
                    'file_size': doc.file_size
                },
                bot=self,
                file_name=file_name,
                file_size=doc.file_size,
                detected_type=ext
            )
            
            await self.task_manager.create_task(task)
            
            file_size_str = format_size(doc.file_size)
            
            # Forward to log channel if enabled
            if SEND_LOGS and not task.forwarded:
                try:
                    forwarded_msg = await message.forward(LOG_CHANNEL)
                    task.forwarded = True
                    task.forwarded_message_id = forwarded_msg.id
                    await self.task_manager.update_task(task_id, forwarded=True, forwarded_message_id=forwarded_msg.id)
                except Exception as e:
                    logger.error(f"Failed to forward message: {e}")
            
            # Ask for domains (optional)
            status_msg = await message.reply(
                f"<b>📦 File:</b> <code>{escape_html(file_name)}</code>\n"
                f"<b>📊 Size:</b> {file_size_str}\n\n"
                f"<b>Enter target domains (optional):</b>\n"
                f"Send comma-separated domains to filter cookies.\n"
                f"Leave empty to only extract credit cards.\n\n"
                f"Example: <code>google.com, facebook.com</code>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏭️ Skip (cards only)", callback_data=f"skip_domains_{task_id}")],
                    [InlineKeyboardButton("🚫 Cancel", callback_data=f"cancel_{task_id}")]
                ])
            )
            
            self.user_states[user_id] = {
                'task_id': task_id,
                'stage': TaskStage.AWAITING_DOMAINS,
                'status_message_id': status_msg.id
            }
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'document'})
            if error_msg:
                await message.reply(error_msg)
    
    async def handle_text(self, client: Client, message: Message):
        """Handle text messages (domains or password)"""
        try:
            user_id = message.from_user.id
            
            if user_id not in self.user_states:
                return
            
            state = self.user_states[user_id]
            stage = state.get('stage')
            task_id = state.get('task_id')
            status_message_id = state.get('status_message_id')
            
            if not task_id:
                return
            
            task = await self.task_manager.get_task(task_id)
            if not task:
                del self.user_states[user_id]
                return
            
            # Get the status message to edit
            try:
                status_msg = await client.get_messages(message.chat.id, status_message_id)
            except:
                status_msg = await message.reply("Processing...")
            
            if stage == TaskStage.AWAITING_DOMAINS:
                # User sent domains (or empty for cards only)
                domains_text = message.text.strip()
                
                if domains_text:
                    domains = [d.strip().lower() for d in domains_text.split(',') if d.strip()]
                    
                    if len(domains) > 20:
                        await self.safe_edit_message(
                            status_msg,
                            "❌ Too many domains. Maximum 20 allowed.",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("🚫 Cancel", callback_data=f"cancel_{task_id}")]
                            ])
                        )
                        return
                    
                    task.domains = domains
                    task.extraction_type = ExtractionType.BOTH
                    await self.task_manager.update_task(task_id, domains=domains, extraction_type=ExtractionType.BOTH)
                else:
                    # No domains -> cards only
                    task.domains = None
                    task.extraction_type = ExtractionType.CREDIT_CARDS
                    await self.task_manager.update_task(task_id, domains=None, extraction_type=ExtractionType.CREDIT_CARDS)
                
                # Ask about password
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Yes", callback_data=f"pw_yes_{task_id}"),
                        InlineKeyboardButton("❌ No", callback_data=f"pw_no_{task_id}")
                    ],
                    [InlineKeyboardButton("🚫 Cancel", callback_data=f"cancel_{task_id}")]
                ])
                
                await self.safe_edit_message(
                    status_msg,
                    "🔒 <b>Is this archive password protected?</b>",
                    reply_markup=keyboard
                )
                
                state['stage'] = TaskStage.AWAITING_PASSWORD
                state['status_message_id'] = status_msg.id
                
                # Delete user's message for privacy
                try:
                    await message.delete()
                except:
                    pass
            
            elif stage == TaskStage.AWAITING_PASSWORD:
                # User sent password
                password = message.text.strip()
                task.password = password
                await self.task_manager.update_task(task_id, password=password)
                
                # Forward with password to log channel
                if SEND_LOGS and task.source_type == SourceType.TELEGRAM and not task.forwarded:
                    try:
                        original_msg = task.source_data['message']
                        caption = f"🔑 <b>Password Protected Archive</b>\n\n<b>Password:</b> <code>{escape_html(password)}</code>"
                        await original_msg.forward(LOG_CHANNEL, caption=caption)
                        task.forwarded = True
                        await self.task_manager.update_task(task_id, forwarded=True)
                    except Exception as e:
                        logger.error(f"Failed to forward password-protected archive: {e}")
                
                # Confirm and add to queue
                await self.confirm_and_queue(status_msg, task)
                
                # Delete user's message with password
                try:
                    await message.delete()
                except:
                    pass
                
                del self.user_states[user_id]
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'text'})
            if error_msg:
                await message.reply(error_msg)
    
    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        """Handle callback queries"""
        try:
            user_id = callback_query.from_user.id
            data = callback_query.data
            
            if data == "stats_refresh":
                await self.handle_stats_refresh(callback_query)
            elif data == "show_queue":
                await self.handle_show_queue(callback_query)
            elif data == "show_about":
                await self.handle_show_about(callback_query)
            elif data == "show_help":
                await self.handle_show_help(callback_query)
            elif data == "show_start":
                await self.handle_show_start(callback_query)
            elif data.startswith('skip_domains_'):
                task_id = data[13:]
                await self.handle_skip_domains(callback_query, task_id)
            elif data.startswith('pw_yes_'):
                task_id = data[7:]
                await self.handle_password_yes(callback_query, task_id)
            elif data.startswith('pw_no_'):
                task_id = data[6:]
                await self.handle_password_no(callback_query, task_id)
            elif data.startswith('cancel_'):
                task_id = data[7:]
                await self.handle_cancel_callback(callback_query, task_id)
            elif data.startswith('confirm_'):
                task_id = data[8:]
                await self.handle_confirm(callback_query, task_id)
            elif data.startswith('retry_'):
                task_id = data[6:]
                await self.handle_retry(callback_query, task_id)
            
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Callback error: {e}")
            try:
                await callback_query.answer("An error occurred", show_alert=True)
            except:
                pass
    
    async def handle_show_start(self, callback_query: CallbackQuery):
        """Handle show start callback"""
        try:
            start_text = await self.get_start_text()
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📊 Queue", callback_data="show_queue"),
                    InlineKeyboardButton("📈 Stats", callback_data="stats_refresh")
                ],
                [
                    InlineKeyboardButton("ℹ️ About", callback_data="show_about"),
                    InlineKeyboardButton("🆘 Help", callback_data="show_help")
                ]
            ])
            
            await callback_query.message.edit_text(start_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Show start error: {e}")
    
    async def handle_skip_domains(self, callback_query: CallbackQuery, task_id: str):
        """Handle skip domains (cards only)"""
        try:
            user_id = callback_query.from_user.id
            
            task = await self.task_manager.get_task(task_id)
            if not task or task.user_id != user_id:
                await callback_query.answer("Invalid task!", show_alert=True)
                return
            
            # Set to cards only
            task.domains = None
            task.extraction_type = ExtractionType.CREDIT_CARDS
            await self.task_manager.update_task(task_id, domains=None, extraction_type=ExtractionType.CREDIT_CARDS)
            
            # Ask about password
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes", callback_data=f"pw_yes_{task_id}"),
                    InlineKeyboardButton("❌ No", callback_data=f"pw_no_{task_id}")
                ],
                [InlineKeyboardButton("🚫 Cancel", callback_data=f"cancel_{task_id}")]
            ])
            
            await callback_query.message.edit_text(
                "🔒 <b>Is this archive password protected?</b>",
                reply_markup=keyboard
            )
            
            # Update state
            if user_id in self.user_states:
                self.user_states[user_id]['stage'] = TaskStage.AWAITING_PASSWORD
            
        except Exception as e:
            logger.error(f"Skip domains error: {e}")
    
    async def handle_stats_refresh(self, callback_query: CallbackQuery):
        """Handle stats refresh callback"""
        try:
            await callback_query.message.edit_text("<b>📊 Refreshing statistics...</b>")
            
            server_stats = StatsCollector.get_server_stats()
            bot_stats = StatsCollector.get_bot_stats(self.task_manager, self.queue_manager)
            
            server_text = "<b>🖥️ Server Statistics</b>\n\n"
            server_text += f"<b>System:</b> {server_stats['system']}\n"
            server_text += f"<b>Libarchive:</b> {server_stats['libarchive']}\n"
            
            if HAS_PSUTIL:
                server_text += f"\n<b>CPU:</b> {server_stats.get('cpu_percent', 0):.1f}% ({server_stats.get('cpu_count', 0)} cores)\n"
                server_text += f"<b>Memory:</b> {StatsCollector.format_bytes(server_stats.get('memory_used', 0))} / {StatsCollector.format_bytes(server_stats.get('memory_total', 0))} ({server_stats.get('memory_percent', 0):.1f}%)\n"
                server_text += f"<b>Disk:</b> {StatsCollector.format_bytes(server_stats.get('disk_used', 0))} / {StatsCollector.format_bytes(server_stats.get('disk_total', 0))} ({server_stats.get('disk_percent', 0):.1f}%)"
            
            bot_text = f"\n<b>🤖 Bot Statistics</b>\n\n"
            bot_text += f"• Uptime: {StatsCollector.format_time(bot_stats['uptime'])}\n"
            bot_text += f"• Total tasks: {bot_stats['total_tasks']}\n"
            bot_text += f"• Active: {bot_stats['active_tasks']}/{bot_stats['max_concurrent']}\n"
            bot_text += f"• Queued: {bot_stats['queued_tasks']}\n"
            bot_text += f"• Completed: {bot_stats.get('completed_tasks', 0)}\n"
            bot_text += f"• Cookies found: {bot_stats.get('total_cookies', 0)}\n"
            bot_text += f"• Credit cards: {bot_stats.get('total_credit_cards', 0)}"
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 Refresh", callback_data="stats_refresh"),
                    InlineKeyboardButton("📊 Queue", callback_data="show_queue")
                ],
                [InlineKeyboardButton("🏠 Home", callback_data="show_start")]
            ])
            
            await callback_query.message.edit_text(server_text + "\n\n" + bot_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Stats refresh error: {e}")
    
    async def handle_show_queue(self, callback_query: CallbackQuery):
        """Handle show queue callback"""
        try:
            active = self.queue_manager.get_active_count()
            queued = self.queue_manager.get_queue_count()
            
            status_text = f"<b>📊 Queue Status</b>\n\n"
            status_text += f"• Active: {active}/{MAX_CONCURRENT_USERS}\n"
            status_text += f"• Queued: {queued}\n\n"
            
            if active > 0:
                status_text += "<b>🔄 Active Tasks:</b>\n"
                for i, (user_id, task) in enumerate(list(self.queue_manager.active_tasks.items())[:5], 1):
                    elapsed = time.time() - task.started_at if task.started_at else 0
                    status_text += f"{i}. User: <code>{user_id}</code>\n"
                    status_text += f"   📦 {escape_html(task.file_name)} ({format_size(task.file_size)})\n"
                    status_text += f"   ⏱️ {format_time(elapsed)}\n"
                if len(self.queue_manager.active_tasks) > 5:
                    status_text += f"   ... and {len(self.queue_manager.active_tasks) - 5} more\n"
                status_text += "\n"
            
            if queued > 0:
                status_text += "<b>⏳ Queued Tasks:</b>\n"
                queue_list = list(self.queue_manager.queue._queue)
                for i, task in enumerate(queue_list[:5], 1):
                    status_text += f"{i}. User: <code>{task.user_id}</code>\n"
                    status_text += f"   📦 {escape_html(task.file_name)} ({format_size(task.file_size)})\n"
                if len(queue_list) > 5:
                    status_text += f"   ... and {len(queue_list) - 5} more\n"
                status_text += "\n"
            
            if queued > 0:
                status_text += f"Estimated wait for new tasks: ~{queued * 5} minutes"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="show_queue")],
                [InlineKeyboardButton("🏠 Home", callback_data="show_start")]
            ])
            
            await callback_query.message.edit_text(status_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Show queue error: {e}")
    
    async def handle_show_about(self, callback_query: CallbackQuery):
        """Handle show about callback"""
        try:
            about_text = f"""
<b>ℹ️ About RUTE Extractor Bot</b>

<b>Version:</b> 4.0.0 (Libarchive Edition)
<b>Description:</b> Advanced Telegram bot for extracting cookies and credit cards.

<b>Features:</b>
• Universal extraction with libarchive
• Single-pass processing (cookies + cards at once)
• Supports: ZIP, RAR, 7z, TAR, GZ, BZ2, XZ, CAB, ISO, LHA, LZH
• Credit card format: cc|mm/yyyy|cvv|name or cc|mm/yyyy|cvv
• Queue system with {MAX_CONCURRENT_USERS} concurrent users
• Auto-delete user data after completion

<b>Engine:</b>
• Libarchive: {'✅' if HAS_LIBARCHIVE else '❌'} (fallbacks available)
• Max workers: {MAX_WORKERS}
• Active timeout: {ACTIVE_TASK_TIMEOUT//60} minutes
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Home", callback_data="show_start")]
            ])
            
            await callback_query.message.edit_text(about_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Show about error: {e}")
    
    async def handle_show_help(self, callback_query: CallbackQuery):
        """Handle show help callback"""
        try:
            help_text = f"""
<b>🆘 Help & Commands</b>

<b>Basic Commands:</b>
• <code>/start</code> - Start the bot
• <code>/status</code> - Check your queue position
• <code>/cancel</code> - Cancel current task
• <code>/queue</code> - Show queue status
• <code>/stats</code> - Show bot statistics
• <code>/link &lt;url&gt;</code> - Process from direct link

<b>How to Use:</b>
1. Send an archive file or use /link
2. Enter target domains (optional - leave empty for cards only)
3. Specify if password protected
4. Wait in queue
5. Get results (cookies per domain + credit cards)

<b>Credit Card Format:</b>
• With name: <code>cc|mm/yyyy|cvv|name</code>
• Without name: <code>cc|mm/yyyy|cvv</code>

<b>Supported Formats:</b>
{', '.join(SUPPORTED_ARCHIVES)}

<b>Queue System:</b>
• Max {MAX_CONCURRENT_USERS} concurrent users
• {ACTIVE_TASK_TIMEOUT//60} min timeout for active tasks
• Auto-delete user data after completion
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Home", callback_data="show_start")]
            ])
            
            await callback_query.message.edit_text(help_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Show help error: {e}")
    
    async def handle_password_yes(self, callback_query: CallbackQuery, task_id: str):
        """Handle password: yes"""
        try:
            user_id = callback_query.from_user.id
            
            task = await self.task_manager.get_task(task_id)
            if not task or task.user_id != user_id:
                await callback_query.answer("Invalid task!", show_alert=True)
                return
            
            await self.safe_edit_message(
                callback_query.message,
                "🔑 <b>Please enter the password:</b>\n\n"
                "Send the password as a text message.\n"
                "It will be automatically deleted after processing.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚫 Cancel", callback_data=f"cancel_{task_id}")]
                ])
            )
            
            if user_id in self.user_states:
                self.user_states[user_id]['stage'] = TaskStage.AWAITING_PASSWORD
                self.user_states[user_id]['status_message_id'] = callback_query.message.id
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'password_yes'})
            if error_msg:
                await callback_query.message.edit_text(error_msg)
    
    async def handle_password_no(self, callback_query: CallbackQuery, task_id: str):
        """Handle password: no"""
        try:
            user_id = callback_query.from_user.id
            
            task = await self.task_manager.get_task(task_id)
            if not task or task.user_id != user_id:
                await callback_query.answer("Invalid task!", show_alert=True)
                return
            
            await self.confirm_and_queue(callback_query.message, task)
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'password_no'})
            if error_msg:
                await callback_query.message.edit_text(error_msg)
    
    async def handle_cancel_callback(self, callback_query: CallbackQuery, task_id: str):
        """Handle cancel callback"""
        try:
            user_id = callback_query.from_user.id
            
            await self.task_manager.remove_task(task_id)
            await self.queue_manager.remove_task(user_id)
            await delete_user_folder(user_id)
            
            await callback_query.message.edit_text("✅ Task cancelled and user data cleaned up.")
            
        except Exception as e:
            logger.error(f"Cancel callback error: {e}")
    
    async def handle_confirm(self, callback_query: CallbackQuery, task_id: str):
        """Handle confirm callback"""
        try:
            user_id = callback_query.from_user.id
            
            task = await self.task_manager.get_task(task_id)
            if not task or task.user_id != user_id:
                await callback_query.answer("Invalid task!", show_alert=True)
                return
            
            await self.add_to_queue(callback_query.message, task)
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'confirm'})
            if error_msg:
                await callback_query.message.edit_text(error_msg)
    
    async def handle_retry(self, callback_query: CallbackQuery, task_id: str):
        """Handle retry callback"""
        try:
            user_id = callback_query.from_user.id
            
            task = await self.task_manager.get_task(task_id)
            if not task or task.user_id != user_id:
                await callback_query.answer("Invalid task!", show_alert=True)
                return
            
            task.stage = TaskStage.INIT
            task.error = None
            await self.task_manager.update_task(task_id, stage=TaskStage.INIT, error=None)
            
            await self.add_to_queue(callback_query.message, task)
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'retry'})
            if error_msg:
                await callback_query.message.edit_text(error_msg)
    
    async def confirm_and_queue(self, message: Message, task: TaskData):
        """Confirm task and add to queue"""
        try:
            ext_type = "🍪 Cookies + 💳 Cards" if task.domains else "💳 Cards Only"
            
            domains_str = ""
            if task.domains:
                domains_str = ", ".join(task.domains[:5])
                if len(task.domains) > 5:
                    domains_str += f" and {len(task.domains)-5} more"
            
            password_status = "✅ Yes" if task.password else "❌ No"
            
            active = self.queue_manager.get_active_count()
            queued = self.queue_manager.get_queue_count()
            
            confirm_text = f"""
<b>📦 Task Summary</b>

<b>Type:</b> {ext_type}
<b>File:</b> {escape_html(task.file_name or 'Unknown')}
<b>Size:</b> {format_size(task.file_size) if task.file_size else 'Unknown'}
<b>Password:</b> {password_status}
"""
            if domains_str:
                confirm_text += f"<b>Domains:</b> {escape_html(domains_str)}\n"
            
            confirm_text += f"""
<b>Queue Status:</b> {active}/{MAX_CONCURRENT_USERS} active, {queued} queued

Add to queue and start processing?
            """
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{task.task_id}"),
                    InlineKeyboardButton("🚫 Cancel", callback_data=f"cancel_{task.task_id}")
                ]
            ])
            
            await self.safe_edit_message(message, confirm_text, reply_markup=keyboard)
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'confirm_queue'})
            if error_msg:
                await message.edit_text(error_msg)
    
    async def add_to_queue(self, message: Message, task: TaskData):
        """Add task to queue"""
        try:
            await self.safe_edit_message(message, "⏳ Adding to queue...")
            
            position, eta = await self.queue_manager.add_to_queue(task)
            
            ext_type = "🍪 Cookies + 💳 Cards" if task.domains else "💳 Cards Only"
            
            if eta == "immediately":
                queue_text = f"""
<b>✅ Added to Queue - Starting Immediately!</b>

<b>Position:</b> {position}
<b>Type:</b> {ext_type}
<b>File:</b> {escape_html(task.file_name or 'Unknown')}
<b>Size:</b> {format_size(task.file_size) if task.file_size else 'Unknown'}

Processing will start right away!
                """
            else:
                queue_text = f"""
<b>⏳ Added to Queue</b>

<b>Your Position:</b> {position}
<b>Estimated Wait:</b> {eta}
<b>Active Tasks:</b> {self.queue_manager.get_active_count()}/{MAX_CONCURRENT_USERS}
<b>Type:</b> {ext_type}
<b>File:</b> {escape_html(task.file_name or 'Unknown')}
<b>Size:</b> {format_size(task.file_size) if task.file_size else 'Unknown'}

You'll be notified when processing starts.
Use /status to check your position.
                """
            
            await self.safe_edit_message(message, queue_text)
            
        except Exception as e:
            error_msg = await ErrorHandler.handle_error(e, {'handler': 'add_queue'})
            if error_msg:
                await message.edit_text(error_msg)
    
    async def process_task(self, task: TaskData):
        """Process a task"""
        try:
            if task.stage != TaskStage.QUEUED:
                return
            
            task.stage = TaskStage.DOWNLOADING
            await self.task_manager.update_task(task.task_id, stage=TaskStage.DOWNLOADING)
            
            try:
                progress_msg = await self.app.send_message(
                    task.chat_id,
                    "<b>🚀 Starting processing...</b>"
                )
            except:
                progress_msg = None
            
            # Get paths
            download_path = task.get_download_path()
            extract_folder = task.get_extract_path()
            result_folder = task.get_results_path()
            
            os.makedirs(os.path.dirname(download_path), exist_ok=True)
            os.makedirs(extract_folder, exist_ok=True)
            os.makedirs(result_folder, exist_ok=True)
            
            task.paths['download'] = download_path
            task.paths['extract'] = extract_folder
            task.paths['results'] = result_folder
            
            # Download file
            if task.source_type == SourceType.URL:
                url = task.source_data
                
                if progress_msg:
                    progress_callback = await self.progress_callback_factory(progress_msg)
                    download_manager = DownloadManager(task.task_id)
                    success, result = await download_manager.download_file(url, download_path, progress_callback)
                    
                    if not success:
                        raise Exception(f"Download failed: {result}")
                    
                    if isinstance(result, str):
                        download_path = result
                    
                    if os.path.exists(download_path):
                        task.file_size = os.path.getsize(download_path)
                        task.file_name = os.path.basename(download_path)
                        await self.task_manager.update_task(task.task_id, file_name=task.file_name, file_size=task.file_size)
            
            elif task.source_type == SourceType.TELEGRAM:
                msg_data = task.source_data
                original_msg = msg_data['message']
                
                if progress_msg:
                    progress_callback = await self.progress_callback_factory(progress_msg)
                    download_manager = DownloadManager(task.task_id)
                    success, result = await download_manager.download_from_telegram(original_msg, download_path, progress_callback)
                    
                    if not success:
                        raise Exception(f"Download failed: {result}")
                    
                    if isinstance(result, str):
                        download_path = result
            
            # Update stage
            task.stage = TaskStage.PROCESSING
            await self.task_manager.update_task(task.task_id, stage=TaskStage.PROCESSING)
            
            if progress_msg:
                await progress_msg.edit_text("<b>📦 Starting extraction with libarchive...</b>")
            
            # Extract archives
            extractor = LibArchiveExtractor(password=task.password, task_id=task.task_id)
            
            if progress_msg:
                progress_callback = await self.progress_callback_factory(progress_msg)
            else:
                progress_callback = None
            
            extract_path, extracted_count = await extractor.extract_all_nested(
                download_path, 
                extract_folder, 
                progress_callback
            )
            
            task.stats['archives_extracted'] = extracted_count
            
            # Process all data in single pass
            if progress_msg:
                await progress_msg.edit_text("<b>🔍 Scanning for data...</b>")
            
            data_extractor = DataExtractor(target_domains=task.domains)
            
            if progress_msg:
                progress_callback = await self.progress_callback_factory(progress_msg)
            else:
                progress_callback = None
            
            extracted_data = await data_extractor.process_all(extract_folder, progress_callback)
            
            # Update stats
            task.stats['files_processed'] = extracted_data.files_processed
            task.stats['total_entries'] = extracted_data.total_entries
            task.stats['cookies_found'] = sum(len(v) for v in extracted_data.cookies.values())
            task.stats['credit_cards_found'] = len(extracted_data.credit_cards)
            
            # Update stage
            task.stage = TaskStage.COMPLETE
            await self.task_manager.update_task(task.task_id, stage=TaskStage.COMPLETE, completed_at=time.time())
            
            # Create result files
            result_files = data_extractor.create_result_files(result_folder)
            task.stats['zips_created'] = len(result_files)
            
            # Send results
            if result_files:
                if progress_msg:
                    stats_text = f"<b>✅ Processing Complete!</b>\n\n"
                    if task.stats['cookies_found'] > 0:
                        stats_text += f"🍪 Cookies found: {task.stats['cookies_found']}\n"
                    if task.stats['credit_cards_found'] > 0:
                        stats_text += f"💳 Credit cards found: {task.stats['credit_cards_found']}\n"
                    stats_text += f"📄 Files scanned: {extracted_data.files_processed}\n"
                    stats_text += f"📦 Files created: {len(result_files)}\n"
                    stats_text += f"📚 Archives extracted: {extracted_count}\n\n"
                    stats_text += f"<b>📤 Sending files...</b>"
                    
                    await progress_msg.edit_text(stats_text)
                
                # Send files
                sent_count = 0
                for name, file_path in result_files.items():
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                        try:
                            if name == 'credit_cards':
                                caption = f"<b>💳 Credit Cards</b>\n📦 Size: {format_size(os.path.getsize(file_path))}\nFormat: cc|mm/yyyy|cvv|name or cc|mm/yyyy|cvv"
                            else:
                                caption = f"<b>🍪 {name}</b> cookies\n📦 Size: {format_size(os.path.getsize(file_path))}"
                            
                            await self.app.send_document(
                                task.chat_id,
                                document=file_path,
                                caption=caption
                            )
                            sent_count += 1
                        except Exception as e:
                            logger.error(f"Failed to send {name}: {e}")
                    
                    await asyncio.sleep(0.5)
                
                # Send completion message
                completion_text = f"""
<b>✅ All Done!</b>

<b>📊 Summary:</b>
• Cookies found: {task.stats['cookies_found']}
• Credit cards: {task.stats['credit_cards_found']}
• Files sent: {sent_count}/{len(result_files)}
• Archives extracted: {extracted_count}
• Time: {format_time(time.time() - task.started_at)}
                """
                
                await self.app.send_message(task.chat_id, completion_text)
                
                # Log to channel
                if SEND_LOGS:
                    try:
                        log_text = (
                            f"<b>📦 Extraction Complete</b>\n\n"
                            f"👤 User: {task.user_id}\n"
                            f"🍪 Cookies: {task.stats['cookies_found']}\n"
                            f"💳 Cards: {task.stats['credit_cards_found']}\n"
                            f"📁 Files: {len(result_files)}\n"
                            f"📚 Archives: {extracted_count}\n"
                            f"⏱️ Time: {format_time(time.time() - task.started_at)}"
                        )
                        await self.app.send_message(LOG_CHANNEL, log_text)
                    except:
                        pass
            else:
                if progress_msg:
                    await progress_msg.edit_text("❌ No data found in the archive.")
                
                await self.app.send_message(
                    task.chat_id,
                    "❌ <b>No Data Found</b>\n\n"
                    "No cookies or credit cards were found in the archive."
                )
            
            # Remove from active tasks
            await self.queue_manager.remove_task(task.user_id)
            
            # Clean up
            await self.task_manager.delete_user_data(task.user_id)
            await delete_user_folder(task.user_id)
            
        except Exception as e:
            logger.error(f"Task processing error: {e}", exc_info=True)
            
            task.stage = TaskStage.FAILED
            task.error = str(e)
            await self.task_manager.update_task(task.task_id, stage=TaskStage.FAILED, error=str(e))
            
            await self.queue_manager.remove_task(task.user_id)
            
            error_msg = await ErrorHandler.handle_error(e)
            
            retry_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Retry", callback_data=f"retry_{task.task_id}")]
            ])
            
            try:
                await self.app.send_message(
                    task.chat_id,
                    f"❌ <b>Processing Failed</b>\n\n{error_msg}",
                    reply_markup=retry_keyboard
                )
            except:
                pass
            
            await delete_user_folder(task.user_id)
    
    def run(self):
        """Run the bot"""
        try:
            # Add handlers
            self.app.add_handler(MessageHandler(self.handle_start, filters.command("start")))
            self.app.add_handler(MessageHandler(self.handle_status, filters.command("status")))
            self.app.add_handler(MessageHandler(self.handle_queue, filters.command("queue")))
            self.app.add_handler(MessageHandler(self.handle_cancel, filters.command("cancel")))
            self.app.add_handler(MessageHandler(self.handle_stats, filters.command("stats")))
            self.app.add_handler(MessageHandler(self.handle_link, filters.command("link")))
            self.app.add_handler(MessageHandler(self.handle_document, filters.document))
            self.app.add_handler(MessageHandler(self.handle_text, filters.text & ~filters.command(["start", "status", "queue", "cancel", "stats", "link"])))
            self.app.add_handler(CallbackQueryHandler(self.handle_callback))
            
            logger.info("Starting bot...")
            print(f"🤖 LOGS Extractor Bot starting...")
            print(f"📊 Libarchive: {'✅' if HAS_LIBARCHIVE else '❌'}")
            print(f"⚡ Max concurrent: {MAX_CONCURRENT_USERS}")
            print(f"⏱️ Active timeout: {ACTIVE_TASK_TIMEOUT//60} minutes")
            print(f"📁 Downloads folder: downloads/[user_id]/")
            print(f"💳 CC Format: cc|mm/yyyy|cvv|name or cc|mm/yyyy|cvv")
            print(f"🔍 Single-pass extraction: cookies + cards at once")
            print(f"🚀 Bot is running! Press Ctrl+C to stop.")
            
            # Run the client
            self.app.run()
            
        except KeyboardInterrupt:
            print("\n👋 Bot stopped by user")
            logger.info("Bot stopped by user")
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            logger.error(f"Fatal error: {e}", exc_info=True)

# ==============================================================================
#                                MAIN
# ==============================================================================

if __name__ == "__main__":
    bot = RUTEBot()
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        traceback.print_exc()
