import os
import re
import json
import argparse
from typing import List, Dict, Any, Tuple, Optional, Callable, Union
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import yt_dlp
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

DEFAULT_OUTPUT_DIR = "./downloads"
MAX_WORKERS = 3
MAX_COMMENTS = 100
EXPORT_FORMATS = ["txt", "csv", "xlsx", "json", "md"]
TIMECODE_RE = re.compile(r'\b(?:\d{1,2}:)?\d{1,2}:\d{2}\b')

API_KEY = os.getenv("YOUTUBE_API_KEY")
if not API_KEY:
    raise ValueError("YouTube API key not found. Set YOUTUBE_API_KEY in .env file.")

youtube = build("youtube", "v3", developerKey=API_KEY)


@dataclass
class VideoInfo:
    title: str
    channel: str
    publish_date: str


@dataclass
class ProcessResult:
    url: str
    status: str = "ERROR"
    message: str = ""
    video_info: Optional[VideoInfo] = None
    stats: Dict[str, int] = None
    timecode_info: Optional[Dict[str, Any]] = None
    download_status: Optional[str] = None
    
    def __post_init__(self):
        if self.stats is None:
            self.stats = {}


def sanitize_filename(filename: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", filename)


def get_video_id(url: str) -> str:
    if "youtu.be" in url:
        return url.split("/")[-1].split("?")[0]
    elif "youtube.com" in url:
        return url.split("v=")[1].split("&")[0]
    return url


def get_video_info(video_id: str) -> Optional[VideoInfo]:
    try:
        response = youtube.videos().list(part="snippet", id=video_id).execute()
        
        if response.get("items"):
            snippet = response["items"][0]["snippet"]
            return VideoInfo(
                title=snippet["title"],
                channel=snippet["channelTitle"],
                publish_date=snippet["publishedAt"]
            )
        return None
    except HttpError as e:
        print(f"HTTP error fetching video info: {e}")
        return None
    except Exception as e:
        print(f"Error fetching video info: {e}")
        return None


def fetch_comments(video_id: str, max_results: int = MAX_COMMENTS, sort_by: str = "relevance") -> List[Dict[str, Any]]:
    try:
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            order=sort_by
        )
        
        comments = []
        while request and len(comments) < max_results:
            response = request.execute()
            
            for item in response.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                
                comments.append({
                    "_no_": len(comments) + 1,
                    "author": snippet["authorDisplayName"],
                    "text": snippet["textOriginal"],
                    "like_count": snippet["likeCount"],
                    "published_at": snippet["publishedAt"],
                    "updated_at": snippet["updatedAt"]
                })
                
                if len(comments) >= max_results:
                    break
                    
            if len(comments) < max_results:
                request = youtube.commentThreads().list_next(request, response)
            else:
                request = None
        
        if sort_by == "time":
            comments.sort(key=lambda x: x.get("published_at", ""))
            for i, comment in enumerate(comments, 1):
                comment["_no_"] = i
            
        return comments
        
    except HttpError as e:
        print(f"HTTP error fetching comments: {e}")
        return []
    except Exception as e:
        print(f"Error fetching comments: {e}")
        return []


