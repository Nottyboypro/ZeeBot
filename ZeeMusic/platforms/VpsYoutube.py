import asyncio, httpx, os, re, yt_dlp
import aiofiles
import aiohttp
from urllib.parse import urlparse, parse_qs

from typing import Union
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType
from youtubesearchpython.__future__ import VideosSearch


def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60**i for i, x in enumerate(reversed(stringt.split(":"))))


async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    if errorz:
        if "unavailable videos are hidden" in (errorz.decode("utf-8")).lower():
            return out.decode("utf-8")
        else:
            return errorz.decode("utf-8")
    return out.decode("utf-8")

DOWNLOAD_DIR = "downloads"
API_BASE = "http://82.180.147.88:5000"
API_KEY = "NOTTYBOY_1d194d5fa96614b8cdbcd1fcee1551378afed30144f517bfd0c5aadc8455a489"
API_ENDPOINT = "/ytmp3"  # or /ytmp4 if you want video

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def extract_youtube_id(query: str) -> str:
    """
    Try to extract a youtube id from a url or return the input (if it already is an id).
    """
    # common youtube patterns
    if "youtu" in query:
        parsed = urlparse(query)
        # youtu.be/<id>
        if parsed.netloc.endswith("youtu.be"):
            return parsed.path.strip("/")
        # youtube.com/watch?v=...
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]
        # /shorts/<id> or /watch/<id>
        m = re.search(r"/(shorts|watch)/([A-Za-z0-9_-]{8,})", parsed.path)
        if m:
            return m.group(2)
    # fallback: assume the query passed is an id already
    return query.strip()


