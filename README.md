# Hudl Video Downloader

Download any Hudl video by URL. CLI + GUI. One command.

```
python hudl_dl.py "https://fan.hudl.com/.../watch?b=..."
```

## Features

- **Multi-URL Support** — Direct m3u8, fan pages, vCloud embeds, generic Hudl pages
- **Quality Selection** — best, 1080p, 720p, 540p, worst with HEVC/H.264 detection
- **Batch Mode** — Download multiple videos concurrently (up to 5 workers)
- **GUI Mode** — Dark-themed tkinter interface for non-technical users
- **File Import** — Load URLs from `.txt`, `.csv`, or `.xlsx` files
- **Live Progress** — Real-time percent, speed, ETA, file size tracking
- **Ships as .exe** — PyInstaller-ready for single binary distribution

## Supported URL Types

| Type | Example | How it works |
|------|---------|-------------|
| **Direct m3u8** | `va.hudl.com/.../video.ondemand.m3u8` | Validates and downloads directly |
| **Fan Page** | `fan.hudl.com/.../watch?b=...` | GraphQL API + base64 decode + VMAP |
| **vCloud Embed** | `vcloud.hudl.com/broadcast/embed/...` | VMAP extraction + fallback scrape |
| **Generic Page** | Any `hudl.com` video page | HTML/JS scraping with m3u8 regex |

Just paste any URL — the tool auto-detects the type.

## Quick Start

### CLI

```bash
# Single video (best quality)
python hudl_dl.py "URL"

# Specific quality
python hudl_dl.py -q 1080p "URL"

# Save to folder
python hudl_dl.py -o downloads/ "URL"

# Batch from file
python hudl_dl.py -f urls.txt -o downloads/ -w 3

# Multiple URLs
python hudl_dl.py "URL1" "URL2" "URL3" -w 3

# Check available qualities
python hudl_dl.py --list-quality "URL"
```

### GUI

```bash
python hudl_dl.py --gui
```

Paste URLs, pick quality, hit Download.

## Requirements

- **Python 3.8+**
- **FFmpeg** — must be in PATH ([download](https://www.gyan.dev/ffmpeg/builds/))

```bash
pip install -r requirements.txt
```

## All Options

```
positional arguments:
  urls                  Hudl URLs to download

options:
  -h, --help            Show help message
  -f FILE, --file FILE  Load URLs from file (.txt, .csv, .xlsx)
  -o DIR, --output DIR  Output directory (default: current)
  -q QUALITY            Quality: best, 1080p, 720p, 540p, worst
  -w N, --workers N     Concurrent downloads (default: 2, max: 5)
  --gui                 Launch GUI mode
  --ffmpeg PATH         Custom FFmpeg path
  --list-quality        Show available qualities without downloading
```

## Architecture

```
hudl_dl.py        CLI entry point + orchestrator
extractor.py      Multi-format URL extraction (GraphQL, VMAP, scraping)
quality.py        m3u8 master playlist parser + quality selector
downloader.py     FFmpeg HLS download with real-time progress
batch.py          Concurrent batch manager (ThreadPoolExecutor)
gui.py            Dark-themed tkinter GUI
utils.py          FFmpeg finder, file sanitizers, format helpers
```

## How to Get Video URLs

**Method 1 — Fan Page (easiest):**
1. Go to `fan.hudl.com`
2. Find and click on a game/video
3. Copy the URL from the address bar

**Method 2 — Direct m3u8 (most reliable):**
1. Open the video in Chrome
2. Press `F12` (DevTools) → Network tab
3. Filter by `m3u8`
4. Play the video
5. Right-click the m3u8 request → Copy URL

## Troubleshooting

| Problem | Solution |
|---------|----------|
| FFmpeg not found | Install FFmpeg and add to PATH |
| 403 Forbidden | URL token expired — get a fresh URL |
| Download is slow | Hudl streams at ~1x speed. Use `-q 540p` for faster downloads |
| GUI won't open | Run from terminal: `python hudl_dl.py --gui` |

## License

MIT
