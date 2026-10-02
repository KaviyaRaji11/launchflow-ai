"""Create exact-size social assets around the user's unaltered product image."""
import base64
import io
import os
import uuid

import httpx
from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont, ImageOps

from services.media_storage import save_media

VISUAL_PROVIDER = os.getenv("VISUAL_PROVIDER", "local").strip().lower()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_IMAGE_MODEL = os.getenv("OPENROUTER_IMAGE_MODEL", "google/gemini-3.1-flash-image")
OPENROUTER_IMAGE_URL = "https://openrouter.ai/api/v1/images"

# The keys match the frontend's individual asset selectors.
PLATFORM_SPECS = {
    "instagram": (1080, 1350), "instagram_story": (1080, 1920),
    "youtube": (1280, 720), "youtube_shorts": (1080, 1920),
    "facebook": (1080, 1080), "x": (1600, 900),
    "whatsapp": (1080, 1080), "whatsapp_status": (1080, 1920),
}

PALETTES = {
    "premium": ("#243A46", "#E2E8E9", "#172B33"),
    "playful": ("#B84F36", "#F5E9DD", "#30241E"),
    "warm": ("#945D42", "#F1E6DB", "#37281F"),
    "bold": ("#A64036", "#F2E1DC", "#311D1A"),
    "professional": ("#315B68", "#E3ECEC", "#1F343A"),
    "friendly": ("#34634D", "#E5EEE5", "#20352B"),
}


def _font(size, bold=False):
    names = ("DejaVuSans-Bold.ttf", "Arial Bold.ttf") if bold else ("DejaVuSans.ttf", "Arial.ttf")
    paths = [f"/usr/share/fonts/truetype/dejavu/{names[0]}", f"/System/Library/Fonts/Supplemental/{names[-1]}", f"/Library/Fonts/{names[-1]}"]
    for path in paths:
        try:
            return ImageFont.truetype(path, max(12, int(size)))
        except OSError:
            pass
    return ImageFont.load_default()


def _price_font(size):
    paths = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
        "/System/Library/Fonts/Supplemental/ITFDevanagari.ttc",
        "/System/Library/Fonts/Supplemental/DevanagariMT.ttc",
    )
    for path in paths:
        try:
            font = ImageFont.truetype(path, max(12, int(size)))
            rupee = font.getmask("₹")
            square = font.getmask("□")
            if rupee.getbbox() and (rupee.size != square.size or list(rupee) != list(square)):
                return font
        except OSError:
            continue
    return _font(size, True)


def _trim_empty_margins(product):
    """Remove transparent padding only; never infer/crop an opaque product edge."""
    alpha = product.getchannel("A")
    alpha_box = alpha.getbbox()
    if alpha_box and alpha_box != (0, 0, *product.size):
        product = product.crop(alpha_box)
    return product


def _fit_product(canvas, product, box):
    """Proportionally contain-fit and return the exact occupied rectangle."""
    x1, y1, x2, y2 = box
    scale = min((x2 - x1) / product.width, (y2 - y1) / product.height)
    fitted_size = (max(1, int(product.width * scale)), max(1, int(product.height * scale)))
    fitted = product.resize(fitted_size, Image.Resampling.LANCZOS)
    x = x1 + (x2 - x1 - fitted.width) // 2
    y = y1 + (y2 - y1 - fitted.height) // 2
    canvas.paste(fitted, (x, y), fitted if fitted.mode == "RGBA" else None)
    return (x, y, x + fitted.width, y + fitted.height)


def _text_lines(draw, value, font, width):
    words, lines, line = str(value or "").split(), [], ""
    for word in words:
        proposal = f"{line} {word}".strip()
        if draw.textbbox((0, 0), proposal, font=font)[2] <= width:
            line = proposal
        else:
            if line:
                lines.append(line)
            # Long words are split character-by-character rather than clipped.
            line = ""
            for char in word:
                if draw.textbbox((0, 0), line + char, font=font)[2] > width and line:
                    lines.append(line); line = char
                else:
                    line += char
    if line:
        lines.append(line)
    return lines


