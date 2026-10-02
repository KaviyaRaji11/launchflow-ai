"""
Campaign Brain for LaunchFlow AI.

Uses the product brief directly to create a complete campaign structure.
No external AI provider is required, so the campaign generation endpoint
works reliably without OpenRouter credits or model availability issues.
"""

from fastapi import HTTPException


def _text(value) -> str:
    return str(value or "").strip()


def _hashtags(product_name: str, usp: str) -> list[str]:
    words = [
        word.strip(".,!?()[]{}:;\"'")
        for word in product_name.split()
    ]

    tags = ["#LaunchFlowAI"]

    for word in words:
        if word and word.isalnum() and len(word) > 2:
            tags.append("#" + word.replace(" ", ""))

    if usp:
        for word in usp.split():
            word = word.strip(".,!?()[]{}:;\"'")
            if word and word.isalnum() and len(word) > 4:
                tag = "#" + word
                if tag.lower() not in {x.lower() for x in tags}:
                    tags.append(tag)

    return tags[:6]


def build_campaign(brief: dict) -> dict:
    product_name = _text(brief.get("product_name"))
    description = _text(brief.get("description"))
    price = _text(brief.get("price"))
    audience = _text(brief.get("audience"))
    usp = _text(brief.get("usp"))
    brand_tone = _text(brief.get("brand_tone")) or "friendly"
    language = _text(brief.get("language")) or "English"

    if not product_name:
        raise HTTPException(
            status_code=422,
            detail="Product name is required.",
        )

    if not usp:
        usp = description

    if not usp:
        usp = "Discover what makes this product special."

    if not audience:
        audience = "people looking for a product that fits their needs"

    price_text = f" Available at {price}." if price else ""

    core_message = (
        f"Meet {product_name} — "
        f"{usp}"
    )

    cta = "Discover more"

    hashtags = _hashtags(product_name, usp)

    instagram_caption = (
        f"Meet {product_name} ✨\n\n"
        f"{usp}\n\n"
        f"Made for {audience}.{price_text}\n\n"
        f"{cta}."
    )

    instagram_reel_script = (
        f"Looking for something made for {audience}?\n"
        f"Meet {product_name}.\n"
        f"{usp}\n"
        f"{price_text}\n"
        f"{cta}."
    )

    campaign = {
        "campaign_brain": {
            "product_identity": product_name,
            "audience": audience,
            "usp": usp,
            "brand_voice": brand_tone,
            "core_message": core_message,
            "cta": cta,
        },

        "platforms": {
            "instagram": {
                "post": {
                    "caption": instagram_caption,
                    "hashtags": hashtags,
                    "cta": cta,
                },

                "reel": {
                    "hook": f"Meet {product_name}.",
                    "script": instagram_reel_script,
                    "caption": (
                        f"{product_name}: {usp} "
                        f"{price_text}"
                    ).strip(),
                    "cta": cta,
                },

                "story": {
                    "frame_1": f"Meet {product_name}.",
                    "frame_2": usp,
                    "frame_3": (
                        f"Made for {audience}.{price_text}"
                    ),
                    "cta": cta,
                },
            },

            "youtube": {
                "short": {
                    "hook": f"Why {product_name}?",
                    "script": (
                        f"Meet {product_name}. "
                        f"{usp} "
                        f"Designed with {audience} in mind."
                        f"{price_text}"
                    ),
                    "caption": (
                        f"{product_name} — {usp}"
                        f"{price_text}"
                    ),
                    "cta": cta,
                },

                "thumbnail": {
                    "text": product_name,
                    "visual_concept": (
                        f"Clean product-focused composition highlighting "
                        f"{product_name} and its main selling point."
                    ),
                },
            },

            "facebook": {
                "post": {
                    "caption": (
                        f"Discover {product_name}.\n\n"
                        f"{usp}\n\n"
                        f"This campaign is created for {audience}."
                        f"{price_text}"
                    ),
                    "cta": cta,
                },
            },

            "x": {
                "post": {
                    "text": (
                        f"{product_name}: {usp}"
                        f"{price_text}"
                    )[:279],
                    "cta": cta,
                },
            },

            "whatsapp": {
                "message": {
                    "text": (
                        f"Hi! 👋\n\n"
                        f"Check out {product_name}.\n"
                        f"{usp}\n\n"
                        f"Made for {audience}."
                        f"{price_text}\n\n"
                        f"{cta}."
                    ),
                    "cta": cta,
                },

                "status": {
                    "frame_1": f"✨ {product_name}",
                    "frame_2": usp,
                    "frame_3": (
                        f"Made for {audience}.{price_text}"
                    ),
                    "cta": cta,
                },
            },
        },
    }

    return campaign


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