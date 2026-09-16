import base64
import logging
import random
import os
import re
import json
import urllib.request
import urllib.error
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_URL = OLLAMA_BASE + "/api/generate"
# gemma3:12b, mesure sur cette machine (RTX 2080 Ti, MEmu tournant en parallele) :
# il se charge a 100% sur le GPU et repond en 3,7-4,3s a chaud, image redimensionnee.
# Le chargement initial coute ~290s, paye une seule fois : keep_alive=24h le garde
# resident. moondream n'est pas installe ici, ce qui faisait echouer chaque appel
# en ~2s et retomber silencieusement sur comments_list.txt (des emojis seuls).
# Renvoye quand le post ne doit PAS etre commente du tout (et non "l'IA a
# echoue, prends un emoji par defaut"). interaction.py sait le distinguer.
SKIP_POST = "__SKIP_POST__"

MODEL_NAME = "gemma3:12b"
KEEP_ALIVE = "24h"

# La capture brute fait 720x1280 (~450 Ko). Reduite a 512px de large en JPEG elle
# tombe a ~30 Ko, soit 7% du poids, et l'appel gagne environ 25% de temps.
MAX_IMAGE_WIDTH = 512
JPEG_QUALITY = 80

# Nom d'artiste de la persona. Volontairement ABSENT du depot : il identifierait
# le compte Instagram. L'orchestrateur le lit dans accounts/<compte>/persona.txt
# (ignore par git) et le transmet via AI_PERSONA_NAME. Sans lui, la persona reste
# anonyme et le prompt fonctionne tel quel.
PERSONA_NAME = os.environ.get("AI_PERSONA_NAME", "").strip()

PROMPT = """You are __PERSONA__a music producer/DJ scrolling Instagram and dropping a
quick comment on another artist's post - one artist supporting another, not a fan
and not a brand account.

Look carefully at the image and react to WHAT YOU ACTUALLY SEE in it.

YOUR VOICE: you are a working DJ/producer, not a photographer or an art critic.
You react to the VIBE, the gear, the room, the energy - never to composition,
colours or framing. Write the way you would text a mate: short, blunt, a bit
slangy, lowercase feel. No polished sentences, no literary words.
BANNED - never use these or anything like them: aesthetic, palette, composition,
framing, striking, intriguing, captivating, crimson, foliage, greenery, orb,
sphere, amongst, hues, tones, imagery, visual, depth, contrast, moody.
If you cannot say something a DJ would actually say about the post, just send
emojis instead.
Never end with a full stop, a comma or an exclamation mark.

RULES:
1. React to the POST AS A WHOLE, the way a mate scrolling would - not to one
   small detail. Posts are often carousels: you only see the first image, so
   never build the comment around a detail that may not be the point (the
   lighting, a lamp, a plant). Go for the overall thing: the release, the
   artwork, the set, the session, the moment.
   If the post announces something (a track, an EP, a gig), react to THAT:
   looking forward to hearing it, the cover looks great, wish you a good set.
2. Write it in your OWN words. Do not reuse a stock phrase you have seen before,
   invent the reaction each time.
3. You are looking at a phone screenshot: IGNORE the Instagram interface - the
   buttons, the counters, the "collaborators" or "tagged" labels, the usernames.
   Never read the screen out loud and never name a place, a venue or a person.
   Never describe the image like a photographer would ("nice lighting", "great
   framing", "love the colours") - that is not what a DJ writes under a mate's
   post.
   When a WHAT THE POST SAYS line is given below, that text is the subject of
   the post: react to what it ANNOUNCES (a release, a gig, a remix, a studio
   session) rather than to the look of the picture. Never quote it back word
   for word, react to it in your own words.
4. NEVER guess details you cannot see - not the genre, not whether it is an
   album/single/EP, not a name or a job. A vague reaction beats a wrong guess.
5. If the photo is clearly NOT about music, DJing or nightlife (food, animals,
   landscape, sport), react to what is actually shown. Do not force music words.
6. NEVER refer to yourself__PERSONA_OR__ in the third person. Just react.
7. NEVER ask a question. Never write "huh", "right", "no?" or any tag question either. A comment is a reaction, not a question.
8. ALWAYS write in English, whatever the post shows.
9. NEVER comment on anyone's physical appearance, body or looks, and never write
   anything flirtatious, romantic or seductive. No "beautiful", "gorgeous",
   "cute", "sexy", "love you". If the post shows a person, react to what they
   are DOING or to the music/scene, never to how they look.
10. If the post is mainly a person posing for the camera - a selfie, a body
    shot, someone in underwear, swimwear, lingerie or barely dressed, or any
    photo whose subject is the person's body rather than music - do NOT write a
    comment. Answer with exactly this word and nothing else: SKIP
    Same thing if the post has nothing to do with music, nightlife or creative
    work and commenting would look random.
11. Output ONLY the comment. No quotes, no intro, no explanation.
"""
PROMPT = PROMPT.replace("__PERSONA__", f"{PERSONA_NAME}, " if PERSONA_NAME else "").replace(
    "__PERSONA_OR__", f' or to "{PERSONA_NAME}"' if PERSONA_NAME else ""
)

