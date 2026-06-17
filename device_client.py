"""
Device client (Session Auth)
- On connect, waits for Auth Challenge.
- Prompts user for QKD Code (displayed on Server).
- Once Authenticated, enters message loop.
- Receives messages directly.
"""

import argparse
import socketio
import os
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--server", required=True)
parser.add_argument("--device", required=True)
args = parser.parse_args()

SERVER = args.server.rstrip("/")
DEVICE = args.device.upper()
USER_EMAIL = ""

sio = socketio.Client()

def clear():
    os.system("cls" if os.name == "nt" else "clear")

@sio.event
def connect():
    clear()
    print(f"[{DEVICE}] Connected to server. Waiting for Auth Challenge...")
    sio.emit("register", {"device_id": DEVICE, "email": USER_EMAIL})

@sio.on("auth_challenge")
def on_auth_challenge(p):
    print("\n--- SECURITY CHECK ---")
    print("Please enter the QKD Code displayed on the Server Console.")
    while True:
        code = input("QKD Code: ").strip()
        if code:
            sio.emit("auth_response", {"code": code})
            break

@sio.on("auth_result")
def on_auth_result(p):
    if p.get("ok"):
        print("\n[SUCCESS] Authenticated! Secure Session Established.")
        # Start the main loop in a separate thread or just call it?
        # Since socketio client is blocking in main(), we can't block here easily if we want to receive events.
        # But we are using a callback. We should signal the main thread to proceed.
        # Actually, let's just start a thread for input loop.
        import threading
        t = threading.Thread(target=message_loop)
        t.daemon = True
        t.start()
    else:
        print(f"\n[FAILED] Authentication Failed: {p.get('reason')}")
        print("Disconnecting...")
        sio.disconnect()

def message_loop():
    time.sleep(1)
    print("\nYou can now send messages.")
    print("Type 'quit' to exit.")
    while True:
        try:
            msg = input(f"[{DEVICE}] Enter message (or 'quit'): ").strip()
            if msg.lower() == "quit":
                sio.disconnect()
                break
            if not msg: continue
            
            to = input(f"[{DEVICE}] Send to (A/B): ").strip().upper()
            if to not in ("A", "B"):
                print("Invalid target.")
                continue
                
            sio.emit("send_message", {"from": DEVICE, "to": to, "text": msg})
            # Wait for confirmation?
            time.sleep(0.2)
            
        except EOFError:
            break

@sio.on("incoming_message")
def on_incoming(p):
    frm = p.get("from")
    text = p.get("text")
    lbl = p.get("label")
    
    warn = ""
    if lbl == 1:
        warn = " [⚠️ WARNING: EAVESDROPPING DETECTED ON THIS MESSAGE ⚠️]"
        
    print(f"\n\n>>> MESSAGE FROM {frm}: {text}{warn}\n")
    print(f"[{DEVICE}] Enter message (or 'quit'): ", end="", flush=True)

@sio.on("force_disconnect")
def on_force_disconnect(p):
    reason = p.get("reason")
    if reason == "EAVESDROPPING_DETECTED":
        print("\n\n" + "="*40)
        print("STATUS: ❗ EAVESDROPPING DETECTED ❗")
        
        details = p.get("details")
        if details:
            print(details)
            
        print("Server has terminated the connection.")
        print("="*40 + "\n")
    else:
        print(f"\nForced disconnect: {reason}")
    
    sio.disconnect()
    sys.exit(0)

@sio.on("send_result")
def on_send_result(p):
    if not p.get("ok"):
        print(f"Error sending: {p.get('reason')}")

@sio.on("disconnect")
def on_disconnect(*args):
    print("\nDisconnected from server.")
    # Do not sys.exit(0) here, it causes the traceback in the socketio thread.
    # The main loop will exit naturally or we can let the user close the terminal.
    os._exit(0) # Force exit without traceback if really needed, or just return.

def main():
    try:
        global USER_EMAIL
        print(f"\n--- {DEVICE} SETUP ---")
        USER_EMAIL = input("Enter your email address to receive QKD Code: ").strip()
        
        sio.connect(SERVER)
        sio.wait()
    except KeyboardInterrupt:
        try:
            sio.disconnect()
        except:
            pass
        sys.exit(0)
    except Exception as e:
        print("Connection error:", e)

if __name__ == "__main__":
    main()
