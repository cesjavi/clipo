import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import logging
import queue
from config import config
from window_context import list_open_windows, extract_text_uia, get_active_window_info
from text_cleaner import build_context
from groq_client import groq_client

# Configure logging
logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

class WinAutomationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Windows 10 Automation Assistant (GUI)")
        self.root.geometry("900x700")

        # --- Variables ---
        self.selected_window_var = tk.StringVar()
        self.windows_map = {}  # "Title (Process)" -> window_info_dict
        self.context_text = ""

        # --- Threading ---
        self.msg_queue = queue.Queue()
        self.root.after(100, self.process_queue)

        # --- Layout ---
        self.create_widgets()

        # Initial load
        self.refresh_windows()

    def create_widgets(self):
        # Top Frame: Window Selection
        top_frame = ttk.LabelFrame(self.root, text="Target Window", padding=10)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(top_frame, text="Select Window:").pack(side=tk.LEFT, padx=5)

        self.window_combo = ttk.Combobox(top_frame, textvariable=self.selected_window_var, state="readonly", width=60)
        self.window_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.window_combo.bind("<<ComboboxSelected>>", self.on_window_selected)

        ttk.Button(top_frame, text="Refresh List", command=self.refresh_windows).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Capture Context", command=self.capture_context).pack(side=tk.LEFT, padx=5)

        # Middle Frame: Paned Window (Context vs Chat)
        paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Context Frame (Top Pane)
        context_frame = ttk.LabelFrame(paned, text="Extracted Context (Editable)", padding=5)
        paned.add(context_frame, weight=1)

        self.txt_context = scrolledtext.ScrolledText(context_frame, height=10)
        self.txt_context.pack(fill=tk.BOTH, expand=True)

        context_btn_frame = ttk.Frame(context_frame)
        context_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(context_btn_frame, text="Copy Context", command=lambda: self.copy_to_clipboard(self.txt_context.get("1.0", tk.END))).pack(side=tk.RIGHT)

        # Chat Frame (Bottom Pane)
        chat_frame = ttk.LabelFrame(paned, text="Assistant Chat", padding=5)
        paned.add(chat_frame, weight=2)

        self.txt_chat = scrolledtext.ScrolledText(chat_frame, state="disabled", height=15)
        self.txt_chat.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Input Area
        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(input_frame, text="Question:").pack(side=tk.LEFT)
        self.entry_question = ttk.Entry(input_frame)
        self.entry_question.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.entry_question.bind("<Return>", lambda event: self.ask_groq())

        self.btn_send = ttk.Button(input_frame, text="Ask Groq", command=self.ask_groq)
        self.btn_send.pack(side=tk.LEFT)

        ttk.Button(chat_frame, text="Copy Response", command=self.copy_last_response).pack(side=tk.RIGHT, pady=2, padx=5)

    def process_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "context_ready":
                    self.txt_context.delete("1.0", tk.END)
                    self.txt_context.insert(tk.END, data)
                    self.status("Context captured.")
                elif msg_type == "response_ready":
                    self.append_chat(f"Assistant: {data}\n\n")
                    self.btn_send.config(state="normal")
                    self.status("Response received.")
                elif msg_type == "error":
                    messagebox.showerror("Error", data)
                    self.btn_send.config(state="normal")
                    self.status("Error occurred.")
                self.msg_queue.task_done()
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)

    def status(self, msg):
        # Could add a status bar, for now just log
        logger.info(msg)

    def refresh_windows(self):
        windows = list_open_windows()
        self.windows_map = {}
        display_list = []

        for w in windows:
            key = f"{w['title']} ({w['process_name']})"
            self.windows_map[key] = w
            display_list.append(key)

        self.window_combo['values'] = sorted(display_list)
        if display_list:
            self.window_combo.current(0)

    def on_window_selected(self, event):
        pass

    def capture_context(self):
        key = self.selected_window_var.get()
        if not key:
            return

        window_info = self.windows_map.get(key)
        if not window_info:
            return

        self.status(f"Capturing context for {key}...")
        self.txt_context.delete("1.0", tk.END)
        self.txt_context.insert(tk.END, "Capturing... please wait.")

        threading.Thread(target=self._capture_worker, args=(window_info,), daemon=True).start()

    def _capture_worker(self, window_info):
        try:
            raw_text = extract_text_uia(window_info['hwnd'])
            cleaned_text = build_context(window_info, raw_text, max_chars=config.MAX_CHARS)
            self.msg_queue.put(("context_ready", cleaned_text))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    def ask_groq(self):
        question = self.entry_question.get().strip()
        if not question:
            return

        context = self.txt_context.get("1.0", tk.END).strip()
        if not context or context == "Capturing... please wait.":
            if not messagebox.askyesno("Warning", "Context seems empty or capturing. Send anyway?"):
                return

        self.append_chat(f"User: {question}\n")
        self.entry_question.delete(0, tk.END)
        self.btn_send.config(state="disabled")

        # Prepare prompt
        SYSTEM_PROMPT = """
        You are a senior Windows 10 automation assistant.
        Use the provided context (active window text) to answer the user's question.
        Be concrete and concise.
        """

        user_msg = f"CONTEXT:\n{context}\n\nQUESTION:\n{question}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg}
        ]

        threading.Thread(target=self._groq_worker, args=(messages,), daemon=True).start()

    def _groq_worker(self, messages):
        try:
            response = groq_client.ask_groq(messages, model=config.GROQ_MODEL)
            self.msg_queue.put(("response_ready", response))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    def append_chat(self, text):
        self.txt_chat.config(state="normal")
        self.txt_chat.insert(tk.END, text)
        self.txt_chat.see(tk.END)
        self.txt_chat.config(state="disabled")

    def copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status("Copied to clipboard.")

    def copy_last_response(self):
        # Heuristic: get text since last "Assistant:"
        content = self.txt_chat.get("1.0", tk.END)
        last_idx = content.rfind("Assistant:")
        if last_idx != -1:
            text = content[last_idx + len("Assistant:"):].strip()
            self.copy_to_clipboard(text)
        else:
            messagebox.showinfo("Info", "No assistant response found.")

if __name__ == "__main__":
    root = tk.Tk()
    app = WinAutomationApp(root)
    root.mainloop()