# moondream doesn't reliably follow instruction #4 above on its own, so this is
# enforced in code too: reject anything that reads like a question rather than
# a hype reaction — a generic "What do you think of this?" under a stranger's
# post reads as obviously bot-written and confuses people.
_QUESTION_STARTS = re.compile(
    r"^(what|how|why|who|when|where|which|is|are|do|does|did|can|could|would|will|should)\b",
    re.IGNORECASE,
)
# Le prompt ne suffit pas : un modele finit toujours par lacher un "beautiful".
# Meme logique que pour les questions plus bas, on refuse en dur.
_APPEARANCE_RE = re.compile(
    r"\b(beautiful|gorgeous|pretty|cute|hot|sexy|stunning|handsome|babe|baby|"
    r"queen|king|goddess|angel|perfect body|body goals|smile|eyes|legs|"
    r"love you|luv you|marry me|date|dm me|text me|hit me up|single)\b",
    re.IGNORECASE,
)
# Vocabulaire de critique d'art : un DJ n'ecrit pas "crimson sphere amongst dark
# leaves" sous un post. Comme pour l'apparence, le prompt seul ne tient pas.
_ART_CRITIC_RE = re.compile(
    r"\b(aesthetic|aesthetics|palette|composition|framing|frames?|striking|"
    r"intriguing|captivating|crimson|foliage|greenery|orb|sphere|amongst|"
    r"hues?|tones?|imagery|visuals?|juxtapos\w*|silhouette|contrast|moody|"
    r"ambiance|serene|evocative|obscures?)\b",
    re.IGNORECASE,
)
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)

# Recent comments this run, so we can tell the model what to avoid repeating -
# without this, a small local model like moondream tends to converge on the
# same handful of stock phrases from the prompt's examples over and over.
_recent_comments: list[str] = []
_RECENT_COMMENTS_MAX = 15

# Elements d'interface a ignorer : ce sont des libelles de l'app, pas le contenu
# du post. Sans ce filtre le modele commente "View all comments" ou "Add a comment".
_UI_NOISE = re.compile(
    r"^(add a comment|view all|reply|see more|liked by|likes?|comments?|share|"
    r"send|follow|following|translate|see translation|original audio|sponsored|"
    r"suggested for you|no comments yet|be the first|write a comment|"
    r"\d+\s*likes?\b|\d+\s*comments?\b|"
    r"\d+\s*[hdwm]$|\d+\s*(hours?|days?|weeks?|minutes?)( ago)?$|"
    r"view \d+|load more|show more)\b",
    re.IGNORECASE,
)

# Libelles d'accessibilite Android : ils decrivent comment MANIPULER l'element,
# pas son contenu. Ils sont souvent hauts a l'ecran, donc le critere "texte le
# plus haut" les selectionnait a la place de la legende. Vu en production :
# "1 likes. Double tap to like comment and press and hold to see all likes".
_A11Y_NOISE = re.compile(
    r"double[- ]?tap|press and hold|tap to |swipe |long press|button$|"
    r"heading$|selected$|not selected",
    re.IGNORECASE,
)


