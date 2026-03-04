"""
Hudl Batch Queue Manager
Handles concurrent downloads with a configurable worker pool.
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from typing import Callable, Optional

from extractor import extract, ExtractResult
from quality import fetch_and_select
from downloader import HudlDownloader, DownloadProgress
from utils import sanitize_filename, get_unique_filepath


@dataclass
class QueueItem:
    """Represents one URL in the download queue."""
    url: str
    status: str = "pending"  # pending, extracting, downloading, done, error, cancelled
    title: str = ""
    m3u8_url: str = ""
    output_path: str = ""
    quality_info: str = ""
    progress: Optional[DownloadProgress] = None
    error: str = ""
    index: int = 0


class BatchManager:
    """
    Manages a queue of Hudl URLs for concurrent downloading.

    Usage:
        bm = BatchManager(output_dir="./downloads", max_workers=2)
        bm.add_url("https://va.hudl.com/.../video.ondemand.m3u8?v=...")
        bm.add_url("https://fan.hudl.com/.../watch?b=...")
        bm.start(on_progress=my_callback)
    """

    def __init__(self, output_dir: str = ".", max_workers: int = 2,
                 preferred_quality: str = "best", ffmpeg_path: str = None):
        self.output_dir = os.path.abspath(output_dir)
        self.max_workers = max_workers
        self.preferred_quality = preferred_quality
        self.ffmpeg_path = ffmpeg_path
        self.queue: list[QueueItem] = []
        self._lock = threading.Lock()
        self._cancel_all = threading.Event()
        self._downloaders: list[HudlDownloader] = []
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running = False

    def add_url(self, url: str) -> QueueItem:
        """Add a URL to the download queue."""
        url = url.strip()
        if not url:
            return None
        item = QueueItem(url=url, index=len(self.queue))
        self.queue.append(item)
        return item

    def add_urls(self, urls: list) -> list:
        """Add multiple URLs. Skips empty lines and comments."""
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
        """
        Start processing the queue.

        Args:
            on_progress: Called with (QueueItem) on progress updates
            on_item_done: Called with (QueueItem) when an item finishes
        """
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
        futures = []
        for item in self.queue:
            if item.status in ("pending",):
                f = self._executor.submit(_worker, item)
                futures.append(f)

        # Wait for all to complete
        for f in futures:
            f.result()

        self._running = False
        self._executor.shutdown(wait=False)

    def start_async(self, on_progress: Callable = None,
                    on_item_done: Callable = None, on_all_done: Callable = None):
        """Start processing in a background thread."""
        def _run():
            self.start(on_progress, on_item_done)
            if on_all_done:
                on_all_done()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def cancel_all(self):
        """Cancel all pending/active downloads."""
        self._cancel_all.set()
        for dl in self._downloaders:
            dl.cancel()

    def _process_item(self, item: QueueItem, on_progress: Callable = None):
        """Process a single queue item: extract → select quality → download."""
        # Step 1: Extract m3u8 URL
        item.status = "extracting"
        if on_progress:
            on_progress(item)

        try:
            result = extract(item.url)
        except Exception as e:
            item.status = "error"
            item.error = f"Extraction failed: {e}"
            return

        item.m3u8_url = result.m3u8_url
        item.title = result.title
        headers = result.headers

        if self._cancel_all.is_set():
            item.status = "cancelled"
            return

        # Step 2: Select quality
        try:
            selected_url, variant, all_variants = fetch_and_select(
                result.m3u8_url, headers, result.base_url, self.preferred_quality
            )
            item.m3u8_url = selected_url
            if variant:
                item.quality_info = variant.name
        except Exception:
            # If quality selection fails, use the original URL
            pass

        if self._cancel_all.is_set():
            item.status = "cancelled"
            return

        # Step 3: Download
        filename = sanitize_filename(item.title) + ".mp4"
        item.output_path = get_unique_filepath(self.output_dir, filename)

        item.status = "downloading"
        dl = HudlDownloader(self.ffmpeg_path)
        self._downloaders.append(dl)

        def _dl_progress(prog: DownloadProgress):
            item.progress = prog
            if on_progress:
                on_progress(item)

        progress = dl.download(item.m3u8_url, item.output_path, headers, _dl_progress)

        self._downloaders.remove(dl)

        if progress.status == "done":
            item.status = "done"
            item.progress = progress
        elif progress.status == "cancelled":
            item.status = "cancelled"
        else:
            item.status = "error"
            item.error = progress.error or "Download failed"
