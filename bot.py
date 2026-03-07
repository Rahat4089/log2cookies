import os
import re
import asyncio
import tempfile
import shutil
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
import patoolib
from patoolib.util import PatoolError
import zipfile
import rarfile
import py7zr

# Configuration
API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8640428737:AAEGIaJWxm9dMFBcM2aKTrbgE8Oo47aQdvk"

# Create downloads directory if not exists
os.makedirs("downloads", exist_ok=True)
os.makedirs("temp_extract", exist_ok=True)

app = Client("extractor_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# User session storage
user_sessions = {}

class UserSession:
    def __init__(self):
        self.archive_path = None
        self.extract_path = None
        self.password = None
        self.is_password_protected = False
        self.selected_modes = []
        self.domains = []
        self.message = None
        self.progress_message = None
        self.total_size = 0
        self.downloaded = 0

async def progress_callback(current, total, message, action):
    """Progress callback for downloads"""
    percent = current * 100 / total
    await message.edit_text(
        f"📥 **{action}**\n"
        f"Progress: {percent:.1f}%\n"
        f"Downloaded: {current / 1024 / 1024:.1f}MB / {total / 1024 / 1024:.1f}MB"
    )

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    await message.reply_text(
        "🤖 **Archive Extractor Bot**\n\n"
        "Send me any archive file (.zip, .rar, .7z) and I'll extract and find:\n"
        "💳 Credit Cards\n"
        "🍪 Cookies\n"
        "🔑 ULP (Host:Login:Password)\n\n"
        "I'll process the archive and send you the extracted data!"
    )

@app.on_message(filters.document)
async def handle_document(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Check if file is archive
    file_name = message.document.file_name
    if not any(file_name.lower().endswith(ext) for ext in ['.zip', '.rar', '.7z']):
        await message.reply_text("❌ Please send a valid archive file (.zip, .rar, .7z)")
        return
    
    # Create user session
    session = UserSession()
    session.message = await message.reply_text("📥 **Downloading archive...**")
    user_sessions[user_id] = session
    
    # Download file
    file_path = os.path.join("downloads", f"{user_id}_{file_name}")
    try:
        await message.download(
            file_name=file_path,
            progress=progress_callback,
            progress_args=(session.message, "Downloading archive")
        )
        session.archive_path = file_path
        session.total_size = os.path.getsize(file_path)
        
        # Check if password protected
        is_protected = await check_password_protected(file_path)
        session.is_password_protected = is_protected
        
        if is_protected:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔑 Enter Password", callback_data="enter_password")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ])
            await session.message.edit_text(
                "🔒 **This archive is password protected!**\n\n"
                "Click the button below to enter the password.",
                reply_markup=keyboard
            )
        else:
            await show_mode_selection(user_id)
            
    except Exception as e:
        await session.message.edit_text(f"❌ Error: {str(e)}")
        cleanup_user_data(user_id)

async def check_password_protected(file_path):
    """Check if archive is password protected"""
    try:
        if file_path.endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as zf:
                # Try to read a file to check if password needed
                for file in zf.namelist()[:1]:
                    try:
                        zf.read(file)
                        return False
                    except RuntimeError:
                        return True
        elif file_path.endswith('.rar'):
            with rarfile.RarFile(file_path) as rf:
                try:
                    rf.testrar()
                    return False
                except rarfile.RarWrongPassword:
                    return True
        elif file_path.endswith('.7z'):
            with py7zr.SevenZipFile(file_path, mode='r') as sz:
                try:
                    sz.getnames()
                    return False
                except py7zr.exceptions.PasswordRequired:
                    return True
    except:
        return False
    return False

@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if user_id not in user_sessions:
        await callback_query.answer("Session expired! Send a new archive.")
        return
    
    session = user_sessions[user_id]
    
    if data == "enter_password":
        await callback_query.message.edit_text(
            "🔑 **Please enter the archive password:**\n\n"
            "Just type the password and send it as a message."
        )
        session.waiting_for_password = True
        
    elif data == "cancel":
        cleanup_user_data(user_id)
        await callback_query.message.edit_text("❌ Operation cancelled.")
        
    elif data.startswith("mode_"):
        mode = data.replace("mode_", "")
        if mode in session.selected_modes:
            session.selected_modes.remove(mode)
        else:
            session.selected_modes.append(mode)
        
        # Update keyboard
        keyboard = get_mode_keyboard(session.selected_modes)
        keyboard.append([InlineKeyboardButton("✅ Start Extraction", callback_data="start_extraction")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
        
        await callback_query.message.edit_reply_markup(
            InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "start_extraction":
        if not session.selected_modes:
            await callback_query.answer("Please select at least one option!", show_alert=True)
            return
        
        if "cookies" in session.selected_modes:
            await callback_query.message.edit_text(
                "🍪 **Cookie mode selected**\n\n"
                "Please enter domains to search for (comma separated):\n"
                "Example: `google.com, facebook.com, instagram.com`"
            )
            session.waiting_for_domains = True
        else:
            await start_processing(user_id)
    
    elif data == "skip_domains":
        session.domains = []
        await start_processing(user_id)

def get_mode_keyboard(selected_modes):
    """Create mode selection keyboard"""
    keyboard = []
    
    modes = [
        ("💳 Credit Cards", "cc"),
        ("🍪 Cookies", "cookies"),
        ("🔑 ULP (Host:Login:Pass)", "ulp")
    ]
    
    for name, mode in modes:
        if mode in selected_modes:
            name = f"✅ {name}"
        keyboard.append([InlineKeyboardButton(name, callback_data=f"mode_{mode}")])
    
    return keyboard

async def show_mode_selection(user_id):
    """Show mode selection interface"""
    session = user_sessions[user_id]
    
    keyboard = get_mode_keyboard([])
    keyboard.append([InlineKeyboardButton("✅ Start Extraction", callback_data="start_extraction")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    
    await session.message.edit_text(
        "📋 **Select what to extract:**\n\n"
        "Choose the types of data you want to extract:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@app.on_message(filters.text & filters.private)
async def handle_text(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        await message.reply_text("Please send an archive file first.")
        return
    
    session = user_sessions[user_id]
    
    if hasattr(session, 'waiting_for_password') and session.waiting_for_password:
        session.password = message.text
        session.waiting_for_password = False
        await message.reply_text("✅ Password saved! Checking archive...")
        
        # Try to extract with password
        try:
            extract_path = os.path.join("temp_extract", str(user_id))
            os.makedirs(extract_path, exist_ok=True)
            session.extract_path = extract_path
            
            await extract_archive(session.archive_path, extract_path, session.password)
            await show_mode_selection(user_id)
            
        except PatoolError:
            await message.reply_text("❌ Wrong password! Please try again.")
            session.waiting_for_password = True
        except Exception as e:
            await message.reply_text(f"❌ Error: {str(e)}")
            cleanup_user_data(user_id)
    
    elif hasattr(session, 'waiting_for_domains') and session.waiting_for_domains:
        # Parse domains
        domains = [d.strip().lower() for d in message.text.split(',')]
        domains = [d.replace('http://', '').replace('https://', '').replace('www.', '') for d in domains]
        session.domains = domains
        session.waiting_for_domains = False
        
        await message.reply_text(f"✅ Searching for {len(domains)} domains")
        await start_processing(user_id)

async def extract_archive(archive_path, extract_path, password=None):
    """Extract archive using patool"""
    try:
        if password:
            patoolib.extract_archive(archive_path, outdir=extract_path, password=password)
        else:
            patoolib.extract_archive(archive_path, outdir=extract_path)
        return True
    except PatoolError as e:
        if "password" in str(e).lower():
            raise Exception("Password required")
        raise e

async def start_processing(user_id):
    """Start the extraction and data processing"""
    session = user_sessions[user_id]
    
    # Create extraction directory
    extract_path = os.path.join("temp_extract", str(user_id))
    os.makedirs(extract_path, exist_ok=True)
    session.extract_path = extract_path
    
    # Update progress message
    session.progress_message = await session.message.edit_text(
        "🔄 **Extracting archive...**\n"
        "Please wait..."
    )
    
    try:
        # Extract archive
        await extract_archive(session.archive_path, extract_path, session.password)
        
        # Search for data
        results = {
            'cc': [],
            'cookies': {},
            'ulp': []
        }
        
        # Walk through extracted files
        total_files = sum([len(files) for _, _, files in os.walk(extract_path)])
        processed = 0
        
        for root, dirs, files in os.walk(extract_path):
            for file in files:
                processed += 1
                if processed % 10 == 0:  # Update progress every 10 files
                    await session.progress_message.edit_text(
                        f"🔍 **Processing files...**\n"
                        f"Progress: {processed}/{total_files}\n"
                        f"Found: CC:{len(results['cc'])} | "
                        f"Cookies:{sum(len(c) for c in results['cookies'].values())} | "
                        f"ULP:{len(results['ulp'])}"
                    )
                
                file_path = os.path.join(root, file)
                
                # Skip if too large (>10MB)
                if os.path.getsize(file_path) > 10 * 1024 * 1024:
                    continue
                
                # Process based on selected modes
                if "cc" in session.selected_modes:
                    cards = extract_credit_cards(file_path)
                    if cards:
                        results['cc'].extend(cards)
                
                if "cookies" in session.selected_modes and session.domains:
                    cookies = extract_cookies(file_path, session.domains)
                    if cookies:
                        # Store cookies per source file
                        rel_path = os.path.relpath(file_path, extract_path)
                        results['cookies'][rel_path] = cookies
                
                if "ulp" in session.selected_modes and file.lower() == 'passwords.txt':
                    ulps = extract_ulp(file_path)
                    if ulps:
                        results['ulp'].extend(ulps)
                
                # Small delay to prevent blocking
                if processed % 20 == 0:
                    await asyncio.sleep(0.1)
        
        # Prepare output files
        output_files = []
        
        # Save CC results
        if results['cc']:
            cc_file = os.path.join("downloads", f"{user_id}_cc.txt")
            with open(cc_file, 'w', encoding='utf-8') as f:
                f.write("CREDIT CARDS FOUND\n")
                f.write("="*50 + "\n")
                f.write("Format: CARD|EXPIRY|CVV|HOLDER\n\n")
                for card in results['cc']:
                    f.write(card + "\n")
            output_files.append(cc_file)
        
        # Save ULP results
        if results['ulp']:
            ulp_file = os.path.join("downloads", f"{user_id}_ulp.txt")
            with open(ulp_file, 'w', encoding='utf-8') as f:
                f.write("ULP (Host:Login:Password) FOUND\n")
                f.write("="*50 + "\n\n")
                for ulp in results['ulp']:
                    f.write(ulp + "\n")
            output_files.append(ulp_file)
        
        # Save cookies (as separate files in a zip)
        if results['cookies']:
            cookies_dir = os.path.join("downloads", f"{user_id}_cookies")
            os.makedirs(cookies_dir, exist_ok=True)
            
            for rel_path, cookie_data in results['cookies'].items():
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', rel_path)
                cookie_file = os.path.join(cookies_dir, f"{safe_name}.txt")
                
                with open(cookie_file, 'w', encoding='utf-8') as f:
                    f.write(f"# Cookies from: {rel_path}\n")
                    f.write(f"# Domains: {', '.join(session.domains)}\n")
                    f.write("#"*50 + "\n\n")
                    
                    for cookie in cookie_data:
                        if 'raw' in cookie:
                            f.write(cookie['raw'] + "\n")
                        else:
                            f.write(f"Domain: {cookie.get('domain', 'N/A')}\n")
                            f.write(f"Name: {cookie.get('name', 'N/A')}\n")
                            f.write(f"Value: {cookie.get('value', 'N/A')}\n")
                            f.write("-"*30 + "\n")
            
            # Zip all cookie files
            cookies_zip = os.path.join("downloads", f"{user_id}_cookies.zip")
            with zipfile.ZipFile(cookies_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(cookies_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, cookies_dir)
                        zf.write(file_path, arcname)
            
            output_files.append(cookies_zip)
        
        # Send results
        if output_files:
            await session.progress_message.edit_text(
                f"✅ **Extraction Complete!**\n\n"
                f"Found:\n"
                f"💳 Credit Cards: {len(results['cc'])}\n"
                f"🍪 Cookie Files: {len(results['cookies'])}\n"
                f"🔑 ULP: {len(results['ulp'])}\n\n"
                f"📤 Sending files..."
            )
            
            # Send each file
            for file_path in output_files:
                await asyncio.sleep(0.5)  # Small delay between files
                caption = os.path.basename(file_path)
                if file_path.endswith('.txt'):
                    await client.send_document(
                        user_id,
                        file_path,
                        caption=f"📄 {caption}"
                    )
                elif file_path.endswith('.zip'):
                    await client.send_document(
                        user_id,
                        file_path,
                        caption=f"📦 {caption}"
                    )
            
            await client.send_message(
                user_id,
                "✅ **All files sent successfully!**\n"
                "Send another archive to process more files."
            )
        else:
            await session.progress_message.edit_text(
                "❌ **No data found** in the selected categories.\n"
                "Try selecting different options or check if the archive contains relevant files."
            )
        
    except PatoolError as e:
        await session.progress_message.edit_text(f"❌ Extraction error: {str(e)}")
    except Exception as e:
        await session.progress_message.edit_text(f"❌ Error: {str(e)}")
    finally:
        cleanup_user_data(user_id)

def extract_credit_cards(file_path):
    """Extract credit cards from file"""
    cards = []
    pattern = r'(.+?)\s*\|\s*(\d{16})\s*\|\s*(\d{1,2}/\d{4})\s*\|\s*(\d{3,4})'
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        matches = re.findall(pattern, content)
        seen = set()
        
        for match in matches:
            name = match[0].strip()
            card = match[1].strip()
            expiry = match[2].strip()
            cvv = match[3].strip()
            
            if card in seen:
                continue
                
            try:
                month, year = expiry.split('/')
                year_int = int(year)
                if 2025 <= year_int <= 2035:
                    cards.append(f"{card}|{expiry}|{cvv}|{name}")
                    seen.add(card)
            except:
                continue
                
    except Exception:
        pass
        
    return cards

def extract_cookies(file_path, domains):
    """Extract cookies for specified domains"""
    cookies = []
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Check if line contains any of the domains
            line_lower = line.lower()
            for domain in domains:
                if domain in line_lower:
                    # Try to parse as cookie
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        cookie = {
                            'domain': parts[0],
                            'name': parts[5],
                            'value': parts[6],
                            'raw': line
                        }
                        cookies.append(cookie)
                    else:
                        # Store raw line
                        cookies.append({'raw': line, 'domain': domain})
                    break
                    
    except Exception:
        pass
        
    return cookies

def extract_ulp(file_path):
    """Extract ULP from passwords.txt files"""
    ulps = []
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Split by sections
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
                    # Clean URL
                    host = re.sub(r'https?://', '', host)
                    host = host.split('/')[0]
                elif line.startswith('Login:'):
                    login = line.replace('Login:', '').strip()
                elif line.startswith('Password:'):
                    password = line.replace('Password:', '').strip()
            
            if host and login and password:
                ulps.append(f"{host}:{login}:{password}")
                
    except Exception:
        pass
        
    return ulps

def cleanup_user_data(user_id):
    """Clean up all user data"""
    if user_id in user_sessions:
        session = user_sessions[user_id]
        
        # Remove archive
        if session.archive_path and os.path.exists(session.archive_path):
            try:
                os.remove(session.archive_path)
            except:
                pass
        
        # Remove extraction directory
        if session.extract_path and os.path.exists(session.extract_path):
            try:
                shutil.rmtree(session.extract_path)
            except:
                pass
        
        # Remove output files
        for ext in ['_cc.txt', '_ulp.txt', '_cookies.zip']:
            file_path = os.path.join("downloads", f"{user_id}{ext}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
        
        # Remove cookies directory
        cookies_dir = os.path.join("downloads", f"{user_id}_cookies")
        if os.path.exists(cookies_dir):
            try:
                shutil.rmtree(cookies_dir)
            except:
                pass
        
        del user_sessions[user_id]

@app.on_message(filters.command("clean"))
async def clean_command(client: Client, message: Message):
    """Clean up user's temporary files"""
    user_id = message.from_user.id
    cleanup_user_data(user_id)
    await message.reply_text("✅ Cleaned up your temporary files!")

if __name__ == "__main__":
    print("🚀 Starting Archive Extractor Bot...")
    print("📦 Using patool for extraction")
    print("💳 Credit Card extraction enabled")
    print("🍪 Cookie extraction enabled")
    print("🔑 ULP extraction enabled")
    app.run()
