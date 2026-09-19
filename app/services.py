import logging
import re
from pathlib import Path
from uuid import uuid4

import requests
from flask import current_app

logger = logging.getLogger(__name__)

LEVELS = {
    "basic": "court, clair et factuel",
    "intermediate": "développé, contextualisé et structuré",
    "professional": "approfondi, fluide et conforme aux standards journalistiques",
}
DEFAULT_MODEL = "nex-agi/nex-n2.5-mini:free"


def clean_generated_text(content):
    """Remove Markdown formatting while preserving readable article text."""
    content = re.sub(r"```(?:text|markdown)?\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"```", "", content)
    content = re.sub(r"^\s{0,3}#{1,6}\s*", "", content, flags=re.MULTILINE)
    content = re.sub(r"^[ \t]*[-+*][ \t]+", "", content, flags=re.MULTILINE)
    content = re.sub(r"[*_`~]", "", content)
    content = re.sub(r"^[ \t]*>[ \t]?", "", content, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", content).strip()


def build_prompt(title, raw_content, level, category, language):
    style = LEVELS.get(level, LEVELS["intermediate"])
    return (
        f"Tu dois transformer la source brute en article de presse {style} en {language}.\n"
        f"Sujet : {title}. Catégorie : {category}.\n\n"
        "Règles impératives :\n"
        "- Utilise uniquement les informations présentes dans la source.\n"
        "- N'invente aucune date, chiffre, lieu, nom, citation, institution, déclaration "
        "ou conséquence.\n"
        "- Ne présente pas une opinion comme un fait vérifié. Conserve les formulations "
        "subjectives en les attribuant à la source.\n"
        "- Si la source est trop courte, produis un article court et fidèle au lieu "
        "d'ajouter des détails imaginaires.\n"
        "- Retourne uniquement l'article final, sans commentaire sur ta méthode.\n"
        "- N'utilise aucun formatage Markdown : pas de dièses, astérisques, backticks, "
        "puces ou caractères de mise en forme.\n"
        "- Structure le texte avec un titre et des paragraphes lisibles.\n\n"
        f"SOURCE BRUTE À REFORMULER :\n{raw_content}"
    )


def generate_article(title, raw_content, level, category, language):
    api_key = current_app.config["OPENROUTER_API_KEY"]
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY est manquante.")
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "GTv Studio",
        },
        json={
            "model": current_app.config.get("OPENROUTER_MODEL") or DEFAULT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Tu es un journaliste professionnel, rigoureux et fidèle "
                        "aux sources. Tu ne fabriques jamais de faits."
                    ),
                },
                {
                    "role": "user",
                    "content": build_prompt(
                        title, raw_content, level, category, language
                    ),
                },
            ],
            "temperature": 0.3,
            "max_tokens": 900,
        },
        timeout=60,
    )
    if not response.ok:
        logger.error(
            "OpenRouter returned HTTP %s: %s",
            response.status_code,
            response.text[:500],
        )
        response.raise_for_status()
    data = response.json()
    try:
        content = clean_generated_text(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Réponse OpenRouter invalide.") from exc
    if not content:
        raise RuntimeError("Le modèle n'a renvoyé aucun contenu.")
    return content


def generate_audio(text, language, article_id):
    from gtts import gTTS

    directory = Path(current_app.instance_path) / "audio"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"article-{article_id}-{uuid4().hex}.mp3"
    path = directory / filename
    gTTS(text=text, lang=language).save(str(path))
    return filename
