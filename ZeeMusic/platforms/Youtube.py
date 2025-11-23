import asyncio, httpx, os, re, yt_dlp
import aiofiles
import aiohttp

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


async def get_stream_url(query, video=False):
    """
    Updated get_stream_url for user's API:
    - Checks local cache (downloads/<videoid>.mp3 or .mp4). If present -> returns local path (string).
    - If not cached -> calls your API (82.180.147.88) to get download_url, spawns background cache task,
      and RETURNS the download_url string immediately so the bot can start streaming instantly.
    - Background task downloads to .part then renames atomically to final file.
    """
    # API config (your API)
    api_base = "http://82.180.147.88:5000"
    api_key = "NOTTYBOY_1d194d5fa96614b8cdbcd1fcee1551378afed30144f517bfd0c5aadc8455a489"
    endpoint = "/ytmp4" if video else "/ytmp3"
    api_url = f"{api_base.rstrip('/')}{endpoint}"

    # ensure download dir
    os.makedirs("downloads", exist_ok=True)

    # helper: try to extract a youtube id to create stable filename
    def extract_id(q: str) -> str:
        q = str(q).strip()
        # youtu.be/<id>
        m = re.search(r"youtu\.be/([A-Za-z0-9_-]{6,})", q)
        if m:
            return m.group(1)
        # v=<id>
        m = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", q)
        if m:
            return m.group(1)
        # /shorts/<id>
        m = re.search(r"/shorts/([A-Za-z0-9_-]{6,})", q)
        if m:
            return m.group(1)
        # if it looks like an id already
        if re.fullmatch(r"[A-Za-z0-9_-]{6,}", q):
            return q
        # fallback: hash of url (safe fallback)
        import hashlib
        return hashlib.md5(q.encode()).hexdigest()

    vidid = extract_id(query)
    ext = "mp4" if video else "mp3"
    filename = f"{vidid}.{ext}"
    local_path = os.path.join("downloads", filename)
    part_path = local_path + ".part"

    # quick cache check: if present and size > threshold -> return local path
    try:
        if os.path.exists(local_path) and os.path.getsize(local_path) > 20_000:
            # cached -> instant local file (string path)
            print(f"🧠 Cache hit -> {local_path}")
            return os.path.abspath(local_path)
    except Exception as e:
        print("Cache check error:", e)

    # Not cached -> call API for download_url
    params = {"q": query, "key": api_key}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(api_url, params=params)
            if resp.status_code != 200:
                print(f"API HTTP error: {resp.status_code}")
                return None
            data = resp.json()
    except Exception as e:
        print("API request failed:", e)
        return None

    # API expected response: {"code":"SUCCESS","download_url":"http://..."}
    download_url = data.get("download_url") or data.get("url") or data.get("downloadUrl") or data.get("data")
    # handle nested response where data might be dict
    if isinstance(download_url, dict):
        # try common fields
        download_url = download_url.get("url") or download_url.get("download_url")

    if not download_url:
        print("⚠️ Unexpected API response:", data)
        return None

    # Background downloader
    async def _bg_download(url: str, final_path: str, tmp_path: str, timeout_sec: int = 180):
        try:
            # if file already created by another task, skip
            if os.path.exists(final_path) and os.path.getsize(final_path) > 20_000:
                return final_path

            # remove tiny partials
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) < 1024:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
                async with session.get(url) as r:
                    if r.status != 200:
                        print(f"Background download failed HTTP {r.status}")
                        return None
                    # stream write
                    async with aiofiles.open(tmp_path, "wb") as f:
                        async for chunk in r.content.iter_chunked(64 * 1024):
                            if not chunk:
                                break
                            await f.write(chunk)
            # atomic rename
            try:
                os.replace(tmp_path, final_path)
            except Exception:
                import shutil
                shutil.move(tmp_path, final_path)

            # verify size
            if os.path.exists(final_path) and os.path.getsize(final_path) > 20_000:
                print(f"✅ Cached: {final_path}")
                return final_path
            else:
                try:
                    os.remove(final_path)
                except Exception:
                    pass
                return None
        except Exception as e:
            print("Background download exception:", e)
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return None

    # spawn background caching task (do NOT await)
    task = asyncio.create_task(_bg_download(download_url, local_path, part_path))

    # optional: attach callback to log
    def _done_cb(t):
        try:
            res = t.result()
            # can log success/failure
        except Exception:
            pass

    task.add_done_callback(_done_cb)

    # return download_url immediately so bot can start streaming from URL
    print(f"➡️ Returning direct URL for instant stream: {download_url} (caching in background)")
    return download_url


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
