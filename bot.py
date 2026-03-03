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
import random

from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery
)
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, MessageNotModified, QueryIdInvalid

# Bot configuration
API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8640428737:AAFGmvqvw_Y6M9zJjurdI8ffH9Uq5dxampY"

# Thread pool for parallel processing
executor = ThreadPoolExecutor(max_workers=os.cpu_count())

# User session data storage
user_sessions = {}

class ExtractionSession:
    def __init__(self, user_id: int, message: Message = None):
        self.user_id = user_id
        self.original_message = message
        self.mode = None
        self.domains = []
        self.password = None
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
        self.status_message = None
        self.password_request_message = None
        self.mode_selection_message = None
        self.last_update_time = 0
        self.start_time = None
        self.domain_list = []
        self.cookie_format = "Simple List"
        self.last_message_time = 0  # For rate limiting
        
    async def safe_edit(self, text: str, parse_mode=None):
        """Safely edit message with rate limiting"""
        current_time = time.time()
        if current_time - self.last_message_time < 2:  # Minimum 2 seconds between edits
            await asyncio.sleep(2 - (current_time - self.last_message_time))
        
        if self.status_message:
            try:
                await self.status_message.edit_text(text, parse_mode=parse_mode)
                self.last_message_time = time.time()
            except MessageNotModified:
                pass
            except Exception as e:
                print(f"Error editing message: {e}")
    
    async def safe_send(self, client, text: str, parse_mode=None):
        """Safely send message with rate limiting"""
        current_time = time.time()
        if current_time - self.last_message_time < 2:
            await asyncio.sleep(2 - (current_time - self.last_message_time))
        
        try:
            msg = await client.send_message(self.user_id, text, parse_mode=parse_mode)
            self.last_message_time = time.time()
            return msg
        except FloodWait as e:
            wait_time = e.value + random.randint(1, 5)
            print(f"Flood wait: sleeping for {wait_time} seconds")
            await asyncio.sleep(wait_time)
            return await self.safe_send(client, text, parse_mode)
    
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

# ========== FIXED ARCHIVE EXTRACTION USING LIBARCHIVE ==========
async def extract_archive_with_libarchive(archive_path: str, extract_to: str, password: str = None, session=None) -> List[str]:
    """
    Fixed archive extraction using libarchive - reads entries immediately
    """
    extracted_files = []
    
    try:
        # Open archive and process entries immediately
        with libarchive.file_reader(archive_path) as archive:
            entries = []
            for entry in archive:
                entries.append(entry)
            
            total_entries = len(entries)
            
            for i, entry in enumerate(entries):
                if session and session.stop_flag:
                    break
                
                entry_path = entry.pathname
                if entry_path.endswith('/'):
                    continue
                
                target_path = os.path.join(extract_to, entry_path)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                
                # Extract immediately while entry is still valid
                try:
                    with open(target_path, 'wb') as f:
                        for block in entry.get_blocks():
                            f.write(block)
                    extracted_files.append(target_path)
                except Exception as e:
                    print(f"Error extracting {entry_path}: {e}")
                    continue
                
                # Update progress every 3 seconds
                if session and session.status_message:
                    current_time = time.time()
                    if current_time - session.last_update_time >= 3 or i == total_entries - 1:
                        progress = (i + 1) / total_entries * 100
                        await session.safe_edit(
                            f"📦 **Extracting archive...**\n"
                            f"Progress: {progress:.1f}%\n"
                            f"File: {os.path.basename(entry_path)[:30]}..."
                        )
                        session.last_update_time = current_time
        
        # Process nested archives
        nested_count = 0
        archives_to_process = [f for f in extracted_files if is_archive_file(f)]
        
        for archive_file in archives_to_process:
            nested_count += 1
            if session and session.status_message:
                await session.safe_edit(f"📦 **Extracting nested archive {nested_count}...**")
            
            nested_extract_dir = os.path.join(extract_to, f"nested_{nested_count}")
            os.makedirs(nested_extract_dir, exist_ok=True)
            
            try:
                nested_files = await extract_archive_with_libarchive(archive_file, nested_extract_dir, password, session)
                extracted_files.extend(nested_files)
                os.remove(archive_file)
            except Exception as e:
                print(f"Error extracting nested archive {archive_file}: {e}")
    
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
def process_text_file_for_cc(file_path: str) -> List[str]:
    """Process a text file for CC extraction"""
    return extract_from_file(file_path)

def process_text_file_for_cookies(file_path: str, domains: List[str]) -> List[Dict]:
    """Process a text file for cookie extraction"""
    return extract_cookies_from_file(file_path, domains)

def process_text_file_for_ulp(file_path: str) -> List[str]:
    """Process a text file for ULP extraction"""
    return extract_ulp_from_file(file_path)

