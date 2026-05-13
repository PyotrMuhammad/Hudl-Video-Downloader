"""
Multi-Platform Batch Queue Manager
Handles concurrent downloads with a configurable worker pool.
Supports: HUDL, VEO, YouTube, TRACE, PIXELLOT
"""

import os
import re
import time
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional

from extractors import extract, get_platform
from extractors.base import ExtractResult, ExtractionError, AuthRequiredError
from quality import fetch_and_select
from downloader import HudlDownloader, DownloadProgress
from utils import sanitize_filename, get_unique_filepath, format_size


@dataclass
class QueueItem:
    """Represents one URL in the download queue."""
    url: str
    status: str = "pending"   # pending, extracting, downloading, done, error, cancelled
    title: str = ""
    platform: str = ""
    m3u8_url: str = ""
    output_path: str = ""
    quality_info: str = ""
    progress: Optional[DownloadProgress] = None
    error: str = ""
    index: int = 0


class BatchManager:
    """
    Manages a queue of URLs for concurrent downloading.
    Supports all platforms: HUDL (HLS/FFmpeg), YouTube/VEO (yt-dlp).

    Usage:
        bm = BatchManager(output_dir="./downloads", max_workers=2)
        bm.add_urls(["https://fan.hudl.com/...", "https://youtube.com/watch?v=..."])
        bm.start(on_progress=my_callback)
    """

    def __init__(self, output_dir: str = ".", max_workers: int = 2,
                 preferred_quality: str = "best", ffmpeg_path: str = None,
                 cookies=None, session_token: str = None):
        self.output_dir = os.path.abspath(output_dir)
        self.max_workers = max_workers
        self.preferred_quality = preferred_quality
        self.ffmpeg_path = ffmpeg_path
        self.cookies = cookies
        self.session_token = session_token
        self.queue: list[QueueItem] = []
        self._lock = threading.Lock()
        self._cancel_all = threading.Event()
        self._downloaders: list[HudlDownloader] = []
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running = False

    def add_url(self, url: str) -> QueueItem:
        url = url.strip()
        if not url:
            return None
        item = QueueItem(url=url, index=len(self.queue),
                         platform=get_platform(url))
        self.queue.append(item)
        return item

    def add_urls(self, urls: list) -> list:
        items = []
        for url in urls:
            url = url.strip()
            if url and not url.startswith("#"):
                items.append(self.add_url(url))
        return items

    @property
    def total(self) -> int:
        return len(self.queue)

    @property
    def completed(self) -> int:
        return sum(1 for item in self.queue if item.status == "done")

    @property
    def failed(self) -> int:
        return sum(1 for item in self.queue if item.status == "error")

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, on_progress: Callable = None, on_item_done: Callable = None):
        if self._running:
            return

        self._running = True
        self._cancel_all.clear()
        os.makedirs(self.output_dir, exist_ok=True)

        def _worker(item: QueueItem):
            if self._cancel_all.is_set():
                item.status = "cancelled"
                return
            try:
                self._process_item(item, on_progress)
            except Exception as e:
                item.status = "error"
                item.error = str(e)
            if on_item_done:
                on_item_done(item)

        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = [self._executor.submit(_worker, item)
                   for item in self.queue if item.status == "pending"]
        for f in futures:
            f.result()

        self._running = False
        self._executor.shutdown(wait=False)

    def start_async(self, on_progress: Callable = None,
                    on_item_done: Callable = None, on_all_done: Callable = None):
        def _run():
            self.start(on_progress, on_item_done)
            if on_all_done:
                on_all_done()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def cancel_all(self):
        self._cancel_all.set()
        for dl in self._downloaders:
            dl.cancel()

    # ── Core processing ───────────────────────────────────────────────

    def _process_item(self, item: QueueItem, on_progress: Callable = None):
        """Extract → select quality → download (HLS or yt-dlp)."""

        # Step 1: Extract
        item.status = "extracting"
        if on_progress:
            on_progress(item)

        try:
            # Pass cookies as-is: dict (header injection) or str (file path for MozillaCookieJar)
            result = extract(item.url, cookies=self.cookies,
                             session_token=self.session_token)
        except AuthRequiredError as e:
            item.status = "error"
            item.error = f"Auth required for {e.platform}: {e.instructions[:120]}"
            return
        except ExtractionError as e:
            item.status = "error"
            item.error = f"Extraction failed: {e}"
            return

        item.title = result.title
        item.platform = result.platform

        if self._cancel_all.is_set():
            item.status = "cancelled"
            return

        # Step 2: Route by platform type
        filename = sanitize_filename(result.title) + ".mp4"
        item.output_path = get_unique_filepath(self.output_dir, filename)

        if result.use_ytdlp:
            # YouTube, VEO, and other yt-dlp-native platforms
            self._download_ytdlp(item, result, on_progress)
        else:
            # HLS via FFmpeg (HUDL, PIXELLOT, TRACE)
            self._download_hls(item, result, on_progress)

    def _download_hls(self, item: QueueItem, result: ExtractResult,
                      on_progress: Callable = None):
        """Download HLS stream via FFmpeg."""
        selected_url = result.m3u8_url
        headers = result.headers

        # Quality selection
        try:
            selected_url, variant, _ = fetch_and_select(
                result.m3u8_url, headers, result.base_url, self.preferred_quality
            )
            if variant:
                item.quality_info = variant.name
        except Exception:
            pass  # Use original URL

        item.status = "downloading"
        dl = HudlDownloader(self.ffmpeg_path)
        self._downloaders.append(dl)

        def _dl_progress(prog: DownloadProgress):
            item.progress = prog
            if on_progress:
                on_progress(item)

        progress = dl.download(selected_url, item.output_path, headers, _dl_progress)
        self._downloaders.remove(dl)

        if progress.status == "done":
            item.status = "done"
            item.progress = progress
        elif progress.status == "cancelled":
            item.status = "cancelled"
        else:
            item.status = "error"
            item.error = progress.error or "Download failed"

    def _download_ytdlp(self, item: QueueItem, result: ExtractResult,
                        on_progress: Callable = None):
        """Download via yt-dlp (YouTube, VEO)."""
        item.status = "downloading"

        fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        q = self.preferred_quality
        if q == "720p":
            fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
        elif q == "480p":
            fmt = "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best"
        elif q == "1080p":
            fmt = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"

        cmd = [
            "yt-dlp", "--no-warnings",
            "-f", fmt,
            "--merge-output-format", "mp4",
            "-o", item.output_path,
            "--no-playlist",
            "--newline",
        ]

        cookies_path = self.cookies if isinstance(self.cookies, str) and os.path.isfile(self.cookies) else None
        if cookies_path:
            cmd += ["--cookies", cookies_path]

        for k, v in (result.headers or {}).items():
            cmd += ["--add-header", f"{k}:{v}"]

        cmd.append(result.source_url or result.direct_url or item.url)

        prog = DownloadProgress()
        prog.output_path = item.output_path
        prog.start_time = time.time()
        prog.status = "downloading"
        item.progress = prog

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            for line in proc.stdout:
                if self._cancel_all.is_set():
                    proc.terminate()
                    item.status = "cancelled"
                    return

                line = line.strip()
                m = re.search(r'\[download\]\s+([\d.]+)%', line)
                if m:
                    prog.percent = float(m.group(1))
                    speed_m = re.search(r'at\s+([\d.]+\s*\w+/s)', line)
                    eta_m = re.search(r'ETA\s+([\d:]+)', line)
                    if speed_m:
                        prog.speed = speed_m.group(1)
                    if eta_m:
                        prog.eta = eta_m.group(1)
                    item.progress = prog
                    if on_progress:
                        on_progress(item)

            proc.wait()

            if proc.returncode == 0 and os.path.isfile(item.output_path) and os.path.getsize(item.output_path) > 1024:
                prog.status = "done"
                prog.percent = 100.0
                prog.size = format_size(os.path.getsize(item.output_path))
                item.status = "done"
                item.progress = prog
            else:
                item.status = "error"
                item.error = f"yt-dlp exited with code {proc.returncode}"

        except FileNotFoundError:
            item.status = "error"
            item.error = "yt-dlp not found. Install: pip install yt-dlp"
        except Exception as e:
            item.status = "error"
            item.error = str(e)
