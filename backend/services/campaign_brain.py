import json
import os
import re

import httpx
from fastapi import HTTPException

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "meta-llama/llama-3.1-8b-instruct:free",
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


SYSTEM_PROMPT = """
You are the Campaign Brain inside LaunchFlow AI.

LaunchFlow AI takes ONE product brief and creates ONE coordinated
marketing campaign adapted separately for Instagram, YouTube,
Facebook, X and WhatsApp.

Return ONLY valid JSON.
Do not use markdown.
Do not add explanations outside the JSON.

The response MUST follow this exact structure:

{
  "campaign_brain": {
    "product_identity": "",
    "audience": "",
    "usp": "",
    "brand_voice": "",
    "core_message": "",
    "cta": ""
  },

  "platforms": {

    "instagram": {
      "post": {
        "caption": "",
        "hashtags": [],
        "cta": ""
      },
      "reel": {
        "hook": "",
        "script": "",
        "caption": "",
        "cta": ""
      },
      "story": {
        "frame_1": "",
        "frame_2": "",
        "frame_3": "",
        "cta": ""
      }
    },

    "youtube": {
      "short": {
        "hook": "",
        "script": "",
        "caption": "",
        "cta": ""
      },
      "thumbnail": {
        "text": "",
        "visual_concept": ""
      }
    },

    "facebook": {
      "post": {
        "caption": "",
        "cta": ""
      }
    },

    "x": {
      "post": {
        "text": "",
        "cta": ""
      }
    },

    "whatsapp": {
      "message": {
        "text": "",
        "cta": ""
      },
      "status": {
        "frame_1": "",
        "frame_2": "",
        "frame_3": "",
        "cta": ""
      }
    }
  }
}

RULES:

1. Preserve the product name exactly.

2. Preserve the exact price when provided.

3. Never invent:
   - product features
   - discounts
   - reviews
   - statistics
   - certifications
   - ingredients
   - guarantees
   - prices

4. Use ONE shared campaign idea across all platforms.

5. Do NOT copy the same text between platforms.

6. Every platform must feel native to that platform.

7. Follow the requested brand tone.

8. Follow the requested language.

9. Instagram:
   - Feed post
   - Reel
   - 3-frame Story
   - hashtags
   - CTA

10. YouTube:
   - Short
   - thumbnail concept

11. Facebook:
   - descriptive promotional post
   - CTA

12. X:
   - concise promotional post
   - post text MUST be under 280 characters

13. WhatsApp:
   - conversational promotional message
   - 3-frame Status
   - CTA

14. Keep all content consistent with the product brief.

15. Return valid JSON only.
"""


def build_user_prompt(data: dict) -> str:
    return f"""
Create a complete coordinated marketing campaign from this product brief.

Product name:
{data.get("product_name", "")}

Description:
{data.get("description", "")}

Price:
{data.get("price", "")}

Target audience:
{data.get("audience", "")}

Main selling point:
{data.get("usp", "")}

Brand tone:
{data.get("brand_tone", "friendly")}

Language:
{data.get("language", "English")}

Create every required platform section.

Remember:

- Preserve the product name.
- Preserve the exact price.
- Preserve the main selling point (USP) clearly in each platform's primary copy.
- Do not invent facts.
- Keep one campaign message.
- Adapt the content for every platform; do not reuse identical primary copy.
"""


async def call_campaign_brain(brief: dict) -> dict:

    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY is not set.",
        )

    payload = {
        "model": OPENROUTER_MODEL,

        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": build_user_prompt(brief),
            },
        ],

        "temperature": 0.7,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "LaunchFlow AI",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail=f"Campaign Brain request timed out: {error}")
    except httpx.RequestError as error:
        raise HTTPException(status_code=502, detail=f"Could not connect to OpenRouter Campaign Brain: {error}")

    if response.status_code != 200:

        raise HTTPException(
            status_code=502,
            detail=f"Campaign text provider returned HTTP {response.status_code}.",
        )

    try:
        data = response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="OpenRouter Campaign Brain returned invalid JSON.")
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="OpenRouter Campaign Brain returned an invalid response.")

    try:
        raw = data["choices"][0]["message"]["content"]
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("empty message content")

    except (KeyError, IndexError, TypeError, ValueError) as error:

        raise HTTPException(
            status_code=502,
            detail=(
                f"Unexpected OpenRouter response: {error}"
            ),
        )

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
    ).strip()

    try:

        campaign = json.loads(raw)

    except json.JSONDecodeError as error:

        raise HTTPException(
            status_code=502,
            detail=(
                f"Campaign Brain returned invalid JSON: "
                f"{error}. Raw response: {raw[:800]}"
            ),
        )

    return campaign
