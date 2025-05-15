# crdl 🎬

A command-line tool for downloading content from Crunchyroll with customizable quality options and output settings.

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.8%2B-blue.svg" alt="Python Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License"></a>
  <a href="https://badge.fury.io/py/crdl"><img src="https://badge.fury.io/py/crdl.svg?nocache=1" alt="PyPI version"></a>
  <a href="https://pepy.tech/projects/crdl"><img src="https://static.pepy.tech/badge/crdl" alt="PyPI Downloads"></a>
</p>

## ✨ Features

- 📺 Download specific episodes, seasons, or entire series
- 🎨 Choose between different video quality settings
- 🔐 Automatic token management and stream cleanup
- 💻 Cross-platform compatibility (Windows, macOS, Linux)
- 🔑 DRM support with Widevine CDM

## 📋 Prerequisites

1. 🐍 **[Python 3.8+](https://www.python.org/downloads/)**
2. 📥 **[N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE)** (in PATH)
3. 🎬 **[ffmpeg](https://ffmpeg.org/download.html)** (in PATH)
4. 📦 **[mkvmerge](https://mkvtoolnix.download/downloads.html)** (in PATH)
5. 🔓 **[mp4decrypt](https://www.bento4.com/downloads/)** (in PATH)

For DRM content: Place `device.wvd` in `~/.config/crdl/widevine/`

⚠️ **Note**: Due to legal reasons, this CDM file is not provided with the project.

## 📥 Installation

```bash
pip install crdl
```

## 🚀 Usage

```bash
# First time setup with credentials
crdl -u YOUR_USERNAME -p YOUR_PASSWORD -e EPISODE_ID

# Download episode
crdl -e EPISODE_ID

# Browse and Download entire series
crdl -s SERIES_ID
```

## ⚙️ Command-Line Options

```
options:
  -h, --help            show this help message and exit
  --version             Show version information and exit

Authentication:
  --username USERNAME, -u USERNAME
                        Crunchyroll username
  --password PASSWORD, -p PASSWORD
                        Crunchyroll password

Content Selection:
  --series SERIES, -s SERIES
                        Series ID to download
  --season SEASON       Season ID to download
  --episode EPISODE, -e EPISODE
                        Episode ID to download
  --locale LOCALE       Content locale (default: en-US)
  --audio AUDIO, -a AUDIO
                        Audio languages to download (comma-separated, e.g., "ja-JP,en-US" or "all")

Output Options:
  --output OUTPUT, -o OUTPUT
                        Output directory
  --verbose, -v         Enable verbose logging
  --quality {1080p,720p,best,worst}, -q {1080p,720p,best,worst}
                        Video quality (1080p, 720p, best, or worst)
  --release-group RELEASE_GROUP, -r RELEASE_GROUP
                        Release group name for filename
```

## 🗂️ Configuration

```~/.config/crdl/
  ├── credentials.json  # Saved credentials
  ├── json/            # API responses
  ├── widevine/        # DRM files
  │   └── device.wvd   # Required for DRM
  └── logs/            # Application logs
```
## ❓ Troubleshooting

- 🔑 Verify your Crunchyroll credentials and subscription status
- 📦 Ensure all required tools are updated and in your PATH
- 🔍 Run with `-v` for detailed logging
- 📝 Check logs at: `~/.config/crdl/logs/crunchyroll_downloader.log`

## ⚠️ Disclaimer

> This project is for educational purposes only. Please respect Crunchyroll's terms of service and copyright regulations. You need a Crunchyroll Premium subscription to access premium content. This tool is not affiliated with, maintained, authorized, sponsored, or officially associated with Crunchyroll LLC or any of its subsidiaries or affiliates. Use of this application may violate Crunchyroll's Terms of Service and could be illegal in your country. You are solely responsible for your use of this software.

## 👥 Contributors

<a href="https://github.com/TanmoyTheBoT"><img src="https://github.com/TanmoyTheBoT.png" width="50" height="50" style="border-radius:50%" alt="TanmoyTheBoT"/></a>

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

© TanmoyTheBoT 2025

