"""
Campaign Brain for LaunchFlow AI.

Generates a coordinated marketing campaign locally from the product brief.
No external AI provider or API credits are required.
"""

import re

from fastapi import HTTPException


def _text(value) -> str:
    return str(value or "").strip()


def _clean_sentence(value: str) -> str:
    value = _text(value)
    if not value:
        return ""
    return value.rstrip(".!? ") + "."


def _hashtags(product_name: str, usp: str) -> list[str]:
    tags = ["#LaunchFlowAI"]

    for value in (product_name, usp):
        for word in re.findall(r"[A-Za-z0-9]+", value):
            if len(word) > 3:
                tag = "#" + word
                if tag.lower() not in {item.lower() for item in tags}:
                    tags.append(tag)

    return tags[:6]


def _tone_content(tone: str, product_name: str, usp: str, audience: str):
    tone = tone.casefold()

    if "premium" in tone:
        return {
            "opening": f"Elevate the everyday with {product_name}.",
            "support": f"Thoughtfully positioned for {audience}, with a focus on {usp}.",
            "closing": "A refined choice for those who value more from every experience.",
            "cta": "Explore more",
        }

    if "professional" in tone:
        return {
            "opening": f"Meet {product_name} — a practical choice for modern needs.",
            "support": f"Designed around {usp}, with {audience} in mind.",
            "closing": "Simple, focused and easy to consider.",
            "cta": "Learn more",
        }

    if "playful" in tone:
        return {
            "opening": f"Say hello to {product_name}. ✨",
            "support": f"{usp} — because everyday choices can be a little more fun.",
            "closing": f"Made with {audience} in mind. Ready to make it yours?",
            "cta": "Give it a try",
        }

    if "warm" in tone:
        return {
            "opening": f"Meet {product_name} — something made to feel just right.",
            "support": f"With {usp}, it brings a simple touch of value to everyday moments.",
            "closing": f"A thoughtful choice for {audience}.",
            "cta": "Discover more",
        }

    if "bold" in tone:
        return {
            "opening": f"Meet {product_name}. Make the choice that stands out.",
            "support": f"Built around one clear idea: {usp}.",
            "closing": f"For {audience} who want something that gets noticed.",
            "cta": "Make it yours",
        }

    # Friendly default
    return {
        "opening": f"Meet {product_name}. ✨",
        "support": f"{usp} — a simple reason to make it part of your day.",
        "closing": f"Made with {audience} in mind.",
        "cta": "Discover more",
    }



def _platform_ctas(tone: str) -> dict[str, str]:
    tone = tone.casefold()
    if "premium" in tone:
        return {
            "instagram": "Explore the collection", "reel": "See the details", "story": "View the edit",
            "youtube": "Watch the full overview", "facebook": "Discover the collection",
            "x": "Explore further", "whatsapp": "Message us for details", "status": "View the collection",
        }
    if "professional" in tone:
        return {
            "instagram": "View the key details", "reel": "See the process", "story": "Review the highlights",
            "youtube": "Get the full overview", "facebook": "Request more information",
            "x": "Read the summary", "whatsapp": "Contact us for details", "status": "See the information",
        }
    if "playful" in tone:
        return {
            "instagram": "Save a spot in your day", "reel": "Watch the fun unfold", "story": "Tap for a closer look",
            "youtube": "Catch the quick tour", "facebook": "Join the conversation",
            "x": "Take a peek", "whatsapp": "Say hi to learn more", "status": "Take a quick peek",
        }
    if "warm" in tone:
        return {
            "instagram": "Find your new favorite", "reel": "Take a closer look", "story": "Discover the little details",
            "youtube": "Get to know it", "facebook": "Share what you think",
            "x": "Learn a little more", "whatsapp": "Reach out any time", "status": "Find out more",
        }
    if "bold" in tone:
        return {
            "instagram": "Make your move", "reel": "See it in action", "story": "Choose your next step",
            "youtube": "Get the full story", "facebook": "Make your choice heard",
            "x": "Make it happen", "whatsapp": "Talk to us today", "status": "Step in and explore",
        }
    return {
        "instagram": "Take a closer look", "reel": "See what makes it different", "story": "Explore the details",
        "youtube": "Watch the quick tour", "facebook": "Tell us what you think",
        "x": "Find out more", "whatsapp": "Send us a message", "status": "See more here",
    }

