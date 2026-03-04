#!/usr/bin/env python3
"""
Hudl Video Downloader — CLI Interface
Download Hudl videos by URL. Supports direct m3u8 links and Hudl page URLs.

Usage:
    python hudl_dl.py URL [URL2 URL3 ...]
    python hudl_dl.py -f urls.txt
    python hudl_dl.py --gui
"""

import argparse
import os
import sys
import time

from extractor import extract
from quality import fetch_and_select, format_variants_table
from downloader import HudlDownloader, DownloadProgress
from batch import BatchManager
from utils import find_ffmpeg, get_ffmpeg_version, sanitize_filename, get_unique_filepath, format_size, read_urls_from_file


def print_banner():
    print()
    print("  +----------------------------------+")
    print("  |     Hudl Video Downloader v1.0   |")
    print("  +----------------------------------+")
    print()


def cli_progress_callback(item):
    """Print progress updates for CLI mode."""
    if item.progress and item.status == "downloading":
        p = item.progress
        bar_width = 30
        filled = int(bar_width * p.percent / 100)
        bar = "#" * filled + "-" * (bar_width - filled)
        line = f"\r  [{bar}] {p.percent:5.1f}% | {p.size} | {p.speed} | ETA: {p.eta}  "
        sys.stdout.write(line)
        sys.stdout.flush()


def download_single_cli(url: str, output_dir: str, quality: str, ffmpeg_path: str):
    """Download a single URL with CLI output."""
    print(f"  URL: {url[:80]}{'...' if len(url) > 80 else ''}")
    print()

    # Step 1: Extract
    print("  [1/3] Extracting m3u8 URL...")
    try:
        result = extract(url)
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

    print(f"  Title: {result.title}")
    print(f"  m3u8:  {result.m3u8_url[:70]}...")
    print()

    # Step 2: Quality selection
    print("  [2/3] Checking available qualities...")
    try:
        selected_url, variant, all_variants = fetch_and_select(
            result.m3u8_url, result.headers, result.base_url, quality
        )
    except Exception as e:
        print(f"  WARNING: Could not parse qualities ({e}), using original URL")
        selected_url = result.m3u8_url
        variant = None
        all_variants = []

    if all_variants:
        print(f"  Found {len(all_variants)} quality options:")
        print(format_variants_table(all_variants))
        if variant:
            print(f"  Selected: {variant.name}")
    else:
        print("  Single quality stream (no variants)")
    print()

    # Step 3: Download
    filename = sanitize_filename(result.title) + ".mp4"
    output_path = get_unique_filepath(output_dir, filename)

    print(f"  [3/3] Downloading to: {os.path.basename(output_path)}")
    print()

    dl = HudlDownloader(ffmpeg_path)
    start = time.time()

    def _progress(prog: DownloadProgress):
        if prog.status == "downloading":
            bar_width = 30
            filled = int(bar_width * prog.percent / 100)
            bar = "#" * filled + "-" * (bar_width - filled)
            line = f"\r  [{bar}] {prog.percent:5.1f}% | {prog.size} | {prog.speed} | ETA: {prog.eta}  "
            sys.stdout.write(line)
            sys.stdout.flush()

    progress = dl.download(selected_url, output_path, result.headers, _progress)

    print()  # New line after progress bar
    elapsed = time.time() - start

    if progress.status == "done":
        size = format_size(os.path.getsize(output_path))
        print(f"  DONE! {size} in {progress.time_elapsed}")
        print(f"  Saved: {output_path}")
        return True
    else:
        print(f"  FAILED: {progress.error}")
        return False


