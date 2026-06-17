import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext
import socketio
import threading
import time
import math
import random

# --- Configuration ---
# Cyberpunk / Hacker Theme Colors
BG_COLOR = "#0b0c10"       # Dark Slate
BG_SEC = "#1f2833"         # Lighter Dark
ACCENT_CYAN = "#66fcf1"    # Neon Cyan
ACCENT_GREEN = "#45a29e"   # Dull Green
ACCENT_RED = "#ff003c"     # Cyber Red
TEXT_MAIN = "#c5c6c7"      # Light Gray
TEXT_BRIGHT = "#ffffff"    # White

FONT_MONO = ("Consolas", 10)
FONT_HEADER = ("Segoe UI", 12, "bold")
FONT_DIGITAL = ("Courier New", 12, "bold")

class QKDClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("QUANTUM SECURE LINK v2.0")
        self.root.geometry("900x650")
        self.root.configure(bg=BG_COLOR)
        
        self.sio = socketio.Client()
        self.device_id = ""
        self.server_url = ""
        self.email = ""
        self.is_connected = False
        self.qber_history = [0.0] * 20 # For graph
        
        self.setup_ui()
        self.setup_socket_events()
        
        # Start background animations
        self.animate_pulse()

    def setup_ui(self):
        # --- Styles ---
        style_frame = {"bg": BG_COLOR}
        style_label = {"bg": BG_COLOR, "fg": ACCENT_CYAN, "font": FONT_MONO}
        style_entry = {"bg": BG_SEC, "fg": TEXT_BRIGHT, "insertbackground": "white", "relief": "flat", "font": FONT_MONO}
        style_btn = {"bg": ACCENT_CYAN, "fg": "black", "activebackground": ACCENT_GREEN, "relief": "flat", "font": ("Segoe UI", 9, "bold")}

        # 1. Top Bar (Connection)
        self.top_frame = tk.Frame(self.root, bg=BG_SEC, pady=8, padx=10)
        self.top_frame.pack(fill="x", side="top")
        
        tk.Label(self.top_frame, text="SERVER:", bg=BG_SEC, fg=ACCENT_CYAN, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.entry_server = tk.Entry(self.top_frame, width=25, **style_entry)
        self.entry_server.insert(0, "http://localhost:5000")
        self.entry_server.pack(side="left", padx=5)
        
        tk.Label(self.top_frame, text="ID:", bg=BG_SEC, fg=ACCENT_CYAN, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(10,0))
        self.entry_device = tk.Entry(self.top_frame, width=5, **style_entry)
        self.entry_device.insert(0, "A")
        self.entry_device.pack(side="left", padx=5)

        tk.Label(self.top_frame, text="EMAIL:", bg=BG_SEC, fg=ACCENT_CYAN, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(10,0))
        self.entry_email = tk.Entry(self.top_frame, width=25, **style_entry)
        self.entry_email.pack(side="left", padx=5)
        
        self.btn_connect = tk.Button(self.top_frame, text="INITIALIZE LINK", command=self.start_connection, **style_btn)
        self.btn_connect.pack(side="right", padx=5)
        
        # 2. Main Content Area (Split Left/Right)
        self.main_split = tk.Frame(self.root, bg=BG_COLOR)
        self.main_split.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Left: Chat Terminal
        self.left_panel = tk.Frame(self.main_split, bg=BG_COLOR)
        self.left_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        tk.Label(self.left_panel, text=">> SECURE COMMUNICATION LOG", **style_label).pack(anchor="w")
        
        self.chat_frame = tk.Frame(self.left_panel, bg=ACCENT_CYAN, padx=1, pady=1) # Border effect
        self.chat_frame.pack(fill="both", expand=True, pady=5)
        
        self.chat_area = scrolledtext.ScrolledText(self.chat_frame, bg="black", fg=TEXT_MAIN, font=("Consolas", 11), state="disabled", highlightthickness=0)
        self.chat_area.pack(fill="both", expand=True)
        
        # Tags for coloring text
        self.chat_area.tag_config("me", foreground=ACCENT_CYAN)
        self.chat_area.tag_config("other", foreground="#00ff00") # Bright Green
        self.chat_area.tag_config("system", foreground="#888888", font=("Consolas", 9, "italic"))
        self.chat_area.tag_config("alert", foreground=ACCENT_RED, font=("Consolas", 11, "bold"))
        self.chat_area.tag_config("secure", foreground=ACCENT_CYAN, background="#002222")

        # Right: Visuals & Metrics
        self.right_panel = tk.Frame(self.main_split, bg=BG_COLOR, width=300)
        self.right_panel.pack(side="right", fill="y", padx=0)
        self.right_panel.pack_propagate(False) # Fixed width
        
        # -- Status Box --
        self.status_frame = tk.LabelFrame(self.right_panel, text="SYSTEM STATUS", bg=BG_COLOR, fg=ACCENT_CYAN, font=("Segoe UI", 10, "bold"))
        self.status_frame.pack(fill="x", pady=(0, 10))
        
        self.lbl_status = tk.Label(self.status_frame, text="OFFLINE", bg=BG_COLOR, fg="#555", font=("Segoe UI", 14, "bold"))
        self.lbl_status.pack(pady=10)
        
        # -- Visualizer Canvas --
        tk.Label(self.right_panel, text="CHANNEL VISUALIZER", **style_label).pack(anchor="w")
        self.canvas = tk.Canvas(self.right_panel, bg="black", height=150, highlightthickness=1, highlightbackground=BG_SEC)
        self.canvas.pack(fill="x", pady=5)
        
        # Draw static nodes
        self.node_me = self.canvas.create_oval(30, 60, 60, 90, outline=ACCENT_CYAN, width=2)
        self.canvas.create_text(45, 105, text="ME", fill="white", font=("Arial", 8))
        
        self.node_server = self.canvas.create_oval(135, 60, 165, 90, outline="#333", width=2)
        self.canvas.create_text(150, 105, text="SERVER", fill="#666", font=("Arial", 8))
        
        self.node_other = self.canvas.create_oval(240, 60, 270, 90, outline="#333", width=2)
        self.canvas.create_text(255, 105, text="TARGET", fill="#666", font=("Arial", 8))
        
        # Lines
        self.link_1 = self.canvas.create_line(60, 75, 135, 75, fill="#222", width=2)
        self.link_2 = self.canvas.create_line(165, 75, 240, 75, fill="#222", width=2)

        # -- Metrics --
        self.metrics_frame = tk.LabelFrame(self.right_panel, text="TELEMETRY", bg=BG_COLOR, fg=ACCENT_CYAN, font=("Segoe UI", 10, "bold"))
        self.metrics_frame.pack(fill="both", expand=True, pady=10)
        
        self.lbl_qber = tk.Label(self.metrics_frame, text="QBER: 0.0000", bg=BG_COLOR, fg=ACCENT_RED, font=FONT_DIGITAL)
        self.lbl_qber.pack(anchor="w", padx=10, pady=5)
        
        self.lbl_signal = tk.Label(self.metrics_frame, text="SIGNAL: 0.0000", bg=BG_COLOR, fg=ACCENT_GREEN, font=FONT_DIGITAL)
        self.lbl_signal.pack(anchor="w", padx=10, pady=5)
        
        # Mini Graph for QBER
        self.graph_canvas = tk.Canvas(self.metrics_frame, bg="#050505", height=100, highlightthickness=0)
        self.graph_canvas.pack(fill="x", padx=5, pady=5)
        self.draw_graph()

        # 3. Bottom Input Area
        self.bottom_frame = tk.Frame(self.root, bg=BG_SEC, pady=10, padx=10)
        self.bottom_frame.pack(fill="x", side="bottom")
        
        tk.Label(self.bottom_frame, text="TARGET:", bg=BG_SEC, fg=ACCENT_CYAN, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.entry_target = tk.Entry(self.bottom_frame, width=5, **style_entry)
        self.entry_target.insert(0, "B")
        self.entry_target.pack(side="left", padx=5)
        
        tk.Label(self.bottom_frame, text="MSG:", bg=BG_SEC, fg=ACCENT_CYAN, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(10,0))
        self.entry_msg = tk.Entry(self.bottom_frame, **style_entry)
        self.entry_msg.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_msg.bind("<Return>", self.send_message)
        
        self.btn_send = tk.Button(self.bottom_frame, text="SEND ENCRYPTED", command=self.send_message, **style_btn)
        self.btn_send.pack(side="right", padx=5)

    # --- Visuals ---
    def log(self, msg, tag="system"):
        self.chat_area.config(state="normal")
        self.chat_area.insert("end", msg + "\n", tag)
        self.chat_area.see("end")
        self.chat_area.config(state="disabled")

    def animate_pulse(self):
        # Pulse the "ME" node if connected
        if self.is_connected:
            cur_color = self.canvas.itemcget(self.node_me, "outline")
            new_color = "white" if cur_color == ACCENT_CYAN else ACCENT_CYAN
            self.canvas.itemconfig(self.node_me, outline=new_color)
        else:
            self.canvas.itemconfig(self.node_me, outline="#333")
            
        self.root.after(800, self.animate_pulse)

    def draw_graph(self):
        self.graph_canvas.delete("all")
        w = self.graph_canvas.winfo_width()
        h = self.graph_canvas.winfo_height()
        if w < 10: w = 280 # Default if not packed yet
        
        # Normalize QBER (0.0 to 0.1 usually, max 1.0)
        max_val = 0.1
        step = w / (len(self.qber_history) - 1)
        
        points = []
        for i, val in enumerate(self.qber_history):
            x = i * step
            y = h - (min(val, max_val) / max_val * h)
            points.append(x)
            points.append(y)
            
        if len(points) >= 4:
            self.graph_canvas.create_line(points, fill=ACCENT_RED, width=2, smooth=True)

    def animate_packet(self, direction="out", color=ACCENT_CYAN):
        # direction: 'out' (Me -> Server), 'in' (Server -> Me)
        packet_size = 6
        if direction == "out":
            start_x, start_y = 60, 75
            end_x, end_y = 135, 75
        else:
            start_x, start_y = 135, 75
            end_x, end_y = 60, 75
            
        packet = self.canvas.create_oval(start_x-packet_size, start_y-packet_size, 
                                         start_x+packet_size, start_y+packet_size, 
                                         fill=color, outline="white")
        
        def move():
            coords = self.canvas.coords(packet)
            if not coords: return
            curr_x = (coords[0] + coords[2]) / 2
            
            dx = 4 if direction == "out" else -4
            
            if (direction == "out" and curr_x < end_x) or (direction == "in" and curr_x > end_x):
                self.canvas.move(packet, dx, 0)
                self.root.after(10, move)
            else:
                self.canvas.delete(packet)
                if direction == "out":
                    self.animate_server_to_other()

        move()

    def animate_server_to_other(self):
        packet = self.canvas.create_oval(165-4, 75-4, 165+4, 75+4, fill="#555", outline="")
        def move():
            coords = self.canvas.coords(packet)
            if not coords: return
            curr_x = (coords[0] + coords[2]) / 2
            if curr_x < 240:
                self.canvas.move(packet, 4, 0)
                self.root.after(10, move)
            else:
                self.canvas.delete(packet)
        move()

    # --- Socket Logic ---
    def setup_socket_events(self):
        @self.sio.event
        def connect():
            self.log("[SYSTEM] Connected to Server. Authenticating...", "system")
            self.canvas.itemconfig(self.node_server, outline=ACCENT_CYAN)
            self.canvas.itemconfig(self.link_1, fill=ACCENT_CYAN)
            self.sio.emit("register", {"device_id": self.device_id, "email": self.email})

        @self.sio.on("auth_challenge")
        def on_auth_challenge(data):
            self.root.after(0, self.ask_auth_code)

        @self.sio.on("auth_result")
        def on_auth_result(data):
            if data.get("ok"):
                self.log("[SYSTEM] Authentication Successful. Channel Secure.", "secure")
                self.is_connected = True
                self.lbl_status.config(text="SECURE LINK", fg=ACCENT_CYAN)
                self.canvas.itemconfig(self.node_me, fill=ACCENT_CYAN)
            else:
                self.log(f"[ERROR] Auth Failed: {data.get('reason')}", "alert")
                self.sio.disconnect()

        @self.sio.on("incoming_message")
        def on_incoming(data):
            self.root.after(0, lambda: self.handle_incoming(data))

        @self.sio.on("alert_attack")
        def on_alert_attack(data):
            self.root.after(0, lambda: self.update_metrics(data))

        @self.sio.on("force_disconnect")
        def on_force_disconnect(data):
            reason = data.get("reason")
            details = data.get("details", "")
            self.log(f"\n[CRITICAL] DISCONNECTED: {reason}", "alert")
            self.log(details, "alert")
            self.is_connected = False
            self.lbl_status.config(text="TERMINATED", fg=ACCENT_RED)
            self.canvas.itemconfig(self.node_me, fill="")
            self.canvas.itemconfig(self.link_1, fill="#222")
            self.sio.disconnect()

        @self.sio.on("disconnect")
        def on_disconnect():
            self.log("[SYSTEM] Connection lost.", "alert")
            self.is_connected = False
            self.lbl_status.config(text="OFFLINE", fg="#555")
            self.canvas.itemconfig(self.node_server, outline="#333")
            self.canvas.itemconfig(self.link_1, fill="#222")

    def ask_auth_code(self):
        code = simpledialog.askstring("AUTHENTICATION", f"Enter QKD Code sent to {self.email}:", parent=self.root)
        if code:
            self.sio.emit("auth_response", {"code": code})

    def handle_incoming(self, data):
        frm = data.get("from")
        text = data.get("text")
        label = data.get("label")
        
        self.animate_packet("in", color=ACCENT_RED if label==1 else ACCENT_CYAN)
        
        if label == 1:
            self.log(f"\n[WARNING] INTERCEPTION DETECTED FROM {frm}", "alert")
            self.lbl_status.config(text="COMPROMISED", fg=ACCENT_RED)
        else:
            self.lbl_status.config(text="SECURE LINK", fg=ACCENT_CYAN)
        
        self.log(f"[{frm}]: {text}", "other")

    def update_metrics(self, data):
        qber = data.get("QBER", 0.0)
        signal = data.get("SignalIntensity", 0.0)
        
        self.lbl_qber.config(text=f"QBER: {qber:.4f}")
        self.lbl_signal.config(text=f"SIGNAL: {signal:.4f}")
        
        # Update Graph
        self.qber_history.append(qber)
        self.qber_history.pop(0)
        self.draw_graph()
        
        self.lbl_status.config(text="ATTACK DETECTED", fg=ACCENT_RED)
        
        narrative = data.get("narrative", "")
        self.log(f"\n[ALERT] {narrative}", "alert")

    def start_connection(self):
        self.server_url = self.entry_server.get().strip()
        self.device_id = self.entry_device.get().strip().upper()
        self.email = self.entry_email.get().strip()
        
        if not self.email:
            messagebox.showerror("Error", "Email is required for QKD Authentication.")
            return

        threading.Thread(target=self.connect_thread, daemon=True).start()

    def connect_thread(self):
        try:
            self.sio.connect(self.server_url)
        except Exception as e:
            self.log(f"Connection Failed: {e}", "alert")

    def send_message(self, event=None):
        if not self.is_connected:
            self.log("System Offline. Connect first.", "alert")
            return
            
        target = self.entry_target.get().strip().upper()
        text = self.entry_msg.get().strip()
        
        if not target or not text:
            return
            
        self.sio.emit("send_message", {"from": self.device_id, "to": target, "text": text})
        self.log(f"[ME]: {text}", "me")
        self.entry_msg.delete(0, "end")
        
        self.animate_packet("out")

if __name__ == "__main__":
    root = tk.Tk()
    app = QKDClientGUI(root)
    root.mainloop()
