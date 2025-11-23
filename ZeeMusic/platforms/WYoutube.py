# updated_zee_youtube_api.py
import asyncio
import os
import re
import json
import logging
import random
import glob
from typing import Union, Optional, Tuple, List

import aiohttp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch
import yt_dlp

from ZeeMusic.utils.database import is_on_off
from ZeeMusic.utils.formatters import time_to_seconds

# ---------- config / constants ----------
API_URL = "http://82.180.147.88:5000"
API_KEY = "NOTTYBOY_1d194d5fa96614b8cdbcd1fcee1551378afed30144f517bfd0c5aadc8455a489"
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# background cache concurrency limit
_CACHE_SEMAPHORE = asyncio.Semaphore(3)

# logging
log = logging.getLogger(__name__)
if not log.handlers:
    # Default basic config; your app bootstrap can reconfigure logging more globally
    logging.basicConfig(level=logging.INFO)

# ---------- helper utils ----------
def cookie_txt_file() -> Optional[str]:
    cookie_dir = f"{os.getcwd()}/cookies"
    if not os.path.exists(cookie_dir):
        return None
    cookies_files = [f for f in os.listdir(cookie_dir) if f.endswith(".txt")]
    if not cookies_files:
        return None
    cookie_file = os.path.join(cookie_dir, random.choice(cookies_files))
    return cookie_file

def _extract_video_id(link: str) -> str:
    if "v=" in link:
        return link.split('v=')[-1].split('&')[0]
    if "youtu.be/" in link:
        return link.split("youtu.be/")[-1].split('?')[0].split('&')[0]
    # fallback: assume it's already an id
    return link.split('&')[0].split('?')[0]

def _normalize_extension(format_field: Optional[str], default: str) -> str:
    if not format_field:
        return default
    f = format_field.lower()
    if "/" in f:
        f = f.split("/")[-1]
    if f in ("mpeg", "mp3", "audio-mpeg"):
        return "mp3"
    if f in ("m4a", "aac"):
        return "m4a"
    if f in ("webm",):
        return "webm"
    if f in ("mp4", "video/mp4"):
        return "mp4"
    if f in ("mkv",):
        return "mkv"
    return default

async def _background_cache(download_url: str, file_path: str, session_timeout: int = 30) -> Optional[str]:
    """
    Download the remote file to file_path. Returns file_path on success, else None.
    Uses a .part temporary file and atomic replacement to avoid corruption.
    """
    if os.path.exists(file_path):
        log.debug("Cache already present: %s", file_path)
        return file_path

    tmp_path = file_path + ".part"
    try:
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=session_timeout, sock_read=None)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    log.warning("Background cache request returned status %s for %s", resp.status, download_url)
                    return None
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                os.replace(tmp_path, file_path)
                log.info("Cached file saved: %s", file_path)
                return file_path
    except Exception as e:
        log.exception("Background caching failed for %s: %s", download_url, e)
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return None

async def _start_background_cache(download_url: str, file_path: str):
    """Concurrency-limited wrapper for background caching."""
    async with _CACHE_SEMAPHORE:
        return await _background_cache(download_url, file_path)

async def _query_api_and_get_info(endpoint: str, q: str, key: str, max_attempts: int = 5) -> Optional[dict]:
    params = {"q": q, "key": key}
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(1, max_attempts + 1):
            try:
                async with session.get(endpoint, params=params) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        raise Exception(f"API status {resp.status}: {text[:200]}")
                    data = await resp.json()
                    return data
            except Exception as e:
                log.warning("API query failed attempt %s for %s: %s", attempt, endpoint, e)
                if attempt < max_attempts:
                    await asyncio.sleep(1 + attempt)
                    continue
                return None
    return None