def _draw_text_in_box(draw, text, box, size, color, bold=False, align="left", max_lines=16, price=False):
    """Fit complete copy in a fixed safe area or fail rather than clip it."""
    x1, y1, x2, y2 = box
    width, height = x2 - x1, y2 - y1
    font = _price_font(size) if price else _font(size, bold)
    lines = _text_lines(draw, text, font, width)
    while lines and (len(lines) > max_lines or len(lines) * font.size * 1.2 > height) and font.size > 12:
        next_size = font.size - 2
        font = _price_font(next_size) if price else _font(next_size, bold)
        lines = _text_lines(draw, text, font, width)
    if len(lines) > max_lines or len(lines) * font.size * 1.2 > height:
        raise HTTPException(status_code=422, detail="Campaign text is too long for the selected image format. Shorten the product name, USP, price, or CTA and retry campaign generation.")
    bounds = []
    y = y1
    for line in lines:
        line_box = draw.textbbox((0, 0), line, font=font)
        line_width = line_box[2] - line_box[0]
        target_x = x1 if align == "left" else x1 + (width - line_width) // 2
        x = target_x - line_box[0]
        y_draw = y - line_box[1]
        draw.text((x, y_draw), line, font=font, fill=color)
        actual = draw.textbbox((x, y_draw), line, font=font)
        if actual[0] < x1 or actual[2] > x2 or actual[1] < y1 or actual[3] > y2:
            raise HTTPException(status_code=500, detail="Text layout exceeded its safe area.")
        bounds.append(actual)
        y += int(font.size * 1.2)
    return bounds


