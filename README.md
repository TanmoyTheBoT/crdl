# crdl 🎬

A simple crunchyroll downloader.

## 🌟 Key Features

### Content Management
- 📺 **Content Selection**: Download specific episodes, seasons, or entire series
- 🎨 **Quality Options**: Choose between different video quality settings (best, 1080p, 720p, worst, etc.)
- 📂 **Output Customization**: Configure output directory and naming conventions

### Security & Performance
- 🔐 **Robust Token Management**: Automatic handling of access token expiration and refresh
- 🧹 **Stream Cleanup**: Efficient management of stream resources
- 🔒 **Credential Storage**: Secure storage of credentials for future use

### Platform Support
- 💻 **Cross-Platform**: Works seamlessly on Windows, macOS, and Linux
- ⚙️ **Standardized Paths**: Consistent configuration across all platforms

## 📋 Requirements

### Software Dependencies
- 🐍 Python 3.6+
- 📥 N_m3u8DL-RE (must be in PATH)
- 🎬 ffmpeg (must be in PATH)
- 📦 mkvmerge (must be in PATH)
- 🔓 mp4decrypt (must be in PATH)

### Account & DRM
- 👤 Valid Crunchyroll account credentials
- 🔑 Widevine CDM for DRM content
  - Place in: `~/.config/crdl/widevine/device.wvd`

## 📥 Installation

Choose one of these installation methods:

### 🚀 Quick Install (Recommended)
```bash
pip install crdl
```

### 🔧 Development Install
1. Clone the repository:
   ```bash
   git clone https://github.com/TanmoyTheBoT/crdl.git
   cd crdl
   ```

2. Install in development mode:
   ```bash
   pip install -e .
   ```
This makes the `crdl` command available globally while allowing you to modify the source code.

## 🚀 Usage Guide

### 🔰 First Time Setup
```bash
crdl --username YOUR_USERNAME --password YOUR_PASSWORD --episode EPISODE_ID
```
Your credentials will be securely saved in `~/.config/crdl/credentials.json`

### 📺 Basic Usage
After initial setup, you can download content easily:
```bash
crdl --episode EPISODE_ID    # Download a single episode
crdl --series SERIES_ID      # Browse and select from a series
```

### ⚙️ Command Line Options

#### Authentication
- 👤 `-u, --username`: Crunchyroll username
- 🔑 `-p, --password`: Crunchyroll password

#### Content Selection
- 📺 `-s, --series`: Series ID to browse and download
- 🎬 `-e, --episode`: Specific episode ID
- 📂 `--season`: Season ID for batch download

#### Download Settings
- 🌍 `--locale`: Content locale (default: en-US)
- 🎵 `-a, --audio`: Audio languages (e.g., "ja-JP,en-US" or "all")
- 📁 `-o, --output`: Custom output directory
- 📊 `-q, --quality`: Video quality (1080p, 720p, best, worst)
- 🏷️ `-r, --release-group`: Custom release group name

#### Advanced
- 📝 `-v, --verbose`: Enable detailed logging

## 🗂️ Configuration Structure

### 📁 Directory Layout
```
~/.config/crdl/
  ├── credentials.json    # 🔐 Saved credentials
  ├── json/              # 📊 API responses & debug info
  ├── widevine/          # 🔑 DRM files
  │   └── device.wvd     # Required Widevine CDM
  └── logs/              # 📝 Application logs
      └── crunchyroll_downloader.log
```

## 🔧

### 🌊 Stream Management
Our robust stream handling system:
- 🔄 **Smart Token Refresh**: Auto-refresh of expired tokens
- 📊 **Active Stream Tracking**: Prevents resource leaks
- ⚡ **Signal Handling**: Graceful handling of SIGINT/SIGTERM
- 🧹 **Auto Cleanup**: Guaranteed resource cleanup on exit

prevents "TOO_MANY_ACTIVE_STREAMS" error.

### 🔐 Security Features

#### Token Management
- ⏰ **Expiry Tracking**: Smart token lifetime monitoring
- 📈 **Efficient Renewal**: Uses refresh tokens
- 🛡️ **Rate Protection**: Prevents token refresh spam

#### Credential Handling
- 🔒 **Secure Storage**: credential storage
- 💾 **Single Login**: Remember credentials for future use
- 🌐 **Cross-Platform**: Consistent paths across OS

## 🔒 DRM Content Setup

### Widevine Configuration
1. 📥 Obtain a valid Widevine CDM file
2. 📁 Place `device.wvd` in: `~/.config/crdl/widevine/`
3. ✅ Only one device file needed

## ❓ Troubleshooting Guide

Having issues? Check these common solutions:

### 🔍 Quick Fixes
1. 🔑 Verify your Crunchyroll credentials
2. 📦 Update N_m3u8DL-RE to latest version
3. 🔍 Run with `--verbose` for detailed logs

### 📋 Additional Checks
4. 💳 Confirm Premium account status
5. 📝 Review logs at: `~/.config/crdl/logs/crunchyroll_downloader.log`
6. 🔐 Verify Widevine CDM at: `~/.config/crdl/widevine/device.wvd`

## 📜 Legal Notice

This project is for educational purposes only.  
Please respect Crunchyroll's terms of service.

## 👥 Contributors

👨‍💻 Original Author: TanmoyTheBoT