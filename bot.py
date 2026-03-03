import os
import re
import json
import asyncio
import tempfile
import shutil
from datetime import datetime
from typing import List, Dict, Set, Optional
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
import libarchive

# Configuration
API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8640428737:AAGgJLvjGsIkt9L-hCsj-CeOfUzxBEvtJoM"  # Replace with your bot token

app = Client("multi_extractor_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# User session storage
user_sessions = {}

class ExtractorSession:
    def __init__(self, user_id):
        self.user_id = user_id
        self.archive_path = None
        self.extract_path = None
        self.modes = []
        self.domains = []
        self.password = None
        self.use_password = False
        self.results = {
            "cc": [],
            "cookies": [],
            "ulp": []
        }
        self.total_files = 0
        self.processed_files = 0
        self.current_stage = "waiting"  # waiting, extracting, processing, complete
        
    def cleanup(self):
        """Clean up temporary files"""
        if self.extract_path and os.path.exists(self.extract_path):
            shutil.rmtree(self.extract_path, ignore_errors=True)
        if self.archive_path and os.path.exists(self.archive_path):
            os.remove(self.archive_path)

# Helper functions for extraction
def extract_nested_archive(archive_path: str, extract_to: str, password: str = None) -> List[str]:
    """
    Recursively extract archives using libarchive-c
    Returns list of all extracted file paths
    """
    extracted_files = []
    
    def extract_with_libarchive(source_path, target_dir, pwd=None):
        nonlocal extracted_files
        try:
            # Open archive with optional password
            flags = 0
            if pwd:
                # For password-protected archives
                with libarchive.stream_reader(source_path, password=pwd.encode()) as archive:
                    for entry in archive:
                        entry_path = os.path.join(target_dir, entry.pathname)
                        os.makedirs(os.path.dirname(entry_path), exist_ok=True)
                        
                        if entry.isdir:
                            os.makedirs(entry_path, exist_ok=True)
                        else:
                            with open(entry_path, 'wb') as f:
                                for block in entry.get_blocks():
                                    f.write(block)
                            extracted_files.append(entry_path)
            else:
                # For archives without password
                with libarchive.stream_reader(source_path) as archive:
                    for entry in archive:
                        entry_path = os.path.join(target_dir, entry.pathname)
                        os.makedirs(os.path.dirname(entry_path), exist_ok=True)
                        
                        if entry.isdir:
                            os.makedirs(entry_path, exist_ok=True)
                        else:
                            with open(entry_path, 'wb') as f:
                                for block in entry.get_blocks():
                                    f.write(block)
                            extracted_files.append(entry_path)
        except Exception as e:
            print(f"Extraction error: {e}")
            raise
    
    # First extraction
    temp_dir = os.path.join(extract_to, "level_0")
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        extract_with_libarchive(archive_path, temp_dir, password)
    except Exception as e:
        print(f"Failed to extract main archive: {e}")
        return []
    
    # Check for nested archives
    archive_extensions = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.tgz', '.tbz2'}
    processed = set()
    
    while True:
        found_new = False
        current_files = [f for f in extracted_files if f not in processed]
        
        for file_path in current_files:
            processed.add(file_path)
            ext = os.path.splitext(file_path)[1].lower()
            
            # Check if it's an archive
            if ext in archive_extensions or any(file_path.endswith(ae) for ae in archive_extensions):
                try:
                    nested_dir = os.path.join(extract_to, f"nested_{len(processed)}")
                    os.makedirs(nested_dir, exist_ok=True)
                    
                    # Try to extract nested archive
                    extract_with_libarchive(file_path, nested_dir, password)
                    found_new = True
                    
                    # Add newly extracted files to list
                    for root, _, files in os.walk(nested_dir):
                        for f in files:
                            new_path = os.path.join(root, f)
                            if new_path not in extracted_files:
                                extracted_files.append(new_path)
                except Exception as e:
                    print(f"Skipping nested archive {file_path}: {e}")
        
        if not found_new:
            break
    
    return extracted_files

def find_cc_in_file(file_path: str) -> List[str]:
    """Extract credit card information from file"""
    cc_pattern = r'(.+?)\s*\|\s*(\d{16})\s*\|\s*(\d{1,2}/\d{4})\s*\|\s*(\d{3,4})'
    cards = []
    seen_cards = set()
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        matches = re.findall(cc_pattern, content)
        
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
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        
    return cards

def find_cookies_in_file(file_path: str, domains: List[str]) -> List[Dict]:
    """Extract cookies for specific domains from file"""
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
            
            # Try to parse cookie format
            parts = line.split('\t')
            if len(parts) < 7:
                parts = re.split(r'\s+', line)
            
            if len(parts) >= 7:
                domain = parts[0].strip()
                
                for target_domain in domains:
                    if target_domain.lower() in domain.lower():
                        cookie_data = {
                            'domain': domain,
                            'flag': parts[1] if len(parts) > 1 else '',
                            'path': parts[2] if len(parts) > 2 else '',
                            'secure': parts[3] if len(parts) > 3 else '',
                            'expiration': parts[4] if len(parts) > 4 else '',
                            'name': parts[5] if len(parts) > 5 else '',
                            'value': parts[6] if len(parts) > 6 else '',
                        }
                        cookie_entries.append(cookie_data)
                        break
            
            # Check for domain in raw line if not parsed
            elif any(domain in line.lower() for domain in domains):
                cookie_entries.append({'raw_line': line})
        
        if cookie_entries:
            cookies.append({
                'file': os.path.basename(file_path),
                'cookies': cookie_entries,
                'domains_found': list(set(c.get('domain', '') for c in cookie_entries if 'domain' in c))
            })
            
    except Exception as e:
        print(f"Error reading cookies from {file_path}: {e}")
        
    return cookies

def find_ulp_in_file(file_path: str) -> List[str]:
    """Extract ULP (Host:Login:Password) from file"""
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
            
            if host and login and password:
                host = host.replace('https://', '').replace('http://', '').split('/')[0]
                ulp_entry = f"{host}:{login}:{password}"
                ulps.append(ulp_entry)
                
    except Exception as e:
        print(f"Error reading ULP from {file_path}: {e}")
        
    return ulps

def should_process_file(file_path: str, mode: str) -> bool:
    """Determine if file should be processed based on mode"""
    file_lower = file_path.lower()
    
    if mode == "cc":
        # Check if file is in Autofill or CreditCards folders
        path_parts = file_path.split(os.sep)
        for i, part in enumerate(path_parts):
            if part.lower() in ["autofill", "creditcards"]:
                return True
        return False
    
    elif mode == "cookies":
        # Check if file is in cookies folder
        path_parts = file_path.split(os.sep)
        return any(part.lower() == "cookies" for part in path_parts[:-1])
    
    elif mode == "ulp":
        # Check if file is named passwords.txt
        return os.path.basename(file_path).lower() == "passwords.txt"
    
    return False

# Bot command handlers
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    welcome_text = """
    🔥 **Multi-Extractor Bot** 🔥
    
    Send me any archive file (ZIP, RAR, 7Z, TAR, etc.) and I'll extract:
    • 💳 Credit Cards (from Autofill/CreditCards folders)
    • 🍪 Cookies (from cookies folders)
    • 🔑 ULP (Host:Login:Password from passwords.txt)
    
    **Features:**
    • Supports password-protected archives
    • Handles nested archives recursively
    • Progress tracking
    • Clean extraction results
    
    Just forward or upload an archive to get started!
    """
    await message.reply(welcome_text)

@app.on_message(filters.document)
async def handle_document(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Check if it's an archive
    file_name = message.document.file_name.lower()
    archive_extensions = ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.tgz', '.tbz2']
    
    if not any(file_name.endswith(ext) for ext in archive_extensions):
        await message.reply("❌ Please send an archive file (ZIP, RAR, 7Z, TAR, etc.)")
        return
    
    # Create session
    if user_id in user_sessions:
        user_sessions[user_id].cleanup()
    
    session = ExtractorSession(user_id)
    user_sessions[user_id] = session
    
    # Download archive
    status_msg = await message.reply("📥 Downloading archive...")
    
    temp_dir = tempfile.mkdtemp()
    archive_path = os.path.join(temp_dir, message.document.file_name)
    
    try:
        await message.download(archive_path)
        session.archive_path = archive_path
        session.extract_path = os.path.join(temp_dir, "extracted")
        os.makedirs(session.extract_path, exist_ok=True)
        
        await status_msg.delete()
        
        # Ask for extraction mode
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Credit Cards Only", callback_data="mode_cc")],
            [InlineKeyboardButton("🍪 Cookies Only", callback_data="mode_cookies")],
            [InlineKeyboardButton("🔑 ULP Only", callback_data="mode_ulp")],
            [InlineKeyboardButton("📦 All Modes", callback_data="mode_all")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
        
        await message.reply(
            "🔍 **Select extraction mode:**\n\n"
            "• CC: Credit cards from Autofill/CreditCards folders\n"
            "• Cookies: Cookies from cookies folders\n"
            "• ULP: Host:Login:Password from passwords.txt",
            reply_markup=keyboard
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)[:100]}")
        session.cleanup()
        del user_sessions[user_id]

@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if user_id not in user_sessions:
        await callback_query.answer("Session expired! Please send a new archive.")
        await callback_query.message.delete()
        return
    
    session = user_sessions[user_id]
    
    if data == "cancel":
        await callback_query.answer("Cancelled")
        await callback_query.message.edit_text("❌ Extraction cancelled")
        session.cleanup()
        del user_sessions[user_id]
        return
    
    if data.startswith("mode_"):
        mode = data.replace("mode_", "")
        
        if mode == "all":
            session.modes = ["cc", "cookies", "ulp"]
        else:
            session.modes = [mode]
        
        # Check if cookies mode is selected and ask for domains
        if "cookies" in session.modes:
            await callback_query.message.edit_text(
                "🌐 **Enter domains to search for cookies**\n\n"
                "Separate multiple domains with commas\n"
                "Example: `udemy.com, facebook.com, instagram.com`\n\n"
                "Or type `skip` to continue without domain filtering"
            )
            session.current_stage = "awaiting_domains"
            await callback_query.answer()
            return
        
        # Ask for password
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, it's password protected", callback_data="password_yes")],
            [InlineKeyboardButton("❌ No password", callback_data="password_no")]
        ])
        
        await callback_query.message.edit_text(
            "🔐 **Is the archive password protected?**",
            reply_markup=keyboard
        )
        await callback_query.answer()
    
    elif data == "password_yes":
        await callback_query.message.edit_text(
            "🔑 **Please enter the archive password:**\n\n"
            "Send it as a text message"
        )
        session.use_password = True
        session.current_stage = "awaiting_password"
        await callback_query.answer()
    
    elif data == "password_no":
        session.use_password = False
        session.password = None
        await callback_query.answer()
        await callback_query.message.delete()
        
        # Start extraction
        await start_extraction(callback_query.message, session)

