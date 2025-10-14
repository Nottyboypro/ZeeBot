import os
import re
import aiofiles
import aiohttp
import logging
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from youtubesearchpython.__future__ import VideosSearch
from config import YOUTUBE_IMG_URL
from ZeeMusic import app

# Logging Setup
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

# Directories
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# Professional Layout Constants
CANVAS_W, CANVAS_H = 1280, 720
CONTENT_PADDING = 80
THUMBNAIL_SIZE = (400, 225)  # Clean aspect ratio
TEXT_AREA_WIDTH = 600

# Professional Color Scheme
DARK_BG = (18, 18, 24)
CARD_BG = (30, 30, 38)
ACCENT_COLOR = (220, 220, 220)  # Clean gray
TEXT_WHITE = (250, 250, 250)
TEXT_GRAY = (180, 180, 180)
YOUTUBE_RED = (255, 0, 0)

async def gen_thumb(videoid: str) -> str:
    cache_path = os.path.join(CACHE_DIR, f"{videoid}_pro.png")
    if os.path.exists(cache_path):
        return cache_path

    try:
        results = VideosSearch(f"https://www.youtube.com/watch?v={videoid}", limit=1)
        results_data = await results.next()
        data = results_data["result"][0]
        title = re.sub(r"\W+", " ", data.get("title", "Unsupported Title")).title()
        thumbnail = data.get("thumbnails", [{}])[0].get("url", YOUTUBE_IMG_URL)
        duration = data.get("duration")
        views = data.get("viewCount", {}).get("short", "Unknown Views")
        channel = data.get("channel", {}).get("name", "Unknown Channel")
    except Exception as e:
        logging.error(f"Error fetching YouTube data: {e}")
        title, thumbnail, duration, views, channel = "Unsupported Title", YOUTUBE_IMG_URL, None, "Unknown Views", "Unknown Channel"

    is_live = not duration or str(duration).strip().lower() in {"", "live", "live now"}
    duration_text = "LIVE" if is_live else f"{duration}"

    # Download thumbnail
    thumb_path = os.path.join(CACHE_DIR, f"thumb_{videoid}.jpg")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail) as resp:
                if resp.status == 200:
                    async with aiofiles.open(thumb_path, "wb") as f:
                        await f.write(await resp.read())
                else:
                    logging.error(f"Failed to download thumbnail (HTTP {resp.status})")
                    return YOUTUBE_IMG_URL
    except Exception as e:
        logging.error(f"Download error: {e}")
        return YOUTUBE_IMG_URL

    try:
        # Create clean dark background
        base = Image.new("RGB", (CANVAS_W, CANVAS_H), color=DARK_BG)
        draw = ImageDraw.Draw(base)
        
        # Create content card
        card_width = CANVAS_W - (CONTENT_PADDING * 2)
        card_height = CANVAS_H - (CONTENT_PADDING * 2)
        card_x = CONTENT_PADDING
        card_y = CONTENT_PADDING
        
        # Draw main card
        draw.rounded_rectangle([(card_x, card_y), 
                              (card_x + card_width, card_y + card_height)], 
                             radius=12, fill=CARD_BG)
        
        # Process and position thumbnail
        thumb_img = Image.open(thumb_path)
        thumb_img = thumb_img.resize(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        
        # Add subtle border to thumbnail
        thumb_with_border = Image.new("RGB", 
                                    (THUMBNAIL_SIZE[0] + 2, THUMBNAIL_SIZE[1] + 2), 
                                    color=ACCENT_COLOR)
        thumb_with_border.paste(thumb_img, (1, 1))
        
        thumb_x = card_x + 40
        thumb_y = card_y + 40
        base.paste(thumb_with_border, (thumb_x, thumb_y))
        
        # Text content area (right side)
        text_x = thumb_x + THUMBNAIL_SIZE[0] + 40
        text_y = thumb_y
        
        try:
            # Professional fonts
            title_font = ImageFont.truetype("ZeeMusic/assets/font2.ttf", 36)
            channel_font = ImageFont.truetype("ZeeMusic/assets/font.ttf", 26)
            meta_font = ImageFont.truetype("ZeeMusic/assets/font.ttf", 22)
            small_font = ImageFont.truetype("ZeeMusic/assets/font.ttf", 20)
        except:
            # Fallback to default fonts
            title_font = ImageFont.load_default()
            channel_font = ImageFont.load_default()
            meta_font = ImageFont.load_default()
            small_font = ImageFont.load_default()

        # Title - Clean and professional
        title_lines = []
        current_line = ""
        for word in title.split():
            test_line = f"{current_line} {word}".strip()
            if draw.textlength(test_line, font=title_font) <= TEXT_AREA_WIDTH:
                current_line = test_line
            else:
                if current_line:
                    title_lines.append(current_line)
                current_line = word
        if current_line:
            title_lines.append(current_line)
        
        # Limit to 3 lines maximum
        if len(title_lines) > 3:
            title_lines = title_lines[:3]
            if len(title_lines[2]) > 45:
                title_lines[2] = title_lines[2][:42] + "..."
        
        # Draw title lines
        for i, line in enumerate(title_lines):
            y_pos = text_y + (i * 45)
            draw.text((text_x, y_pos), line, font=title_font, fill=TEXT_WHITE)
        
        # Channel info
        channel_y = text_y + len(title_lines) * 45 + 30
        draw.text((text_x, channel_y), channel, font=channel_font, fill=TEXT_GRAY)
        
        # Stats line
        stats_y = channel_y + 40
        stats_text = f"{views} • {duration_text}"
        if is_live:
            # Live indicator
            live_indicator_size = 8
            draw.ellipse([(text_x, stats_y + 10), 
                         (text_x + live_indicator_size, stats_y + 10 + live_indicator_size)], 
                        fill=YOUTUBE_RED)
            stats_text = f"LIVE • {views}"
        
        draw.text((text_x + 15, stats_y), stats_text, font=meta_font, fill=TEXT_GRAY)
        
        # Separator line
        separator_y = stats_y + 40
        draw.line([(text_x, separator_y), 
                  (text_x + TEXT_AREA_WIDTH, separator_y)], 
                 fill=ACCENT_COLOR, width=1)
        
        # Progress section (minimal)
        progress_y = separator_y + 30
        draw.text((text_x, progress_y), "00:00", font=small_font, fill=TEXT_GRAY)
        
        progress_end_x = text_x + TEXT_AREA_WIDTH - 60
        draw.text((progress_end_x, progress_y), duration_text, font=small_font, 
                 fill=YOUTUBE_RED if is_live else TEXT_WHITE)
        
        # Progress bar background
        bar_y = progress_y + 30
        bar_height = 4
        draw.rounded_rectangle([(text_x, bar_y), 
                              (text_x + TEXT_AREA_WIDTH, bar_y + bar_height)], 
                             radius=2, fill=(60, 60, 70))
        
        # Progress indicator
        progress_width = int(TEXT_AREA_WIDTH * 0.3)  # 30% progress
        draw.rounded_rectangle([(text_x, bar_y), 
                              (text_x + progress_width, bar_y + bar_height)], 
                             radius=2, fill=TEXT_WHITE)
        
        # Bot attribution (subtle)
        bot_text = f"@{app.username}"
        bot_text_width = draw.textlength(bot_text, font=small_font)
        bot_x = card_x + card_width - bot_text_width - 20
        bot_y = card_y + card_height - 30
        draw.text((bot_x, bot_y), bot_text, font=small_font, fill=TEXT_GRAY)
        
        # YouTube branding (minimal)
        yt_text = "YouTube"
        yt_x = card_x + 20
        yt_y = card_y + card_height - 30
        draw.text((yt_x, yt_y), yt_text, font=small_font, fill=YOUTUBE_RED)
        
    except Exception as e:
        logging.error(f"Image generation error: {e}")
        return YOUTUBE_IMG_URL

    # Cleanup
    try:
        os.remove(thumb_path)
    except Exception as e:
        logging.error(f"Cleanup error: {e}")

    # Save final image
    try:
        base.save(cache_path, "PNG", quality=95)
        return cache_path
    except Exception as e:
        logging.error(f"Save error: {e}")
        return YOUTUBE_IMG_URL
