import base64
import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from services.campaign_brain import call_campaign_brain
from services.image_generator import PLATFORM_SPECS, generate_platform_image
from services.media_storage import MEDIA_DIR as UPLOAD_DIR, save_media


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
APP_ROOT = Path(__file__).resolve().parent
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# React Vite development server handles the frontend.
FRONTEND_DIR = APP_ROOT.parent / "frontend-react"
FRONTEND_DIST = FRONTEND_DIR / "dist"


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="LaunchFlow AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://launchflow-cygwin5pt-kaviya-raji-s-projects.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PLATFORMS = [
    "instagram",
    "youtube",
    "facebook",
    "x",
    "whatsapp",
]


def clean_json_text(raw: str) -> str:
    raw = raw.strip()

    raw = re.sub(
        r"^```(?:json)?",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()

    raw = re.sub(
        r"```$",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()

    return raw


def limit_x_text(value: str) -> str:
    """Keep generated X copy within its hard platform limit without splitting a word."""
    text = str(value or "")
    if len(text) <= 280:
        return text
    shortened = text[:277].rsplit(" ", 1)[0].rstrip()
    return f"{shortened}…" if shortened else text[:280]


def get_chat_headers():
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "LaunchFlow AI",
    }


def ensure_api_key():
    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY is not set.",
        )


def normalize_campaign(campaign: dict) -> dict:
    """
    Ensures LaunchFlow's final campaign structure matches the product
    requirements.

    Instagram:
        Post + Reel + Story

    YouTube:
        Short + Thumbnail

    Facebook:
        Post

    X:
        Post

    WhatsApp:
        Message + Status

    Video scripts are intentionally NOT included automatically.
    They are generated only by /api/generate-video-script.
    """

    if not isinstance(campaign, dict):
        raise HTTPException(status_code=502, detail="Campaign Brain returned a non-object campaign.")
    platforms = campaign.get("platforms")
    if not isinstance(platforms, dict):
        platforms = {}
        campaign["platforms"] = platforms

    def object_at(parent, key):
        if not isinstance(parent.get(key), dict):
            parent[key] = {}
        return parent[key]

    object_at(campaign, "campaign_brain")
    instagram = object_at(platforms, "instagram")
    object_at(instagram, "post")
    object_at(instagram, "reel")
    object_at(instagram, "story")

    youtube = object_at(platforms, "youtube")
    object_at(youtube, "short")
    object_at(youtube, "thumbnail")

    # Remove unwanted long-form YouTube section.
    youtube.pop("video", None)

    facebook = object_at(platforms, "facebook")
    object_at(facebook, "post")

    x = object_at(platforms, "x")
    x_post = object_at(x, "post")
    if isinstance(x_post.get("text"), str):
        x_post["text"] = limit_x_text(x_post["text"])

    whatsapp = object_at(platforms, "whatsapp")
    object_at(whatsapp, "message")
    object_at(whatsapp, "status")

    # Never show generated scripts automatically.
    for platform_name in PLATFORMS:
        platform = platforms.get(platform_name)

        if not isinstance(platform, dict):
            continue

        for key in list(platform.keys()):
            if key in {
                "generated_video",
                "video_script",
                "script_idea",
            }:
                platform.pop(key, None)

        if platform_name == "instagram":
            object_at(platform, "reel").pop("script", None)

        if platform_name == "youtube":
            object_at(platform, "short").pop("script", None)

    return campaign


