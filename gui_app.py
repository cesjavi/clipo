import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import logging
import queue
import os
import psutil
from PIL import Image, ImageTk

# Windows-specific imports
try:
    import win32gui
    import win32process
    import win32con
    import win32api
    import win32ui
except ImportError:
    win32gui = None

from config import config
from window_context import list_open_windows, extract_text_uia, get_active_window_info
from text_cleaner import build_context
from groq_client import groq_client

# Configure logging
logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Colors & Fonts
# Using a modern palette: Slate 800/900 for backgrounds, Blue for accents
BG_DARK = "#0f172a"
BG_PANEL = "#1e293b"
BG_ITEM = "#334155"
BG_ITEM_SELECTED = "#2563eb"
FG_TEXT = "#f8fafc"
FG_DIM = "#94a3b8"
ACCENT = "#3b82f6"

FONT_MAIN = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI Semibold", 10)
FONT_CHAT = ("Segoe UI", 11)

class WinAutomationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Clipo")
        
        # High DPI awareness
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        # Floating icon geometry
        self.root.geometry("64x64+40+120")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG_DARK)

        # --- Variables ---
        self.selected_window_hwnd = None
        self.windows_map = {}  # hwnd -> window_info_dict
        self.context_text = ""
        self.icon_cache = {} # path -> PhotoImage

        # Drag state for floating icon
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Assistant panel
        self.panel = None

        # --- Threading ---
        self.msg_queue = queue.Queue()
        self.root.after(100, self.process_queue)

        # Style Configuration
        self.setup_styles()

        # --- Layout ---
        self.create_floating_widget()
        self.create_panel_window()

        # Initial load
        self.refresh_windows()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure scrollbar
        style.configure("TScrollbar", gripcount=0, background=BG_ITEM, darkcolor=BG_DARK, lightcolor=BG_ITEM, bordercolor=BG_DARK, arrowcolor=FG_TEXT)
        
        # Panel style
        style.configure("Panel.TFrame", background=BG_PANEL)
        style.configure("Panel.TLabelframe", background=BG_PANEL, foreground=FG_TEXT, font=FONT_BOLD)
        style.configure("Panel.TLabelframe.Label", background=BG_PANEL, foreground=FG_TEXT)
        
        style.configure("Action.TButton", font=FONT_BOLD, padding=6)
        style.map("Action.TButton",
            background=[('active', ACCENT), ('disabled', BG_DARK)],
            foreground=[('disabled', FG_DIM)]
        )
        
        style.configure("Command.TButton", font=("Segoe UI", 9), padding=4)
        style.map("Command.TButton",
            background=[('active', "#10b981"), ('!disabled', BG_ITEM)],
            foreground=[('!disabled', 'white')]
        )

    def create_floating_widget(self):
        self.icon_btn = tk.Button(
            self.root,
            text="🤖",
            font=("Segoe UI Emoji", 24),
            bg=ACCENT,
            fg="white",
            activebackground="#2563eb",
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            command=self.toggle_panel,
            cursor="hand2",
        )
        self.icon_btn.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Drag the floating assistant icon
        self.icon_btn.bind("<ButtonPress-1>", self._start_drag)
        self.icon_btn.bind("<B1-Motion>", self._do_drag)

    def create_panel_window(self):
        self.panel = tk.Toplevel(self.root)
        self.panel.title("Clipo Assistant")
        self.panel.geometry("900x750+120+120")
        self.panel.withdraw()
        self.panel.configure(bg=BG_PANEL)
        self.panel.protocol("WM_DELETE_WINDOW", self.hide_panel)

        # Main layout: Sidebar (Controls) + Main Area (Chat)
        self.paned = tk.PanedWindow(self.panel, orient=tk.HORIZONTAL, bg=BG_DARK, sashwidth=4, bd=0)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # --- Sidebar ---
        sidebar = tk.Frame(self.paned, bg=BG_PANEL, width=250)
        self.paned.add(sidebar, width=300)

        sidebar_container = ttk.Frame(sidebar, style="Panel.TFrame", padding=10)
        sidebar_container.pack(fill=tk.BOTH, expand=True)

        tk.Label(sidebar_container, text="Ventanas", font=FONT_BOLD, bg=BG_PANEL, fg=FG_TEXT).pack(anchor="w", pady=(0, 5))
        
        # Window Selection Scroll Area (Vertical for sidebar)
        canvas_container = tk.Frame(sidebar_container, bg=BG_DARK, bd=1, relief=tk.FLAT)
        canvas_container.pack(fill=tk.BOTH, expand=True)

        self.canvas_windows = tk.Canvas(canvas_container, bg=BG_DARK, highlightthickness=0)
        self.canvas_windows.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        self.scrollbar_v = ttk.Scrollbar(canvas_container, orient=tk.VERTICAL, command=self.canvas_windows.yview)
        self.scrollbar_v.pack(fill=tk.Y, side=tk.RIGHT)

        self.canvas_windows.configure(yscrollcommand=self.scrollbar_v.set)
        
        self.frame_icons = tk.Frame(self.canvas_windows, bg=BG_DARK)
        self.canvas_windows.create_window((0, 0), window=self.frame_icons, anchor="nw")
        
        self.frame_icons.bind("<Configure>", lambda e: self.canvas_windows.configure(scrollregion=self.canvas_windows.bbox("all")))

        # --- Automation Commands Section ---
        cmd_frame = ttk.LabelFrame(sidebar_container, text="Comandos", style="Panel.TLabelframe", padding=8)
        cmd_frame.pack(fill=tk.X, pady=(10, 0))

        # Focus
        ttk.Button(cmd_frame, text="🎯 Traer al frente", style="Command.TButton", command=self.cmd_focus).pack(fill=tk.X, pady=2)
        # Highlight (Simulated via focus)
        ttk.Button(cmd_frame, text="✨ Señalar", style="Command.TButton", command=self.cmd_highlight).pack(fill=tk.X, pady=2)
        # Type Keys
        ttk.Button(cmd_frame, text="⌨️ Escribir texto...", style="Command.TButton", command=self.cmd_type_dialog).pack(fill=tk.X, pady=2)
        
        ttk.Button(sidebar_container, text="🔄 Refrescar Lista", command=self.refresh_windows, style="Action.TButton").pack(fill=tk.X, pady=(10, 0))

        # --- Main Chat Area ---
        main_area = tk.Frame(self.paned, bg=BG_DARK)
        self.paned.add(main_area)

        chat_container = ttk.Frame(main_area, style="Panel.TFrame", padding=15)
        chat_container.pack(fill=tk.BOTH, expand=True)

        # Header in main area
        header_frame = ttk.Frame(chat_container, style="Panel.TFrame")
        header_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(header_frame, text="Clipo Assistant", font=("Segoe UI Semibold", 16), bg=BG_PANEL, fg=FG_TEXT).pack(side=tk.LEFT)

        self.txt_chat = scrolledtext.ScrolledText(
            chat_container, 
            state="disabled", 
            wrap=tk.WORD, 
            font=FONT_CHAT,
            bg=BG_DARK,
            fg=FG_TEXT,
            insertbackground="white",
            padx=15,
            pady=15,
            bd=0
        )
        self.txt_chat.pack(fill=tk.BOTH, expand=True)
        
        # Tags for chat styling
        self.txt_chat.tag_configure("user", foreground=ACCENT, font=("Segoe UI Bold", 11))
        self.txt_chat.tag_configure("bot", foreground=FG_TEXT)
        self.txt_chat.tag_configure("system", foreground=FG_DIM, font=("Segoe UI Italic", 9))

        # Input Section
        input_container = ttk.Frame(chat_container, style="Panel.TFrame", padding=(0, 10, 0, 0))
        input_container.pack(fill=tk.X)

        self.entry_question = tk.Entry(
            input_container, 
            font=FONT_CHAT, 
            bg=BG_ITEM, 
            fg=FG_TEXT, 
            insertbackground="white",
            relief=tk.FLAT,
            bd=10
        )
        self.entry_question.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.entry_question.bind("<Return>", lambda event: self.ask_groq())

        self.btn_send = tk.Button(
            input_container, 
            text="Enviar", 
            font=FONT_BOLD,
            bg=ACCENT,
            fg="white",
            activebackground="#2563eb",
            activeforeground="white",
            relief=tk.FLAT,
            padx=20,
            command=self.ask_groq,
            cursor="hand2"
        )
        self.btn_send.pack(side=tk.RIGHT)

    def _on_mousewheel(self, event):
        self.canvas_windows.yview_scroll(int(-1*(event.delta/120)), "units")

    def toggle_panel(self):
        if self.panel.state() == "withdrawn":
            self.panel.deiconify()
            self.panel.attributes("-topmost", True)
            self.panel.attributes("-topmost", False)
            self.refresh_windows()
        else:
            self.hide_panel()

    def hide_panel(self):
        self.panel.withdraw()

    def _start_drag(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _do_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_start_x)
        y = self.root.winfo_y() + (event.y - self._drag_start_y)
        self.root.geometry(f"+{x}+{y}")

    def process_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "context_ready":
                    self.context_text = data
                elif msg_type == "response_ready":
                    self.append_chat("Clipo", data, "bot")
                    self.btn_send.config(state="normal", text="Enviar")
                elif msg_type == "error":
                    self.append_chat("Error", data, "system")
                    self.btn_send.config(state="normal", text="Enviar")
                elif msg_type == "automation_done":
                    self.append_chat("System", data, "system")
                self.msg_queue.task_done()
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)

    def status(self, msg):
        logger.info(msg)

    # --- Automation Commands Implementation ---
    def cmd_focus(self):
        if not self.selected_window_hwnd:
            messagebox.showwarning("Atención", "Seleccioná una ventana primero.")
            return
        try:
            # Trick to allow SetForegroundWindow: send ALT
            import ctypes
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0) # ALT
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0) # ALT release
            
            win32gui.ShowWindow(self.selected_window_hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self.selected_window_hwnd)
            self.msg_queue.put(("automation_done", "Ventana enfocada."))
        except Exception as e:
            self.msg_queue.put(("error", f"No se pudo enfocar: {e}"))

    def cmd_highlight(self):
        if not self.selected_window_hwnd:
            messagebox.showwarning("Atención", "Seleccioná una ventana primero.")
            return
        win_info = self.windows_map.get(self.selected_window_hwnd)
        if win_info:
            messagebox.showinfo("Información de Ventana", 
                f"Título: {win_info['title']}\n"
                f"Proceso: {win_info['process_name']}\n"
                f"PID: {win_info['pid']}\n"
                f"HWND: {win_info['hwnd']}")

    def cmd_type_dialog(self):
        if not self.selected_window_hwnd:
            messagebox.showwarning("Atención", "Seleccioná una ventana primero.")
            return
        
        # Simple input dialog
        import tkinter.simpledialog as sd
        text_to_type = sd.askstring("Escribir texto", "Ingresá el texto que querés enviar a la ventana:")
        if text_to_type:
            threading.Thread(target=self._type_worker, args=(text_to_type,), daemon=True).start()

    def _type_worker(self, text):
        try:
            self.cmd_focus() # Ensure it's in front
            # Use pywinauto to type
            app = Application(backend="uia").connect(handle=self.selected_window_hwnd)
            window = app.window(handle=self.selected_window_hwnd)
            window.type_keys(text, with_spaces=True)
            self.msg_queue.put(("automation_done", f"Texto enviado: '{text}'"))
        except Exception as e:
            self.msg_queue.put(("error", f"Error al escribir: {e}"))

    def get_window_icon(self, hwnd):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            exe_path = proc.exe()
            
            if exe_path in self.icon_cache:
                return self.icon_cache[exe_path]

            large, small = win32gui.ExtractIconEx(exe_path, 0)
            if not large: return None

            ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
            ico_y = win32api.GetSystemMetrics(win32con.SM_CYICON)

            hdc = win32gui.GetDC(0)
            hdc_mem = win32gui.CreateCompatibleDC(hdc)
            hbmp = win32gui.CreateCompatibleBitmap(hdc, ico_x, ico_y)
            win32gui.SelectObject(hdc_mem, hbmp)
            win32gui.DrawIconEx(hdc_mem, 0, 0, large[0], ico_x, ico_y, 0, 0, win32con.DI_NORMAL)
            
            bmpinfo = win32gui.GetBitmap(hbmp)
            bmpstr = win32gui.GetBitmapBits(hbmp)
            
            img = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)

            win32gui.DeleteObject(hbmp); win32gui.DeleteDC(hdc_mem); win32gui.ReleaseDC(0, hdc)
            for h in large + small: win32api.DestroyIcon(h)

            img = img.resize((24, 24), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.icon_cache[exe_path] = photo
            return photo
        except: return None

    def refresh_windows(self):
        for widget in self.frame_icons.winfo_children(): widget.destroy()
        windows = list_open_windows()
        self.windows_map = {}
        windows = sorted(windows, key=lambda x: x['title'].lower())

        for w in windows:
            hwnd = w['hwnd']
            self.windows_map[hwnd] = w
            
            item_frame = tk.Frame(self.frame_icons, bg=BG_DARK, cursor="hand2")
            item_frame.pack(fill=tk.X, padx=2, pady=1)
            
            icon_img = self.get_window_icon(hwnd)
            if icon_img:
                lbl_icon = tk.Label(item_frame, image=icon_img, bg=BG_DARK)
            else:
                lbl_icon = tk.Label(item_frame, text="📄", font=("Segoe UI Emoji", 12), bg=BG_DARK, fg=FG_TEXT)
            lbl_icon.pack(side=tk.LEFT, padx=5)
            
            title = w['title']
            if len(title) > 30: title = title[:27] + "..."
            lbl_title = tk.Label(item_frame, text=title, font=("Segoe UI", 9), bg=BG_DARK, fg=FG_TEXT, anchor="w")
            lbl_title.pack(side=tk.LEFT, fill=tk.X, expand=True)

            def select_handler(h=hwnd, f=item_frame): self.on_window_selected(h, f)
            for child in (item_frame, lbl_icon, lbl_title):
                child.bind("<Button-1>", lambda e, h=hwnd, f=item_frame: self.on_window_selected(h, f))

        self.frame_icons.update_idletasks()
        self.canvas_windows.configure(scrollregion=self.canvas_windows.bbox("all"))

    def on_window_selected(self, hwnd, frame):
        for f in self.frame_icons.winfo_children():
            f.config(bg=BG_DARK)
            for child in f.winfo_children(): child.config(bg=BG_DARK)

        frame.config(bg=BG_ITEM_SELECTED)
        for child in frame.winfo_children(): child.config(bg=BG_ITEM_SELECTED)
        
        self.selected_window_hwnd = hwnd
        window_info = self.windows_map.get(hwnd)
        if window_info:
            self.append_chat("System", f"Seleccionaste: {window_info['title']}", "system")
            threading.Thread(target=self._capture_worker, args=(window_info,), daemon=True).start()

    def _capture_worker(self, window_info):
        try:
            raw_text = extract_text_uia(window_info['hwnd'])
            cleaned_text = build_context(window_info, raw_text, max_chars=config.MAX_CHARS)
            self.msg_queue.put(("context_ready", cleaned_text))
        except Exception as e:
            self.msg_queue.put(("error", f"Error de captura: {str(e)}"))

    def ask_groq(self):
        question = self.entry_question.get().strip()
        if not question: return
        if not self.selected_window_hwnd:
            messagebox.showwarning("Atención", "Seleccioná una ventana primero.")
            return

        self.append_chat("Tú", question, "user")
        self.entry_question.delete(0, tk.END)
        self.btn_send.config(state="disabled", text="...")

        SYSTEM_PROMPT = """
        Eres Clipo, un asistente de Windows 10 experto en automatización.
        Responde basándote en el contexto de la ventana seleccionada.
        Sé directo y servicial.
        """
        user_msg = f"CONTEXTO:\n{self.context_text}\n\nPREGUNTA:\n{question}"
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_msg}]
        threading.Thread(target=self._groq_worker, args=(messages,), daemon=True).start()

    def _groq_worker(self, messages):
        try:
            response = groq_client.ask_groq(messages, model=config.GROQ_MODEL)
            self.msg_queue.put(("response_ready", response))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    def append_chat(self, sender, text, tag):
        self.txt_chat.config(state="normal")
        self.txt_chat.insert(tk.END, f"{sender}: ", tag)
        self.txt_chat.insert(tk.END, f"{text}\n\n", "bot" if tag == "bot" else tag)
        self.txt_chat.see(tk.END)
        self.txt_chat.config(state="disabled")

if __name__ == "__main__":
    root = tk.Tk()
    root.configure(bg=BG_DARK)
    app = WinAutomationApp(root)
    root.mainloop()