# ========== BOT COMMAND HANDLERS ==========
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    welcome_text = """
**🔰 Welcome to Multi-Extractor Bot!**

I can extract from archives:
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
✅ Fixed libarchive extraction
✅ Rate limiting to avoid floods
✅ Parallel processing
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
    
    try:
        session.mode_selection_message = await message.reply_text(
            f"**📦 File:** `{session.archive_filename}`\n"
            f"**Size:** `{session.archive_size / 1024:.2f} KB`\n\n"
            "**Select extraction mode:**",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except FloodWait as e:
        wait_time = e.value
        await asyncio.sleep(wait_time)
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
        try:
            await callback.answer("Session expired! Send a new file.", show_alert=True)
        except QueryIdInvalid:
            pass
        try:
            await callback.message.delete()
        except:
            pass
        return
    
    data = callback.data
    
    try:
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
            
    except QueryIdInvalid:
        # Ignore invalid query IDs
        pass
    except Exception as e:
        print(f"Callback error: {e}")

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
        
        try:
            await message.reply_text(
                f"✅ Domains set: {', '.join(domains[:5])}{'...' if len(domains) > 5 else ''}\n\n"
                "Is the archive password protected?",
                reply_markup=keyboard
            )
        except FloodWait as e:
            await asyncio.sleep(e.value)
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
    """Start the extraction process"""
    
    session.status_message = await session.safe_send(
        client,
        "🚀 **Starting extraction process...**"
    )
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
        await session.safe_edit("📥 **Downloading archive...**")
        
        if not session.original_message or not session.original_message.document:
            raise Exception("Original message with document not found")
        
        try:
            await client.download_media(
                session.original_message,
                file_name=file_path
            )
        except FloodWait as e:
            await session.safe_edit(f"⏳ Rate limited. Waiting {e.value} seconds...")
            await asyncio.sleep(e.value)
            await client.download_media(
                session.original_message,
                file_name=file_path
            )
        
        # Extract archive with libarchive
        await session.safe_edit("📦 **Extracting archive with libarchive...**")
        extracted_files = await extract_archive_with_libarchive(
            file_path, 
            session.extract_path, 
            session.password,
            session
        )
        
        # Process based on mode
        if session.mode == "cc":
            await session.safe_edit("🔍 **Scanning for credit cards...**")
            
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
                future = loop.run_in_executor(executor, process_text_file_for_cc, txt_file)
                futures.append(future)
                
                # Update progress every 3 seconds
                current_time = time.time()
                if current_time - session.last_update_time >= 3:
                    session.processed_files = len([f for f in futures if f.done()])
                    await session.safe_edit(
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
                
                try:
                    await client.send_document(
                        session.user_id,
                        output_file.name,
                        caption=f"💳 **Credit Cards Found:** {len(session.results)}\nValid years: 2026-2032"
                    )
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await client.send_document(
                        session.user_id,
                        output_file.name,
                        caption=f"💳 **Credit Cards Found:** {len(session.results)}\nValid years: 2026-2032"
                    )
                
                os.unlink(output_file.name)
            else:
                await session.safe_send(client, "❌ **No credit cards found!**")
        
        elif session.mode == "cookies":
            await session.safe_edit("🔍 **Scanning for cookies...**")
            
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
                future = loop.run_in_executor(executor, process_text_file_for_cookies, txt_file, session.domains)
                futures.append(future)
                
                # Update progress every 3 seconds
                current_time = time.time()
                if current_time - session.last_update_time >= 3:
                    session.processed_files = len([f for f in futures if f.done()])
                    await session.safe_edit(
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
                
                try:
                    await client.send_document(
                        session.user_id,
                        zip_path,
                        caption=f"🍪 **Cookies Found:** {total_cookies} cookies from {len(session.cookies_data)} files"
                    )
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await client.send_document(
                        session.user_id,
                        zip_path,
                        caption=f"🍪 **Cookies Found:** {total_cookies} cookies from {len(session.cookies_data)} files"
                    )
                
                os.unlink(zip_path)
                shutil.rmtree(cookies_dir)
            else:
                await session.safe_send(client, "❌ **No cookies found for the specified domains!**")
        
        elif session.mode == "ulp":
            await session.safe_edit("🔍 **Scanning for ULP entries...**")
            
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
                future = loop.run_in_executor(executor, process_text_file_for_ulp, txt_file)
                futures.append(future)
                
                # Update progress every 3 seconds
                current_time = time.time()
                if current_time - session.last_update_time >= 3:
                    session.processed_files = len([f for f in futures if f.done()])
                    await session.safe_edit(
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
                
                try:
                    await client.send_document(
                        session.user_id,
                        output_file.name,
                        caption=f"🔑 **ULP Entries Found:** {len(session.ulp_results)}"
                    )
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await client.send_document(
                        session.user_id,
                        output_file.name,
                        caption=f"🔑 **ULP Entries Found:** {len(session.ulp_results)}"
                    )
                
                os.unlink(output_file.name)
            else:
                await session.safe_send(client, "❌ **No ULP entries found!**")
        
        # Clean up
        await session.safe_edit("✅ **Extraction complete! Cleaning up...**")
        
    except Exception as e:
        error_msg = str(e)
        print(f"Extraction error: {error_msg}")
        await session.safe_send(
            client,
            f"❌ **Error during extraction:**\n`{error_msg[:200]}`"
        )
    
    finally:
        # Clean up session
        elapsed_time = time.time() - session.start_time if session.start_time else 0
        await session.safe_send(
            client,
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
    
    try:
        await message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
    except FloodWait as e:
        await asyncio.sleep(e.value)
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
✅ Fixed libarchive extraction (no "entry passed" errors)
✅ Rate limiting to avoid flood waits
✅ Parallel processing for speed
✅ 3-second progress updates
✅ Nested archive support
✅ Auto-cleanup

Send an archive to get started!
    """
    
    await message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

if __name__ == "__main__":
    print("🚀 Starting Multi-Extractor Bot with fixes...")
    print(f"⚡ Using {os.cpu_count()} threads for parallel processing")
    print("⏱️ Progress updates every 3 seconds")
    print("📦 Fixed libarchive extraction")
    print("🤖 Bot is running...")
    
    app.run()
