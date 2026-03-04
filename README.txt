============================================
   HUDL VIDEO DOWNLOADER v1.0
   Download Hudl videos by URL
============================================

REQUIREMENTS
------------
- Windows 10/11 (64-bit)
- FFmpeg (required for downloading)

If you don't have FFmpeg installed:
  1. Go to: https://www.gyan.dev/ffmpeg/builds/
  2. Download "ffmpeg-release-essentials.zip"
  3. Extract it to C:\ffmpeg
  4. Add C:\ffmpeg\bin to your system PATH:
     - Search "Environment Variables" in Windows
     - Under System Variables, find "Path", click Edit
     - Add: C:\ffmpeg\bin
     - Click OK, restart any open terminals
  5. Verify: open Command Prompt, type: ffmpeg -version


QUICK START (GUI - Easiest)
---------------------------
1. Double-click HudlDownloader.exe
2. Type: --gui    (then press Enter)
   OR run from Command Prompt: HudlDownloader.exe --gui

3. The GUI window opens:
   - Paste your Hudl URLs in the text box (one per line)
   - OR click "Load File" to load URLs from a .txt, .csv, or .xlsx file
   - Choose output folder with "Browse"
   - Select quality (best, 1080p, 720p, 540p)
   - Click "Download"
   - Watch progress in the log area


QUICK START (Command Line)
--------------------------
Open Command Prompt or PowerShell in the folder where HudlDownloader.exe is located.

Download a single video (best quality):
  HudlDownloader.exe "https://va.hudl.com/.../video.ondemand.m3u8?v=..."

Download at specific quality:
  HudlDownloader.exe -q 1080p "https://va.hudl.com/.../video.ondemand.m3u8?v=..."

Download to a specific folder:
  HudlDownloader.exe -o "C:\Users\YourName\Videos" "URL_HERE"

Download multiple videos at once:
  HudlDownloader.exe "URL1" "URL2" "URL3" -w 3 -o downloads/

Download from a file (txt, csv, or xlsx):
  HudlDownloader.exe -f urls.txt -o downloads/
  HudlDownloader.exe -f urls.xlsx -o downloads/
  HudlDownloader.exe -f urls.csv -o downloads/

Check available qualities without downloading:
  HudlDownloader.exe --list-quality "URL_HERE"


SUPPORTED URL TYPES
-------------------
The tool automatically detects what type of URL you provide:

1. Direct m3u8 links (from Network tab / DevTools):
   https://va.hudl.com/.../video.ondemand.m3u8?v=...

2. Fan page URLs (from fan.hudl.com):
   https://fan.hudl.com/.../watch?b=...

3. vCloud embed URLs:
   https://vcloud.hudl.com/broadcast/embed/...

Just paste any of these - the tool figures out the rest.


HOW TO GET VIDEO URLs
---------------------
Method 1 - Direct m3u8 (most reliable):
  1. Open the video in Chrome
  2. Press F12 (Developer Tools)
  3. Go to Network tab
  4. Type "m3u8" in the filter box
  5. Play the video
  6. Right-click the m3u8 request -> Copy -> Copy URL

Method 2 - Fan page URL (easiest):
  1. Go to fan.hudl.com
  2. Find and click on a game/video
  3. Copy the URL from the address bar
     (should look like: https://fan.hudl.com/.../watch?b=...)


BATCH DOWNLOAD FROM FILE
-------------------------
You can put URLs in a file and load them all at once.

Text file (.txt):
  Just one URL per line. Lines starting with # are ignored.

CSV file (.csv):
  URLs can be in any column. The tool scans all cells and
  picks out anything that looks like a Hudl URL.

Excel file (.xlsx):
  Same as CSV - URLs can be in any column on any sheet.
  The tool scans everything automatically.


ALL OPTIONS
-----------
  -h, --help           Show help message
  -f FILE              Load URLs from file (.txt, .csv, .xlsx)
  -o FOLDER            Output folder (default: current folder)
  -q QUALITY           Quality: best, 1080p, 720p, 540p, worst
  -w NUMBER            Concurrent downloads (default: 2, max: 5)
  --gui                Launch the GUI window
  --ffmpeg PATH        Custom FFmpeg path (auto-detected normally)
  --list-quality       Show available qualities, don't download


TROUBLESHOOTING
---------------
"FFmpeg not found"
  -> Install FFmpeg and add it to PATH (see REQUIREMENTS above)

"403 Forbidden" or download fails
  -> The video URL token may have expired. Get a fresh URL.
  -> Some videos require specific headers. Try the direct m3u8 method.

Video downloads but won't play
  -> Make sure you have VLC media player or similar installed
  -> The file might be incomplete if download was interrupted

Download is very slow
  -> Hudl streams at real-time speed (~1x). A 2-hour game takes ~2 hours.
  -> Use -q 540p for faster downloads (smaller file, lower quality)
  -> Lower quality = faster download

GUI won't open
  -> Run from Command Prompt: HudlDownloader.exe --gui
  -> Check for error messages in the terminal


CONTACT
-------
For issues or questions, contact the developer.