def build_campaign(brief: dict) -> dict:
    product_name = _text(brief.get("product_name"))
    description = _text(brief.get("description"))
    price = _text(brief.get("price"))
    audience = _text(brief.get("audience"))
    usp = _text(brief.get("usp"))
    brand_tone = _text(brief.get("brand_tone")) or "friendly"

    if not product_name:
        raise HTTPException(
            status_code=422,
            detail="Product name is required.",
        )

    if not usp or usp.casefold().rstrip(".!? ") == description.casefold().rstrip(".!? "):
        # Keep a long description as background context instead of copying it into every caption.
        usp = "a considered choice for everyday needs"

    if not audience:
        audience = "people looking for a practical choice"

    tone = _tone_content(
        brand_tone,
        product_name,
        usp,
        audience,
    )

    price_line = f"Available at {price}." if price else ""

    ctas = _platform_ctas(brand_tone)
    cta = ctas["instagram"]
    hashtags = _hashtags(product_name, usp)

    # ---------------------------------------------------------
    # INSTAGRAM
    # ---------------------------------------------------------

    instagram_caption = (
        f"{tone['opening']}\n\n"
        f"{tone['support']}\n\n"
        f"{tone['closing']}"
        f"{f' {price_line}' if price_line else ''}\n\n"
        f"{ctas['instagram']}."
    )

    instagram_reel = (
        f"{tone['opening']}\n\n"
        f"Here's the idea: {usp}.\n\n"
        f"Made with {audience} in mind."
        f"{f' {price_line}' if price_line else ''}\n\n"
        f"{ctas['reel']}."
    )

    instagram_reel_caption = (
        f"A closer look at {product_name}: {tone['closing']}"
        f"{f' {price_line}' if price_line else ''}"
    )

    instagram_story = {
        "frame_1": f"{product_name}.",
        "frame_2": f"{usp}.",
        "frame_3": (
            f"{tone['closing']}"
            f"{f' {price_line}' if price_line else ''}"
        ),
        "cta": ctas["story"],
    }

    # ---------------------------------------------------------
    # YOUTUBE
    # ---------------------------------------------------------

    youtube_script = (
        f"Looking for something that fits your needs?\n\n"
        f"Meet {product_name}.\n\n"
        f"The idea is simple: {usp}.\n\n"
        f"It's made with {audience} in mind."
        f"{f' {price_line}' if price_line else ''}\n\n"
        f"{ctas['youtube']}."
    )

    youtube_caption = (
        f"{tone['opening']} Quick take: {product_name} brings {usp.rstrip('.!?')} into focus."
        f"{f' {price_line}' if price_line else ''}"
    )

    # ---------------------------------------------------------
    # FACEBOOK
    # ---------------------------------------------------------

    facebook_caption = (
        f"Some choices are easier when the value is clear.\n\n"
        f"Meet {product_name}.\n\n"
        f"{tone['support']}\n\n"
        f"{tone['closing']}"
        f"{f' {price_line}' if price_line else ''}\n\n"
        f"{ctas['facebook']}."
    )

    # ---------------------------------------------------------
    # X
    # ---------------------------------------------------------

    x_text = (
        f"Worth a look: {product_name}. {tone['closing']}"
    )

    if price:
        x_text += f" {price_line}"

    if len(x_text) > 279:
        x_text = f"{product_name}: {usp}."
        if price:
            x_text += f" {price_line}"

    x_text = x_text[:279].rstrip()

    # ---------------------------------------------------------
    # WHATSAPP
    # ---------------------------------------------------------

    whatsapp_message = (
        f"Hi! 👋\n\n"
        f"Thought you might like {product_name}.\n\n"
        f"{usp}.\n\n"
        f"{tone['closing']}"
        f"{f' {price_line}' if price_line else ''}\n\n"
        f"{ctas['whatsapp']}."
    )

    whatsapp_status = {
        "frame_1": f"✨ {product_name}",
        "frame_2": f"{usp}.",
        "frame_3": (
            f"{tone['closing']}"
            f"{f' {price_line}' if price_line else ''}"
        ),
        "cta": ctas["status"],
    }

    return {
        "campaign_brain": {
            "product_identity": product_name,
            "audience": audience,
            "usp": usp,
            "brand_voice": brand_tone,
            "core_message": tone["opening"],
            "cta": cta,
        },

        "platforms": {
            "instagram": {
                "post": {
                    "caption": instagram_caption,
                    "hashtags": hashtags,
                    "cta": ctas["instagram"],
                },
                "reel": {
                    "hook": tone["opening"],
                    "script": instagram_reel,
                    "caption": instagram_reel_caption,
                    "cta": ctas["reel"],
                },
                "story": instagram_story,
            },

            "youtube": {
                "short": {
                    "hook": f"Why choose {product_name}?",
                    "script": youtube_script,
                    "caption": youtube_caption,
                    "cta": ctas["youtube"],
                },
                "thumbnail": {
                    "text": product_name,
                    "visual_concept": (
                        f"Clean product-focused visual featuring "
                        f"{product_name}, with emphasis on {usp}."
                    ),
                },
            },

            "facebook": {
                "post": {
                    "caption": facebook_caption,
                    "cta": ctas["facebook"],
                },
            },

            "x": {
                "post": {
                    "text": x_text,
                    "cta": ctas["x"],
                },
            },

            "whatsapp": {
                "message": {
                    "text": whatsapp_message,
                    "cta": ctas["whatsapp"],
                },
                "status": whatsapp_status,
            },
        },
    }


async def call_campaign_brain(brief: dict) -> dict:
    """
    Keep this function async because main.py already awaits it.
    """
    try:
        return build_campaign(brief)

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Campaign Brain failed: {error}",
        )