@app.on_message(filters.text & filters.private)
async def handle_text(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        await message.reply("Please send an archive first!")
        return
    
    session = user_sessions[user_id]
    
    if session.current_stage == "awaiting_domains":
        text = message.text.strip()
        
        if text.lower() == "skip":
            session.domains = []
        else:
            # Parse domains
            domains = [d.strip().lower() for d in text.split(',')]
            domains = [d.replace('http://', '').replace('https://', '').replace('www.', '') for d in domains]
            session.domains = domains
        
        # Ask for password
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, it's password protected", callback_data="password_yes")],
            [InlineKeyboardButton("❌ No password", callback_data="password_no")]
        ])
        
        await message.reply(
            "🔐 **Is the archive password protected?**",
            reply_markup=keyboard
        )
        session.current_stage = "waiting"
        
    elif session.current_stage == "awaiting_password":
        session.password = message.text.strip()
        await message.reply("✅ Password received! Starting extraction...")
        
        # Start extraction
        await start_extraction(message, session)

async def start_extraction(message: Message, session: ExtractorSession):
    """Start the extraction process"""
    user_id = message.chat.id
    
    # Send progress message
    progress_msg = await message.reply("🔄 **Starting extraction...**")
    
    try:
        # Extract archive with nested handling
        await progress_msg.edit_text("📦 **Extracting archive (this may take a while)...**")
        
        extracted_files = extract_nested_archive(
            session.archive_path,
            session.extract_path,
            session.password if session.use_password else None
        )
        
        if not extracted_files:
            await progress_msg.edit_text("❌ No files extracted or wrong password!")
            session.cleanup()
            del user_sessions[user_id]
            return
        
        session.total_files = len(extracted_files)
        
        # Process files based on selected modes
        await progress_msg.edit_text("🔍 **Processing extracted files...**")
        
        cc_results = []
        cookie_results = []
        ulp_results = []
        
        for i, file_path in enumerate(extracted_files):
            session.processed_files = i + 1
            
            # Update progress every 10 files
            if i % 10 == 0:
                await progress_msg.edit_text(
                    f"🔍 **Processing files...**\n\n"
                    f"Progress: {i}/{session.total_files}\n"
                    f"Found: {len(cc_results)} CC | {len(cookie_results)} Cookie files | {len(ulp_results)} ULP"
                )
            
            # Check if file is a text file
            if not file_path.lower().endswith('.txt'):
                continue
            
            # Process based on modes
            if "cc" in session.modes and should_process_file(file_path, "cc"):
                cards = find_cc_in_file(file_path)
                cc_results.extend(cards)
                session.results["cc"].extend(cards)
            
            if "cookies" in session.modes and should_process_file(file_path, "cookies"):
                if session.domains:
                    cookies = find_cookies_in_file(file_path, session.domains)
                else:
                    # If no domains specified, extract all cookies
                    cookies = find_cookies_in_file(file_path, [""])  # Empty string matches all
                
                if cookies:
                    cookie_results.extend(cookies)
                    session.results["cookies"].extend(cookies)
            
            if "ulp" in session.modes and should_process_file(file_path, "ulp"):
                ulps = find_ulp_in_file(file_path)
                ulp_results.extend(ulps)
                session.results["ulp"].extend(ulps)
        
        # Prepare results
        await progress_msg.delete()
        
        if not any(session.results.values()):
            await message.reply("❌ No data found matching your criteria!")
            session.cleanup()
            del user_sessions[user_id]
            return
        
        # Send results
        await send_results(message, session)
        
    except Exception as e:
        await message.reply(f"❌ Error during extraction: {str(e)[:200]}")
        session.cleanup()
        del user_sessions[user_id]