def run_quality_checks(brief: dict, campaign: dict) -> dict:
    checks = []
    platforms = campaign.get("platforms") or {}
    required = {
        "instagram": {"post": ("caption", "cta"), "reel": ("hook", "caption", "cta"), "story": ("frame_1", "frame_2", "frame_3", "cta")},
        "youtube": {"short": ("hook", "caption", "cta"), "thumbnail": ("text", "visual_concept")},
        "facebook": {"post": ("caption", "cta")},
        "x": {"post": ("text", "cta")},
        "whatsapp": {"message": ("text", "cta"), "status": ("frame_1", "frame_2", "frame_3", "cta")},
    }

    def collect(value):
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [part for child in value.values() for part in collect(child)]
        if isinstance(value, list):
            return [part for child in value for part in collect(child)]
        return []

    all_text = " ".join(collect(platforms)).strip()
    checks.append({"check": "campaign_content_present", "passed": bool(all_text), "severity": "error", "detail": "Campaign has generated text." if all_text else "Campaign has no usable text."})

    for platform, sections in required.items():
        data = platforms.get(platform) or {}
        for section, fields in sections.items():
            item = data.get(section) if isinstance(data, dict) else None
            for field in fields:
                value = item.get(field) if isinstance(item, dict) else None
                valid = isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in {"null", "none", "undefined"}
                checks.append({"check": "required_content", "platform": platform, "field": f"{section}.{field}", "passed": valid, "severity": "error", "detail": f"{platform} {section}.{field} is present." if valid else f"{platform} {section}.{field} is missing or empty."})
        if platform == "instagram":
            hashtags = data.get("post", {}).get("hashtags") if isinstance(data.get("post"), dict) else None
            valid_hashtags = isinstance(hashtags, list) and any(isinstance(tag, str) and tag.strip() for tag in hashtags)
            checks.append({"check": "required_content", "platform": platform, "field": "post.hashtags", "passed": valid_hashtags, "severity": "error", "detail": "Instagram hashtags are present." if valid_hashtags else "Instagram hashtags are missing."})

    brain = campaign.get("campaign_brain") or {}
    for field in ("product_identity", "audience", "usp", "brand_voice", "core_message", "cta"):
        value = brain.get(field) if isinstance(brain, dict) else None
        valid = isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in {"null", "none", "undefined"}
        checks.append({"check": "campaign_brain_field", "field": field, "passed": valid, "severity": "error", "detail": f"Campaign Brain {field.replace('_', ' ')} is present." if valid else f"Campaign Brain {field.replace('_', ' ')} is missing or empty."})

    for required_field in ("product_name", "price", "usp", "audience", "brand_tone"):
        value = str(brief.get(required_field) or "").strip()
        if not value:
            checks.append({"check": "brief_field_present", "field": required_field, "passed": False, "severity": "error", "detail": f"{required_field.replace('_', ' ').title()} is missing from the brief."})

    product_name = str(brief.get("product_name") or "").strip()
    price = str(brief.get("price") or "").strip()
    usp = str(brief.get("usp") or "").strip()
    audience = str(brief.get("audience") or "").strip()
    tone = str(brief.get("brand_tone") or "").strip()
    content_text = {name: " ".join(collect(data)).casefold() for name, data in platforms.items()}

    for name, text in content_text.items():
        if product_name:
            checks.append({"check": "product_name", "platform": name, "passed": product_name.casefold() in text, "severity": "error", "detail": f"Product name {'found' if product_name.casefold() in text else 'not found'} in {name} content."})
        if price:
            checks.append({"check": "price_accuracy", "platform": name, "passed": price.casefold() in text, "severity": "error", "detail": f"Price {'found' if price.casefold() in text else 'not found'} in {name} content."})
        if usp:
            usp_terms = [term.casefold() for term in re.findall(r"[\w%]+", usp) if len(term) > 2]
            usp_found = bool(usp_terms) and sum(term in text for term in usp_terms) >= max(1, (len(usp_terms) + 1) // 2)
            checks.append({"check": "usp_preserved", "platform": name, "passed": usp_found, "severity": "error", "detail": "Main USP is reflected." if usp_found else "Could not find enough of the main USP in this platform's content."})
        if audience:
            audience_terms = [term.casefold() for term in re.findall(r"[\w]+", audience) if len(term) > 2]
            audience_found = any(term in text for term in audience_terms)
            checks.append({"check": "audience_match", "platform": name, "passed": audience_found, "severity": "warning", "detail": "Target audience appears in the content." if audience_found else "Target audience is not explicitly reflected; review suitability."})
        if tone:
            tone_cues = {
                "friendly": ("hey", "you", "your", "love", "warm", "welcome", "enjoy", "perfect", "let's"),
                "professional": ("professional", "reliable", "designed", "quality", "efficient", "crafted", "ideal", "delivers"),
                "playful": ("playful", "fun", "exciting", "delight", "adventure", "spark", "✨", "🎉", "😉"),
                "premium": ("premium", "elevate", "elegant", "refined", "luxury", "exclusive", "signature", "indulgent"),
                "warm": ("warm", "welcome", "cozy", "comfort", "care", "heart", "love", "made for you"),
            }
            cues = tone_cues.get(tone.casefold(), (tone.casefold(),))
            tone_found = any(cue in text for cue in cues)
            checks.append({"check": "brand_tone", "platform": name, "passed": tone_found, "severity": "warning", "detail": f"Copy contains cues associated with the {tone} tone." if tone_found else f"Confirm the content reflects the selected {tone} tone."})

    x_post = ((platforms.get("x") or {}).get("post") or {}).get("text") or ""
    checks.append({"check": "platform_length_limit", "platform": "x", "passed": isinstance(x_post, str) and len(x_post) <= 280, "severity": "error", "detail": f"X post is {len(x_post)} characters; limit is 280."})
    primary_texts = {
        "instagram": ((platforms.get("instagram") or {}).get("post") or {}).get("caption"),
        "youtube": ((platforms.get("youtube") or {}).get("short") or {}).get("caption"),
        "facebook": ((platforms.get("facebook") or {}).get("post") or {}).get("caption"),
        "x": ((platforms.get("x") or {}).get("post") or {}).get("text"),
        "whatsapp": ((platforms.get("whatsapp") or {}).get("message") or {}).get("text"),
    }
    normalized_primary = [re.sub(r"\s+", " ", text.strip()).casefold() for text in primary_texts.values() if isinstance(text, str) and text.strip()]
    adapted = len(normalized_primary) == len(primary_texts) and len(set(normalized_primary)) == len(normalized_primary)
    checks.append({"check": "platform_adaptation", "passed": adapted, "severity": "error", "detail": "Each platform has distinct primary copy." if adapted else "Primary copy is missing or duplicated between platforms."})
    checks.append({"check": "broken_content", "passed": not re.search(r"\b(?:undefined|null|nan)\b", all_text, re.I), "severity": "error", "detail": "No obvious null or broken placeholders found." if not re.search(r"\b(?:undefined|null|nan)\b", all_text, re.I) else "Campaign contains an obvious null or broken placeholder."})

    errors = [c for c in checks if c["severity"] == "error" and not c["passed"]]
    passed = sum(bool(c["passed"]) for c in checks)
    warnings = sum(c["severity"] == "warning" and not c["passed"] for c in checks)
    return {"checks": checks, "summary": f"{passed}/{len(checks)} checks passed; {len(errors)} blocking issue(s), {warnings} warning(s).", "all_passed": passed == len(checks), "blocking_passed": not errors, "completed": True}


@app.post("/api/quality-check")
async def quality_check(payload: dict = Body(...)):
    brief = payload.get("brief")
    campaign = payload.get("campaign")
    if not isinstance(brief, dict) or not isinstance(campaign, dict):
        raise HTTPException(status_code=400, detail="brief and campaign must be JSON objects.")
    return {"ok": True, "quality": run_quality_checks(brief, campaign)}


async def call_openrouter_copy(prompt: str, temperature: float = 0.8):
    ensure_api_key()

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a professional marketing copywriter "
                    "inside LaunchFlow AI. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers=get_chat_headers(),
                json=payload,
            )
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail=f"OpenRouter copy request timed out: {error}")
    except httpx.RequestError as error:
        raise HTTPException(status_code=502, detail=f"Could not connect to OpenRouter: {error}")

    if response.status_code != 200:
        try:
            provider_error = response.json()
        except Exception:
            provider_error = response.text

        print("OPENROUTER ERROR:", response.status_code, provider_error)

        raise HTTPException(
            status_code=502,
            detail=f"Campaign text provider returned HTTP {response.status_code}: {provider_error}",
        )

    try:
        raw = response.json()["choices"][0]["message"]["content"]
        return json.loads(clean_json_text(raw))
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not parse AI response: {error}",
        )


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------

