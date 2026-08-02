import base64
import logging
import os
import re
import json
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
# moondream (~1.9GB) fits entirely on the GPU alongside the emulator; llama3.2-vision
# (11GB) doesn't fit in the VRAM left over after the emulator, so Ollama splits it
# 47/53 CPU/GPU and inference becomes 50s+ per comment. Once moondream is loaded
# (kept resident via OLLAMA_KEEP_ALIVE=24h in docker-compose.yml), responses take
# ~0.3-0.5s; only the very first call after a cold start pays a ~40-90s load cost.
MODEL_NAME = "moondream"

PROMPT = """You are ARTISTE, a music producer/DJ browsing Instagram and leaving a
comment on a fellow artist's post — one artist supporting another, not a fan
or a brand account.
Look at this photo or post. Write a short, natural, human Instagram comment in ENGLISH.
CRITICAL RULES:
1. Maximum 3 to 6 words total.
2. End with 1 or 2 relevant emojis.
3. Talk like a peer artist hyping up another artist's work. Good examples: "Insane vibes! 🔥", "This track is crazy 🔊", "Unreal energy 🔥🔥", "That setup looks sick! 🚀", "Big tune mate 🔥".
4. NEVER refer to yourself or "ARTISTE" in third person (do not write things like "ARTISTE loves this"). Just react, like you're the one talking.
5. NEVER ask a question. Do not write things like "What do you think?" or "Is this real?". A comment is a reaction, not a question.
6. NEVER guess or name specific details you can't actually see — not the music genre, not whether it's an album/single/EP, not a person's name or job. If you're not sure it's an album, say "track" or don't mention the format at all. A vague, safe reaction beats a specific wrong guess.
7. If the photo is clearly NOT about music, DJing, or nightlife (for example food, animals, landscapes, sports), just react to what's actually shown — do not force in music words like "vibes" or "tune" where they don't fit.
8. Output ONLY the comment. No quotes, no intro, no punctuation except emojis.
"""

# moondream doesn't reliably follow instruction #4 above on its own, so this is
# enforced in code too: reject anything that reads like a question rather than
# a hype reaction — a generic "What do you think of this?" under a stranger's
# post reads as obviously bot-written and confuses people.
_QUESTION_STARTS = re.compile(
    r"^(what|how|why|who|when|where|which|is|are|do|does|did|can|could|would|will|should)\b",
    re.IGNORECASE,
)
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)

def generate_ai_comment(device, screenshot_path: str = "temp_post.png") -> Optional[str]:
    """
    Captures current post screenshot, sends to local Ollama vision model,
    and returns a short, natural English comment. Returns None on failure/timeout.
    """
    try:
        # 1. Take screenshot of current screen
        device.deviceV2.screenshot(screenshot_path)
        if not os.path.exists(screenshot_path):
            logger.debug("AI Commenter: Failed to save screenshot.")
            return None

        # 2. Encode image to base64
        with open(screenshot_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        # Clean up temp screenshot
        try:
            os.remove(screenshot_path)
        except Exception:
            pass

        # 3. Build payload for Ollama
        payload = {
            "model": MODEL_NAME,
            "prompt": PROMPT,
            "images": [base64_image],
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 25,
            }
        }

        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        logger.info("AI Commenter: Asking Ollama to analyze image...")
        # 5s was nowhere near enough — even the fast moondream model needs up to
        # ~60-90s the very first time it's loaded onto the GPU in a session. Once
        # warm (kept resident 24h via OLLAMA_KEEP_ALIVE), real calls take <1s, so
        # this generous ceiling is only ever paid once per day in practice.
        with urllib.request.urlopen(req, timeout=90) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            comment_text = res_data.get("response", "").strip()

        # 4. Clean & sanitize response
        # Strip every quote/dash variant (straight and curly quotes, hyphen,
        # en dash, em dash) — even one is an instant "written by an AI" tell.
        for ch in ['"', "'", "“", "”", "‘", "’", "-", "–", "—"]:
            comment_text = comment_text.replace(ch, " ")
        comment_text = re.sub(r"\s+", " ", comment_text).strip()
        comment_text = re.sub(r'^(Here is a comment|Comment|Sure|AI|Output):?\s*', '', comment_text, flags=re.IGNORECASE)

        # Word count safety check (3 to 8 words max)
        words = comment_text.split()
        if len(words) > 8 or len(words) < 2:
            logger.warning(f"AI Commenter: Generated comment too long/short ('{comment_text}'). Skipping AI.")
            return None

        # Talking about "ARTISTE" in third person ("ARTISTE loves this") reads as a
        # brand account, not the artist themself commenting — reject it even if
        # the prompt's instruction gets ignored.
        if "ARTISTE" in comment_text.lower():
            logger.warning(f"AI Commenter: Referred to itself in third person ('{comment_text}'). Skipping AI.")
            return None

        # Reject anything that reads like a question instead of a hype reaction,
        # and require an emoji — moondream doesn't reliably follow those rules
        # from the prompt alone, and a plain "What do you think of this?" under
        # a stranger's post is an obvious tell that it wasn't written by a fan.
        if comment_text.rstrip().endswith("?") or _QUESTION_STARTS.match(comment_text):
            logger.warning(f"AI Commenter: Generated a question, not a reaction ('{comment_text}'). Skipping AI.")
            return None
        if not _EMOJI_RE.search(comment_text):
            logger.warning(f"AI Commenter: No emoji in generated comment ('{comment_text}'). Skipping AI.")
            return None

        logger.info(f"AI Commenter generated: '{comment_text}'")
        return comment_text

    except urllib.error.URLError:
        logger.debug("AI Commenter: Ollama is not running on http://localhost:11434.")
        return None
    except Exception as e:
        logger.debug(f"AI Commenter error: {e}")
        return None
