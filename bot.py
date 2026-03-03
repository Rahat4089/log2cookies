import os
import asyncio
import re
import json
import tempfile
import shutil
import zipfile
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
import libarchive
import libarchive.ffi as ffi
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import time

from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery
)
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, MessageNotModified

# Bot configuration
API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8640428737:AAELyJIu3sWBUYhpJY_tcPzcDbbtd9K6bY8"

# Thread pool for parallel processing
executor = ThreadPoolExecutor(max_workers=os.cpu_count() * 3)

# User session data storage
user_sessions = {}

class ExtractionSession:
    def __init__(self, user_id: int, message: Message = None):
        self.user_id = user_id
        self.original_message = message
        self.mode = None  # "zip", "folder", "cookies", "ulp"
        self.domains = []  # For cookies mode
        self.password = None
        self.archive_path = None
        self.archive_filename = None
        self.archive_size = 0
        self.extract_path = None
        self.results = []  # For CC results
        self.cookie_results = []  # For cookie results
        self.cookies_data = []  # Structured cookie data
        self.ulp_results = []  # For ULP results
        self.total_files = 0
        self.processed_files = 0
        self.stop_flag = False
        self.status_message = None
        self.password_request_message = None
        self.mode_selection_message = None
        self.last_update_time = 0
        self.start_time = None
        self.domain_list = []
        self.cookie_format = "Simple List"  # Default format
        
    def reset(self):
        self.mode = None
        self.domains = []
        self.password = None
        if self.archive_path and os.path.exists(self.archive_path):
            try:
                os.remove(self.archive_path)
            except:
                pass
        if self.extract_path and os.path.exists(self.extract_path):
            try:
                shutil.rmtree(self.extract_path)
            except:
                pass
        self.archive_path = None
        self.archive_filename = None
        self.archive_size = 0
        self.extract_path = None
        self.results = []
        self.cookie_results = []
        self.cookies_data = []
        self.ulp_results = []
        self.total_files = 0
        self.processed_files = 0
        self.stop_flag = False
        self.last_update_time = 0
        self.start_time = None
        
        # Delete status messages
        messages_to_delete = []
        if self.status_message:
            messages_to_delete.append(self.status_message)
        if self.password_request_message:
            messages_to_delete.append(self.password_request_message)
        if self.mode_selection_message:
            messages_to_delete.append(self.mode_selection_message)
        
        for msg in messages_to_delete:
            try:
                asyncio.create_task(msg.delete())
            except:
                pass
        
        self.status_message = None
        self.password_request_message = None
        self.mode_selection_message = None