# ---------- public streaming helpers ----------
async def get_stream_url_for_song(link_or_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (stream_source, cached_file_path)
    - stream_source: immediate best URL/path to stream from (local path or remote download_url)
    - cached_file_path: where file will be cached (or existing local path). May be None.
    """
    video_id = _extract_video_id(link_or_id)
    for ext in ("mp3", "m4a", "webm"):
        p = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.{ext}")
        if os.path.exists(p):
            log.debug("Found local cache for song: %s", p)
            return (p, p)

    endpoint = f"{API_URL}/ytmp3"
    data = await _query_api_and_get_info(endpoint, video_id, API_KEY, max_attempts=4)
    if not data:
        log.debug("No API data for song %s", video_id)
        return (None, None)

    download_url = data.get("download_url") or data.get("link")
    fmt = _normalize_extension(data.get("format"), "mp3")
    cached_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.{fmt}")

    if download_url:
        # Kick off background caching (limited by semaphore)
        asyncio.create_task(_start_background_cache(download_url, cached_path))
        return (download_url, cached_path)

    # If API returns processing status, allow a few quick polls (non-blocking)
    status = (data.get("status") or "").lower()
    if status in ("downloading", "processing"):
        # try simple polling a few times to wait for immediate link
        for i in range(3):
            await asyncio.sleep(2)
            data = await _query_api_and_get_info(endpoint, video_id, API_KEY, max_attempts=1)
            if not data:
                break
            download_url = data.get("download_url") or data.get("link")
            if download_url:
                asyncio.create_task(_start_background_cache(download_url, cached_path))
                return (download_url, cached_path)
        # still no link
        log.info("API still processing for %s", video_id)
        return (None, None)

    return (None, None)

async def get_stream_url_for_video(link_or_id: str) -> Tuple[Optional[str], Optional[str]]:
    video_id = _extract_video_id(link_or_id)
    for ext in ("mp4", "webm", "mkv"):
        p = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.{ext}")
        if os.path.exists(p):
            log.debug("Found local cache for video: %s", p)
            return (p, p)

    endpoint = f"{API_URL}/ytmp4"
    data = await _query_api_and_get_info(endpoint, video_id, API_KEY, max_attempts=4)
    if not data:
        log.debug("No API data for video %s", video_id)
        return (None, None)

    download_url = data.get("download_url") or data.get("link")
    fmt = _normalize_extension(data.get("format"), "mp4")
    cached_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.{fmt}")

    if download_url:
        asyncio.create_task(_start_background_cache(download_url, cached_path))
        return (download_url, cached_path)

    status = (data.get("status") or "").lower()
    if status in ("downloading", "processing"):
        for i in range(3):
            await asyncio.sleep(3)
            data = await _query_api_and_get_info(endpoint, video_id, API_KEY, max_attempts=1)
            if not data:
                break
            download_url = data.get("download_url") or data.get("link")
            if download_url:
                asyncio.create_task(_start_background_cache(download_url, cached_path))
                return (download_url, cached_path)
        log.info("API still processing for video %s", video_id)
        return (None, None)

    return (None, None)

# ---------- synchronous downloads triggered by bot when explicit download is needed ----------
async def download_song(link_or_id: str) -> Optional[str]:
    """
    Ensure the song is available as a local file. Returns local file path on success,
    or a remote URL if caching failed but streaming link exists, else None.
    """
    stream_source, cached_path = await get_stream_url_for_song(link_or_id)
    if stream_source is None:
        return None

    # if it's a local path already
    if os.path.exists(stream_source):
        return stream_source

    # if remote URL, attempt to download (await, because caller asked to download)
    if stream_source.startswith("http"):
        res = await _background_cache(stream_source, cached_path)
        if res:
            return res
        # fallback: if caching failed, still return remote URL so caller can stream
        return stream_source

    # other fallback
    return None

async def download_video(link_or_id: str) -> Optional[str]:
    """
    Ensure the video is available as a local file. Returns local file path on success,
    or a remote URL if caching failed but streaming link exists, else None.
    """
    stream_source, cached_path = await get_stream_url_for_video(link_or_id)
    if stream_source is None:
        return None

    if os.path.exists(stream_source):
        return stream_source

    if stream_source.startswith("http"):
        res = await _background_cache(stream_source, cached_path)
        if res:
            return res
        return stream_source

    return None

# ---------- yt-dlp helpers ----------
async def shell_cmd(cmd: str) -> str:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    if errorz:
        err_text = errorz.decode("utf-8")
        # sometimes yt-dlp writes useful info to stderr; preserve that
        if "unavailable videos are hidden" in err_text.lower():
            return out.decode("utf-8")
        return err_text
    return out.decode("utf-8")

async def check_file_size(link: str) -> Optional[int]:
    """
    Uses yt-dlp -J to get JSON and sums 'filesize' and 'filesize_approx' across formats.
    Returns total bytes or None.
    """
    async def get_format_info(link: str):
        cookie_file = cookie_txt_file()
        if not cookie_file:
            log.warning("No cookies found. Cannot check file size.")
            return None

        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--cookies", cookie_file,
            "-J",
            link,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            log.error("yt-dlp -J failed: %s", stderr.decode())
            return None
        try:
            return json.loads(stdout.decode())
        except Exception as e:
            log.exception("Parsing yt-dlp output failed: %s", e)
            return None

    def parse_size(formats: List[dict]) -> int:
        total_size = 0
        for fmt in formats:
            fs = fmt.get("filesize") or fmt.get("filesize_approx")
            if fs:
                try:
                    total_size += int(fs)
                except Exception:
                    continue
        return total_size

    info = await get_format_info(link)
    if not info:
        return None
    formats = info.get("formats", [])
    if not formats:
        log.warning("No formats found for %s", link)
        return None
    total = parse_size(formats)
    return total

# ---------- YouTubeAPI class (cleaned up) ----------
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        text = ""
        offset = None
        length = None
        for message in messages:
            if offset:
                break
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        offset, length = entity.offset, entity.length
                        break
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        if offset in (None,):
            return None
        return text[offset : offset + length]

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            vidid = result["id"]
            if str(duration_min) == "None":
                duration_sec = 0
            else:
                duration_sec = int(time_to_seconds(duration_min))
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
        return title

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            duration = result["duration"]
        return duration

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        return thumbnail

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        # Try video API first (returns path or remote URL)
        try:
            downloaded_file = await download_video(link)
            if downloaded_file:
                return 1, downloaded_file
        except Exception as e:
            log.exception("Video API failed: %s", e)

        # Fallback to cookies + yt-dlp direct URL
        cookie_file = cookie_txt_file()
        if not cookie_file:
            return 0, "No cookies found. Cannot download video."

        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--cookies", cookie_file,
            "-g",
            "-f",
            "best[height<=?720][width<=?1280]",
            f"{link}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            return 1, stdout.decode().split("\n")[0]
        else:
            return 0, stderr.decode()

    async def playlist(self, link: str, limit: int, user_id: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]

        cookie_file = cookie_txt_file()
        if not cookie_file:
            return []

        playlist = await shell_cmd(
            f"yt-dlp -i --get-id --flat-playlist --cookies {cookie_file} --playlist-end {limit} --skip-download {link}"
        )
        result = [k for k in playlist.split("\n") if k]
        return result

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            vidid = result["id"]
            yturl = result["link"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        track_details = {
            "title": title,
            "link": yturl,
            "vidid": vidid,
            "duration_min": duration_min,
            "thumb": thumbnail,
        }
        return track_details, vidid

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        cookie_file = cookie_txt_file()
        if not cookie_file:
            return [], link

        ytdl_opts = {"quiet": True, "cookiefile": cookie_file}
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for fmt in r.get("formats", []):
                try:
                    str(fmt["format"])
                except Exception:
                    continue
                if "dash" in str(fmt["format"]).lower():
                    continue
                try:
                    _ = fmt["format"], fmt.get("filesize"), fmt.get("format_id"), fmt.get("ext"), fmt.get("format_note")
                except Exception:
                    continue
                if not fmt.get("filesize") and not fmt.get("filesize_approx"):
                    # skip if there is no filesize meta (optional)
                    pass
                formats_available.append(
                    {
                        "format": fmt["format"],
                        "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
                        "format_id": fmt.get("format_id"),
                        "ext": fmt.get("ext"),
                        "format_note": fmt.get("format_note"),
                        "yturl": link,
                    }
                )
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        a = VideosSearch(link, limit=10)
        result = (await a.next()).get("result")
        title = result[query_type]["title"]
        duration_min = result[query_type]["duration"]
        vidid = result[query_type]["id"]
        thumbnail = result[query_type]["thumbnails"][0]["url"].split("?")[0]
        return title, duration_min, thumbnail, vidid

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], Optional[bool]]:
        """
        Returns tuple (downloaded_file_or_url, direct_bool).
        direct_bool True => we used direct/download approach; False => returned streaming URL from yt-dlp (or other)
        """
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        loop = asyncio.get_running_loop()

        def audio_dl():
            cookie_file = cookie_txt_file()
            if not cookie_file:
                raise Exception("No cookies found. Cannot download audio.")

            ydl_optssx = {
                "format": "bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": cookie_file,
                "no_warnings": True,
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            info = x.extract_info(link, False)
            xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        def video_dl():
            cookie_file = cookie_txt_file()
            if not cookie_file:
                raise Exception("No cookies found. Cannot download video.")

            ydl_optssx = {
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": cookie_file,
                "no_warnings": True,
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            info = x.extract_info(link, False)
            xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        def song_video_dl():
            cookie_file = cookie_txt_file()
            if not cookie_file:
                raise Exception("No cookies found. Cannot download song video.")

            formats = f"{format_id}+140"
            fpath = f"downloads/{title}"
            ydl_optssx = {
                "format": formats,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "cookiefile": cookie_file,
                "prefer_ffmpeg": True,
                "merge_output_format": "mp4",
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            x.download([link])

        def song_audio_dl():
            cookie_file = cookie_txt_file()
            if not cookie_file:
                raise Exception("No cookies found. Cannot download song audio.")
            fpath = f"downloads/{title}.%(ext)s"
            ydl_optssx = {
                "format": format_id,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "cookiefile": cookie_file,
                "prefer_ffmpeg": True,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            x.download([link])

        # MAIN decision logic
        if songvideo:
            # use download_song (which will call API or cache and return path)
            result = await download_song(link)
            if result:
                return result, True
            return None, None

        elif songaudio:
            result = await download_song(link)
            if result:
                return result, True
            return None, None

        elif video:
            # Try video API first
            try:
                downloaded_file = await download_video(link)
                if downloaded_file:
                    direct = True
                    return downloaded_file, direct
            except Exception as e:
                log.exception("Video API failed: %s", e)

            # Fallback to cookies + yt-dlp
            cookie_file = cookie_txt_file()
            if not cookie_file:
                log.warning("No cookies found. Cannot download video.")
                return None, None

            if await is_on_off(1):
                # direct mode: use API/audio pipeline
                direct = True
                downloaded_file = await download_song(link)
                return downloaded_file, direct
            else:
                proc = await asyncio.create_subprocess_exec(
                    "yt-dlp",
                    "--cookies", cookie_file,
                    "-g",
                    "-f",
                    "best[height<=?720][width<=?1280]",
                    f"{link}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if stdout:
                    downloaded_file = stdout.decode().split("\n")[0]
                    direct = False
                else:
                    file_size = await check_file_size(link)
                    if not file_size:
                        log.info("Unable to determine file size for %s", link)
                        return None, None
                    total_size_mb = file_size / (1024 * 1024)
                    if total_size_mb > 250:
                        log.info("File size %.2f MB exceeds the limit.", total_size_mb)
                        return None, None
                    direct = True
                    downloaded_file = await loop.run_in_executor(None, video_dl)
        else:
            direct = True
            downloaded_file = await download_song(link)
        return downloaded_file, direct
