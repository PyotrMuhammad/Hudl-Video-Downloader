"""
Multi-Platform Sports Video Downloader — GUI Interface
Simple tkinter GUI for non-technical users.
Supports: HUDL, VEO, YouTube, TRACE, PIXELLOT
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from extractors import get_platform
from batch import BatchManager, QueueItem
from downloader import DownloadProgress
from utils import find_ffmpeg, format_size, sanitize_filename, read_urls_from_file
from hudl_auth import ensure_valid_cookies, needs_hudl_auth, load_credentials, are_cookies_valid


class HudlDownloaderGUI:
    """Main GUI window."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Sports Video Downloader")
        self.root.geometry("780x660")
        self.root.minsize(660, 580)
        self.root.configure(bg="#1e1e2e")

        self.batch_manager = None
        self._ffmpeg_path = None

        self._setup_styles()
        self._build_ui()
        self._check_ffmpeg()
        self._load_saved_credentials()

    def _setup_styles(self):
        """Configure ttk styles for dark theme."""
        self.style = ttk.Style()
        self.style.theme_use("clam")

        bg = "#1e1e2e"
        fg = "#cdd6f4"
        accent = "#89b4fa"
        surface = "#313244"
        red = "#f38ba8"
        green = "#a6e3a1"

        self.style.configure("TFrame", background=bg)
        self.style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
        self.style.configure("Title.TLabel", background=bg, foreground=accent,
                             font=("Segoe UI", 16, "bold"))
        self.style.configure("Status.TLabel", background=bg, foreground=green,
                             font=("Segoe UI", 9))
        self.style.configure("Warn.TLabel", background=bg, foreground="#fab387",
                             font=("Segoe UI", 9))
        self.style.configure("Error.TLabel", background=bg, foreground=red,
                             font=("Segoe UI", 9))
        self.style.configure("TButton", background=accent, foreground="#1e1e2e",
                             font=("Segoe UI", 10, "bold"), padding=(12, 6))
        self.style.map("TButton", background=[("active", "#74c7ec")])
        self.style.configure("Cancel.TButton", background=red, foreground="#1e1e2e")
        self.style.configure("Small.TButton", background=surface, foreground=fg,
                             font=("Segoe UI", 9), padding=(6, 3))
        self.style.map("Small.TButton", background=[("active", "#45475a")])
        self.style.configure("TEntry", fieldbackground=surface, foreground=fg,
                             insertcolor=fg, font=("Consolas", 10))
        self.style.configure("Horizontal.TProgressbar", background=accent,
                             troughcolor=surface, thickness=20)

        self.colors = {"bg": bg, "fg": fg, "accent": accent, "surface": surface,
                       "red": red, "green": green}

    def _build_ui(self):
        """Build the main UI layout."""
        c = self.colors

        # Main container with padding
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill=tk.BOTH, expand=True)

        # Title row with Load File button
        title_row = ttk.Frame(main)
        title_row.pack(fill=tk.X)
        ttk.Label(title_row, text="Sports Video Downloader", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(title_row, text="Load File", command=self._load_url_file,
                   style="TButton").pack(side=tk.RIGHT)

        ttk.Label(main, text="Paste video URLs below (HUDL, VEO, YouTube, TRACE, PIXELLOT), or load from file",
                  style="TLabel").pack(anchor="w", pady=(2, 10))

        # URL input area
        url_frame = tk.Frame(main, bg=c["surface"], bd=1, relief="solid")
        url_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.url_text = scrolledtext.ScrolledText(
            url_frame, height=7, bg=c["surface"], fg=c["fg"],
            insertbackground=c["fg"], font=("Consolas", 10),
            wrap=tk.WORD, bd=0, padx=8, pady=8,
            selectbackground=c["accent"], selectforeground=c["bg"],
        )
        self.url_text.pack(fill=tk.BOTH, expand=True)

        # Settings row
        settings = ttk.Frame(main)
        settings.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(settings, text="Save to:").grid(row=0, column=0, sticky="w")
        self.output_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        output_entry = ttk.Entry(settings, textvariable=self.output_var, width=40)
        output_entry.grid(row=0, column=1, padx=(8, 4), sticky="ew")
        ttk.Button(settings, text="Browse", command=self._browse_output,
                   style="TButton").grid(row=0, column=2, padx=(4, 0))
        settings.columnconfigure(1, weight=1)

        # Quality + Workers row
        opts = ttk.Frame(main)
        opts.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(opts, text="Quality:").grid(row=0, column=0, sticky="w")
        self.quality_var = tk.StringVar(value="best")
        quality_combo = ttk.Combobox(opts, textvariable=self.quality_var, width=12,
                                     values=["best", "1080p", "720p", "540p", "worst"],
                                     state="readonly")
        quality_combo.grid(row=0, column=1, padx=(8, 20), sticky="w")

        ttk.Label(opts, text="Concurrent:").grid(row=0, column=2, sticky="w")
        self.workers_var = tk.StringVar(value="2")
        workers_spin = ttk.Spinbox(opts, textvariable=self.workers_var, from_=1, to=5, width=5)
        workers_spin.grid(row=0, column=3, padx=(8, 0), sticky="w")

        # ── HUDL Login section ────────────────────────────────────────────────
        hudl_frame = tk.Frame(main, bg=c["surface"], bd=1, relief="solid")
        hudl_frame.pack(fill=tk.X, pady=(0, 6))

        inner = tk.Frame(hudl_frame, bg=c["surface"])
        inner.pack(fill=tk.X, padx=10, pady=6)

        tk.Label(inner, text="HUDL Login", bg=c["surface"], fg=c["accent"],
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", columnspan=4)

        tk.Label(inner, text="Email:", bg=c["surface"], fg=c["fg"],
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.hudl_email_var = tk.StringVar()
        tk.Entry(inner, textvariable=self.hudl_email_var, width=28,
                 bg=c["bg"], fg=c["fg"], insertbackground=c["fg"],
                 font=("Consolas", 9), relief="flat", bd=1
                 ).grid(row=1, column=1, padx=(6, 10), pady=(4, 0), sticky="w")

        tk.Label(inner, text="Password:", bg=c["surface"], fg=c["fg"],
                 font=("Segoe UI", 9)).grid(row=1, column=2, sticky="w", pady=(4, 0))
        self.hudl_pass_var = tk.StringVar()
        tk.Entry(inner, textvariable=self.hudl_pass_var, width=22, show="*",
                 bg=c["bg"], fg=c["fg"], insertbackground=c["fg"],
                 font=("Consolas", 9), relief="flat", bd=1
                 ).grid(row=1, column=3, padx=(6, 10), pady=(4, 0), sticky="w")

        self.hudl_status_var = tk.StringVar(value="Not checked")
        self.hudl_status_lbl = tk.Label(inner, textvariable=self.hudl_status_var,
                                        bg=c["surface"], fg=c["fg"],
                                        font=("Segoe UI", 8))
        self.hudl_status_lbl.grid(row=2, column=0, columnspan=3, sticky="w", pady=(3, 0))

        ttk.Button(inner, text="Test Login", command=self._test_hudl_login,
                   style="Small.TButton").grid(row=2, column=3, sticky="e", pady=(3, 0))

        # ── Auth token row (TRACE / PIXELLOT JWT) ────────────────────────────
        auth_row = ttk.Frame(main)
        auth_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(auth_row, text="Auth Token:").grid(row=0, column=0, sticky="w")
        self.token_var = tk.StringVar()
        ttk.Entry(auth_row, textvariable=self.token_var, width=40, show="*"
                  ).grid(row=0, column=1, padx=(8, 8), sticky="ew")
        ttk.Label(auth_row, text="(optional — for TRACE/PIXELLOT JWT)",
                  style="Status.TLabel").grid(row=0, column=2, sticky="w")
        auth_row.columnconfigure(1, weight=1)

        # Buttons row
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.download_btn = ttk.Button(btn_frame, text="Download",
                                       command=self._start_download)
        self.download_btn.pack(side=tk.LEFT)

        self.cancel_btn = ttk.Button(btn_frame, text="Cancel", style="Cancel.TButton",
                                     command=self._cancel_download, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.clear_btn = ttk.Button(btn_frame, text="Clear Log", command=self._clear_log)
        self.clear_btn.pack(side=tk.RIGHT)

        # Progress bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(main, variable=self.progress_var,
                                            maximum=100, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        # Status label
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(main, textvariable=self.status_var, style="Status.TLabel")
        self.status_label.pack(anchor="w", pady=(0, 5))

        # Log area
        log_frame = tk.Frame(main, bg=c["surface"], bd=1, relief="solid")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=7, bg=c["surface"], fg=c["fg"],
            font=("Consolas", 9), wrap=tk.WORD, bd=0, padx=8, pady=8,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.log_text.tag_configure("info", foreground=c["fg"])
        self.log_text.tag_configure("success", foreground=c["green"])
        self.log_text.tag_configure("error", foreground=c["red"])
        self.log_text.tag_configure("accent", foreground=c["accent"])

    # ── Startup ───────────────────────────────────────────────────────────────

    def _check_ffmpeg(self):
        try:
            self._ffmpeg_path = find_ffmpeg()
            self._log(f"FFmpeg found: {self._ffmpeg_path}\n", "info")
        except FileNotFoundError:
            self._log("FFmpeg not found! Download from: https://www.gyan.dev/ffmpeg/builds/\n", "error")
            self._ffmpeg_path = None

    def _load_saved_credentials(self):
        """Load saved HUDL credentials and check cookie validity on startup."""
        email, password = load_credentials()
        if email:
            self.hudl_email_var.set(email)
            self.hudl_pass_var.set(password)
            # Check cookie validity in background (non-blocking)
            threading.Thread(target=self._check_hudl_cookies_bg, daemon=True).start()

    def _check_hudl_cookies_bg(self):
        """Background thread: check cookies locally (no HTTP) and update label."""
        valid = are_cookies_valid(full_check=False)
        def _update():
            if valid:
                self._set_hudl_status("Session active", "green")
            else:
                self._set_hudl_status("Session expired — will auto-login on next download", "warn")
        self.root.after(0, _update)

    def _set_hudl_status(self, msg: str, level: str = "info"):
        c = self.colors
        color = {"green": c["green"], "warn": "#fab387", "error": c["red"]}.get(level, c["fg"])
        self.hudl_status_var.set(msg)
        self.hudl_status_lbl.configure(fg=color)

    # ── HUDL Test Login button ────────────────────────────────────────────────

    def _test_hudl_login(self):
        email = self.hudl_email_var.get().strip()
        password = self.hudl_pass_var.get().strip()
        if not email or not password:
            messagebox.showwarning("HUDL Login", "Enter your HUDL email and password first.")
            return
        self._set_hudl_status("Testing...", "info")
        self.root.update_idletasks()

        def _run():
            try:
                # Force re-login (ignore cached cookies) then do full HTTP check
                from hudl_auth import COOKIES_FILE
                COOKIES_FILE.unlink(missing_ok=True)
                path = ensure_valid_cookies(
                    email, password,
                    on_status=lambda m: self.root.after(0, lambda: self._set_hudl_status(m, "info"))
                )
                self.root.after(0, lambda: self._set_hudl_status("Login verified — session active", "green"))
                self.root.after(0, lambda: self._log("HUDL login OK — session saved\n", "success"))
            except Exception as e:
                msg = str(e)
                self.root.after(0, lambda: self._set_hudl_status(f"Login failed: {msg}", "error"))
                self.root.after(0, lambda: self._log(f"HUDL login failed: {msg}\n", "error"))

        threading.Thread(target=_run, daemon=True).start()

    # ── File helpers ──────────────────────────────────────────────────────────

    def _load_url_file(self):
        filepath = filedialog.askopenfilename(
            title="Select URL file",
            filetypes=[
                ("All supported", "*.txt *.csv *.xlsx"),
                ("Text files", "*.txt"),
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
            ],
        )
        if not filepath:
            return
        try:
            urls = read_urls_from_file(filepath)
        except Exception as e:
            messagebox.showerror("Load Error", f"Could not read file:\n{e}")
            return
        if not urls:
            messagebox.showwarning("No URLs", f"No URLs found in:\n{os.path.basename(filepath)}")
            return
        existing = self.url_text.get("1.0", tk.END).strip()
        if existing:
            self.url_text.insert(tk.END, "\n")
        self.url_text.insert(tk.END, "\n".join(urls))
        self._log(f"Loaded {len(urls)} URL(s) from: {os.path.basename(filepath)}\n", "accent")

    def _browse_output(self):
        d = filedialog.askdirectory(initialdir=self.output_var.get())
        if d:
            self.output_var.set(d)

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _log(self, message: str, tag: str = "info"):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message, tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ── Download flow ─────────────────────────────────────────────────────────

    def _start_download(self):
        if not self._ffmpeg_path:
            messagebox.showerror("FFmpeg Missing",
                                 "FFmpeg is required. Download from:\nhttps://www.gyan.dev/ffmpeg/builds/")
            return

        raw = self.url_text.get("1.0", tk.END).strip()
        urls = [line.strip() for line in raw.split("\n")
                if line.strip() and not line.strip().startswith("#")]

        if not urls:
            messagebox.showwarning("No URLs", "Please paste at least one video URL.")
            return

        output_dir = self.output_var.get()
        quality = self.quality_var.get()
        workers = int(self.workers_var.get())
        token = self.token_var.get().strip() or None
        email = self.hudl_email_var.get().strip()
        password = self.hudl_pass_var.get().strip()

        self.download_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        self.progress_var.set(0)

        self._log(f"\nStarting download of {len(urls)} URL(s)...\n", "accent")
        self._log(f"Output: {output_dir}\n", "info")
        self._log(f"Quality: {quality} | Workers: {workers}\n\n", "info")

        def _run():
            cookies_path = None

            # Auto-login for HUDL app.hudl.com URLs
            if needs_hudl_auth(urls):
                if not email or not password:
                    self.root.after(0, lambda: self._log(
                        "HUDL private videos detected — enter HUDL email & password above.\n", "error"))
                    self.root.after(0, self._reset_buttons)
                    return
                try:
                    def _status(msg):
                        self.root.after(0, lambda: self._set_hudl_status(msg, "info"))
                        self.root.after(0, lambda: self.status_var.set(msg))

                    cookies_path = ensure_valid_cookies(email, password, on_status=_status)
                    self.root.after(0, lambda: self._set_hudl_status("Session active", "green"))
                    self.root.after(0, lambda: self._log("HUDL: session ready\n", "success"))
                except Exception as e:
                    msg = str(e)
                    self.root.after(0, lambda: self._log(f"HUDL login failed: {msg}\n", "error"))
                    self.root.after(0, lambda: self._set_hudl_status(f"Login failed: {msg}", "error"))
                    self.root.after(0, self._reset_buttons)
                    return

            bm = BatchManager(
                output_dir=output_dir,
                max_workers=workers,
                preferred_quality=quality,
                ffmpeg_path=self._ffmpeg_path,
                session_token=token,
                cookies=cookies_path,
            )
            bm.add_urls(urls)
            self.batch_manager = bm

            bm.start(
                on_progress=self._on_progress,
                on_item_done=self._on_item_done,
            )
            self.root.after(0, self._on_all_done)

        threading.Thread(target=_run, daemon=True).start()

    def _reset_buttons(self):
        self.download_btn.configure(state=tk.NORMAL)
        self.cancel_btn.configure(state=tk.DISABLED)

    def _on_progress(self, item: QueueItem):
        def _update():
            if item.status == "extracting":
                self.status_var.set(
                    f"[{item.index + 1}/{self.batch_manager.total}] Extracting: {item.url[:50]}...")
            elif item.status == "downloading" and item.progress:
                p = item.progress
                self.progress_var.set(p.percent)
                title = item.title[:30] if item.title else "video"
                self.status_var.set(
                    f"[{item.index + 1}/{self.batch_manager.total}] {title} — "
                    f"{p.percent:.1f}% | {p.size} | {p.speed}"
                )
        self.root.after(0, _update)

    def _on_item_done(self, item: QueueItem):
        def _update():
            if item.status == "done":
                size = ""
                if item.output_path and os.path.isfile(item.output_path):
                    size = f" ({format_size(os.path.getsize(item.output_path))})"
                self._log(f"DONE: {item.title}{size}\n", "success")
                self._log(f"  -> {item.output_path}\n", "info")
            elif item.status == "error":
                self._log(f"FAIL: {item.url[:60]}...\n", "error")
                self._log(f"  Error: {item.error}\n", "error")
            elif item.status == "cancelled":
                self._log(f"CANCELLED: {item.url[:60]}...\n", "error")

            done = self.batch_manager.completed + self.batch_manager.failed
            total = self.batch_manager.total
            if total > 0:
                self.progress_var.set((done / total) * 100)
        self.root.after(0, _update)

    def _on_all_done(self):
        bm = self.batch_manager
        self._log(f"\nAll done! {bm.completed} completed, {bm.failed} failed\n", "accent")
        self.status_var.set(f"Done — {bm.completed}/{bm.total} downloaded")
        self.progress_var.set(100)
        self._reset_buttons()

    def _cancel_download(self):
        if self.batch_manager:
            self.batch_manager.cancel_all()
            self._log("\nCancelling...\n", "error")
            self.status_var.set("Cancelling...")

    def run(self):
        self.root.mainloop()


def launch_gui():
    app = HudlDownloaderGUI()
    app.run()


if __name__ == "__main__":
    launch_gui()