async def _download_and_cache(download_url: str, local_path: str, timeout: int = 180):
    """
    Background downloader: writes to local_path.part then renames to local_path.
    Skips if file already exists and size > 20KB.
    """
    part_path = local_path + ".part"
    try:
        # quick exist check
        if os.path.exists(local_path) and os.path.getsize(local_path) > 20_000:
            # already cached
            return local_path

        # if a partial exists but is small, remove it (or we could resume)
        if os.path.exists(part_path) and os.path.getsize(part_path) < 1024:
            try:
                os.remove(part_path)
            except Exception:
                pass

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    # download failed
                    return None
                # stream to disk
                async with aiofiles.open(part_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        if not chunk:
                            break
                        await f.write(chunk)

        # move/rename atomically
        try:
            os.replace(part_path, local_path)
        except Exception:
            # fallback copy
            import shutil
            shutil.move(part_path, local_path)

        # final size check
        if os.path.exists(local_path) and os.path.getsize(local_path) > 20_000:
            return local_path
        else:
            # corrupted/small file
            try:
                os.remove(local_path)
            except Exception:
                pass
            return None

    except Exception as e:
        # cleanup partial
        try:
            if os.path.exists(part_path):
                os.remove(part_path)
        except Exception:
            pass
        return None


async def get_stream_source(query: str, *, api_base: str = API_BASE, api_key: str = API_KEY, use_video: bool = False):
    """
    Main helper for bot streaming.

    Returns a dict:
      - {'type': 'file', 'path': '/full/path/to/file.mp3'}  # use local file for streaming
      - {'type': 'url', 'url': 'http://...download...?key=...'}  # use direct URL for instant stream

    Behavior:
      - If cache exists -> returns 'file'
      - Else -> calls API, obtains download_url, immediately spawns background caching task
                and returns {'type':'url', 'url': download_url} so you can start streaming instantly.
    """
    # normalize and pick filename
    video_id = extract_youtube_id(query)
    # safe filename
    filename = f"{video_id}.mp3" if not use_video else f"{video_id}.mp4"
    local_path = os.path.join(DOWNLOAD_DIR, filename)

    # 1) cache check
    try:
        if os.path.exists(local_path) and os.path.getsize(local_path) > 20_000:
            # cached; return local file path immediately
            return {"type": "file", "path": os.path.abspath(local_path)}
    except Exception:
        pass

    # 2) not cached -> call API to get download_url
    endpoint = "/ytmp4" if use_video else "/ytmp3"
    api_url = f"{api_base.rstrip('/')}{endpoint}"
    params = {"q": query, "key": api_key}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(api_url, params=params)
            if resp.status_code != 200:
                # log and return None (bot can handle)
                return None
            data = resp.json()
    except Exception:
        return None

    # Expecting API response like: {"code":"SUCCESS", "download_url":"http://..."}
    download_url = data.get("download_url") or data.get("downloadUrl") or data.get("url")
    if not download_url:
        return None

    # start background caching (do not await)
    # use a unique local_path based on filename; if API provides filename, you can prefer that.
    bg_task = asyncio.create_task(_download_and_cache(download_url, local_path))
    # (optional) attach a done callback to log errors
    def _on_done(t):
        try:
            res = t.result()
            # you can add logging here: print("Cache result:", res)
        except Exception:
            pass

    bg_task.add_done_callback(_on_done)

    # return the direct URL for instant streaming
    return {"type": "url", "url": download_url}


# ----------------------------
# Usage example (pseudo)
# ----------------------------
# Suppose you use pytgcalls (or any library that accepts a URL or file path as source):
#
# src = await get_stream_source("https://youtu.be/abcd1234")
# if src is None:
#     # handle error (e.g., send message "Failed to fetch")
# elif src["type"] == "file":
#     # play local file
#     await pytgcalls.play_local(peer, src["path"])
# elif src["type"] == "url":
#     # play the remote url directly (instant)
#     await pytgcalls.play_stream(peer, src["url"])
#
# The background task will cache the file into downloads/<videoid>.mp3 for later reuse.


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if re.search(self.regex, link):
            return True
        else:
            return False

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
        """
        Updated to use our integrated API for video streaming
        """
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
            
        return await get_stream_url(link, True)
        
    async def audio(self, link: str, videoid: Union[bool, str] = None):
        """
        New method to get audio stream URL using our integrated API
        """
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
            
        return await get_stream_url(link, False)

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        playlist = await shell_cmd(
            f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}"
        )
        try:
            result = playlist.split("\n")
            for key in result:
                if key == "":
                    result.remove(key)
        except:
            result = []
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
        ytdl_opts = {"quiet": True}
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for format in r["formats"]:
                try:
                    str(format["format"])
                except:
                    continue
                if not "dash" in str(format["format"]).lower():
                    try:
                        format["format"]
                        format["filesize"]
                        format["format_id"]
                        format["ext"]
                        format["format_note"]
                    except:
                        continue
                    formats_available.append(
                        {
                            "format": format["format"],
                            "filesize": format["filesize"],
                            "format_id": format["format_id"],
                            "ext": format["ext"],
                            "format_note": format["format_note"],
                            "yturl": link,
                        }
                    )
        return formats_available, link

    async def slider(
        self,
        link: str,
        query_type: int,
        videoid: Union[bool, str] = None,
    ):
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
    ) -> str:
        """
        Updated download method to use our integrated API instead of yt-dlp
        """
        if videoid:
            link = self.base + link
            
        # For simple audio/video downloads, use our API
        if video and not songvideo:
            downloaded_file = await get_stream_url(link, True)
            return downloaded_file, None
        elif not video and not songaudio:
            downloaded_file = await get_stream_url(link, False)
            return downloaded_file, None
        
        # For specific format downloads, fall back to original yt-dlp method
        loop = asyncio.get_running_loop()

        def audio_dl():
            ydl_optssx = {
                "format": "bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
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
            ydl_optssx = {
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
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
            formats = f"{format_id}+140"
            fpath = f"downloads/{title}"
            ydl_optssx = {
                "format": formats,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "prefer_ffmpeg": True,
                "merge_output_format": "mp4",
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            x.download([link])

        def song_audio_dl():
            fpath = f"downloads/{title}.%(ext)s"
            ydl_optssx = {
                "format": format_id,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
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

        if songvideo:
            await loop.run_in_executor(None, song_video_dl)
            fpath = f"downloads/{title}.mp4"
            return fpath
        elif songaudio:
            await loop.run_in_executor(None, song_audio_dl)
            fpath = f"downloads/{title}.mp3"
            return fpath
        elif video:
            downloaded_file = await loop.run_in_executor(None, video_dl)
            direct = None
        else:
            downloaded_file = await loop.run_in_executor(None, audio_dl)
            direct = None
        return downloaded_file, direct
