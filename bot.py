# bot.py - FIXED: Downloads actual archive files from URLs
import os
import re
import sys
import time
import zipfile
import tarfile
import shutil
import asyncio
import tempfile
import aiohttp
import aiofiles
from pathlib import Path
from typing import Optional, List, Tuple, Set, Dict
from urllib.parse import urlparse, unquote
from collections import defaultdict
from enum import Enum

import pyrogram
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# Configuration - YOU MUST FILL THESE!
API_ID = 28724954  # Get from https://my.telegram.org
API_HASH = "3ac42791738b153a980e2cdabf97e02f"  # Get from https://my.telegram.org
BOT_TOKEN = "8640428737:AAG5WAfwDOlBERALfacOJ_ht25_Kic217Us"
# Initialize bot
app = Client("cc_extractor_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Create necessary directories
for folder in ["downloads", "temp", "links", "results", "batch", "parts"]:
    os.makedirs(folder, exist_ok=True)

# Session for HTTP downloads
session = None

# User states for interactive modes
user_states = defaultdict(dict)


class UserState(Enum):
    BATCH_MODE = "batch"
    PART_MODE = "part"
    WAITING_PASSWORD = "waiting_password"


def extract_cc_data(text):
    """EXACT COPY FROM t.py - Extracts CC | MM | YYYY | CVV from any messy format"""
    text = re.sub(r'\s+', ' ', text)  # normalize spaces
    found = set()

    # 1. Direct pipe/slash format: 4111111111111111|12|2027|123  or  4111... / 03 / 26 / 999
    pattern1 = r'\b(\d{13,19})\s*[\|/\\]\s*(\d{1,2})\s*[\|/\\]\s*(\d{2,4})\s*[\|/\\]\s*(\d{3,4})\b'
    for cc, m, y, cvv in re.findall(pattern1, text):
        y = '20' + y if len(y) == 2 else y
        found.add((cc, m.zfill(2), y, cvv))

    # 2. Labeled format (CC:, Card:, Num:, etc.) – very flexible
    # Card number (with or without spaces/dashes)
    cards = re.findall(r'(?:cc|card|num|ccnum|number)[\s:]*([\d\s\-]{13,25})', text, re.I)
    cards += re.findall(r'\b(\d{13,19})\b', text)  # raw numbers

    clean_cards = [re.sub(r'\D', '', c) for c in cards if 13 <= len(re.sub(r'\D', '', c)) <= 19]

    # Month
    months = re.findall(r'(?:mo|mm|month|exp|expiry)[\s:/]*(\d{1,2})', text, re.I)
    months += [m for m, _ in re.findall(r'(?:exp|expiry)[\s:/]*(\d{1,2})[\/\-\s](\d{2,4})', text, re.I)]

    # Year
    years = re.findall(r'(?:ye|year|exp|expiry)[\s:/]*(\d{2,4})', text, re.I)
    years += [y for _, y in re.findall(r'(?:exp|expiry)[\s:/]*(\d{1,2})[\/\-\s](\d{2,4})', text, re.I)]

    # CVV
    cvvs = re.findall(r'(?:cvv|cvc|cv2|security|code)[\s:/]*(\d{3,4})', text, re.I)

    # If we found at least one card number, pair it with the first found month/year/cvv
    if clean_cards and (months or years or cvvs):
        m = (months[0] if months else '12').zfill(2)
        y = years[0] if years else '2028'
        if len(y) == 2:
            y = '20' + y
        c = cvvs[0] if cvvs else '000'

        for cc in clean_cards:
            found.add((cc, m, y, c))

    # 3. All-in-one-line pattern (very common in logs)
    pattern3 = r'(?:cc|card|num)[\s:]*(\d{13,19}).*?(?:mo|mm|month)[\s:]*(\d{1,2}).*?(?:ye|year)[\s:]*(\d{2,4}).*?(?:cvv|cvc)[\s:]*(\d{3,4})'
    for cc, m, y, cvv in re.findall(pattern3, text, re.I):
        y = '20' + y if len(y) == 2 else y
        found.add((cc, m.zfill(2), y, cvv))

    return list(found)


def find_all_folders(target_name, start_path):
    """Find all folders with target name"""
    found = []
    for root, dirs, _ in os.walk(start_path):
        for d in dirs:
            if d.lower() == target_name.lower():
                found.append(os.path.join(root, d))
    return found


def is_part_file(filename):
    """Check if file is a part of split archive"""
    if not filename:
        return False
    
    filename_lower = filename.lower()
    
    # Common part patterns
    part_patterns = [
        r'\.part\d+\.(?:rar|zip|7z|tar)$',
        r'\.r\d+$',  # .r00, .r01, etc
        r'\.z\d+$',  # .z00, .z01, etc
        r'\.\d{3}$',  # .001, .002, etc
        r'\.part\d+$',
        r'\.\d+$',
        r'_part\d+\.',
        r'\.part\.\d+'
    ]
    
    for pattern in part_patterns:
        if re.search(pattern, filename_lower):
            return True
    
    # Check for split extensions
    if filename_lower.endswith(('.001', '.002', '.003', '.004', '.005')):
        return True
    
    # Check for multi-volume RAR
    if filename_lower.endswith('.rar'):
        if re.search(r'\.part\d*\.rar$', filename_lower) or '.part' in filename_lower:
            return True
    
    return False


def get_base_part_name(filename):
    """Get base name for part files"""
    if not filename:
        return "unknown"
    
    filename_lower = filename.lower()
    
    # Remove part extensions
    patterns_to_remove = [
        r'\.part\d+\.(?:rar|zip|7z|tar)$',
        r'\.r\d+$',
        r'\.z\d+$',
        r'\.\d{3}$',
        r'\.part\d+$',
        r'\.\d+$',
        r'_part\d+\.',
        r'\.part\.\d+'
    ]
    
    base_name = filename
    for pattern in patterns_to_remove:
        base_name = re.sub(pattern, '', base_name, flags=re.IGNORECASE)
    
    # Remove trailing dots or underscores
    base_name = base_name.rstrip('._')
    
    return base_name


class DownloadManager:
    """Manages file downloads with verification"""
    
    @staticmethod
    async def download_telegram_file(message: Message, output_path: str) -> Tuple[bool, str, int]:
        """Download file from Telegram with verification"""
        try:
            # Get file info
            file_size = message.document.file_size if message.document else 0
            file_name = message.document.file_name if message.document else "unknown"
            
            status_msg = await message.reply(f"📥 Downloading: {file_name}")
            
            # Download file
            download_path = await message.download(file_name=output_path)
            
            # Verify download
            if download_path and os.path.exists(download_path):
                actual_size = os.path.getsize(download_path)
                if actual_size == 0:
                    await status_msg.edit("⚠️ Download failed: File is empty!")
                    return False, download_path, actual_size
                
                await status_msg.edit(
                    f"✅ Downloaded: {file_name}\n"
                    f"Size: {actual_size / 1024 / 1024:.2f} MB"
                )
                return True, download_path, actual_size
            
            await status_msg.edit("❌ Download failed!")
            return False, None, 0
            
        except Exception as e:
            await message.reply(f"❌ Download error: {str(e)[:100]}")
            return False, None, 0
    
    @staticmethod
    async def download_from_url(url: str, message: Message, custom_filename: str = None, 
                              part_index: int = None) -> Tuple[bool, str, int]:
        """Download ANY file from URL with progress updates"""
        global session
        
        status_msg = None
        try:
            if session is None:
                session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=300),
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    }
                )
            
            # Get filename from URL or use custom
            parsed = urlparse(url)
            path = parsed.path
            
            # Try to get filename from Content-Disposition header first
            async with session.head(url, allow_redirects=True) as head_response:
                filename = None
                if 'Content-Disposition' in head_response.headers:
                    content_disposition = head_response.headers['Content-Disposition']
                    if 'filename=' in content_disposition:
                        filename = content_disposition.split('filename=')[1].strip('"\'')
                
                if not filename:
                    # Get from URL path
                    filename = unquote(path.split('/')[-1])
                    if not filename or filename == '' or filename == '/':
                        # If no filename in URL, create one
                        if part_index is not None:
                            filename = f"part_{part_index:03d}.bin"
                        else:
                            filename = f"download_{int(time.time())}.bin"
                
                # Use custom filename if provided (for part files)
                if custom_filename:
                    filename = custom_filename
            
            output_dir = "links"
            output_path = os.path.join(output_dir, filename)
            
            # Ensure unique filename
            counter = 1
            original_name = filename
            while os.path.exists(output_path):
                name, ext = os.path.splitext(original_name)
                if not ext:
                    ext = '.bin'
                filename = f"{name}_{counter}{ext}"
                output_path = os.path.join(output_dir, filename)
                counter += 1
            
            status_msg = await message.reply(f"🌐 **Starting download...**\n`{url[:50]}...`")
            
            # Download file with progress updates
            start_time = time.time()
            
            async with session.get(url, allow_redirects=True) as response:
                if response.status != 200:
                    await status_msg.edit(f"❌ **Download failed:** HTTP {response.status}")
                    return False, None, 0
                
                # Get file size if available
                total_size = int(response.headers.get('content-length', 0))
                
                # Update status with file info
                size_info = f"{total_size / 1024 / 1024:.2f} MB" if total_size > 0 else "Unknown size"
                await status_msg.edit(f"🌐 **Downloading...**\n`{filename}`\nSize: {size_info}")
                
                # Download file
                downloaded = 0
                last_update = time.time()
                
                async with aiofiles.open(output_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024 * 64):  # 64KB chunks
                        if chunk:
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Update progress every 2 seconds
                            current_time = time.time()
                            if current_time - last_update >= 2:
                                elapsed = current_time - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                
                                status = (
                                    f"🌐 **Downloading...**\n"
                                    f"`{filename[:40]}`\n"
                                    f"📊 `{downloaded / 1024 / 1024:.2f} MB`"
                                )
                                if total_size > 0:
                                    status += f" / `{total_size / 1024 / 1024:.2f} MB`"
                                    percent = (downloaded / total_size) * 100
                                    bar_length = 10
                                    filled = int(bar_length * downloaded // total_size)
                                    status += f"\n`[{'█' * filled}{'░' * (bar_length - filled)}] {percent:.1f}%`"
                                
                                status += f"\n⚡ `{speed / 1024 / 1024:.2f} MB/s`"
                                
                                try:
                                    await status_msg.edit(status)
                                except:
                                    pass
                                last_update = current_time
            
            # Verify download
            if not os.path.exists(output_path):
                await status_msg.edit("❌ **Download failed: File not saved!**")
                return False, None, 0
            
            actual_size = os.path.getsize(output_path)
            if actual_size == 0:
                os.remove(output_path)
                await status_msg.edit("❌ **Download failed: File is empty!**")
                return False, None, 0
            
            elapsed = time.time() - start_time
            speed = actual_size / elapsed if elapsed > 0 else 0
            
            # Check what type of file we downloaded
            file_ext = os.path.splitext(filename)[1].lower()
            is_archive = file_ext in ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.tgz', '.tbz2']
            
            file_type = "📦 Archive" if is_archive else "📄 File"
            
            await status_msg.edit(
                f"✅ **Download Complete!**\n"
                f"{file_type}: `{filename}`\n"
                f"📊 `{actual_size / 1024 / 1024:.2f} MB`\n"
                f"⚡ `{speed / 1024 / 1024:.2f} MB/s`\n"
                f"⏱️ `{elapsed:.1f}s`"
            )
            
            return True, output_path, actual_size
                
        except aiohttp.ClientError as e:
            error_msg = f"❌ **Network Error:** `{str(e)[:100]}`"
            if status_msg:
                await status_msg.edit(error_msg)
            else:
                await message.reply(error_msg)
            return False, None, 0
        except asyncio.TimeoutError:
            error_msg = "❌ **Download timeout!** (5 minutes)"
            if status_msg:
                await status_msg.edit(error_msg)
            else:
                await message.reply(error_msg)
            return False, None, 0
        except Exception as e:
            error_msg = f"❌ **Download Error:** `{str(e)[:100]}`"
            if status_msg:
                await status_msg.edit(error_msg)
            else:
                await message.reply(error_msg)
            print(f"URL download error: {e}")
            return False, None, 0


def extract_archive(archive_path, password=None):
    """Extract archive with verification"""
    temp_dir = tempfile.mkdtemp(dir="temp")
    
    try:
        # Check if file exists and has content
        if not os.path.exists(archive_path):
            return None
        
        file_size = os.path.getsize(archive_path)
        if file_size == 0:
            return None
        
        print(f"Extracting archive: {archive_path} (size: {file_size} bytes)")
        
        # ZIP files
        if zipfile.is_zipfile(archive_path):
            print("Detected ZIP archive")
            with zipfile.ZipFile(archive_path, 'r') as zf:
                # Try with password if provided
                if password:
                    print(f"Trying with password: {password}")
                    try:
                        zf.setpassword(password.encode())
                        # Test if password works by trying to read first file
                        for file in zf.namelist():
                            try:
                                with zf.open(file, 'r', pwd=password.encode()) as f:
                                    f.read(10)  # Try to read a small amount
                                break
                            except:
                                continue
                    except Exception as e:
                        print(f"Password failed: {e}")
                        return None
                
                # List files in archive
                file_list = zf.namelist()
                print(f"Files in archive: {len(file_list)}")
                for f in file_list[:10]:  # Show first 10 files
                    print(f"  - {f}")
                
                # Extract
                zf.extractall(temp_dir)
                
                # Verify extraction
                extracted_files = list(Path(temp_dir).rglob('*'))
                print(f"Extracted {len(extracted_files)} files/folders")
                if len(extracted_files) > 0:
                    return temp_dir
                return None
        
        # TAR files
        elif archive_path.endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2')):
            print("Detected TAR archive")
            try:
                mode = 'r'
                if archive_path.endswith('.gz') or archive_path.endswith('.tgz'):
                    mode = 'r:gz'
                elif archive_path.endswith('.bz2') or archive_path.endswith('.tbz2'):
                    mode = 'r:bz2'
                
                with tarfile.open(archive_path, mode) as tf:
                    # List files
                    file_list = tf.getnames()
                    print(f"Files in archive: {len(file_list)}")
                    for f in file_list[:10]:
                        print(f"  - {f}")
                    
                    # Extract
                    tf.extractall(temp_dir)
                    
                    # Verify extraction
                    extracted_files = list(Path(temp_dir).rglob('*'))
                    print(f"Extracted {len(extracted_files)} files/folders")
                    if len(extracted_files) > 0:
                        return temp_dir
                    return None
            except tarfile.ReadError as e:
                print(f"TAR read error: {e}")
                return None
        
        print(f"Not a supported archive: {archive_path}")
        return None
        
    except Exception as e:
        print(f"Extraction error: {e}")
        # Cleanup on error
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        return None


def process_files_directory(folder_path):
    """Process files in a directory using t.py algorithm"""
    all_cards = []
    
    if not os.path.isdir(folder_path):
        return all_cards
    
    print(f"Processing directory: {folder_path}")
    file_count = 0
    
    for filename in os.listdir(folder_path):
        filepath = os.path.join(folder_path, filename)
        if os.path.isfile(filepath):
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                cards = extract_cc_data(content)
                if cards:
                    all_cards.extend(cards)
                    print(f"  Found {len(cards)} cards in {filename}")
                file_count += 1
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                continue
    
    print(f"Processed {file_count} files, found {len(all_cards)} cards total")
    return all_cards


async def process_any_file(file_path: str, password: Optional[str] = None) -> List[Tuple[str, str, str, str]]:
    """Process ANY file - archive or raw text file"""
    all_cards = []
    
    print(f"\n=== Processing file: {file_path} ===")
    
    # Check if it's an archive
    archive_extensions = ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.tgz', '.tbz2']
    is_archive = any(file_path.lower().endswith(ext) for ext in archive_extensions)
    
    if is_archive:
        print("File is an archive, extracting...")
        # Extract and process archive
        temp_dir = extract_archive(file_path, password)
        
        if not temp_dir and password:
            print("Password failed, trying without password...")
            # Try without password if password failed
            temp_dir = extract_archive(file_path, None)
        
        if temp_dir:
            print(f"Extraction successful to: {temp_dir}")
            
            # Find CreditCards folders first (like t.py does)
            cc_folders = find_all_folders("CreditCards", temp_dir)
            
            if cc_folders:
                print(f"Found {len(cc_folders)} CreditCards folder(s)")
                # Process CreditCards folders (EXACTLY like t.py)
                for folder in cc_folders:
                    print(f"Processing CreditCards folder: {folder}")
                    cards = process_files_directory(folder)
                    all_cards.extend(cards)
            else:
                print("No CreditCards folder found, searching all files")
                # Search in entire extracted content
                # Process all files recursively
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        filepath = os.path.join(root, file)
                        try:
                            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read()
                            cards = extract_cc_data(content)
                            if cards:
                                all_cards.extend(cards)
                        except:
                            continue
            
            # Cleanup temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                print(f"Cleaned up temp directory: {temp_dir}")
        else:
            print("Extraction failed!")
    else:
        print("File is NOT an archive, processing as raw text")
        # Process as raw text file
        try:
            file_size = os.path.getsize(file_path)
            print(f"File size: {file_size} bytes")
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            all_cards = extract_cc_data(content)
            print(f"Found {len(all_cards)} cards in raw file")
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
    
    # Remove duplicates
    unique_cards = []
    seen = set()
    for card in all_cards:
        if card not in seen:
            seen.add(card)
            unique_cards.append(card)
    
    print(f"Total unique cards found: {len(unique_cards)}")
    return unique_cards


async def handle_file_processing(message: Message, file_path: str, file_size: int, 
                               file_name: str, password: Optional[str] = None,
                               batch_id: str = None, index: int = None):
    """Handle processing of any file"""
    status_msg = await message.reply(f"🔍 **Processing {file_name}...**")
    
    try:
        # Process the file
        all_cards = await process_any_file(file_path, password)
        
        if all_cards:
            # Save results
            timestamp = int(time.time())
            if batch_id:
                output_file = f"results/results_{batch_id}_{index}.txt"
            else:
                output_file = f"results/results_{timestamp}.txt"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                for cc, m, y, cvv in all_cards:
                    f.write(f"{cc}|{m}|{y}|{cvv}\n")
            
            # Create result message with sample validation
            result_text = (
                f"✅ **Found {len(all_cards)} unique CCs!**\n"
                f"📁 File: `{file_name}`\n"
                f"📊 Size: `{file_size / 1024 / 1024:.2f} MB`\n"
            )
            
            if password:
                result_text += f"🔑 Password: `{password}`\n"
            
            result_text += "\n**Sample (first 3):**\n"
            
            # Show first 3 cards with full format for verification
            for i, (cc, m, y, cvv) in enumerate(all_cards[:3], 1):
                # Show full format to verify extraction is correct
                result_text += f"{i}. `{cc}|{m}|{y}|{cvv}`\n"
            
            if len(all_cards) > 3:
                result_text += f"... and {len(all_cards) - 3} more\n"
            
            # Send document
            await message.reply_document(
                document=output_file,
                caption=result_text,
                quote=True
            )
            
            # Cleanup output file after sending
            if os.path.exists(output_file):
                os.remove(output_file)
            
            return len(all_cards)
        else:
            await status_msg.edit(f"❌ **No CC data found in {file_name}!**")
            return 0
        
    except Exception as e:
        error_msg = f"❌ **Processing Error in {file_name}:** `{str(e)[:100]}`"
        if status_msg:
            await status_msg.edit(error_msg)
        else:
            await message.reply(error_msg)
        print(f"Error processing {file_path}: {e}")
        return 0
    finally:
        # Cleanup source file
        if os.path.exists(file_path):
            os.remove(file_path)
        
        if status_msg:
            try:
                await status_msg.delete()
            except:
                pass


async def handle_direct_link(message: Message, url: str, password: Optional[str] = None,
                           batch_id: str = None, index: int = None):
    """Handle ANY direct download link"""
    try:
        print(f"\n=== Handling URL: {url} ===")
        
        # Extract password from message if present
        if not password and message.text:
            # Look for password in various formats
            patterns = [
                r'(?:pass|password)[:\s]*([^\s]+)',
                r'pass[:=]\s*([^\s]+)',
                r'pwd[:=]\s*([^\s]+)',
                r'password\s+is\s+([^\s]+)',
                r'pass\s+is\s+([^\s]+)'
            ]
            for pattern in patterns:
                match = re.search(pattern, message.text, re.I)
                if match:
                    password = match.group(1)
                    print(f"Extracted password: {password}")
                    break
        
        # Download from URL - this downloads the actual file from the link
        success, file_path, file_size = await DownloadManager.download_from_url(url, message)
        
        if not success or not file_path:
            # Error message already sent by download_from_url
            return 0
        
        filename = os.path.basename(file_path)
        print(f"Downloaded file: {filename} ({file_size} bytes)")
        
        # Process the downloaded file
        cards_count = await handle_file_processing(message, file_path, file_size, filename, password, batch_id, index)
        return cards_count
        
    except Exception as e:
        await message.reply(f"❌ **URL Error:** `{str(e)[:100]}`")
        print(f"URL handling error: {e}")
        return 0


async def process_part_files_group(message: Message, part_files: List[Dict], password: Optional[str] = None):
    """Process a group of part files by combining and extracting them"""
    try:
        if not part_files:
            await message.reply("❌ **No part files to process!**")
            return 0
        
        status_msg = await message.reply("🔄 **Downloading and combining part files...**")
        
        # Create combined file with correct extension
        combined_dir = "parts"
        timestamp = int(time.time())
        
        # Determine the correct extension from the first part file
        first_file = part_files[0]
        if 'url' in first_file:
            # Get filename from URL
            filename = first_file.get('filename', '')
        elif 'message' in first_file:
            # Get filename from Telegram message
            filename = first_file.get('filename', '')
        else:
            filename = ''
        
        # Extract original extension without part numbers
        if filename:
            # Get base filename without part indicators
            base_name = get_base_part_name(filename)
            # Get extension from base name
            name, ext = os.path.splitext(base_name)
            if not ext:
                ext = '.bin'  # Default extension if none found
        else:
            ext = '.bin'  # Default extension
        
        # If extension indicates it's a multi-part archive, use appropriate extension
        if ext.lower() in ['.001', '.002', '.003']:
            # These are typically split files, the actual extension might be .zip, .rar, etc.
            # Check if we can determine the real extension
            if '_part' in filename.lower() or '.part' in filename.lower():
                # Try to extract original extension from part filename
                for archive_ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
                    if archive_ext in filename.lower():
                        ext = archive_ext
                        break
                else:
                    # If no archive extension found, use .zip as default
                    ext = '.zip'
            else:
                # For .001, .002 files, the actual file is usually .zip or .rar
                # Remove the .001 and check what's left
                base_without_num = re.sub(r'\.\d{3}$', '', filename)
                name, possible_ext = os.path.splitext(base_without_num)
                if possible_ext:
                    ext = possible_ext
                else:
                    ext = '.zip'  # Default
        
        combined_file = os.path.join(combined_dir, f"combined_{timestamp}{ext}")
        total_size = 0
        
        # Download and combine all parts
        with open(combined_file, 'wb') as outfile:
            for i, file_info in enumerate(part_files, 1):
                try:
                    await status_msg.edit(f"📥 **Processing part {i}/{len(part_files)}...**")
                    
                    if 'url' in file_info:
                        # This is a URL, need to download it first
                        url = file_info['url']
                        part_filename = file_info.get('filename', f"part_{i:03d}")
                        
                        success, part_path, part_size = await DownloadManager.download_from_url(
                            url, message, part_filename, i
                        )
                        
                        if not success:
                            await status_msg.edit(f"❌ **Failed to download part {i}**")
                            if os.path.exists(combined_file):
                                os.remove(combined_file)
                            return 0
                        
                        # Read and append to combined file
                        with open(part_path, 'rb') as infile:
                            shutil.copyfileobj(infile, outfile)
                        
                        total_size += part_size
                        
                        # Cleanup part file
                        os.remove(part_path)
                        
                    elif 'message' in file_info:
                        # This is a Telegram file - download it
                        msg = file_info['message']
                        part_filename = file_info.get('filename', f"part_{i:03d}")
                        
                        output_path = os.path.join(combined_dir, f"temp_part_{i}_{part_filename}")
                        success, part_path, part_size = await DownloadManager.download_telegram_file(
                            msg, output_path
                        )
                        
                        if not success:
                            await status_msg.edit(f"❌ **Failed to download Telegram part {i}**")
                            if os.path.exists(combined_file):
                                os.remove(combined_file)
                            return 0
                        
                        # Read and append to combined file
                        with open(part_path, 'rb') as infile:
                            shutil.copyfileobj(infile, outfile)
                        
                        total_size += part_size
                        
                        # Cleanup part file
                        os.remove(part_path)
                    
                except Exception as e:
                    await status_msg.edit(f"⚠️ **Error processing part {i}:** `{str(e)[:50]}`")
                    continue
        
        if total_size == 0:
            await status_msg.edit("❌ **Combined file is empty!**")
            if os.path.exists(combined_file):
                os.remove(combined_file)
            return 0
        
        await status_msg.edit(f"✅ **Combined {len(part_files)} parts ({total_size/1024/1024:.2f} MB)**")
        
        # Now process the combined file
        combined_filename = f"combined{ext}"
        cards_count = await handle_file_processing(
            message, combined_file, total_size, combined_filename, password
        )
        
        # Cleanup combined file
        if os.path.exists(combined_file):
            os.remove(combined_file)
        
        return cards_count
        
    except Exception as e:
        await message.reply(f"❌ **Part files processing error:** `{str(e)[:100]}`")
        print(f"Part files processing error: {e}")
        return 0


async def start_batch_mode(message: Message):
    """Start batch processing mode"""
    user_id = message.from_user.id
    user_states[user_id] = {
        'state': UserState.BATCH_MODE,
        'files': [],  # Store file info
        'batch_id': str(int(time.time())),
        'current_index': 0
    }
    
    await message.reply(
        "📦 **Batch Mode Activated!**\n\n"
        "Now you can send me multiple files/links one by one.\n"
        "I will download and process them all at once.\n\n"
        "**Supported:**\n"
        "• Files (ZIP, RAR, TXT, etc.)\n"
        "• Direct download links\n\n"
        "**Commands in batch mode:**\n"
        "`/done` - Finish batch and process all items\n"
        "`/cancel` - Cancel batch mode\n\n"
        "Send the first file or link now!\n"
        "To include password: `pass:yourpassword` in caption or after link"
    )


async def start_part_mode(message: Message):
    """Start part files processing mode"""
    user_id = message.from_user.id
    user_states[user_id] = {
        'state': UserState.PART_MODE,
        'part_files': [],  # Store part file info
        'password': None,
        'waiting_for_password': True
    }
    
    await message.reply(
        "🔗 **Part Files Mode Activated!**\n\n"
        "Send me all part files (or links to part files) in sequence.\n"
        "I will download and combine them all.\n\n"
        "**First, tell me the password (if any):**\n"
        "Reply with the password or type `no password`\n\n"
        "Examples of part files:\n"
        "• file.part1.rar, file.part2.rar\n"
        "• file.zip.001, file.zip.002\n"
        "• Direct URLs to part files"
    )


async def process_batch(message: Message):
    """Process all batch items"""
    user_id = message.from_user.id
    if user_id not in user_states or user_states[user_id]['state'] != UserState.BATCH_MODE:
        await message.reply("❌ **No active batch to process!**")
        return
    
    batch_data = user_states[user_id]
    files = batch_data.get('files', [])
    
    if not files:
        await message.reply("❌ **No files in batch to process!**")
        del user_states[user_id]
        return
    
    await message.reply(f"🔄 **Processing {len(files)} batch items...**")
    
    total_cards = 0
    processed_count = 0
    
    for i, file_info in enumerate(files, 1):
        try:
            if 'url' in file_info:
                # Process URL
                password = file_info.get('password')
                cards_count = await handle_direct_link(
                    message, file_info['url'], password,
                    batch_data['batch_id'], i
                )
            elif 'message' in file_info:
                # Process Telegram file
                password = file_info.get('password')
                msg = file_info['message']
                filename = file_info.get('filename', f"file_{i}")
                
                # Download the file
                output_path = os.path.join("batch", f"{batch_data['batch_id']}_{i}_{filename}")
                success, file_path, file_size = await DownloadManager.download_telegram_file(
                    msg, output_path
                )
                
                if success:
                    cards_count = await handle_file_processing(
                        message, file_path, file_size, filename, password,
                        batch_data['batch_id'], i
                    )
                else:
                    cards_count = 0
                    await message.reply(f"⚠️ **Failed to download:** `{filename}`")
            
            total_cards += cards_count
            processed_count += 1
            
            # Small delay between processing
            await asyncio.sleep(1)
            
        except Exception as e:
            await message.reply(f"⚠️ **Error processing batch item {i}:** `{str(e)[:50]}`")
    
    # Send summary
    summary = (
        f"📊 **Batch Processing Complete!**\n\n"
        f"✅ Processed: {processed_count}/{len(files)} items\n"
        f"💳 Total CCs found: {total_cards}\n"
        f"🆔 Batch ID: `{batch_data['batch_id']}`"
    )
    
    await message.reply(summary)
    
    # Cleanup
    del user_states[user_id]
    
    # Clean batch directory
    batch_dir = "batch"
    if os.path.exists(batch_dir):
        shutil.rmtree(batch_dir, ignore_errors=True)
        os.makedirs(batch_dir, exist_ok=True)


async def process_part_mode(message: Message):
    """Process all part files in part mode"""
    user_id = message.from_user.id
    if user_id not in user_states or user_states[user_id]['state'] != UserState.PART_MODE:
        await message.reply("❌ **No active part mode to process!**")
        return
    
    part_data = user_states[user_id]
    part_files = part_data.get('part_files', [])
    
    if not part_files:
        await message.reply("❌ **No part files to process!**")
        del user_states[user_id]
        return
    
    password = part_data.get('password')
    
    await message.reply(f"🔄 **Processing {len(part_files)} part files...**")
    
    # Process all part files as one group
    cards_count = await process_part_files_group(message, part_files, password)
    
    # Send summary
    summary = (
        f"📊 **Part Files Processing Complete!**\n\n"
        f"📦 Parts processed: {len(part_files)}\n"
        f"💳 CCs found: {cards_count}"
    )
    
    if password:
        summary += f"\n🔑 Password used: `{password}`"
    
    await message.reply(summary)
    
    # Cleanup
    del user_states[user_id]
    
    # Clean parts directory
    parts_dir = "parts"
    if os.path.exists(parts_dir):
        shutil.rmtree(parts_dir, ignore_errors=True)
        os.makedirs(parts_dir, exist_ok=True)


# Command handlers
@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply(
        "🤖 **CC Extractor Bot v7.0**\n\n"
        "**Uses EXACT t.py extraction algorithm**\n"
        "**Now with BATCH and PART files support!**\n\n"
        "**Send me:**\n"
        "• Any archive file (ZIP/RAR/TAR)\n"
        "• Direct download links to ANY files\n"
        "• Raw text files with CC data\n\n"
        "**New Features:**\n"
        "• `/batch` - Process multiple files/links (collects first, processes all at once)\n"
        "• `/part` - Process split/part files (collects all parts, combines and processes)\n"
        "• URLs, files, part files all supported!\n\n"
        "**How it works:**\n"
        "1. Send files/links in batch/part mode\n"
        "2. Type `/done` when ready\n"
        "3. Bot downloads and processes everything\n"
        "4. Extracts archives (with password support)\n"
        "5. Searches for CreditCards folders\n"
        "6. Extracts CC data from all text files\n\n"
        "**Commands:**\n"
        "`/batch` - Start batch mode (multiple files/links)\n"
        "`/part` - Process part/split files\n"
        "`/done` - Process collected items\n"
        "`/cancel` - Cancel current mode\n"
        "`/clean` - Clean temporary files\n"
        "`/stats` - Show bot statistics"
    )


@app.on_message(filters.command("batch"))
async def batch_command(client, message):
    """Start batch processing mode"""
    await start_batch_mode(message)


@app.on_message(filters.command("part"))
async def part_command(client, message):
    """Start part files processing mode"""
    await start_part_mode(message)


@app.on_message(filters.command("done"))
async def done_command(client, message):
    """Finish current mode and process collected items"""
    user_id = message.from_user.id
    
    if user_id not in user_states:
        await message.reply("❌ **Nothing to finish! Start a mode first.**")
        return
    
    state = user_states[user_id]['state']
    
    if state == UserState.BATCH_MODE:
        await process_batch(message)
    elif state == UserState.PART_MODE:
        # Check if still waiting for password
        if user_states[user_id].get('waiting_for_password', False):
            await message.reply("❌ **Please provide password first!**\nReply with password or type `no password`")
            return
        await process_part_mode(message)
    else:
        await message.reply("❌ **Cannot finish in current state!**")


@app.on_message(filters.command("cancel"))
async def cancel_command(client, message):
    """Cancel current mode"""
    user_id = message.from_user.id
    if user_id in user_states:
        mode = user_states[user_id].get('state')
        
        # Cleanup any stored files
        if mode == UserState.BATCH_MODE:
            files = user_states[user_id].get('files', [])
            for file_info in files:
                if 'path' in file_info and os.path.exists(file_info['path']):
                    try:
                        os.remove(file_info['path'])
                    except:
                        pass
        elif mode == UserState.PART_MODE:
            files = user_states[user_id].get('part_files', [])
            for file_info in files:
                if 'path' in file_info and os.path.exists(file_info['path']):
                    try:
                        os.remove(file_info['path'])
                    except:
                        pass
        
        del user_states[user_id]
        
        if mode == UserState.BATCH_MODE:
            await message.reply("❌ **Batch mode cancelled! All files removed.**")
        elif mode == UserState.PART_MODE:
            await message.reply("❌ **Part mode cancelled! All files removed.**")
        else:
            await message.reply("✅ **Operation cancelled!**")
    else:
        await message.reply("❌ **Nothing to cancel!**")


@app.on_message(filters.command("clean"))
async def clean_command(client, message):
    """Clean temporary files"""
    cleaned = 0
    for folder in ["downloads", "temp", "links", "results", "batch", "parts"]:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
                os.makedirs(folder, exist_ok=True)
                cleaned += 1
            except:
                pass
    
    await message.reply(f"🧹 **Cleaned {cleaned} temporary folders!**")


@app.on_message(filters.command("stats"))
async def stats_command(client, message):
    """Show bot statistics"""
    stats = []
    for folder in ["downloads", "temp", "links", "results", "batch", "parts"]:
        if os.path.exists(folder):
            size = sum(f.stat().st_size for f in Path(folder).rglob('*') if f.is_file())
            count = sum(1 for _ in Path(folder).rglob('*') if _.is_file())
            stats.append(f"**{folder}:** {count} files, {size / 1024 / 1024:.2f} MB")
    
    if stats:
        await message.reply("📊 **Storage Stats:**\n" + "\n".join(stats))
    else:
        await message.reply("📊 **All folders are empty!**")


@app.on_message(filters.document)
async def handle_document(client, message):
    """Handle document (file) upload"""
    user_id = message.from_user.id
    filename = message.document.file_name
    
    # Check user state
    if user_id in user_states:
        state = user_states[user_id]['state']
        
        if state == UserState.BATCH_MODE:
            # Store file info for later processing
            # Extract password from caption if present
            password = None
            if message.caption:
                match = re.search(r'(?:pass|password)[:\s]*([^\s]+)', message.caption, re.I)
                if match:
                    password = match.group(1)
            
            # Store the actual message object for later downloading
            user_states[user_id]['files'].append({
                'message': message,
                'filename': filename,
                'password': password
            })
            
            count = len(user_states[user_id]['files'])
            if password:
                await message.reply(
                    f"📥 **File #{count} added to batch!**\n"
                    f"`{filename}`\n"
                    f"🔑 Password: `{password}`\n\n"
                    f"Files will be downloaded when you type `/done`"
                )
            else:
                await message.reply(
                    f"📥 **File #{count} added to batch!**\n"
                    f"`{filename}`\n\n"
                    f"Files will be downloaded when you type `/done`"
                )
            return
        
        elif state == UserState.PART_MODE:
            # Check if still waiting for password
            if user_states[user_id].get('waiting_for_password', False):
                await message.reply("❌ **Please provide password first!**\nReply with password or type `no password`")
                return
            
            # Store part file info for later processing
            # Extract password from caption if present
            password = None
            if message.caption:
                match = re.search(r'(?:pass|password)[:\s]*([^\s]+)', message.caption, re.I)
                if match:
                    password = match.group(1)
            
            # Check if it looks like a part file
            is_part = is_part_file(filename)
            
            user_states[user_id]['part_files'].append({
                'message': message,
                'filename': filename,
                'is_part_file': is_part,
                'password': password
            })
            
            count = len(user_states[user_id]['part_files'])
            await message.reply(
                f"✅ **Part file #{count} added:** `{filename}`\n"
                f"Files will be downloaded when you type `/done`\n"
                f"Send more part files or type `/done` to process"
            )
            return
    
    # Normal file processing (not in batch/part mode)
    # Check if it's a supported file type
    supported_extensions = [
        '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.tgz', '.tbz2',  # Archives
        '.txt', '.log', '.json', '.csv', '.xml', '.sql', '.db', '.dat'   # Text/data files
    ]
    
    filename_lower = filename.lower()
    is_supported = any(filename_lower.endswith(ext) for ext in supported_extensions)
    
    if not is_supported:
        await message.reply(
            "❌ **Unsupported file type!**\n"
            "Send archives or text files (ZIP, RAR, TXT, LOG, etc.)"
        )
        return
    
    # Download file immediately (normal mode)
    output_path = os.path.join("downloads", f"{int(time.time())}_{filename}")
    success, file_path, file_size = await DownloadManager.download_telegram_file(
        message, output_path
    )
    
    if not success:
        return
    
    # Extract password from caption
    password = None
    if message.caption:
        match = re.search(r'(?:pass|password)[:\s]*([^\s]+)', message.caption, re.I)
        if match:
            password = match.group(1)
    
    # Process the file
    await handle_file_processing(message, file_path, file_size, filename, password)


@app.on_message(filters.text & ~filters.command(["start", "batch", "part", "done", "cancel", "clean", "stats"]))
async def handle_text(client, message):
    """Handle text messages (for links and passwords)"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Check user state
    if user_id in user_states:
        state = user_states[user_id]['state']
        
        if state == UserState.WAITING_PASSWORD:
            # User is providing password for a batch file
            password_type = user_states[user_id].get('password_type')
            index = user_states[user_id].get('password_for')
            
            if password_type == 'batch_file' and index is not None:
                # Set password for batch file
                if text.lower() in ['no password', 'no', 'none', '']:
                    password_text = 'No password'
                    password = None
                else:
                    password_text = text
                    password = text
                
                # Update file info
                if index < len(user_states[user_id]['files']):
                    user_states[user_id]['files'][index]['password'] = password
                
                # Return to batch mode
                user_states[user_id]['state'] = UserState.BATCH_MODE
                del user_states[user_id]['password_for']
                del user_states[user_id]['password_type']
                
                await message.reply(
                    f"✅ **Password set:** `{password_text}`\n\n"
                    f"Send next file/URL or type `/done` to process batch."
                )
                return
            
            elif password_type == 'batch_url' and index is not None:
                # Set password for batch URL
                if text.lower() in ['no password', 'no', 'none', '']:
                    password_text = 'No password'
                    password = None
                else:
                    password_text = text
                    password = text
                
                # Update URL info
                if index < len(user_states[user_id]['files']):
                    user_states[user_id]['files'][index]['password'] = password
                
                # Return to batch mode
                user_states[user_id]['state'] = UserState.BATCH_MODE
                del user_states[user_id]['password_for']
                del user_states[user_id]['password_type']
                
                await message.reply(
                    f"✅ **Password set:** `{password_text}`\n\n"
                    f"Send next file/URL or type `/done` to process batch."
                )
                return
        
        elif state == UserState.BATCH_MODE:
            # Check if it's a URL
            url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?'
            urls = re.findall(url_pattern, text)
            
            if urls:
                # Add URL to batch
                url = urls[0]
                
                # Extract password from text if present
                password = None
                password_match = re.search(r'(?:pass|password)[:\s]*([^\s]+)', text, re.I)
                if password_match:
                    password = password_match.group(1)
                
                user_states[user_id]['files'].append({
                    'url': url,
                    'filename': url.split('/')[-1] if '/' in url else f"url_{len(user_states[user_id]['files'])}",
                    'password': password
                })
                
                count = len(user_states[user_id]['files'])
                if password:
                    await message.reply(
                        f"🔗 **URL #{count} added to batch!**\n"
                        f"`{url[:50]}...`\n"
                        f"🔑 Password: `{password}`\n\n"
                        f"Files will be downloaded when you type `/done`"
                    )
                else:
                    await message.reply(
                        f"🔗 **URL #{count} added to batch!**\n"
                        f"`{url[:50]}...`\n\n"
                        f"Files will be downloaded when you type `/done`"
                    )
            else:
                # Check if it's raw CC data
                cards = extract_cc_data(text)
                if cards:
                    result_text = f"✅ **Found {len(cards)} CCs in message!**\n\n"
                    for i, (cc, m, y, cvv) in enumerate(cards[:5], 1):
                        result_text += f"{i}. `{cc}|{m}|{y}|{cvv}`\n"
                    
                    if len(cards) > 5:
                        result_text += f"... and {len(cards) - 5} more\n"
                    
                    await message.reply(result_text)
                else:
                    await message.reply(
                        "📝 **Send me either:**\n"
                        "1. A file (archive or text)\n"
                        "2. A direct download link (http/https)\n"
                        "3. Type `/done` to process batch\n"
                        "4. Type `/cancel` to cancel batch\n\n"
                        "**To include password:**\n"
                        "`https://example.com/data.zip pass:1234`"
                    )
            return
        
        elif state == UserState.PART_MODE:
            if user_states[user_id].get('waiting_for_password', False):
                # User is providing password for part mode
                if text.lower() in ['no password', 'no', 'none', '']:
                    user_states[user_id]['password'] = None
                    password_text = 'No password'
                else:
                    user_states[user_id]['password'] = text
                    password_text = text
                
                user_states[user_id]['waiting_for_password'] = False
                
                await message.reply(
                    f"✅ **Password set:** `{password_text}`\n\n"
                    f"Now send me part files or URLs to part files.\n"
                    f"I will collect them all and process when you type `/done`.\n\n"
                    f"Examples:\n"
                    f"• Send files like file.part1.rar, file.zip.001\n"
                    f"• Send URLs (any format, I'll handle them)\n\n"
                    f"Type `/done` when all parts are sent"
                )
                return
            
            # Check if it's a URL to part file
            url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?'
            urls = re.findall(url_pattern, text)
            
            if urls:
                # Add all URLs as part files
                for url in urls:
                    filename = url.split('/')[-1] if '/' in url else f"part_{len(user_states[user_id]['part_files'])}"
                    
                    # Extract password from text if present
                    password = None
                    password_match = re.search(r'(?:pass|password)[:\s]*([^\s]+)', text, re.I)
                    if password_match:
                        password = password_match.group(1)
                    
                    user_states[user_id]['part_files'].append({
                        'url': url,
                        'filename': filename,
                        'password': password
                    })
                
                count = len(user_states[user_id]['part_files'])
                await message.reply(
                    f"✅ **Added {len(urls)} URL(s) as part files!**\n"
                    f"Total parts collected: {count}\n"
                    f"Files will be downloaded when you type `/done`\n"
                    f"Send more part files/URLs or type `/done` to process"
                )
            else:
                # Check if it's raw CC data
                cards = extract_cc_data(text)
                if cards:
                    result_text = f"✅ **Found {len(cards)} CCs in message!**\n\n"
                    for i, (cc, m, y, cvv) in enumerate(cards[:5], 1):
                        result_text += f"{i}. `{cc}|{m}|{y}|{cvv}`\n"
                    
                    if len(cards) > 5:
                        result_text += f"... and {len(cards) - 5} more\n"
                    
                    await message.reply(result_text)
                else:
                    await message.reply(
                        "📝 **Send me:**\n"
                        "1. Part files (any format, I'll detect)\n"
                        "2. URLs to part files (any URL format)\n"
                        "3. Type `/done` to process all collected parts\n"
                        "4. Type `/cancel` to cancel\n\n"
                        "**To include password:**\n"
                        "`https://example.com/part1.rar pass:1234`"
                    )
            return
    
    # Normal text processing (not in batch/part mode)
    # Check if it's a URL
    url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?'
    urls = re.findall(url_pattern, text)
    
    if urls:
        # Process first URL found immediately
        await handle_direct_link(message, urls[0])
    else:
        # Check if it's raw CC data in the message itself
        cards = extract_cc_data(text)
        if cards:
            result_text = f"✅ **Found {len(cards)} CCs in message!**\n\n"
            for i, (cc, m, y, cvv) in enumerate(cards[:5], 1):
                result_text += f"{i}. `{cc}|{m}|{y}|{cvv}`\n"
            
            if len(cards) > 5:
                result_text += f"... and {len(cards) - 5} more\n"
            
            await message.reply(result_text)
        else:
            await message.reply(
                "📝 **Send me either:**\n"
                "1. A file (archive or text)\n"
                "2. A direct download link (http/https)\n"
                "3. Raw CC data in message\n"
                "4. Use /start for help\n"
                "5. /batch for multiple files\n"
                "6. /part for split archives\n\n"
                "**Example links:**\n"
                "`https://example.com/data.zip`\n"
                "`https://example.com/cc_data.rar pass:1234`\n"
                "`https://example.com/file.part1.rar`"
            )


@app.on_callback_query()
async def handle_callback_query(client, callback_query):
    """Handle inline button callbacks"""
    user_id = callback_query.from_user.id
    data = callback_query.data
    message = callback_query.message
    
    await callback_query.answer()
    
    if user_id not in user_states:
        await message.edit_text("❌ **Session expired! Start again.**")
        return
    
    # Handle batch mode password callbacks
    if data.startswith("batch_has_password:"):
        # File has password, ask for it
        index = int(data.split(":")[1])
        user_states[user_id]['state'] = UserState.WAITING_PASSWORD
        user_states[user_id]['password_for'] = index
        user_states[user_id]['password_type'] = 'batch_file'
        
        await message.edit_text(
            "🔑 **Please send the password for this file:**\n"
            "(Reply with the password or type `no password`)"
        )
        return
    
    elif data.startswith("batch_no_password:"):
        # File has no password, continue
        index = int(data.split(":")[1])
        
        # Mark file as having no password
        if index < len(user_states[user_id]['files']):
            user_states[user_id]['files'][index]['password'] = None
        
        await message.edit_text(
            "✅ **No password set for this file.**\n\n"
            "Send next file/URL or type `/done` to process batch."
        )
        return
    
    elif data.startswith("batch_url_has_password:"):
        # URL file has password
        index = int(data.split(":")[1])
        user_states[user_id]['state'] = UserState.WAITING_PASSWORD
        user_states[user_id]['password_for'] = index
        user_states[user_id]['password_type'] = 'batch_url'
        
        await message.edit_text(
            "🔑 **Please send the password for this URL/file:**\n"
            "(Reply with the password or type `no password`)"
        )
        return
    
    elif data.startswith("batch_url_no_password:"):
        # URL file has no password
        index = int(data.split(":")[1])
        
        # Mark URL as having no password
        if index < len(user_states[user_id]['files']):
            user_states[user_id]['files'][index]['password'] = None
        
        await message.edit_text(
            "✅ **No password set for this URL.**\n\n"
            "Send next file/URL or type `/done` to process batch."
        )
        return


async def shutdown():
    """Clean shutdown"""
    global session
    if session:
        await session.close()
    
    # Cleanup temp directories
    for folder in ["downloads", "temp", "links", "results", "batch", "parts"]:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder, ignore_errors=True)
            except:
                pass


if __name__ == "__main__":
    print("🤖 CC Extractor Bot v7.0")
    print("="*50)
    print("✅ Using EXACT t.py extraction algorithm")
    print("✅ Downloads actual files from URLs")
    print("✅ Batch mode: Collect first, process later")
    print("✅ Part mode: Collect all parts, process together")
    print("✅ Proper CC|MM|YYYY|CVV pairing")
    print("="*50)
    
    # Check API credentials
    if API_ID == 123456 or API_HASH == "your_api_hash_here" or BOT_TOKEN == "your_bot_token_here":
        print("\n❌ **ERROR: Configure API credentials first!**")
        print("\n1. Get API_ID & API_HASH from: https://my.telegram.org")
        print("2. Get BOT_TOKEN from @BotFather")
        print("3. Edit bot.py and replace placeholder values")
        sys.exit(1)
    
    # Check dependencies
    try:
        import pyrogram
        import aiohttp
        print("✅ All dependencies satisfied!")
    except ImportError as e:
        print(f"\n❌ Missing dependency: {e}")
        print("\nInstall required packages:")
        print("pip install pyrogram aiohttp aiofiles")
        sys.exit(1)
    
    print("\n🚀 Starting bot...")
    print("Press Ctrl+C to stop\n")
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
        asyncio.run(shutdown())
        print("✅ Clean shutdown complete!")
    except Exception as e:
        print(f"\n❌ Bot error: {e}")
        asyncio.run(shutdown())
