import subprocess
import sys
import time

def run_gunicorn():
    return subprocess.Popen(
        ["gunicorn", "app:app"],
        stdout=sys.stdout,
        stderr=sys.stderr
    )

def run_bot():
    return subprocess.Popen(
        ["python", "bot.py"],
        stdout=sys.stdout,
        stderr=sys.stderr
    )

if __name__ == "__main__":
    print("Starting gunicorn...")
    gunicorn_process = run_gunicorn()

    # Small delay to ensure gunicorn starts first
    time.sleep(2)

    print("Starting bot...")
    bot_process = run_bot()

    # Wait for both processes
    gunicorn_process.wait()
    bot_process.wait()