def _model_is_loaded(timeout: float = 3.0) -> bool:
    """Le modele est-il deja resident en memoire ?

    Sans ce controle, un appel sur modele decharge declenche un chargement de
    ~5 minutes cote Ollama, que notre timeout de 90s interrompait -- Ollama
    annulait alors le chargement ("client connection closed before llama-server
    finished loading"). Resultat observe du 31/08 au 02/09 : 64 appels, 0
    commentaire genere, 90s perdues a chaque post et un modele jamais charge.

    On preferre echouer immediatement : le prechargement lance par
    run_session_loop.ps1 s'occupe du chargement en tache de fond, sans etre
    interrompu.
    """
    try:
        req = urllib.request.Request(OLLAMA_BASE + "/api/ps")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        noms = [m.get("name", "") for m in data.get("models", [])]
        return any(n.startswith(MODEL_NAME.split(":")[0]) for n in noms)
    except Exception:
        return False


def _extract_post_text(device, max_chars: int = 300) -> str:
    """Recupere la LEGENDE du post, pas les commentaires des autres.

    L'AI Commenter est appele apres l'ouverture de la section commentaires :
    l'ecran contient donc la legende ET les commentaires d'inconnus. Trier par
    longueur prendrait le commentaire le plus bavard. La legende est en revanche
    toujours le premier bloc de texte de la zone, donc on se fie a la POSITION
    VERTICALE : on garde le texte utile le plus haut a l'ecran.
    """
    try:
        xml = device.deviceV2.dump_hierarchy()
    except Exception as e:
        logger.debug(f"AI Commenter: hierarchie illisible ({e}).")
        return ""

    candidats = []
    for noeud in re.findall(r"<node[^>]*>", xml):
        m_txt = re.search(r'text="([^"]*)"', noeud)
        m_bnd = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', noeud)
        if not m_txt or not m_bnd:
            continue
        t = m_txt.group(1).strip()
        top = int(m_bnd.group(2))
        if len(t) < 15:
            continue
        if _UI_NOISE.match(t):
            continue
        if _A11Y_NOISE.search(t):
            continue
        # Un pseudo Instagram est un seul mot colle ("facelessdesigncollective",
        # vu en production) : sans espace, ce n'est pas une legende. Une vraie
        # legende fait au minimum quelques mots.
        if len(t.split()) < 3:
            continue
        # Un @ ou un # seul en debut de ligne, ce sont des mentions/hashtags,
        # pas le texte du post.
        if t.lstrip().startswith(("@", "#")) and len(t.split()) < 5:
            continue
        if t.startswith(("http://", "https://", "www.")):
            continue
        candidats.append((top, t))

    if not candidats:
        logger.info("AI Commenter: aucune legende lisible, l'image seule sera utilisee.")
        return ""

    # Le plus haut a l'ecran = la legende ; les commentaires sont en dessous.
    candidats.sort(key=lambda c: c[0])
    caption = candidats[0][1]

    # Instagram colle le pseudo devant la legende et ajoute "... more" quand le
    # texte est tronque. Vu en production : "listenmosaiq BRING THE BEAT BACK
    # ... more". On nettoie les deux, le modele n'a pas besoin de ce bruit.
    caption = re.sub(r"^[a-z0-9._]{3,30}\s+(?=[A-Z0-9])", "", caption)
    caption = re.sub(r"\s*\.{2,}\s*more\s*$", "", caption, flags=re.IGNORECASE)
    caption = re.sub(r"\s*\bmore\s*$", "", caption, flags=re.IGNORECASE)
    caption = re.sub(r"\s+", " ", caption).strip()[:max_chars]
    # En info et non en debug : c'est la seule facon de verifier en production
    # que le bot a lu la LEGENDE du post et pas le commentaire d'un inconnu.
    # Une ligne par commentaire, ca ne noie pas le journal.
    logger.info(f"AI Commenter: post dit -> {caption[:140]}")
    return caption


