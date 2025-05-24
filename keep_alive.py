
from flask import Flask
from threading import Thread
import time

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    while True:
        try:
            app.run(host='0.0.0.0', port=5000)
        except Exception as e:
            print(f"Flask server error: {e}")
            time.sleep(5)  # Wait before retrying
            continue

def keep_alive():
    server = Thread(target=run)
    server.daemon = True  # Allow the thread to exit when main program exits
    server.start()