app = Client(
    "multi_extractor_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ========== ARCHIVE EXTRACTION USING LIBARCHIVE ==========
async def extract_archive_with_libarchive(archive_path: str, extract_to: str, password: str = None, session=None) -> List[str]:
    """
    Extract archive using libarchive with support for nested archives
    Returns list of extracted file paths
    """
    extracted_files = []
    
    def extract_callback(entry, archive):
        entry_path = entry.pathname
        if entry_path.endswith('/'):
            return 0
        
        target_path = os.path.join(extract_to, entry_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        try:
            with open(target_path, 'wb') as f:
                for block in entry.get_blocks():
                    f.write(block)
            return target_path
        except Exception as e:
            print(f"Error extracting {entry_path}: {e}")
            return None
    
    try:
        # Count total entries for progress
        with libarchive.file_reader(archive_path) as archive:
            entries = list(archive)
            total_entries = len(entries)
        
        # Extract with progress updates (3 second intervals)
        extracted = []
        for i, entry in enumerate(entries):
            if session and session.stop_flag:
                break
                
            result = extract_callback(entry, None)
            if result:
                extracted.append(result)
            
            # Update progress every 3 seconds
            if session and session.status_message:
                current_time = time.time()
                if current_time - session.last_update_time >= 3 or i == total_entries - 1:
                    progress = (i + 1) / total_entries * 100
                    asyncio.create_task(
                        session.status_message.edit_text(
                            f"📦 **Extracting archive...**\n"
                            f"Progress: {progress:.1f}%\n"
                            f"File: {os.path.basename(entry.pathname)[:30]}..."
                        )
                    )
                    session.last_update_time = current_time
        
        extracted_files.extend(extracted)
        
        # Process nested archives
        nested_count = 0
        for file_path in extracted_files[:]:
            if is_archive_file(file_path):
                nested_count += 1
                if session and session.status_message:
                    await session.status_message.edit_text(f"📦 **Extracting nested archive {nested_count}...**")
                
                nested_extract_dir = os.path.join(extract_to, f"nested_{nested_count}")
                os.makedirs(nested_extract_dir, exist_ok=True)
                
                try:
                    nested_files = await extract_archive_with_libarchive(file_path, nested_extract_dir, password, session)
                    extracted_files.extend(nested_files)
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error extracting nested archive {file_path}: {e}")
    
    except Exception as e:
        print(f"Extraction error: {e}")
        raise
    
    return extracted_files

def is_archive_file(filepath: str) -> bool:
    """Check if file is an archive based on extension"""
    archive_extensions = {
        '.zip', '.rar', '.tar', '.gz', '.tgz', '.bz2', 
        '.7z', '.xz', '.zst', '.tar.gz', '.tar.bz2'
    }
    ext = os.path.splitext(filepath)[1].lower()
    if ext in archive_extensions:
        return True
    if filepath.lower().endswith('.tar.gz') or filepath.lower().endswith('.tar.bz2'):
        return True
    return False

# ========== CREDIT CARD EXTRACTION (YOUR LOGIC) ==========
def find_cards(text: str) -> List[str]:
    """Extract credit cards in format: name|number|expiry|cvv"""
    pattern = r'(.+?)\s*\|\s*(\d{16})\s*\|\s*(\d{1,2}/\d{4})\s*\|\s*(\d{3,4})'
    matches = re.findall(pattern, text)
    
    cards = []
    seen_cards = set()
    
    for match in matches:
        name = match[0].strip()
        card = match[1].strip()
        expiry = match[2].strip()
        cvv = match[3].strip()
        
        if card in seen_cards:
            continue
            
        try:
            month, year = expiry.split('/')
            year_int = int(year)
            if 2026 <= year_int <= 2032:
                formatted_card = f"{card}|{expiry}|{cvv}|{name}"
                cards.append(formatted_card)
                seen_cards.add(card)
        except:
            continue
            
    return cards

def extract_from_file(file_path: str) -> List[str]:
    """Extract cards from a text file"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            return find_cards(content)
    except:
        return []

def extract_from_zip(zip_path: str, password: str = None, session=None) -> List[str]:
    """Extract cards from zip file using libarchive"""
    cards = []
    skip_patterns = [
        'information.txt', 'join telegram.txt', 'join_telegram.txt',
        'telegram.txt', 'passwords.txt', 'history/', 'cookies/', 
        'Cookies/', 'cookie/', 'Cookie/'
    ]
    
    try:
        with libarchive.file_reader(zip_path) as archive:
            if session and session.stop_flag:
                return cards
                
            for entry in archive:
                if session and session.stop_flag:
                    break
                    
                entry_path = entry.pathname
                if entry_path.endswith('/'):
                    continue
                
                file_lower = entry_path.lower()
                path_parts = file_lower.split('/')
                
                # Check if in target folders
                in_target_folder = False
                for i in range(len(path_parts) - 1):
                    folder = path_parts[i]
                    if folder in ["autofill", "creditcards"]:
                        in_target_folder = True
                        break
                
                if not in_target_folder:
                    continue
                
                if not (file_lower.endswith('.txt') or file_lower.endswith('.log')):
                    continue
                
                should_skip = False
                for pattern in skip_patterns:
                    if pattern.lower() in file_lower:
                        should_skip = True
                        break
                
                if should_skip:
                    continue
                
                # Extract and read content
                try:
                    content = b''
                    for block in entry.get_blocks():
                        content += block
                    
                    if len(content) < 50:
                        continue
                    
                    text = content.decode('utf-8', errors='ignore')
                    file_cards = find_cards(text)
                    cards.extend(file_cards)
                    
                except Exception as e:
                    print(f"Error reading {entry_path}: {e}")
                    
    except Exception as e:
        print(f"Error in {os.path.basename(zip_path)}: {e}")
    
    return cards

# ========== COOKIE EXTRACTION (YOUR LOGIC) ==========
def extract_cookies_from_file(file_path: str, domains_to_search: List[str]) -> List[Dict]:
    """Extract cookies from a text file"""
    cookies = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
            lines = content.split('\n')
            cookie_entries = []
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split('\t')
                if len(parts) < 7:
                    parts = re.split(r'\s+', line)
                
                if len(parts) >= 7:
                    domain = parts[0].strip()
                    
                    for target_domain in domains_to_search:
                        if target_domain in domain.lower():
                            cookie_data = {
                                'domain': parts[0].strip(),
                                'flag': parts[1] if len(parts) > 1 else '',
                                'path': parts[2] if len(parts) > 2 else '',
                                'secure': parts[3] if len(parts) > 3 else '',
                                'expiration': parts[4] if len(parts) > 4 else '',
                                'name': parts[5] if len(parts) > 5 else '',
                                'value': parts[6] if len(parts) > 6 else '',
                                'source_file': file_path
                            }
                            cookie_entries.append(cookie_data)
                            break
            
            if not cookie_entries:
                for line in lines:
                    line_lower = line.lower()
                    if any(domain in line_lower for domain in domains_to_search):
                        cookie_data = {
                            'raw_line': line,
                            'source_file': file_path
                        }
                        cookie_entries.append(cookie_data)
            
            if cookie_entries:
                cookies.append({
                    'file': file_path,
                    'cookies': cookie_entries,
                    'domains_found': list(set(c['domain'] for c in cookie_entries if 'domain' in c))
                })
                    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    
    return cookies

def format_cookie(cookie_data: Dict, format_type: str) -> str:
    """Format cookie data for output"""
    if format_type == "JSON (Full Cookies)":
        return json.dumps(cookie_data, indent=2)
    elif format_type == "Netscape Format":
        result = []
        for cookie in cookie_data['cookies']:
            if 'domain' in cookie:
                line = f"{cookie.get('domain', '')}\t{cookie.get('flag', 'TRUE')}\t{cookie.get('path', '/')}\t{cookie.get('secure', 'FALSE')}\t{cookie.get('expiration', '0')}\t{cookie.get('name', '')}\t{cookie.get('value', '')}"
                result.append(line)
            else:
                result.append(cookie.get('raw_line', ''))
        return "\n".join(result)
    elif format_type == "Cookie String":
        result = []
        for cookie in cookie_data['cookies']:
            if 'name' in cookie and 'value' in cookie:
                result.append(f"{cookie['name']}={cookie['value']}")
        return "; ".join(result)
    else:  # Simple List
        result = []
        for cookie in cookie_data['cookies']:
            if 'raw_line' in cookie:
                result.append(cookie['raw_line'])
            elif 'domain' in cookie:
                result.append(f"Domain: {cookie['domain']} | Name: {cookie['name']} | Value: {cookie['value'][:30]}...")
        return "\n".join(result)

# ========== ULP EXTRACTION (YOUR LOGIC) ==========
def extract_ulp_from_file(file_path: str) -> List[str]:
    """Extract ULP (Host:Login:Password) from passwords.txt files"""
    ulps = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
            sections = content.split('\n\n')
            
            for section in sections:
                host = None
                login = None
                password = None
                
                lines = section.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('Host:'):
                        host = line.replace('Host:', '').strip()
                    elif line.startswith('Login:'):
                        login = line.replace('Login:', '').strip()
                    elif line.startswith('Password:'):
                        password = line.replace('Password:', '').strip()
                    elif line.startswith('Soft:'):
                        continue
                
                if host and login and password:
                    host = host.replace('https://', '').replace('http://', '').split('/')[0]
                    ulp_entry = f"{host}:{login}:{password}"
                    ulps.append(ulp_entry)
                    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    
    return ulps

# ========== PARALLEL PROCESSING FUNCTIONS ==========
def process_zip_file(zip_file: str, password: str = None, session=None) -> List[str]:
    """Process a single zip file for CC extraction"""
    if session and session.stop_flag:
        return []
    return extract_from_zip(zip_file, password, session)

def process_text_file_for_cc(file_path: str, session=None) -> List[str]:
    """Process a text file for CC extraction"""
    if session and session.stop_flag:
        return []
    return extract_from_file(file_path)

def process_text_file_for_cookies(file_path: str, domains: List[str], session=None) -> List[Dict]:
    """Process a text file for cookie extraction"""
    if session and session.stop_flag:
        return []
    return extract_cookies_from_file(file_path, domains)

def process_text_file_for_ulp(file_path: str, session=None) -> List[str]:
    """Process a text file for ULP extraction"""
    if session and session.stop_flag:
        return []
    return extract_ulp_from_file(file_path)

# ========== SCANNING FUNCTIONS ==========
async def scan_folder_for_cc(session: ExtractionSession) -> List[str]:
    """Scan folder for credit cards using parallel processing"""
    txt_files = []
    
    for root, dirs, files in os.walk(session.folder_path):
        rel_path = os.path.relpath(root, session.folder_path) if root != session.folder_path else ""
        path_parts = rel_path.split(os.sep) if rel_path else []
        
        if any(folder.lower() in ["autofill", "creditcards"] for folder in path_parts):
            for file in files:
                if file.lower().endswith('.txt'):
                    txt_files.append(os.path.join(root, file))
    
    folder_name = os.path.basename(session.folder_path).lower()
    if folder_name in ["autofill", "creditcards"]:
        for root, dirs, files in os.walk(session.folder_path):
            for file in files:
                if file.lower().endswith('.txt'):
                    txt_files.append(os.path.join(root, file))
    
    if not txt_files:
        return []
    
    session.total_files = len(txt_files)
    session.processed_files = 0
    
    # Process files in parallel
    loop = asyncio.get_event_loop()
    futures = []
    all_cards = []
    
    for txt_file in txt_files:
        if session.stop_flag:
            break
        future = loop.run_in_executor(executor, process_text_file_for_cc, txt_file, session)
        futures.append(future)
        
        # Update progress every 3 seconds
        current_time = time.time()
        if current_time - session.last_update_time >= 3:
            session.processed_files = len([f for f in futures if f.done()])
            await update_scan_progress(session)
            session.last_update_time = current_time
    
    # Wait for all to complete
    results = await asyncio.gather(*futures)
    for cards in results:
        all_cards.extend(cards)
        session.processed_files += 1
    
    return all_cards

async def scan_folder_for_cookies(session: ExtractionSession) -> tuple:
    """Scan folder for cookies using parallel processing"""
    txt_files = []
    
    for root, dirs, files in os.walk(session.folder_path):
        if os.path.basename(root).lower() == "cookies":
            for file in files:
                if file.lower().endswith('.txt'):
                    txt_files.append(os.path.join(root, file))
    
    if not txt_files:
        return [], []
    
    # Prepare domains
    domains_to_search = []
    if session.domains:
        domains_to_search = session.domains
    elif session.domain_list:
        domains_to_search = [d.lower().replace('http://', '').replace('https://', '').replace('www.', '') 
                            for d in session.domain_list]
    
    session.total_files = len(txt_files)
    session.processed_files = 0
    
    # Process files in parallel
    loop = asyncio.get_event_loop()
    futures = []
    all_cookies_data = []
    all_formatted = []
    
    for txt_file in txt_files:
        if session.stop_flag:
            break
        future = loop.run_in_executor(executor, process_text_file_for_cookies, txt_file, domains_to_search, session)
        futures.append(future)
        
        # Update progress every 3 seconds
        current_time = time.time()
        if current_time - session.last_update_time >= 3:
            session.processed_files = len([f for f in futures if f.done()])
            await update_scan_progress(session)
            session.last_update_time = current_time
    
    # Wait for all to complete
    results = await asyncio.gather(*futures)
    for cookies_list in results:
        if cookies_list:
            all_cookies_data.extend(cookies_list)
            for cookie_data in cookies_list:
                formatted = format_cookie(cookie_data, session.cookie_format)
                all_formatted.append(f"=== File: {os.path.basename(cookie_data['file'])} ===")
                all_formatted.append(formatted)
                all_formatted.append("")
        session.processed_files += 1
    
    return all_cookies_data, all_formatted

async def scan_folder_for_ulp(session: ExtractionSession) -> List[str]:
    """Scan folder for ULP using parallel processing"""
    txt_files = []
    
    for root, dirs, files in os.walk(session.folder_path):
        for file in files:
            if file.lower() == 'passwords.txt':
                txt_files.append(os.path.join(root, file))
    
    if not txt_files:
        return []
    
    session.total_files = len(txt_files)
    session.processed_files = 0
    
    # Process files in parallel
    loop = asyncio.get_event_loop()
    futures = []
    all_ulps = []
    
    for txt_file in txt_files:
        if session.stop_flag:
            break
        future = loop.run_in_executor(executor, process_text_file_for_ulp, txt_file, session)
        futures.append(future)
        
        # Update progress every 3 seconds
        current_time = time.time()
        if current_time - session.last_update_time >= 3:
            session.processed_files = len([f for f in futures if f.done()])
            await update_scan_progress(session)
            session.last_update_time = current_time
    
    # Wait for all to complete
    results = await asyncio.gather(*futures)
    for ulps in results:
        all_ulps.extend(ulps)
        session.processed_files += 1
    
    return all_ulps

async def update_scan_progress(session: ExtractionSession):
    """Update scan progress with 3-second intervals"""
    if session.status_message:
        try:
            await session.status_message.edit_text(
                f"🔍 **Scanning files...**\n"
                f"Progress: {session.processed_files}/{session.total_files}\n"
                f"Found: {len(session.results)} CC | {len(session.cookies_data)} Cookie files | {len(session.ulp_results)} ULP"
            )
        except:
            pass

# ========== BOT COMMAND HANDLERS ==========
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    welcome_text = """
**🔰 Welcome to Multi-Extractor Bot!**

I can extract from archives using your original extraction logic:
• **💳 Credit Cards** (from Autofill/CreditCards folders)
• **🍪 Cookies** (from cookies folders)
• **🔑 ULP** (Host:Login:Password from passwords.txt)

**How to use:**
1️⃣ Forward me any archive file (zip, rar, tar, etc.)
2️⃣ Choose extraction mode
3️⃣ Provide additional info if needed
4️⃣ Enter password if archive is protected
5️⃣ Get extracted data

**Features:**
✅ Your original extraction logic preserved
✅ libarchive for reliable extraction
✅ Parallel processing for speed
✅ 3-second progress updates
✅ Nested archive support

Forward an archive to get started!
    """
    
    await message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.document)
async def handle_document(client: Client, message: Message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    
    if not session:
        session = ExtractionSession(user_id, message)
        user_sessions[user_id] = session
    else:
        session.reset()
        session.original_message = message
    
    # Store file info
    session.archive_filename = message.document.file_name
    session.archive_size = message.document.file_size
    
    # Ask for extraction mode
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💳 Credit Cards", callback_data="mode_cc"),
            InlineKeyboardButton("🍪 Cookies", callback_data="mode_cookies"),
            InlineKeyboardButton("🔑 ULP", callback_data="mode_ulp")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])
    
    session.mode_selection_message = await message.reply_text(
        f"**📦 File:** `{session.archive_filename}`\n"
        f"**Size:** `{session.archive_size / 1024:.2f} KB`\n\n"
        "**Select extraction mode:**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query()
async def handle_callback(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    
    if not session:
        await callback.answer("Session expired! Send a new file.", show_alert=True)
        await callback.message.delete()
        return
    
    data = callback.data
    
    if data == "cancel":
        session.reset()
        if session.user_id in user_sessions:
            del user_sessions[user_id]
        await callback.message.edit_text("❌ Operation cancelled.")
        await callback.answer()
        return
    
    if data.startswith("mode_"):
        mode = data.replace("mode_", "")
        session.mode = mode
        
        if mode == "cookies":
            await callback.message.edit_text(
                "**🍪 Cookies Mode Selected**\n\n"
                "Please send the domain(s) to extract cookies for.\n"
                "You can send multiple domains separated by commas.\n\n"
                "Example: `udemy.com, coursera.org, skillshare.com`"
            )
            session.password_request_message = callback.message
        else:
            # Ask for password
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔐 Yes, it's password protected", callback_data="password_yes"),
                    InlineKeyboardButton("🔓 No password", callback_data="password_no")
                ],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ])
            
            await callback.message.edit_text(
                f"**{mode.upper()} Mode Selected**\n\n"
                "Is the archive password protected?",
                reply_markup=keyboard
            )
        
        await callback.answer()
    
    elif data.startswith("password_"):
        if data == "password_yes":
            await callback.message.edit_text(
                "🔐 **Please enter the archive password:**"
            )
            session.password_request_message = callback.message
        else:
            session.password = None
            await callback.message.delete()
            await start_extraction_process(client, session)
        
        await callback.answer()

@app.on_message(filters.text & filters.private)
async def handle_text(client: Client, message: Message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    
    if not session or not session.mode:
        await message.reply_text("Please send an archive file first!")
        return
    
    # Handle domain input for cookies mode
    if session.mode == "cookies" and not session.domains:
        domains_text = message.text
        domains = [d.strip().lower().replace('http://', '').replace('https://', '').replace('www.', '') 
                  for d in domains_text.split(',')]
        session.domains = domains
        
        await message.delete()
        
        # Ask for password
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔐 Yes, it's password protected", callback_data="password_yes"),
                InlineKeyboardButton("🔓 No password", callback_data="password_no")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
        
        await message.reply_text(
            f"✅ Domains set: {', '.join(domains[:5])}{'...' if len(domains) > 5 else ''}\n\n"
            "Is the archive password protected?",
            reply_markup=keyboard
        )
        
        if session.password_request_message:
            await session.password_request_message.delete()
    
    # Handle password input
    elif not session.password and session.password_request_message:
        session.password = message.text
        await message.delete()
        await session.password_request_message.delete()
        await start_extraction_process(client, session)

async def start_extraction_process(client: Client, session: ExtractionSession):
    """Start the extraction process with your original logic"""
    
    status_message = await client.send_message(
        session.user_id,
        "🚀 **Starting extraction process...**"
    )
    session.status_message = status_message
    session.start_time = time.time()
    session.last_update_time = time.time()
    
    try:
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, session.archive_filename)
        session.archive_path = file_path
        session.extract_path = os.path.join(temp_dir, "extracted")
        os.makedirs(session.extract_path, exist_ok=True)
        
        # Download file
        await status_message.edit_text("📥 **Downloading archive...**")
        
        if not session.original_message or not session.original_message.document:
            raise Exception("Original message with document not found")
        
        await client.download_media(
            session.original_message,
            file_name=file_path
        )
        
        # Extract archive with libarchive
        await status_message.edit_text("📦 **Extracting archive with libarchive...**")
        extracted_files = await extract_archive_with_libarchive(
            file_path, 
            session.extract_path, 
            session.password,
            session
        )
        
        # Process based on mode
        if session.mode == "cc":
            await status_message.edit_text("🔍 **Scanning for credit cards...**")
            
            # Find all text files in Autofill/CreditCards folders
            txt_files = []
            for root, dirs, files in os.walk(session.extract_path):
                path_parts = Path(root).parts
                if any(folder.lower() in ["autofill", "creditcards"] for folder in path_parts):
                    for file in files:
                        if file.lower().endswith(('.txt', '.log')):
                            txt_files.append(os.path.join(root, file))
            
            session.total_files = len(txt_files)
            session.processed_files = 0
            
            # Process files in parallel
            loop = asyncio.get_event_loop()
            futures = []
            
            for txt_file in txt_files:
                if session.stop_flag:
                    break
                future = loop.run_in_executor(executor, process_text_file_for_cc, txt_file, session)
                futures.append(future)
                
                # Update progress every 3 seconds
                current_time = time.time()
                if current_time - session.last_update_time >= 3:
                    session.processed_files = len([f for f in futures if f.done()])
                    await status_message.edit_text(
                        f"🔍 **Scanning for credit cards...**\n"
                        f"Progress: {session.processed_files}/{session.total_files}\n"
                        f"Found: {len(session.results)} cards"
                    )
                    session.last_update_time = current_time
            
            # Collect results
            results = await asyncio.gather(*futures)
            for cards in results:
                session.results.extend(cards)
            
            # Send results
            if session.results:
                output_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                with open(output_file.name, 'w', encoding='utf-8') as f:
                    f.write("="*60 + "\n")
                    f.write(f"CREDIT CARDS EXTRACTED\n")
                    f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Format: CARD|EXPIRY|CVV|HOLDER\n")
                    f.write(f"Total: {len(session.results)}\n")
                    f.write("="*60 + "\n\n")
                    f.write("\n".join(session.results))
                
                await client.send_document(
                    session.user_id,
                    output_file.name,
                    caption=f"💳 **Credit Cards Found:** {len(session.results)}\nValid years: 2026-2032"
                )
                os.unlink(output_file.name)
            else:
                await client.send_message(session.user_id, "❌ **No credit cards found!**")
        
        elif session.mode == "cookies":
            await status_message.edit_text("🔍 **Scanning for cookies...**")
            
            # Find all cookie files
            txt_files = []
            for root, dirs, files in os.walk(session.extract_path):
                if 'cookies' in Path(root).parts or os.path.basename(root).lower() == 'cookies':
                    for file in files:
                        if file.lower().endswith('.txt'):
                            txt_files.append(os.path.join(root, file))
            
            session.total_files = len(txt_files)
            session.processed_files = 0
            
            # Process files in parallel
            loop = asyncio.get_event_loop()
            futures = []
            
            for txt_file in txt_files:
                if session.stop_flag:
                    break
                future = loop.run_in_executor(executor, process_text_file_for_cookies, txt_file, session.domains, session)
                futures.append(future)
                
                # Update progress every 3 seconds
                current_time = time.time()
                if current_time - session.last_update_time >= 3:
                    session.processed_files = len([f for f in futures if f.done()])
                    await status_message.edit_text(
                        f"🔍 **Scanning for cookies...**\n"
                        f"Progress: {session.processed_files}/{session.total_files}\n"
                        f"Found: {len(session.cookies_data)} cookie files"
                    )
                    session.last_update_time = current_time
            
            # Collect results
            results = await asyncio.gather(*futures)
            for cookies_list in results:
                if cookies_list:
                    session.cookies_data.extend(cookies_list)
                    for cookie_data in cookies_list:
                        formatted = format_cookie(cookie_data, "Simple List")
                        session.cookie_results.append(f"=== File: {os.path.basename(cookie_data['file'])} ===")
                        session.cookie_results.append(formatted)
                        session.cookie_results.append("")
            
            # Send results
            if session.cookies_data:
                # Create a directory for cookie files
                cookies_dir = tempfile.mkdtemp()
                
                for i, cookie_data in enumerate(session.cookies_data):
                    filename = f"cookies_{i+1:03d}.txt"
                    filepath = os.path.join(cookies_dir, filename)
                    
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write("="*60 + "\n")
                        f.write(f"COOKIE EXTRACTION\n")
                        f.write(f"Source: {os.path.basename(cookie_data['file'])}\n")
                        f.write(f"Domains found: {', '.join(cookie_data['domains_found'])}\n")
                        f.write(f"Cookies: {len(cookie_data['cookies'])}\n")
                        f.write("="*60 + "\n\n")
                        f.write(format_cookie(cookie_data, "Simple List"))
                
                # Create zip file
                zip_path = tempfile.NamedTemporaryFile(suffix='.zip', delete=False).name
                with zipfile.ZipFile(zip_path, 'w') as zipf:
                    for root, dirs, files in os.walk(cookies_dir):
                        for file in files:
                            zipf.write(
                                os.path.join(root, file),
                                os.path.relpath(os.path.join(root, file), cookies_dir)
                            )
                
                total_cookies = sum(len(c['cookies']) for c in session.cookies_data)
                await client.send_document(
                    session.user_id,
                    zip_path,
                    caption=f"🍪 **Cookies Found:** {total_cookies} cookies from {len(session.cookies_data)} files"
                )
                
                os.unlink(zip_path)
                shutil.rmtree(cookies_dir)
            else:
                await client.send_message(session.user_id, "❌ **No cookies found for the specified domains!**")
        
        elif session.mode == "ulp":
            await status_message.edit_text("🔍 **Scanning for ULP entries...**")
            
            # Find all passwords.txt files
            txt_files = []
            for root, dirs, files in os.walk(session.extract_path):
                for file in files:
                    if file.lower() == 'passwords.txt':
                        txt_files.append(os.path.join(root, file))
            
            session.total_files = len(txt_files)
            session.processed_files = 0
            
            # Process files in parallel
            loop = asyncio.get_event_loop()
            futures = []
            
            for txt_file in txt_files:
                if session.stop_flag:
                    break
                future = loop.run_in_executor(executor, process_text_file_for_ulp, txt_file, session)
                futures.append(future)
                
                # Update progress every 3 seconds
                current_time = time.time()
                if current_time - session.last_update_time >= 3:
                    session.processed_files = len([f for f in futures if f.done()])
                    await status_message.edit_text(
                        f"🔍 **Scanning for ULP entries...**\n"
                        f"Progress: {session.processed_files}/{session.total_files}\n"
                        f"Found: {len(session.ulp_results)} entries"
                    )
                    session.last_update_time = current_time
            
            # Collect results
            results = await asyncio.gather(*futures)
            for ulps in results:
                session.ulp_results.extend(ulps)
            
            # Send results
            if session.ulp_results:
                output_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                with open(output_file.name, 'w', encoding='utf-8') as f:
                    f.write("="*60 + "\n")
                    f.write(f"ULP EXTRACTED\n")
                    f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Format: HOST:LOGIN:PASSWORD\n")
                    f.write(f"Total: {len(session.ulp_results)}\n")
                    f.write("="*60 + "\n\n")
                    f.write("\n".join(session.ulp_results))
                
                await client.send_document(
                    session.user_id,
                    output_file.name,
                    caption=f"🔑 **ULP Entries Found:** {len(session.ulp_results)}"
                )
                os.unlink(output_file.name)
            else:
                await client.send_message(session.user_id, "❌ **No ULP entries found!**")
        
        # Clean up
        await status_message.edit_text("✅ **Extraction complete! Cleaning up...**")
        
    except Exception as e:
        error_msg = str(e)
        print(f"Extraction error: {error_msg}")
        await client.send_message(
            session.user_id,
            f"❌ **Error during extraction:**\n`{error_msg[:200]}`"
        )
    
    finally:
        # Clean up session
        elapsed_time = time.time() - session.start_time if session.start_time else 0
        await client.send_message(
            session.user_id,
            f"✅ **Process completed in {elapsed_time:.1f} seconds!**"
        )
        session.reset()
        if session.user_id in user_sessions:
            del user_sessions[session.user_id]

@app.on_message(filters.command("stats"))
async def stats_command(client: Client, message: Message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    
    if session and session.total_files > 0:
        elapsed = time.time() - session.start_time if session.start_time else 0
        stats_text = f"""
**📊 Current Extraction Stats:**

• Mode: {session.mode.upper() if session.mode else 'None'}
• Files Processed: {session.processed_files}/{session.total_files}
• Results Found:
  - CC: {len(session.results)}
  - Cookies: {len(session.cookies_data)} files ({sum(len(c['cookies']) for c in session.cookies_data) if session.cookies_data else 0} total)
  - ULP: {len(session.ulp_results)}
• Time Elapsed: {elapsed:.1f}s
• Status: {'🔄 Running' if not session.stop_flag else '⏹ Stopped'}
        """
    else:
        stats_text = "**No active extraction session.**"
    
    await message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    
    if session:
        session.stop_flag = True
        session.reset()
        if session.user_id in user_sessions:
            del user_sessions[user_id]
        await message.reply_text("✅ **Extraction cancelled and cleaned up.**")
    else:
        await message.reply_text("No active extraction to cancel.")

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    help_text = """
**🔰 Multi-Extractor Bot Help**

**Commands:**
• `/start` - Welcome message
• `/help` - Show this help
• `/stats` - Show current extraction stats
• `/cancel` - Cancel current extraction

**Extraction Modes:**

1️⃣ **💳 Credit Cards**
   - Searches in Autofill/CreditCards folders
   - Format: NAME|CARD|EXPIRY|CVV
   - Valid years: 2026-2032

2️⃣ **🍪 Cookies**
   - Searches in 'cookies' folders
   - Extracts cookies for specified domains
   - Returns formatted cookie files

3️⃣ **🔑 ULP**
   - Searches for passwords.txt files
   - Extracts Host:Login:Password
   - Skips software lines

**Features:**
✅ Your original extraction logic preserved
✅ libarchive for reliable extraction
✅ Parallel processing for speed
✅ 3-second progress updates
✅ Nested archive support
✅ Auto-cleanup

Send an archive to get started!
    """
    
    await message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

if __name__ == "__main__":
    print("🚀 Starting Multi-Extractor Bot with your original logic...")
    print(f"⚡ Using {os.cpu_count() * 2} threads for parallel processing")
    print("⏱️ Progress updates every 3 seconds")
    print("📦 Using libarchive for extraction")
    print("🤖 Bot is running...")
    
    app.run()
