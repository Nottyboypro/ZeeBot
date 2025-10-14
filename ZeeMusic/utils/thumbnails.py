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

# Premium Layout Constants
CANVAS_W, CANVAS_H = 1280, 720
GRADIENT_HEIGHT = 400
CONTENT_PADDING = 60
THUMBNAIL_SIZE = (320, 180)  # Larger thumbnail
TEXT_AREA_WIDTH = 600

# Colors for premium look
PRIMARY_COLOR = (255, 45, 85)  # Vibrant pink/red
SECONDARY_COLOR = (30, 215, 96)  # Spotify green
BACKGROUND_OVERLAY = (10, 10, 20, 200)  # Dark blue with alpha
TEXT_COLOR_WHITE = (255, 255, 255)
TEXT_COLOR_GRAY = (180, 180, 180)
ACCENT_COLOR = (255, 215, 0)  # Gold for premium touch

async def gen_thumb(videoid: str) -> str:
    cache_path = os.path.join(CACHE_DIR, f"{videoid}_premium.png")
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
    duration_text = "🔴 LIVE" if is_live else f"⏱ {duration}" if duration else "Unknown"

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
        # Create base canvas with gradient background
        base = Image.new("RGB", (CANVAS_W, CANVAS_H), color=(20, 20, 30))
        draw = ImageDraw.Draw(base)
        
        # Add gradient overlay
        for i in range(GRADIENT_HEIGHT):
            alpha = i / GRADIENT_HEIGHT
            color = (
                int(PRIMARY_COLOR[0] * alpha + 20 * (1 - alpha)),
                int(PRIMARY_COLOR[1] * alpha + 20 * (1 - alpha)),
                int(PRIMARY_COLOR[2] * alpha + 30 * (1 - alpha))
            )
            draw.line([(0, i), (CANVAS_W, i)], fill=color)
        
        # Process and add thumbnail image
        thumb_img = Image.open(thumb_path)
        thumb_img = thumb_img.resize(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        
        # Create thumbnail with modern border
        thumb_with_border = Image.new("RGB", 
                                    (THUMBNAIL_SIZE[0] + 10, THUMBNAIL_SIZE[1] + 10), 
                                    color=PRIMARY_COLOR)
        thumb_with_border.paste(thumb_img, (5, 5))
        
        # Add shadow effect
        shadow = Image.new("RGBA", (thumb_with_border.width + 20, thumb_with_border.height + 20), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle([(10, 10), 
                                     (thumb_with_border.width + 10, thumb_with_border.height + 10)], 
                                    radius=15, fill=(0, 0, 0, 150))
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        
        # Position thumbnail
        thumb_x = CONTENT_PADDING
        thumb_y = (CANVAS_H - thumb_with_border.height) // 2
        base.paste(shadow, (thumb_x - 10, thumb_y - 10), shadow)
        base.paste(thumb_with_border, (thumb_x, thumb_y))
        
        # Add play button overlay on thumbnail
        play_button_size = 40
        play_button = Image.new("RGBA", (play_button_size, play_button_size), (255, 255, 255, 200))
        play_draw = ImageDraw.Draw(play_button)
        play_draw.ellipse([(0, 0), (play_button_size, play_button_size)], 
                         fill=(255, 255, 255, 180))
        
        # Triangle for play icon
        triangle_margin = 12
        triangle_points = [
            (triangle_margin, triangle_margin),
            (triangle_margin, play_button_size - triangle_margin),
            (play_button_size - triangle_margin, play_button_size // 2)
        ]
        play_draw.polygon(triangle_points, fill=PRIMARY_COLOR)
        
        play_x = thumb_x + (THUMBNAIL_SIZE[0] - play_button_size) // 2
        play_y = thumb_y + (THUMBNAIL_SIZE[1] - play_button_size) // 2
        base.paste(play_button, (play_x, play_y), play_button)
        
        # Text content area
        text_x = thumb_x + THUMBNAIL_SIZE[0] + 40
        text_y = thumb_y
        
        try:
            # Load premium fonts
            title_font = ImageFont.truetype("ZeeMusic/assets/font2.ttf", 42)
            channel_font = ImageFont.truetype("ZeeMusic/assets/font.ttf", 28)
            meta_font = ImageFont.truetype("ZeeMusic/assets/font.ttf", 24)
            badge_font = ImageFont.truetype("ZeeMusic/assets/font2.ttf", 20)
        except:
            # Fallback to default fonts
            title_font = ImageFont.load_default()
            channel_font = ImageFont.load_default()
            meta_font = ImageFont.load_default()
            badge_font = ImageFont.load_default()

        # Title with gradient text effect
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
        
        # Limit to 2 lines
        if len(title_lines) > 2:
            title_lines = title_lines[:2]
            # Ensure last line fits with ellipsis
            last_line = title_lines[1]
            while draw.textlength(last_line + "...", font=title_font) > TEXT_AREA_WIDTH and len(last_line) > 3:
                last_line = last_line[:-1]
            title_lines[1] = last_line + "..."
        
        # Draw title lines
        for i, line in enumerate(title_lines):
            y_pos = text_y + (i * 50)
            # Text shadow
            draw.text((text_x + 2, y_pos + 2), line, font=title_font, fill=(0, 0, 0, 150))
            # Main text with gradient
            draw.text((text_x, y_pos), line, font=title_font, fill=TEXT_COLOR_WHITE)
        
        # Channel name
        channel_y = text_y + len(title_lines) * 50 + 20
        draw.text((text_x, channel_y), f"🎵 {channel}", font=channel_font, fill=SECONDARY_COLOR)
        
        # Views and duration
        meta_y = channel_y + 40
        views_text = f"👁 {views}" if views != "Unknown Views" else "👁 Unknown"
        draw.text((text_x, meta_y), views_text, font=meta_font, fill=TEXT_COLOR_GRAY)
        
        duration_x = text_x + 200
        duration_color = PRIMARY_COLOR if is_live else ACCENT_COLOR
        draw.text((duration_x, meta_y), duration_text, font=meta_font, fill=duration_color)
        
        # Premium badge
        badge_y = meta_y + 40
        badge_width = draw.textlength("PREMIUM QUALITY", font=badge_font) + 20
        draw.rounded_rectangle([(text_x, badge_y), 
                              (text_x + badge_width, badge_y + 30)], 
                             radius=15, fill=ACCENT_COLOR)
        draw.text((text_x + 10, badge_y + 5), "PREMIUM QUALITY", font=badge_font, fill=(0, 0, 0))
        
        # Bot username at bottom
        bot_text = f"Powered by @{app.username}"
        bot_text_width = draw.textlength(bot_text, font=meta_font)
        bot_x = CANVAS_W - bot_text_width - CONTENT_PADDING
        bot_y = CANVAS_H - 40
        draw.text((bot_x, bot_y), bot_text, font=meta_font, fill=TEXT_COLOR_GRAY)
        
        # Add decorative elements
        # Wave line at bottom
        wave_y = CANVAS_H - 80
        for x in range(0, CANVAS_W, 20):
            draw.line([(x, wave_y), (x + 10, wave_y - 10)], 
                     fill=PRIMARY_COLOR, width=3)
        
        # Quality indicator dots
        dots_y = badge_y + 40
        for i in range(3):
            color = SECONDARY_COLOR if i < 2 else TEXT_COLOR_GRAY
            draw.ellipse([(text_x + (i * 25), dots_y), 
                         (text_x + 15 + (i * 25), dots_y + 15)], 
                        fill=color)
        
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