@app.post("/api/generate-campaign")
async def generate_campaign(
    product_name: str = Form(...),
    description: str = Form(...),
    price: str = Form(""),
    audience: str = Form(...),
    usp: str = Form(...),
    brand_tone: str = Form("friendly"),
    language: str = Form("English"),
    image: Optional[UploadFile] = File(None),
):
    trace = []

    def step(
        name: str,
        status: str,
        detail: str = "",
    ):
        trace.append(
            {
                "step": name,
                "status": status,
                "detail": detail,
                "ts": time.time(),
            }
        )

    step(
        "campaign_started",
        "ok",
        "Received product brief.",
    )

    brief = {
        "product_name": product_name,
        "description": description,
        "price": price,
        "audience": audience,
        "usp": usp,
        "brand_tone": brand_tone,
        "language": language,
    }

    image_url = None
    image_bytes = None
    image_content_type = None

    if image is not None and image.filename:
        allowed_types = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }
        image_content_type = (image.content_type or "").lower()
        if image_content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Upload a JPG, PNG, or WEBP product image.")
        image_bytes = await image.read(10 * 1024 * 1024 + 1)
        if len(image_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Product images must be 10 MB or smaller.")
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Product image is empty.")

        filename = (
            f"{uuid.uuid4().hex}{allowed_types[image_content_type]}"
        )

        image_url = save_media(image_bytes, filename, image_content_type)

        step(
            "product_image_received",
            "ok",
            f"Saved as {filename}.",
        )
    else:
        step(
            "product_image_received",
            "skipped",
            "No product image uploaded.",
        )

    step(
        "product_understood",
        "pending",
        "Sending brief to Campaign Brain.",
    )

    try:
        campaign = await call_campaign_brain(
            brief
        )

        campaign = normalize_campaign(
            campaign
        )

    except HTTPException as error:
        step(
            "campaign_strategy_created",
            "failed",
            str(error.detail),
        )

        return {
            "ok": False,
            "trace": trace,
            "error": str(error.detail),
        }

    step(
        "product_understood",
        "ok",
        "Campaign Brain extracted product, audience, USP and voice.",
    )

    step(
        "campaign_strategy_created",
        "ok",
        "Core campaign message and CTA created.",
    )

    step(
        "platform_content_generated",
        "ok",
        "Platform-specific content generated.",
    )

    platform_image_urls = {}
    platform_image_errors = {}
    platform_image_variants = {}
    platform_image_variant_errors = {}

    if image_bytes:
        step(
            "platform_images_started",
            "pending",
            "Creating exact-size platform assets and story/status variants.",
        )

        semaphore = asyncio.Semaphore(2)

        image_targets = list(PLATFORMS) + ["instagram_story", "youtube_shorts", "whatsapp_status"]

        async def generate_one_platform_image(asset_key):
            try:
                async with semaphore:
                    platform_name = asset_key.split("_", 1)[0] if asset_key in {"instagram_story", "youtube_shorts", "whatsapp_status"} else asset_key
                    platform_data = (campaign.get("platforms") or {}).get(platform_name) or {}
                    copy_item = platform_data.get("post") or platform_data.get("short") or platform_data.get("message") or {}
                    url = await generate_platform_image(
                        image_bytes=image_bytes,
                        image_content_type=image_content_type,
                        product_name=product_name,
                        description=description,
                        platform=asset_key,
                        price=price,
                        usp=usp,
                        cta=str(copy_item.get("cta") or ""),
                        brand_tone=brand_tone,
                    )
                return asset_key, url, None
            except HTTPException as error:
                return asset_key, None, str(error.detail)
            except Exception as error:
                return asset_key, None, f"Image generation failed: {error}"

        image_results = await asyncio.gather(
            *(generate_one_platform_image(name) for name in image_targets)
        )
        for asset_key, image_result, image_error in image_results:
            target_urls = platform_image_urls if asset_key in PLATFORMS else platform_image_variants
            target_errors = platform_image_errors if asset_key in PLATFORMS else platform_image_variant_errors
            if image_result:
                target_urls[asset_key] = image_result
                step(f"{asset_key}_image_generated", "ok", f"Generated exact-size {asset_key} visual.")
            else:
                target_errors[asset_key] = image_error or "Image generation failed."
                step(f"{asset_key}_image_generated", "failed", target_errors[asset_key])

        step(
            "platform_images_completed",
            "ok",
            (
                f"{len(platform_image_urls) + len(platform_image_variants)}/{len(image_targets)} "
                "platform assets generated."
            ),
        )

    quality = run_quality_checks(
        brief,
        campaign,
    )

    step(
        "quality_checks_completed",
        "ok" if quality["all_passed"] else "flagged",
        quality["summary"],
    )

    step(
        "human_approval_required",
        "pending",
        "Review the generated campaign before approval.",
    )

    return {
        "ok": True,
        "brief": brief,
        "image_url": image_url,
        "platform_images": platform_image_urls,
        "platform_image_errors": platform_image_errors,
        "platform_image_variants": platform_image_variants,
        "platform_image_variant_errors": platform_image_variant_errors,
        "campaign": campaign,
        "quality": quality,
        "trace": trace,
    }


# ---------------------------------------------------------------------------
# Regenerate caption
# ---------------------------------------------------------------------------

@app.post("/api/regenerate-caption")
async def regenerate_caption(
    platform: str = Form(...),
    content_type: str = Form(...),
    product_name: str = Form(...),
    description: str = Form(...),
    price: str = Form(""),
    audience: str = Form(...),
    usp: str = Form(...),
    brand_tone: str = Form("friendly"),
    language: str = Form("English"),
):
    prompt = f"""
Generate ONE new replacement marketing copy item.

Platform:
{platform}

Content type:
{content_type}

Product:
{product_name}

Description:
{description}

Price:
{price}

Audience:
{audience}

USP:
{usp}

Tone:
{brand_tone}

Language:
{language}

Rules:
- Preserve exact product name.
- Preserve exact price if provided.
- Do not invent facts.
- Make it different from previous wording.
- Make it native to the platform.
- Keep it concise.
- For X, keep the main text under 280 characters.

Return ONLY:

{{
  "text": "",
  "cta": "",
  "hashtags": []
}}
"""

    result = await call_openrouter_copy(
        prompt,
        temperature=0.9,
    )

    if platform == "x" and isinstance(result, dict) and isinstance(result.get("text"), str):
        result["text"] = limit_x_text(result["text"])

    return {
        "ok": True,
        "platform": platform,
        "content_type": content_type,
        "content": result,
    }


# ---------------------------------------------------------------------------
# Generate Video Script Idea
# ---------------------------------------------------------------------------

@app.post("/api/generate-video-script")
async def generate_video_script(
    platform: str = Form(...),
    product_name: str = Form(...),
    description: str = Form(...),
    audience: str = Form(...),
    usp: str = Form(...),
    brand_tone: str = Form("friendly"),
    language: str = Form("English"),
):
    if platform not in {"instagram", "youtube"}:
        raise HTTPException(
            status_code=400,
            detail="Script generation is available for Instagram and YouTube.",
        )

    prompt = f"""
Create a platform-specific short-form video SCRIPT for a marketing campaign.

This is only a script/creative idea.
DO NOT generate an actual video.

Platform:
{platform}

Product:
{product_name}

Description:
{description}

Target audience:
{audience}

USP:
{usp}

Brand tone:
{brand_tone}

Language:
{language}

Platform rules:

Instagram:
Create an Instagram Reel idea that works with a short vertical video.

YouTube:
Create a YouTube Short idea that works with a short vertical video.

Facebook:
Create a video content idea suitable for Facebook, even though LaunchFlow
does not automatically generate the Facebook video.

X:
Create a short video content idea suitable for X, even though LaunchFlow
does not automatically generate the X video.

WhatsApp:
Create a short Status/video content idea suitable for WhatsApp.

Do not invent product features.
Keep the product central.
Make the idea practical for a small business.

Return ONLY JSON:

{{
  "title": "",
  "hook": "",
  "idea": "",
  "scenes": [
    {{
      "scene": 1,
      "visual": "",
      "spoken_or_text": ""
    }}
  ],
  "cta": ""
}}
"""

    result = await call_openrouter_copy(
        prompt,
        temperature=0.8,
    )

    return {
        "ok": True,
        "platform": platform,
        "script": result,
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"ok": True}


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

app.mount(
    "/uploads",
    StaticFiles(
        directory=str(UPLOAD_DIR)
    ),
    name="uploads",
)

# Only serve built React files if they exist.
if FRONTEND_DIST.exists():
    app.mount(
        "/",
        StaticFiles(
            directory=str(FRONTEND_DIST),
            html=True,
        ),
        name="frontend",
    )