def download_batch_cli(urls: list, output_dir: str, quality: str,
                       workers: int, ffmpeg_path: str):
    """Download multiple URLs with CLI output."""
    print(f"  Batch download: {len(urls)} URLs")
    print(f"  Output: {output_dir}")
    print(f"  Workers: {workers}")
    print(f"  Quality: {quality}")
    print()

    bm = BatchManager(
        output_dir=output_dir,
        max_workers=workers,
        preferred_quality=quality,
        ffmpeg_path=ffmpeg_path,
    )
    bm.add_urls(urls)

    completed = 0
    failed = 0

    def on_item_done(item):
        nonlocal completed, failed
        if item.status == "done":
            completed += 1
            size = format_size(os.path.getsize(item.output_path)) if item.output_path and os.path.isfile(item.output_path) else "?"
            print(f"  [{completed + failed}/{bm.total}] DONE: {item.title} ({size})")
        else:
            failed += 1
            print(f"  [{completed + failed}/{bm.total}] FAIL: {item.url[:60]}... — {item.error}")

    def on_progress(item):
        # For batch, we just show status changes (not progress bars)
        if item.status == "extracting":
            print(f"  [{item.index + 1}/{bm.total}] Extracting: {item.url[:60]}...")
        elif item.status == "downloading" and item.progress and item.progress.percent == 0:
            q = f" ({item.quality_info})" if item.quality_info else ""
            print(f"  [{item.index + 1}/{bm.total}] Downloading: {item.title}{q}")

    bm.start(on_progress=on_progress, on_item_done=on_item_done)

    print()
    print(f"  Batch complete: {completed} done, {failed} failed out of {bm.total}")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(
        description="Hudl Video Downloader — Download Hudl videos by URL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s https://va.hudl.com/.../video.ondemand.m3u8?v=...
  %(prog)s -f urls.txt -o downloads/ -q 1080p
  %(prog)s -f urls.xlsx -o downloads/
  %(prog)s -f urls.csv -w 3 -o videos/
  %(prog)s --gui
  %(prog)s URL1 URL2 URL3 -w 3 -o videos/
""",
    )
    parser.add_argument("urls", nargs="*", help="Hudl URLs to download")
    parser.add_argument("-f", "--file", help="File with URLs (.txt, .csv, or .xlsx)")
    parser.add_argument("-o", "--output", default=".", help="Output directory (default: current)")
    parser.add_argument("-q", "--quality", default="best",
                        help="Quality: best, 1080p, 720p, 540p, worst (default: best)")
    parser.add_argument("-w", "--workers", type=int, default=2,
                        help="Concurrent downloads for batch mode (default: 2)")
    parser.add_argument("--gui", action="store_true", help="Launch GUI mode")
    parser.add_argument("--ffmpeg", help="Path to FFmpeg binary (auto-detected if not set)")
    parser.add_argument("--list-quality", action="store_true",
                        help="Show available qualities without downloading")

    args = parser.parse_args()

    # GUI mode
    if args.gui:
        try:
            from gui import launch_gui
            launch_gui()
        except ImportError as e:
            print(f"GUI launch failed: {e}")
            sys.exit(1)
        return

    print_banner()

    # Find FFmpeg
    try:
        ffmpeg_path = args.ffmpeg or find_ffmpeg()
        print(f"  FFmpeg: {ffmpeg_path}")
    except FileNotFoundError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    # Collect URLs
    urls = list(args.urls)
    if args.file:
        try:
            file_urls = read_urls_from_file(args.file)
            print(f"  Loaded {len(file_urls)} URL(s) from: {args.file}")
            urls.extend(file_urls)
        except FileNotFoundError:
            print(f"  ERROR: File not found: {args.file}")
            sys.exit(1)
        except ImportError as e:
            print(f"  ERROR: {e}")
            sys.exit(1)

    if not urls:
        parser.print_help()
        sys.exit(0)

    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)
    print(f"  Output: {output_dir}")
    print()

    # List quality mode
    if args.list_quality:
        for url in urls:
            print(f"  URL: {url[:70]}...")
            try:
                result = extract(url)
                _, variant, variants = fetch_and_select(
                    result.m3u8_url, result.headers, result.base_url
                )
                print(format_variants_table(variants))
            except Exception as e:
                print(f"  Error: {e}")
            print()
        return

    # Download
    if len(urls) == 1:
        success = download_single_cli(urls[0], output_dir, args.quality, ffmpeg_path)
    else:
        success = download_batch_cli(urls, output_dir, args.quality, args.workers, ffmpeg_path)

    print()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
