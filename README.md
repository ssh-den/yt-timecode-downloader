# yt-timecode-downloader

**Easily download YouTube videos and extract timestamped comments.**

A powerful Python tool that downloads YouTube videos and extracts comments with timecodes. This tool combines the capabilities of yt-dlp for video downloads with the YouTube API for comment extraction, making it perfect for creating video guides, compilations, or simply organizing your video collection with helpful timestamps.

## Features

- **Video Downloads**: Download videos in your preferred format using yt-dlp
- **Comment Extraction**: Automatically fetch video comments
- **Timecode Analysis**: Identify and extract timestamps from comments
- **Smart Ranking**: Sort timecodes by reliability (based on likes and frequency)
- **Multiple Export Formats**: Export comments to TXT, CSV, XLSX, and JSON
- **Markdown Guides**: Generate ready-to-use timecode guides in Markdown
- **Batch Processing**: Process multiple videos in parallel from a list

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/ssh-den/yt-timecode-downloader.git
   cd yt-timecode-downloader
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory with your YouTube API key:
   ```
   YOUTUBE_API_KEY=your_api_key_here
   ```

## Usage

### Basic Usage

Download a single video and extract its comments with timecodes:

```bash
python ytdownloader.py -v "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### Download Multiple Videos

Process videos from a text file (one URL per line):

```bash
python ytdownloader.py -f videos.txt -o downloads
```

### Comments Only vs. Video Only

Extract just comments without downloading the video:

```bash
python ytdownloader.py -v "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --no-video
```

Download just the video without processing comments:

```bash
python ytdownloader.py -v "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --skip-comments
```

### Customize Export Formats

Specify which formats to export (comma-separated, no spaces):

```bash
python ytdownloader.py -v "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --formats json,csv,md
```

### Change Video Format

Download videos in a specific format:

```bash
python ytdownloader.py -v "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --video-format webm
```

### Increase Comment Count

Fetch more comments per video:

```bash
python ytdownloader.py -v "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --comments 200
```

### Parallel Processing

Adjust the number of parallel downloads for batch processing:

```bash
python ytdownloader.py -f videos.txt --threads 5
```

## Command-Line Arguments

| Argument | Short | Description | Default |
|----------|-------|-------------|---------|
| `--video` | `-v` | Single video URL | - |
| `--file` | `-f` | Text file with video URLs | - |
| `--output` | `-o` | Output directory | ./downloads |
| `--formats` | - | Export formats (comma-separated) | json,md |
| `--no-video` | - | Skip video download | False |
| `--video-format` | - | Video format | mp4 |
| `--comments` | - | Maximum comments to fetch | 100 |
| `--sort` | - | Comment sort order (relevance, time) | relevance |
| `--threads` | - | Number of parallel downloads | 3 |
| `--skip-comments` | - | Skip comments processing | False |# YouTube Downloader with Timecode Extraction |

## Output Structure

For each video processed, the tool creates a directory with the following structure:

```
downloads/
└── Video Title/
    ├── Video Title.mp4             # The downloaded video
    ├── all_comments.json           # All comments
    ├── all_comments.csv            # (if requested)
    ├── timecoded_comments.json     # Comments with timecodes
    ├── timecode_analysis.json      # Analysis of timecodes
    └── timecode_guide.md           # Markdown guide with timecodes
```

## Timecode Guide

The generated Markdown guide includes:

1. **Top Timecodes**: Ranked by reliability (based on frequency and likes)
2. **Context**: Extracted text around each timecode
3. **All Comments**: Full text of comments containing timecodes

This makes it easy to navigate through videos using community-sourced timestamps.

## Getting a YouTube API Key

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the YouTube Data API v3
4. Create an API key
5. Add the key to your `.env` file

## License

This project is licensed under the MIT License - see the LICENSE file for details.