def generate_ai_comment(device, screenshot_path: str = "temp_post.png") -> Optional[str]:
    """
    Captures current post screenshot, sends to local Ollama vision model,
    and returns a short, natural English comment. Returns None on failure/timeout.
    """
    if not _model_is_loaded():
        logger.warning(
            f"AI Commenter: {MODEL_NAME} n'est pas charge en memoire "
            "(Ollama redemarre ?). Commentaire par defaut pour ce post, "
            "le prechargement s'en occupe en arriere-plan."
        )
        return None

    try:
        # 1. Take screenshot of current screen
        device.deviceV2.screenshot(screenshot_path)
        if not os.path.exists(screenshot_path):
            logger.debug("AI Commenter: Failed to save screenshot.")
            return None

        # 2. Downscale before encoding. La capture brute (720x1280 PNG, ~450 Ko)
        #    devient ~30 Ko en 512px JPEG et l'appel gagne ~25% de temps, sans
        #    perte visible pour le modele. Si Pillow manque ou echoue, on retombe
        #    simplement sur l'image d'origine.
        image_bytes = None
        try:
            from PIL import Image

            with Image.open(screenshot_path) as im:
                im = im.convert("RGB")
                if im.width > MAX_IMAGE_WIDTH:
                    ratio = MAX_IMAGE_WIDTH / im.width
                    im = im.resize(
                        (MAX_IMAGE_WIDTH, int(im.height * ratio)), Image.LANCZOS
                    )
                buf = BytesIO()
                im.save(buf, format="JPEG", quality=JPEG_QUALITY)
                image_bytes = buf.getvalue()
        except Exception as e:
            logger.debug(f"AI Commenter: downscale impossible ({e}), image d'origine.")

        if image_bytes is None:
            with open(screenshot_path, "rb") as image_file:
                image_bytes = image_file.read()

        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # 3. Build payload for Ollama
        #
        # Le format est tire AU SORT ICI, pas laisse au modele : on lui a demande
        # de varier lui-meme, il produisait 0 emoji-seul sur 9 essais et oubliait
        # l'emoji 2 fois sur 9. En imposant un seul format precis par appel, la
        # consigne est suivie et la variete devient reellement pilotable.
        _STYLES = [
            ("emoji", "Reply with ONLY 1 to 3 emojis. NO words at all, not a single one."),
            ("court", "Reply with exactly 1 or 2 words, followed by exactly one emoji."),
            ("moyen", "Reply with 3 to 6 words, followed by exactly one emoji."),
            # Un vrai commentaire ne finit pas toujours par des emojis : sans ce
            # format, chaque phrase se terminait invariablement par deux emojis,
            # ce qui devient une signature reconnaissable.
            ("texte", "Reply with 2 to 6 words and NO emoji at all. Plain words only."),
        ]
        style, style_rule = random.choices(_STYLES, weights=[25, 25, 25, 25], k=1)[0]

        prompt = PROMPT + chr(10) + "FORMAT FOR THIS ONE COMMENT: " + style_rule

        # Le texte du post prime sur l'image : c'est lui qui dit de quoi il
        # s'agit (une sortie, un live, un remix...). L'image seule menait a des
        # commentaires a cote de la plaque.
        caption = _extract_post_text(device)
        if caption:
            prompt += (
                chr(10) + chr(10)
                + "WHAT THE POST SAYS (this is the subject - react to THIS, "
                + "not just to the picture; never quote it back word for word): "
                + chr(34) + caption + chr(34)
            )
        if _recent_comments:
            prompt += (
                "\n9. You already used these recent comments - do NOT repeat any of "
                "them or anything too close to them, write something different: "
                + ", ".join(f'"{c}"' for c in _recent_comments)
            )
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "images": [base64_image],
            "stream": False,
            # Garde le modele resident : sans cela chaque appel repaie les ~290s
            # de chargement des 8 Go sur le GPU.
            "keep_alive": KEEP_ALIVE,
            "options": {
                "temperature": 0.95,
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
        # 30s et non 90 : une fois le modele resident il repond en ~4s. Les 90s
        # ne servaient qu'a un chargement a froid, desormais gere en amont.
        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            comment_text = res_data.get("response", "").strip()

        # Le modele a juge le post inapproprie : on ne commente pas DU TOUT.
        if re.match(r"^\s*skip\b", comment_text, re.IGNORECASE):
            logger.info("AI Commenter: post juge inapproprie (personne posant / hors sujet), aucun commentaire.")
            return SKIP_POST

        # 4. Clean & sanitize response
        # Strip every quote/dash variant (straight and curly quotes, hyphen,
        # en dash, em dash) — even one is an instant "written by an AI" tell.
        for ch in ['"', "'", "“", "”", "‘", "’", "-", "–", "—"]:
            comment_text = comment_text.replace(ch, " ")
        comment_text = re.sub(r"\s+", " ", comment_text).strip()
        comment_text = re.sub(r'^(Here is a comment|Comment|Sure|AI|Output):?\s*', '', comment_text, flags=re.IGNORECASE)
        # Un point ou un "!" final fait tres redactionnel : on le retire, les
        # emojis restent.
        comment_text = re.sub(r'[.!,;:]+(?=\s|$)', '', comment_text).strip()

        # Longueur : on plafonne a 8 mots, mais on accepte desormais les
        # commentaires courts, y compris ceux faits UNIQUEMENT d'emojis - c'est
        # le format le plus courant chez un vrai utilisateur. L'ancien
        # "len(words) < 2" rendait un "🔥🔥" impossible.
        words = comment_text.split()
        emoji_only = bool(comment_text) and not re.sub(_EMOJI_RE, "", comment_text).strip()
        if style == "texte" and emoji_only:
            logger.warning(f"AI Commenter: que des emojis alors que du texte etait demande ('{comment_text}'). Skipping AI.")
            return None
        if style == "emoji" and not emoji_only:
            logger.warning(f"AI Commenter: emojis demandes mais du texte est sorti ('{comment_text}'). Skipping AI.")
            return None
        if len(words) > 8:
            logger.warning(f"AI Commenter: Generated comment too long ('{comment_text}'). Skipping AI.")
            return None
        if not comment_text or (len(words) < 2 and not emoji_only):
            logger.warning(f"AI Commenter: Generated comment too short ('{comment_text}'). Skipping AI.")
            return None

        # Talking about the persona in third person ("<name> loves this") reads
        # as a brand account, not the artist themself commenting — reject it
        # even if the prompt's instruction gets ignored.
        if PERSONA_NAME and PERSONA_NAME.lower() in comment_text.lower():
            logger.warning(f"AI Commenter: Referred to itself in third person ('{comment_text}'). Skipping AI.")
            return None

        # Reject anything that reads like a question instead of a hype reaction,
        # and require an emoji — moondream doesn't reliably follow those rules
        # from the prompt alone, and a plain "What do you think of this?" under
        # a stranger's post is an obvious tell that it wasn't written by a fan.
        # "?" n'importe ou, pas seulement en fin : "Gonzaga Lane, huh? 🤔"
        # passait au travers car la chaine se termine par un emoji.
        # On teste le texte SANS les emojis : "Nice set right 🎧" se termine
        # par un emoji, donc un "$" ancre sur la chaine brute rate la tag question.
        _texte_nu = re.sub(_EMOJI_RE, "", comment_text).strip()
        if ("?" in comment_text
                or _QUESTION_STARTS.match(comment_text)
                or re.search(r"\b(huh|right|no|yeah|eh)\s*$", _texte_nu, re.I)):
            logger.warning(f"AI Commenter: Generated a question, not a reaction ('{comment_text}'). Skipping AI.")
            return None
        if _ART_CRITIC_RE.search(comment_text):
            logger.warning(f"AI Commenter: ton de critique d'art ('{comment_text}'). Skipping AI.")
            return None
        if _APPEARANCE_RE.search(comment_text):
            logger.warning(f"AI Commenter: Commented on looks / flirty ('{comment_text}'). Skipping AI.")
            return None
        if style == "texte":
            # Format sans emoji : on refuse au contraire ceux qui en contiennent.
            if _EMOJI_RE.search(comment_text):
                logger.warning(f"AI Commenter: emoji alors que le format texte etait demande ('{comment_text}'). Skipping AI.")
                return None
        elif not _EMOJI_RE.search(comment_text):
            logger.warning(f"AI Commenter: No emoji in generated comment ('{comment_text}'). Skipping AI.")
            return None
        if comment_text in _recent_comments:
            logger.warning(f"AI Commenter: Repeated a recent comment ('{comment_text}'). Skipping AI.")
            return None

        _recent_comments.append(comment_text)
        del _recent_comments[:-_RECENT_COMMENTS_MAX]

        logger.info(f"AI Commenter generated [{style}]: '{comment_text}'")
        return comment_text

    except urllib.error.URLError:
        logger.warning("AI Commenter: Ollama injoignable sur http://localhost:11434.")
        return None
    except Exception as e:
        logger.warning(f"AI Commenter: echec de generation ({type(e).__name__}: {e}).")
        return None
    finally:
        # La capture est supprimee QUOI QU'IL ARRIVE. Avant, le os.remove() se
        # trouvait au milieu du try : la moindre erreur avant lui laissait le
        # fichier sur le disque, et on accumulait des captures d'ecran.
        try:
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
        except Exception:
            pass