def compose_marketing_visual(image_bytes, product_name, platform, description="", price="", usp="", cta="", brand_tone=""):
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Product image is empty.")
    if platform not in PLATFORM_SPECS:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")
    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            product = ImageOps.exif_transpose(source).convert("RGBA")
    except Exception:
        raise HTTPException(status_code=400, detail="Uploaded product image is invalid.")
    product = _trim_empty_margins(product)
    if product.getchannel("A").getbbox() is None:
        raise HTTPException(status_code=400, detail="Uploaded product image is fully transparent.")

    width, height = PLATFORM_SPECS[platform]
    tone = str(brand_tone or "").casefold()
    brand_accent, wash, brand_ink = next((palette for key, palette in PALETTES.items() if key in tone), PALETTES["friendly"])
    # Every canvas has its own palette and geometry. Brand tone supplies the
    # supporting wash while the platform treatment remains recognizable.
    styles = {
        "instagram": ("#FAF1EC", "#B7465A", "#26352F"),
        "instagram_story": ("#FFF3F1", "#BC405D", "#34252A"),
        "youtube_shorts": ("#20252B", "#E33A37", "#FFFFFF"),
        "youtube": ("#17232D", "#E73737", "#FFFFFF"),
        "facebook": ("#EEF3FA", "#356CB4", "#24364B"),
        "x": ("#F1F4F4", "#17202A", "#15212A"),
        "whatsapp": ("#EFF6EF", "#2D8356", "#23372A"),
        "whatsapp_status": ("#EAF5EF", "#16855D", "#19392E"),
    }
    background, accent, default_ink = styles[platform]
    ink = default_ink if platform in {"youtube_shorts", "youtube"} else brand_ink if tone else default_ink
    canvas = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(canvas)
    margin = int(min(width, height) * .055)
    text_bounds = []
    product_bounds = None

    def text(value, box, size, color=ink, bold=False, align="left", max_lines=16, price_text=False):
        if not str(value or "").strip():
            return
        text_bounds.extend(_draw_text_in_box(draw, str(value), box, size, color, bold, align, max_lines, price_text))

    def fit(box):
        nonlocal product_bounds
        product_bounds = _fit_product(canvas, product, box)

    def button(box, size, color="#FFFFFF"):
        if not str(cta or "").strip():
            return
        x1, y1, x2, y2 = box
        draw.rounded_rectangle(box, radius=max(12, (y2-y1)//2), fill=accent)
        inset_x = max(12, int((x2-x1)*.08)); inset_y = max(5, int((y2-y1)*.12))
        text(cta, (x1+inset_x, y1+inset_y, x2-inset_x, y2-inset_y), size, color, True, "center", 2)

    # Instagram Feed: asymmetrical editorial split, product large at left and
    # the full campaign message in a distinct right-hand column.
    if platform == "instagram":
        draw.rounded_rectangle((margin, margin, width-margin, height-margin), radius=34, fill="#FFFFFF", outline="#E8DCD6", width=3)
        draw.ellipse((int(width*.02), int(height*.28), int(width*.61), int(height*.80)), fill=wash)
        draw.rounded_rectangle((int(width*.555), int(height*.10), int(width*.565), int(height*.90)), radius=5, fill=accent)
        fit((int(width*.055), int(height*.20), int(width*.535), int(height*.84)))
        text(product_name, (int(width*.60), int(height*.13), int(width*.93), int(height*.39)), 48, ink, True, max_lines=5)
        text(usp, (int(width*.60), int(height*.43), int(width*.93), int(height*.62)), 29, "#4D5852", max_lines=6)
        if price:
            text(price, (int(width*.60), int(height*.67), int(width*.93), int(height*.75)), 38, ink, True, max_lines=2, price_text=True)
        button((int(width*.60), int(height*.80), int(width*.93), int(height*.90)), 27)

    # Instagram Story: title band, centered product stage and stacked CTA zone.
    elif platform == "instagram_story":
        draw.rounded_rectangle((margin, margin, width-margin, height-margin), radius=46, fill="#FFFFFF", outline="#F0DAD9", width=3)
        draw.rounded_rectangle((margin, margin, width-margin, int(height*.235)), radius=46, fill=accent)
        draw.rectangle((margin, int(height*.17), width-margin, int(height*.235)), fill=accent)
        draw.ellipse((int(width*.19), int(height*.25), int(width*.81), int(height*.62)), fill=wash)
        text(product_name, (int(width*.09), int(height*.075), int(width*.91), int(height*.215)), 59, "#FFFFFF", True, "center", 3)
        fit((int(width*.15), int(height*.27), int(width*.85), int(height*.64)))
        text(usp, (int(width*.10), int(height*.665), int(width*.90), int(height*.755)), 27, "#45534B", False, "center", 4)
        if price:
            text(price, (int(width*.10), int(height*.765), int(width*.90), int(height*.825)), 40, ink, True, "center", 2, True)
        button((int(width*.12), int(height*.85), int(width*.88), int(height*.925)), 30)

    # YouTube Short: bold red headline strip, raised product card, dark footer.
    elif platform == "youtube_shorts":
        draw.rectangle((0, 0, width, int(height*.23)), fill=accent)
        draw.rounded_rectangle((int(width*.08), int(height*.255), int(width*.92), int(height*.68)), radius=40, fill="#FFFFFF")
        draw.rectangle((int(width*.08), int(height*.70), int(width*.92), int(height*.965)), fill="#20252B")
        text(product_name, (int(width*.09), int(height*.055), int(width*.91), int(height*.205)), 56, "#FFFFFF", True, "center", 3)
        fit((int(width*.20), int(height*.275), int(width*.80), int(height*.665)))
        text(usp, (int(width*.11), int(height*.715), int(width*.89), int(height*.79)), 25, "#FFFFFF", False, "center", 3)
        if price:
            text(price, (int(width*.10), int(height*.795), int(width*.90), int(height*.845)), 38, "#FFFFFF", True, "center", 2, True)
        button((int(width*.13), int(height*.865), int(width*.87), int(height*.935)), 28)

    # YouTube Thumbnail: high-contrast headline panel opposite the product.
    elif platform == "youtube":
        draw.polygon([(0, 0), (int(width*.55), 0), (int(width*.42), height), (0, height)], fill="#222D37")
        draw.rounded_rectangle((int(width*.52), int(height*.10), int(width*.96), int(height*.90)), radius=28, fill="#FFFFFF")
        draw.rounded_rectangle((int(width*.045), int(height*.105), int(width*.49), int(height*.895)), radius=24, outline=accent, width=8)
        text(product_name, (int(width*.075), int(height*.15), int(width*.455), int(height*.43)), 50, "#FFFFFF", True, max_lines=4)
        text(usp, (int(width*.075), int(height*.47), int(width*.45), int(height*.64)), 27, "#E8EDF1", False, max_lines=4)
        if price:
            text(price, (int(width*.075), int(height*.67), int(width*.45), int(height*.76)), 37, "#FFFFFF", True, max_lines=2, price_text=True)
        button((int(width*.075), int(height*.79), int(width*.45), int(height*.89)), 24)
        fit((int(width*.55), int(height*.14), int(width*.93), int(height*.86)))

    # Facebook Post: centered product card followed by a full-width copy footer.
    elif platform == "facebook":
        draw.rounded_rectangle((margin, margin, width-margin, height-margin), radius=40, fill="#FFFFFF", outline="#D8E1EF", width=3)
        draw.ellipse((int(width*.18), int(height*.11), int(width*.82), int(height*.62)), fill=wash)
        text(product_name, (int(width*.08), int(height*.065), int(width*.92), int(height*.17)), 42, ink, True, "center", 2)
        fit((int(width*.22), int(height*.19), int(width*.78), int(height*.62)))
        text(usp, (int(width*.08), int(height*.655), int(width*.92), int(height*.77)), 27, "#4D5852", False, "center", 3)
        if price:
            text(price, (int(width*.08), int(height*.80), int(width*.45), int(height*.90)), 34, ink, True, max_lines=2, price_text=True)
        button((int(width*.53), int(height*.80), int(width*.92), int(height*.90)), 24)

    # X Post: product sits left, concise message uses a clean high-contrast
    # right panel with a short horizontal action button.
    elif platform == "x":
        draw.rounded_rectangle((margin, margin, width-margin, height-margin), radius=32, fill="#FFFFFF", outline="#D9E0E2", width=3)
        draw.ellipse((int(width*.015), int(height*.12), int(width*.48), int(height*.88)), fill=wash)
        draw.rounded_rectangle((int(width*.45), int(height*.105), int(width*.455), int(height*.895)), radius=3, fill=accent)
        fit((int(width*.06), int(height*.15), int(width*.43), int(height*.85)))
        text(product_name, (int(width*.51), int(height*.15), int(width*.94), int(height*.39)), 52, ink, True, max_lines=4)
        text(usp, (int(width*.51), int(height*.45), int(width*.94), int(height*.63)), 29, "#45515A", False, max_lines=4)
        if price:
            text(price, (int(width*.51), int(height*.67), int(width*.94), int(height*.75)), 38, ink, True, max_lines=2, price_text=True)
        button((int(width*.51), int(height*.80), int(width*.83), int(height*.90)), 26)

    # WhatsApp Message: chat-card layout with product on one side and a compact
    # conversational message/price/action stack on the other.
    elif platform == "whatsapp":
        draw.rounded_rectangle((margin, margin, width-margin, height-margin), radius=42, fill="#FFFFFF", outline="#D5E8D9", width=4)
        draw.rounded_rectangle((int(width*.04), int(height*.10), int(width*.49), int(height*.90)), radius=28, fill="#E5F1E6")
        draw.rounded_rectangle((int(width*.54), int(height*.14), int(width*.95), int(height*.86)), radius=28, fill="#F7FAF6")
        fit((int(width*.075), int(height*.18), int(width*.455), int(height*.82)))
        text(product_name, (int(width*.58), int(height*.19), int(width*.91), int(height*.38)), 40, ink, True, max_lines=4)
        text(usp, (int(width*.58), int(height*.42), int(width*.91), int(height*.64)), 24, "#4D5852", False, max_lines=5)
        if price:
            text(price, (int(width*.58), int(height*.67), int(width*.91), int(height*.755)), 34, ink, True, max_lines=2, price_text=True)
        button((int(width*.58), int(height*.78), int(width*.91), int(height*.875)), 22)

    # WhatsApp Status: green story frame with an offset product stage and a
    # broad bottom call-to-action safe area.
    elif platform == "whatsapp_status":
        draw.rounded_rectangle((margin, margin, width-margin, height-margin), radius=44, fill="#FFFFFF", outline="#CFE5D6", width=4)
        draw.rounded_rectangle((margin, margin, width-margin, int(height*.22)), radius=44, fill="#DDF0E3")
        draw.rectangle((margin, int(height*.16), width-margin, int(height*.22)), fill="#DDF0E3")
        draw.ellipse((int(width*.16), int(height*.24), int(width*.84), int(height*.63)), fill=wash)
        text(product_name, (int(width*.09), int(height*.065), int(width*.91), int(height*.19)), 52, ink, True, "center", 3)
        fit((int(width*.20), int(height*.26), int(width*.80), int(height*.63)))
        text(usp, (int(width*.10), int(height*.65), int(width*.90), int(height*.755)), 26, "#45534B", False, "center", 4)
        if price:
            text(price, (int(width*.10), int(height*.765), int(width*.90), int(height*.825)), 40, ink, True, "center", 2, True)
        button((int(width*.10), int(height*.85), int(width*.90), int(height*.925)), 29)

    # Validate safe placement and disjoint copy/product zones before encoding.
    if product_bounds is None:
        raise HTTPException(status_code=500, detail="Product image was not placed on the canvas.")
    px1, py1, px2, py2 = product_bounds
    if px1 < margin or py1 < margin or px2 > width-margin or py2 > height-margin:
        raise HTTPException(status_code=500, detail="Product image exceeded the platform safe area.")
    for x1, y1, x2, y2 in text_bounds:
        if x1 < margin or y1 < margin or x2 > width-margin or y2 > height-margin:
            raise HTTPException(status_code=500, detail="Text exceeded the platform safe area.")
        if x1 < px2 and x2 > px1 and y1 < py2 and y2 > py1:
            raise HTTPException(status_code=500, detail="Text layout overlaps the product image.")

    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    data = output.getvalue()
    try:
        with Image.open(io.BytesIO(data)) as check:
            if check.format != "PNG" or check.size != (width, height):
                raise ValueError("Generated file is not a correctly sized PNG.")
            check.verify()
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Generated image validation failed: {error}")
    return data

async def _openrouter_image(image_bytes, image_content_type, product_name, description, platform, price, usp, cta, brand_tone):
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="Optional OpenRouter image provider is selected but its server-side key is not configured.")
    width, height = PLATFORM_SPECS[platform]
    prompt = f"Create a polished marketing composition using this exact reference product image; do not crop, stretch, redraw, or invent product details. Product name: {product_name}. Exact price: {price}. Given USP: {usp}. CTA: {cta}. Tone: {brand_tone}. Canvas {width}x{height}."
    data_url = f"data:{image_content_type or 'image/jpeg'};base64,{base64.b64encode(image_bytes).decode()}"
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(OPENROUTER_IMAGE_URL, headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json", "X-Title": "LaunchFlow AI"}, json={"model": OPENROUTER_IMAGE_MODEL, "prompt": prompt, "aspect_ratio": f"{width}:{height}", "n": 1, "input_references": [{"type": "image_url", "image_url": {"url": data_url}}]})
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Could not connect to the optional image provider.")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Optional image provider returned HTTP {response.status_code}.")
    try:
        return base64.b64decode(response.json()["data"][0]["b64_json"], validate=True)
    except Exception:
        raise HTTPException(status_code=502, detail="Optional image provider returned no valid image.")


async def generate_platform_image(image_bytes: bytes, image_content_type: str, product_name: str, description: str, platform: str, price="", usp="", cta="", brand_tone="") -> str:
    if platform not in PLATFORM_SPECS:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")
    if VISUAL_PROVIDER == "local":
        image = compose_marketing_visual(image_bytes, product_name, platform, description, price, usp, cta, brand_tone)
    elif VISUAL_PROVIDER == "openrouter":
        raw = await _openrouter_image(image_bytes, image_content_type, product_name, description, platform, price, usp, cta, brand_tone)
        try:
            with Image.open(io.BytesIO(raw)) as source:
                # Enforce the requested output canvas even for optional adapters.
                canvas = Image.new("RGB", PLATFORM_SPECS[platform], "white")
                image = ImageOps.contain(source.convert("RGB"), canvas.size, Image.Resampling.LANCZOS)
                canvas.paste(image, ((canvas.width-image.width)//2, (canvas.height-image.height)//2))
                output = io.BytesIO(); canvas.save(output, format="PNG", optimize=True); image = output.getvalue()
        except Exception:
            raise HTTPException(status_code=502, detail="Optional image provider did not return a readable image.")
    else:
        raise HTTPException(status_code=500, detail="VISUAL_PROVIDER must be 'local' or 'openrouter'.")
    return save_media(image, f"{platform}_{uuid.uuid4().hex}.png", "image/png")
