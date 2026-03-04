"""
Hudl Video Downloader — GUI Interface
Simple tkinter GUI for non-technical users.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from extractor import extract
from quality import fetch_and_select, format_variants_table
from batch import BatchManager, QueueItem
from downloader import DownloadProgress
from utils import find_ffmpeg, format_size, sanitize_filename, read_urls_from_file


class HudlDownloaderGUI:
    """Main GUI window."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Hudl Video Downloader")
        self.root.geometry("750x620")
        self.root.minsize(650, 550)
        self.root.configure(bg="#1e1e2e")

        self.batch_manager = None
        self._ffmpeg_path = None

        self._setup_styles()
        self._build_ui()
        self._check_ffmpeg()

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
        self.style.configure("Error.TLabel", background=bg, foreground=red,
                             font=("Segoe UI", 9))
        self.style.configure("TButton", background=accent, foreground="#1e1e2e",
                             font=("Segoe UI", 10, "bold"), padding=(12, 6))
        self.style.map("TButton", background=[("active", "#74c7ec")])
        self.style.configure("Cancel.TButton", background=red, foreground="#1e1e2e")
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
        ttk.Label(title_row, text="Hudl Video Downloader", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(title_row, text="Load File", command=self._load_url_file,
                   style="TButton").pack(side=tk.RIGHT)

        ttk.Label(main, text="Paste Hudl URLs below, or load from .txt / .csv / .xlsx file",
                  style="TLabel").pack(anchor="w", pady=(2, 10))

        # URL input area
        url_frame = tk.Frame(main, bg=c["surface"], bd=1, relief="solid")
        url_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.url_text = scrolledtext.ScrolledText(
            url_frame, height=8, bg=c["surface"], fg=c["fg"],
            insertbackground=c["fg"], font=("Consolas", 10),
            wrap=tk.WORD, bd=0, padx=8, pady=8,
            selectbackground=c["accent"], selectforeground=c["bg"],
        )
        self.url_text.pack(fill=tk.BOTH, expand=True)
        self.url_text.insert("1.0", "")

        # Settings row
        settings = ttk.Frame(main)
        settings.pack(fill=tk.X, pady=(0, 10))

        # Output directory
        ttk.Label(settings, text="Save to:").grid(row=0, column=0, sticky="w")
        self.output_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        output_entry = ttk.Entry(settings, textvariable=self.output_var, width=40)
        output_entry.grid(row=0, column=1, padx=(8, 4), sticky="ew")
        ttk.Button(settings, text="Browse", command=self._browse_output,
                   style="TButton").grid(row=0, column=2, padx=(4, 0))

        settings.columnconfigure(1, weight=1)

        # Quality + Workers row
        opts = ttk.Frame(main)
        opts.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(opts, text="Quality:").grid(row=0, column=0, sticky="w")
        self.quality_var = tk.StringVar(value="best")
        quality_combo = ttk.Combobox(opts, textvariable=self.quality_var, width=12,
                                     values=["best", "1080p", "720p", "540p", "worst"],
                                     state="readonly")
        quality_combo.grid(row=0, column=1, padx=(8, 20), sticky="w")

        ttk.Label(opts, text="Concurrent:").grid(row=0, column=2, sticky="w")
        self.workers_var = tk.StringVar(value="2")
        workers_spin = ttk.Spinbox(opts, textvariable=self.workers_var, from_=1, to=5,
                                   width=5)
        workers_spin.grid(row=0, column=3, padx=(8, 0), sticky="w")

        # Buttons row
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.download_btn = ttk.Button(btn_frame, text="Download",
                                       command=self._start_download)
        self.download_btn.pack(side=tk.LEFT)

        self.cancel_btn = ttk.Button(btn_frame, text="Cancel", style="Cancel.TButton",
                                     command=self._cancel_download, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.clear_btn = ttk.Button(btn_frame, text="Clear Log",
                                    command=self._clear_log)
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
            log_frame, height=8, bg=c["surface"], fg=c["fg"],
            font=("Consolas", 9), wrap=tk.WORD, bd=0, padx=8, pady=8,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configure log text tags
        self.log_text.tag_configure("info", foreground=c["fg"])
        self.log_text.tag_configure("success", foreground=c["green"])
        self.log_text.tag_configure("error", foreground=c["red"])
        self.log_text.tag_configure("accent", foreground=c["accent"])

    def _check_ffmpeg(self):
        """Check if FFmpeg is available."""
        try:
            self._ffmpeg_path = find_ffmpeg()
            self._log(f"FFmpeg found: {self._ffmpeg_path}\n", "info")
        except FileNotFoundError:
            self._log("FFmpeg not found! Download from: https://www.gyan.dev/ffmpeg/builds/\n", "error")
            self._ffmpeg_path = None

    def _load_url_file(self):
        """Load URLs from a .txt, .csv, or .xlsx file into the URL text area."""
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
            messagebox.showwarning("No URLs", f"No Hudl URLs found in:\n{os.path.basename(filepath)}")
            return

        # Append to existing text (don't overwrite)
        existing = self.url_text.get("1.0", tk.END).strip()
        if existing:
            self.url_text.insert(tk.END, "\n")
        self.url_text.insert(tk.END, "\n".join(urls))

        self._log(f"Loaded {len(urls)} URL(s) from: {os.path.basename(filepath)}\n", "accent")

    def _browse_output(self):
        """Open directory picker for output folder."""
        d = filedialog.askdirectory(initialdir=self.output_var.get())
        if d:
            self.output_var.set(d)

    def _log(self, message: str, tag: str = "info"):
        """Append to the log area."""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message, tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        """Clear the log area."""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _start_download(self):
        """Start downloading all URLs."""
        if not self._ffmpeg_path:
            messagebox.showerror("FFmpeg Missing",
                                 "FFmpeg is required. Download from:\nhttps://www.gyan.dev/ffmpeg/builds/")
            return

        # Get URLs from text area
        raw = self.url_text.get("1.0", tk.END).strip()
        urls = [line.strip() for line in raw.split("\n") if line.strip() and not line.strip().startswith("#")]

        if not urls:
            messagebox.showwarning("No URLs", "Please paste at least one Hudl URL.")
            return

        output_dir = self.output_var.get()
        quality = self.quality_var.get()
        workers = int(self.workers_var.get())

        # Disable UI
        self.download_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        self.progress_var.set(0)

        self._log(f"\nStarting download of {len(urls)} URL(s)...\n", "accent")
        self._log(f"Output: {output_dir}\n", "info")
        self._log(f"Quality: {quality} | Workers: {workers}\n\n", "info")

        # Create batch manager
        self.batch_manager = BatchManager(
            output_dir=output_dir,
            max_workers=workers,
            preferred_quality=quality,
            ffmpeg_path=self._ffmpeg_path,
        )
        self.batch_manager.add_urls(urls)

        # Start in background thread
        self.batch_manager.start_async(
            on_progress=self._on_progress,
            on_item_done=self._on_item_done,
            on_all_done=self._on_all_done,
        )

    def _on_progress(self, item: QueueItem):
        """Handle progress update from batch manager (called from worker thread)."""
        def _update():
            if item.status == "extracting":
                self.status_var.set(f"[{item.index + 1}/{self.batch_manager.total}] Extracting: {item.url[:50]}...")
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
        """Handle item completion (called from worker thread)."""
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

            # Update overall progress
            done = self.batch_manager.completed + self.batch_manager.failed
            total = self.batch_manager.total
            if total > 0:
                self.progress_var.set((done / total) * 100)
        self.root.after(0, _update)

    def _on_all_done(self):
        """Handle all downloads complete (called from worker thread)."""
        def _update():
            bm = self.batch_manager
            self._log(f"\nAll done! {bm.completed} completed, {bm.failed} failed\n", "accent")
            self.status_var.set(f"Done — {bm.completed}/{bm.total} downloaded")
            self.progress_var.set(100)
            self.download_btn.configure(state=tk.NORMAL)
            self.cancel_btn.configure(state=tk.DISABLED)
        self.root.after(0, _update)

    def _cancel_download(self):
        """Cancel all downloads."""
        if self.batch_manager:
            self.batch_manager.cancel_all()
            self._log("\nCancelling...\n", "error")
            self.status_var.set("Cancelling...")

    def run(self):
        """Start the GUI event loop."""
        self.root.mainloop()


def launch_gui():
    """Entry point for GUI mode."""
    app = HudlDownloaderGUI()
    app.run()


if __name__ == "__main__":
    launch_gui()