async def send_results(message: Message, session: ExtractorSession):
    """Send extraction results to user"""
    results_text = []
    
    # CC Results
    if session.results["cc"]:
        cc_text = "💳 **CREDIT CARDS FOUND**\n" + "="*30 + "\n"
        cc_text += f"Total: {len(session.results['cc'])}\n\n"
        
        # Show first 50 cards
        for i, card in enumerate(session.results["cc"][:50]):
            cc_text += f"{i+1}. `{card}`\n"
        
        if len(session.results["cc"]) > 50:
            cc_text += f"\n... and {len(session.results['cc']) - 50} more"
        
        results_text.append(cc_text)
    
    # Cookie Results
    if session.results["cookies"]:
        cookie_text = "🍪 **COOKIES FOUND**\n" + "="*30 + "\n"
        cookie_text += f"Cookie files with matches: {len(session.results['cookies'])}\n"
        
        total_cookies = sum(len(c['cookies']) for c in session.results['cookies'])
        cookie_text += f"Total cookie entries: {total_cookies}\n\n"
        
        # Show summary
        for i, cookie_data in enumerate(session.results['cookies'][:10]):
            domains = ', '.join(cookie_data.get('domains_found', ['Unknown'])[:3])
            cookie_text += f"📁 {cookie_data['file']}\n"
            cookie_text += f"   Domains: {domains}\n"
            cookie_text += f"   Cookies: {len(cookie_data['cookies'])}\n\n"
        
        if len(session.results['cookies']) > 10:
            cookie_text += f"... and {len(session.results['cookies']) - 10} more files\n"
        
        results_text.append(cookie_text)
    
    # ULP Results
    if session.results["ulp"]:
        ulp_text = "🔑 **ULP FOUND (Host:Login:Password)**\n" + "="*30 + "\n"
        ulp_text += f"Total: {len(session.results['ulp'])}\n\n"
        
        # Show first 50 ULPs
        for i, ulp in enumerate(session.results["ulp"][:50]):
            ulp_text += f"{i+1}. `{ulp}`\n"
        
        if len(session.results["ulp"]) > 50:
            ulp_text += f"\n... and {len(session.results['ulp']) - 50} more"
        
        results_text.append(ulp_text)
    
    # Send summary
    summary = "📊 **EXTRACTION SUMMARY**\n" + "="*30 + "\n"
    summary += f"✅ Credit Cards: {len(session.results['cc'])}\n"
    summary += f"✅ Cookie Files: {len(session.results['cookies'])}\n"
    summary += f"✅ ULP Entries: {len(session.results['ulp'])}\n\n"
    
    await message.reply(summary)
    
    # Send detailed results in chunks
    for text in results_text:
        if len(text) > 4096:
            # Split long messages
            for i in range(0, len(text), 4096):
                await message.reply(text[i:i+4096])
        else:
            await message.reply(text)
    
    # Offer to send files
    if session.results["cc"]:
        cc_file = os.path.join(tempfile.gettempdir(), f"cc_results_{user_id}.txt")
        with open(cc_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(session.results["cc"]))
        await message.reply_document(cc_file, caption="💳 Credit Cards")
        os.remove(cc_file)
    
    if session.results["cookies"]:
        cookie_file = os.path.join(tempfile.gettempdir(), f"cookie_results_{user_id}.txt")
        with open(cookie_file, 'w', encoding='utf-8') as f:
            for cookie_data in session.results["cookies"]:
                f.write(f"\n=== {cookie_data['file']} ===\n")
                for cookie in cookie_data['cookies']:
                    f.write(json.dumps(cookie) + "\n")
        await message.reply_document(cookie_file, caption="🍪 Cookies")
        os.remove(cookie_file)
    
    if session.results["ulp"]:
        ulp_file = os.path.join(tempfile.gettempdir(), f"ulp_results_{user_id}.txt")
        with open(ulp_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(session.results["ulp"]))
        await message.reply_document(ulp_file, caption="🔑 ULP")
        os.remove(ulp_file)
    
    # Cleanup
    session.cleanup()
    del user_sessions[user_id]

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    help_text = """
    **📚 Help & Commands**
    
    **How to use:**
    1. Send me any archive file (ZIP, RAR, 7Z, etc.)
    2. Select extraction mode (CC, Cookies, ULP, or All)
    3. If needed, enter domains for cookie extraction
    4. Provide password if archive is protected
    5. Wait for extraction and results
    
    **Supported archives:**
    • ZIP, RAR, 7Z, TAR
    • GZ, BZ2, XZ
    • Nested archives supported
    
    **Extraction rules:**
    • 💳 **Credit Cards**: Looks in Autofill/CreditCards folders
    • 🍪 **Cookies**: Looks in cookies folders, filters by domains
    • 🔑 **ULP**: Looks for passwords.txt files
    
    **Commands:**
    /start - Start the bot
    /help - Show this help
    /cancel - Cancel current operation
    """
    await message.reply(help_text)

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id in user_sessions:
        user_sessions[user_id].cleanup()
        del user_sessions[user_id]
        await message.reply("✅ Current operation cancelled")
    else:
        await message.reply("No active operation to cancel")

# Start the bot
if __name__ == "__main__":
    print("🚀 Starting Multi-Extractor Bot...")
    print("📦 Using libarchive-c for extraction")
    print("🔍 Features: CC | Cookies | ULP")
    app.run()
