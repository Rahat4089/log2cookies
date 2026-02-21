# Advanced Configuration File for Cookie Extractor Bot

"""
CONFIG.PY - Configuration and Constants

This file contains all configurable settings for the bot.
Edit these values according to your needs.
"""

# ============================================================================
#                        TELEGRAM CREDENTIALS
# ============================================================================

API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAFzz3T1lU8KKQOyg2yHR5PsL5XkvQZCi54"
LOG_CHANNEL = -1003747061396
SEND_LOGS = True
ADMINS = [7125341830]

# ============================================================================
#                        PERFORMANCE SETTINGS
# ============================================================================

# Threading
MAX_WORKERS = 50                    # Number of concurrent extraction threads
SCAN_WORKERS = 20                   # Workers for file scanning

# Buffer sizes
BUFFER_SIZE = 20 * 1024 * 1024     # 20MB
CHUNK_SIZE = 1024 * 1024           # 1MB

# Timeouts
FILE_DOWNLOAD_TIMEOUT = 3600       # 1 hour
USER_INPUT_TIMEOUT = 300           # 5 minutes
EXTRACTION_TIMEOUT = 300           # 5 minutes per archive

# ============================================================================
#                        ARCHIVE SETTINGS
# ============================================================================

SUPPORTED_ARCHIVES = {
    '.zip',  # ZIP archives
    '.rar',  # RAR archives
    '.7z',   # 7-Zip archives
    '.tar',  # TAR archives
    '.gz',   # GZIP compressed
    '.bz2',  # BZIP2 compressed
    '.xz'    # XZ compressed
}

MAX_ARCHIVE_SIZE = 2000 * 1024 * 1024  # 2GB (Telegram limit)

# ============================================================================
#                        COOKIE SETTINGS
# ============================================================================

COOKIE_FOLDERS = {
    'Cookies',
    'Browsers',
    'cookies',
    'browser_data',
    'BrowserData',
    'AppData'
}

COOKIE_EXTENSIONS = {
    '.txt',
    '.txt.bak',
    '.dat',
    '.db',
    '.sqlite'
}

# ============================================================================
#                        EXTERNAL TOOLS
# ============================================================================

# Windows paths
WINDOWS_7Z_PATHS = [
    'C:\\Program Files\\7-Zip\\7z.exe',
    'C:\\Program Files (x86)\\7-Zip\\7z.exe',
    '7z.exe'
]

WINDOWS_UNRAR_PATHS = [
    'C:\\Program Files\\WinRAR\\UnRAR.exe',
    'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe',
    'unrar.exe'
]

# Unix/Linux tools
UNIX_7Z = '7z'
UNIX_UNRAR = 'unrar'

# ============================================================================
#                        MESSAGES & UI
# ============================================================================

MESSAGES = {
    'start': """🤖 **Cookie Extractor Bot**

📌 **How to use:**
1️⃣ Forward a .zip/.rar/.7z archive or send `/link <url>`
2️⃣ Answer if it's password protected
3️⃣ Provide domains to extract (comma-separated)
4️⃣ Get filtered cookie files as ZIP

⚙️ **Available commands:**
/start - Show this menu
/cancel_[ID] - Cancel current task
/status - Check tool status

🔧 **Tools status:**
7z.exe: {7z_status}
UnRAR.exe: {unrar_status}""",
    
    'error_already_running': "⏳ You already have a running task. Use /cancel_[ID] to stop it.",
    'error_no_domains': "❌ No domains specified",
    'error_timeout': "❌ Timeout. Task cancelled.",
    'error_download': "❌ Download failed: {error}",
    'error_no_cookies': "⚠️ No cookies found matching your domains.",
    'error_extraction': "❌ Extraction failed: {error}",
    
    'downloading': "⏳ Task ID: `{task_id}`\n⬇️ Downloading archive...",
    'downloaded': "✓ Downloaded: {size}",
    'checking_password': "🔍 Checking password protection...",
    'password_protected': "🔐 Archive is password protected.\n🔑 Send password (or /skip):",
    'password_ready': "✓ Password received\n",
    'not_protected': "✓ Not password protected",
    'waiting_domains': "🎯 Send domains (comma-separated):",
    'extracting': "📦 Extracting archives...",
    'filtering': "🔍 Extracting cookies...",
    'uploading': "📦 Uploading results...",
    'complete': """✓ **Extraction Complete!**

📊 **Stats:**
• Files processed: {files_processed}
• Entries found: {total_found}
• ZIP archives: {zip_count}

✓ All files sent."""
}

# ============================================================================
#                        CLEANUP SETTINGS
# ============================================================================

# Auto-cleanup after task completion (in minutes)
CLEANUP_DELAY = 0  # 0 = immediate

# Keep logs for (in days)
LOG_RETENTION_DAYS = 30

# ============================================================================
#                        LOGGING
# ============================================================================

LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

LOG_FILE = "logs/bot.log"

# ============================================================================
#                        RATE LIMITING
# ============================================================================

# User rate limits
RATE_LIMIT_PER_USER_PER_HOUR = 10
RATE_LIMIT_GLOBAL_PER_MINUTE = 50

# ============================================================================
#                        DATABASE (Optional)
# ============================================================================

# For future: persistent user data
USE_DATABASE = False
DATABASE_URL = "sqlite:///bot.db"  # or PostgreSQL URL

# ============================================================================
#                        DEVELOPER OPTIONS
# ============================================================================

DEBUG_MODE = False
VERBOSE_LOGGING = False
DRY_RUN = False  # Test without actual extraction