def extract_timecoded_comments(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    
    for comment in comments:
        matches = TIMECODE_RE.findall(comment.get("text", ""))
        if matches:
            comment_copy = comment.copy()
            comment_copy["timecodes"] = matches
            result.append(comment_copy)
            
    return result


def analyze_timecodes(comments: List[Dict[str, Any]]) -> Dict[str, Any]:
    all_timecodes = {}
    
    for comment in comments:
        timecodes = comment.get("timecodes", [])
        like_count = comment.get("like_count", 0)
        text = comment.get("text", "")
        
        for timecode in timecodes:
            if timecode not in all_timecodes:
                all_timecodes[timecode] = {
                    "count": 0,
                    "total_likes": 0,
                    "contexts": []
                }
            
            all_timecodes[timecode]["count"] += 1
            all_timecodes[timecode]["total_likes"] += like_count
            
            timecode_pos = text.find(timecode)
            if timecode_pos >= 0:
                context = text[timecode_pos:timecode_pos + len(timecode) + 50].strip()
                all_timecodes[timecode]["contexts"].append(context)
    
    scored_timecodes = [
        {
            "timecode": timecode,
            "occurrences": data["count"],
            "total_likes": data["total_likes"],
            "contexts": data["contexts"],
            "reliability_score": data["count"] * 10 + data["total_likes"]
        }
        for timecode, data in all_timecodes.items()
    ]
    
    scored_timecodes.sort(key=lambda x: x["reliability_score"], reverse=True)
    
    return {
        "all_timecodes": scored_timecodes,
        "most_reliable": scored_timecodes[0] if scored_timecodes else None
    }


def save_comments(comments: List[Dict[str, Any]], filename: str) -> None:
    ext = filename.split(".")[-1].lower()
    
    handlers = {
        "txt": lambda c, f: save_as_txt(c, f),
        "csv": lambda c, f: pd.DataFrame(c).to_csv(f, index=False, encoding="utf-8"),
        "xlsx": lambda c, f: pd.DataFrame(c).to_excel(f, index=False, engine="openpyxl"),
        "json": lambda c, f: json.dump(c, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    }
    
    if ext in handlers:
        handlers[ext](comments, filename)


def save_as_txt(comments: List[Dict[str, Any]], filename: str) -> None:
    with open(filename, mode="w", encoding="utf-8") as file:
        for comment in comments:
            file.write(
                f"No.: {comment['_no_']}\n"
                f"Author: {comment['author']}\n"
                f"Text: {comment['text']}\n"
                f"Likes: {comment['like_count']}\n"
                f"Date: {comment['published_at']}\n"
            )
            if "timecodes" in comment:
                file.write(f"Timecodes: {', '.join(comment['timecodes'])}\n")
            file.write("\n")


def create_timecode_guide(video_title: str, timecode_analysis: Dict[str, Any], 
                         comments: List[Dict[str, Any]], output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Timecode Guide for: {video_title}\n\n")
        
        if not timecode_analysis.get("all_timecodes"):
            f.write("No timecodes found in the comments.\n")
            return
        
        f.write("## Top Timecodes (by reliability)\n\n")
        
        for i, tc in enumerate(timecode_analysis["all_timecodes"], 1):
            timecode = tc["timecode"]
            occurrences = tc["occurrences"]
            likes = tc["total_likes"]
            
            contexts = tc.get("contexts", [])
            best_context = max(contexts, key=len) if contexts else ""
            
            if best_context:
                best_context = best_context.replace(timecode, "").strip()
                best_context = best_context.lstrip(" -:,;").strip()
            
            f.write(f"{i}. **{timecode}** {best_context}\n")
            f.write(f"   - Found in {occurrences} comment(s)\n")
            f.write(f"   - Total likes: {likes}\n\n")
        
        f.write("## All Comments with Timecodes\n\n")
        
        for i, comment in enumerate(comments, 1):
            author = comment.get("author", "Anonymous")
            text = comment.get("text", "")
            like_count = comment.get("like_count", 0)
            
            f.write(f"### Comment {i} by {author} (👍 {like_count})\n\n")
            f.write(f"{text}\n\n")
            
            timecodes = comment.get("timecodes", [])
            if timecodes:
                f.write("Timecodes found: " + ", ".join([f"**{tc}**" for tc in timecodes]) + "\n\n")
            
            f.write("---\n\n")


def download_video(url: str, output_dir: str, video_format: str = "mp4", 
                  skip_existing: bool = True) -> Tuple[bool, str]:
    try:
        info = yt_dlp.YoutubeDL({'quiet': True}).extract_info(url, download=False)
        title = sanitize_filename(info.get("title", "video"))
        output_path = os.path.join(output_dir, f"{title}.%(ext)s")
        
        if skip_existing and any(os.path.exists(os.path.join(output_dir, f"{title}.{ext}")) 
                               for ext in ["mp4", "webm", "mkv", "m4a"]):
            return True, f"SKIPPED (Video already exists: {title})"
        
        ydl_opts = {
            "outtmpl": output_path,
            "format": f"bestvideo[ext={video_format}]+bestaudio/best[ext={video_format}]/best",
            "merge_output_format": video_format,
            "quiet": True,
            "no_warnings": True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        return True, f"OK (Downloaded: {title})"
    except Exception as e:
        return False, f"ERROR: {str(e)}"


def export_comments(comments: List[Dict[str, Any]], base_path: str, prefix: str, formats: List[str]) -> None:
    for fmt in formats:
        if fmt in EXPORT_FORMATS and fmt != "md":
            save_comments(comments, f"{base_path}/{prefix}.{fmt}")


def process_video(url: str, output_dir: str, download_video_flag: bool = True,
                 video_format: str = "mp4", max_comments: int = MAX_COMMENTS,
                 export_formats: List[str] = None, skip_comments: bool = False) -> ProcessResult:
    result = ProcessResult(url=url)
    
    try:
        video_id = get_video_id(url)
        video_info = get_video_info(video_id)
        
        if not video_info:
            result.message = "Could not fetch video info"
            return result
        
        title = sanitize_filename(video_info.title)
        video_dir = os.path.join(output_dir, title)
        Path(video_dir).mkdir(parents=True, exist_ok=True)
        
        result.video_info = video_info
        
        if download_video_flag:
            success, message = download_video(url, video_dir, video_format)
            result.download_status = message
        
        # Skip comments processing if requested
        if skip_comments:
            result.status = "OK"
            result.message = "Video processed (comments skipped)"
            return result
            
        all_comments = fetch_comments(video_id, max_comments)
        result.stats["total_comments"] = len(all_comments)
        
        if export_formats is None:
            export_formats = ["json"]
        
        export_comments(all_comments, video_dir, "all_comments", export_formats)
        
        timecoded_comments = extract_timecoded_comments(all_comments)
        result.stats["timecoded_comments"] = len(timecoded_comments)
        
        if timecoded_comments:
            export_comments(timecoded_comments, video_dir, "timecoded_comments", export_formats)
            
            timecode_analysis = analyze_timecodes(timecoded_comments)
            json_path = os.path.join(video_dir, "timecode_analysis.json")
            
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(timecode_analysis, f, ensure_ascii=False, indent=2)
            
            if "md" in export_formats:
                guide_path = os.path.join(video_dir, "timecode_guide.md")
                create_timecode_guide(title, timecode_analysis, timecoded_comments, guide_path)
            
            result.timecode_info = {
                "count": len(timecode_analysis["all_timecodes"]),
                "top_timecodes": [tc["timecode"] for tc in timecode_analysis["all_timecodes"][:5]]
            }
        
        result.status = "OK"
        result.message = "Processing completed"
        return result
    
    except Exception as e:
        result.message = str(e)
        return result


def process_videos_from_file(file_path: str, output_dir: str, **kwargs) -> List[ProcessResult]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
        results = []
        with ThreadPoolExecutor(max_workers=kwargs.get("threads", MAX_WORKERS)) as executor:
            futures = {
                executor.submit(
                    process_video, 
                    url, 
                    output_dir,
                    kwargs.get("download_video", True),
                    kwargs.get("video_format", "mp4"),
                    kwargs.get("max_comments", MAX_COMMENTS),
                    kwargs.get("export_formats", ["json"]),
                    kwargs.get("skip_comments", False)
                ): url for url in urls
            }
            
            for f in tqdm(as_completed(futures), total=len(futures), desc="Processing videos"):
                try:
                    results.append(f.result())
                except Exception as e:
                    url = futures[f]
                    result = ProcessResult(url=url)
                    result.message = str(e)
                    results.append(result)
        
        return results
    
    except Exception as e:
        print(f"Error processing videos from file: {e}")
        return []


def print_results(results: Union[ProcessResult, List[ProcessResult]]) -> None:
    if isinstance(results, ProcessResult):
        results = [results]
        
    print("\n📊 Summary:")
    successes = [r for r in results if r.status == "OK"]
    errors = [r for r in results if r.status == "ERROR"]
    
    print(f"- Successfully processed: {len(successes)}")
    print(f"- Errors: {len(errors)}")
    
    if errors:
        print("\nErrors:")
        for r in errors:
            print(f"- {r.url}: {r.message}")
    
    if successes:
        print("\nSuccessful downloads:")
        for r in successes:
            title = r.video_info.title if r.video_info else "Unknown"
            channel = r.video_info.channel if r.video_info else "Unknown"
            
            print(f"- {title} (by {channel})")
            print(f"  • Total comments: {r.stats.get('total_comments', 0)}")
            print(f"  • Comments with timecodes: {r.stats.get('timecoded_comments', 0)}")
            
            if r.timecode_info and r.timecode_info.get("count", 0) > 0:
                top_timecodes = r.timecode_info["top_timecodes"]
                print(f"  • Top timecodes: {', '.join(top_timecodes)}")
            
            if r.download_status:
                print(f"  • Download status: {r.download_status}")
            print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube Downloader with Timecode Comment Extraction",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("-v", "--video", type=str, help="Single video URL")
    input_group.add_argument("-f", "--file", type=str, help="Text file with video URLs (one per line)")
    
    parser.add_argument("-o", "--output", type=str, default=DEFAULT_OUTPUT_DIR, 
                        help="Output directory")
    parser.add_argument("--formats", type=str, default="json,md", 
                        help="Export formats (comma-separated): txt,csv,xlsx,json,md")
    
    # Video options
    parser.add_argument("--no-video", action="store_true", 
                        help="Skip video download, only process comments")
    parser.add_argument("--video-format", type=str, default="mp4", 
                        help="Video format (mp4, webm, etc.)")
    
    # Comment options
    parser.add_argument("--skip-comments", action="store_true",
                       help="Skip comments processing, only download video")
    parser.add_argument("--comments", type=int, default=MAX_COMMENTS, 
                        help="Maximum comments to fetch per video")
    parser.add_argument("--sort", type=str, default="relevance", choices=["relevance", "time"],
                        help="Comment sort order")
    
    parser.add_argument("--threads", type=int, default=MAX_WORKERS, 
                        help="Number of parallel downloads")
    
    args = parser.parse_args()
    
    # Check for conflicting options
    if args.no_video and args.skip_comments:
        print("Error: --no-video and --skip-comments cannot be used together.")
        return
    
    Path(args.output).mkdir(parents=True, exist_ok=True)
    export_formats = [fmt.strip() for fmt in args.formats.split(",") if fmt.strip() in EXPORT_FORMATS]
    
    if args.video:
        result = process_video(
            url=args.video,
            output_dir=args.output,
            download_video_flag=not args.no_video,
            video_format=args.video_format,
            max_comments=args.comments,
            export_formats=export_formats,
            skip_comments=args.skip_comments
        )
        print_results(result)
    else:
        results = process_videos_from_file(
            file_path=args.file,
            output_dir=args.output,
            download_video=not args.no_video,
            video_format=args.video_format,
            max_comments=args.comments,
            export_formats=export_formats,
            threads=args.threads,
            skip_comments=args.skip_comments
        )
        print_results(results)


if __name__ == "__main__":
    main()
