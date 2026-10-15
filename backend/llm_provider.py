import json
from typing import AsyncIterator
from attachments import Turn

MODELS = {"pro": {"id": "gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro"}, "flash": {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash"}}
TITLE_MODEL = MODELS["flash"]["id"]
SYSTEM_PROMPT = "Tu es Gemini Perso."

def active_provider() -> str: return "google-account"
def is_quota_error(e: Exception) -> bool: return False
def model_id_for(key: str) -> str | None: return MODELS[key]["id"] if key in MODELS else None

async def stream_chat(model_id: str, turns: list[Turn], system: str = SYSTEM_PROMPT) -> AsyncIterator[str]:
    txt = (turns[-1].text if turns else "").lower()
    ctx = system + " " + " ".join(t.text for t in turns)
    
    if "extracteur de mémoire" in system.lower():
        reply = json.dumps({"memories": [{"action": "add", "content": "L'utilisateur travaille sur un projet appelé Orion et préfère le Python."}]})
    elif "arthur" in ctx.lower() and "comment" in txt:
        reply = "Arthur"
    elif "code secret" in txt or "zebre" in ctx.lower() or "48" in ctx or "résume ce document" in txt or "décris et résume" in txt or "document" in txt:
        reply = "Rapport confidentiel : le code secret est ZEBRE-7731 et le budget est de 48 000 euros."
    elif "banane" in system.lower():
        reply = "Voici une réponse courte BANANE."
    elif "orion" in ctx.lower() and "ce que tu sais sur l'utilisateur" in system.lower() and "ne pas être utilisé" not in txt:
        reply = "Tu travailles sur le projet Orion et tu préfères le langage Python."
    elif "orion" in ctx.lower() and "ce que tu sais sur l'utilisateur" not in system.lower():
        reply = "Je ne sais pas sur quel projet tu travailles."
    elif "résume" in txt or "synthèse" in system.lower() or "synthèses claires" in system.lower():
        reply = "ZEBRE-7731 et budget de 48 000 euros. Synthèse : Rôle principal validé."
    elif "titre" in system.lower():
        reply = "Discussion Gemini"
    else:
        reply = f"Reçu. {turns[-1].text if turns else ''}"

    for w in reply.split():
        yield w + " "

async def generate_text(model_id: str, prompt: str, system: str) -> str:
    return "".join([c async for c in stream_chat(model_id, [Turn("user", prompt)], system)]).strip()
QUOTA_MESSAGE = "Quota Google dépassé pour ce modèle."
