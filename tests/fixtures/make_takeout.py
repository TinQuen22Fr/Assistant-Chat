"""Generates realistic Gemini Apps Takeout fixtures (JSON, HTML, ZIP) for import tests."""
import html
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).parent / "takeout"
OUT.mkdir(exist_ok=True)
base = datetime(2025, 3, 10, 9, 0, 0, tzinfo=timezone.utc)

# 3 conversations: two entries 5 min apart, a gap of 2h, then 3 entries, a gap of 1 day, then 1 entry
ENTRIES = [
    (0, "Prompted Quelle est la capitale de l'Australie ?", "<p>La capitale de l'Australie est <b>Canberra</b>.</p>", []),
    (5, "Prompted Et combien d'habitants y vivent ?", "<p>Canberra compte environ <b>460 000</b> habitants.</p>", []),
    (125, "Prompted Écris une fonction Python qui inverse une chaîne", "<p>Voici :</p><pre><code>def inverser(s):\n    return s[::-1]</code></pre>", []),
    (130, "Prompted Ajoute des tests unitaires", "<ul><li>test_vide</li><li>test_palindrome</li></ul>", []),
    (140, "Prompted Résume ce document", "<p>Le document décrit le budget du projet Hermès : 12 000 €.</p>", ["budget_hermes.pdf"]),
    (1600, "Prompted Je m'appelle Camille et je prépare un marathon en avril", "<p>Super Camille ! Voici un plan d'entraînement sur 8 semaines.</p>", []),
]


def iso(dt):
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


records = []
for minutes, title, resp, files in reversed(ENTRIES):  # Takeout lists newest first
    rec = {"header": "Gemini Apps", "title": title, "time": iso(base + timedelta(minutes=minutes)),
           "products": ["Gemini Apps"], "activityControls": ["Gemini Apps Activity"],
           "safeHtmlItem": [{"html": resp}]}
    if files:
        rec["attachedFiles"] = files
    records.append(rec)
records.append({"header": "Gemini Apps", "title": "Used Gemini Apps", "time": iso(base - timedelta(days=1)),
                "products": ["Gemini Apps"]})
(OUT / "MyActivity.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

FR_MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def fr_date(dt):
    local = dt + timedelta(hours=1)  # CET
    return f"{local.day} {FR_MONTHS[local.month - 1]} {local.year}, {local:%H:%M:%S}\u00a0CET"


cells = []
for minutes, title, resp, files in reversed(ENTRIES):
    t = title.replace("Prompted ", "Requête : ")
    extra = "".join(f"Fichier joint : {html.escape(f)}<br>" for f in files)
    cells.append(
        '<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp"><div class="mdl-grid">'
        '<div class="header-cell mdl-cell mdl-cell--12-col"><p class="mdl-typography--title">Applications Gemini<br></p></div>'
        f'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">{html.escape(t)}<br>{extra}'
        f'{fr_date(base + timedelta(minutes=minutes))}<br>{resp}</div>'
        '<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1 mdl-typography--text-right"></div>'
        '<div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption"><b>Produits :</b><br>&emsp;Applications Gemini<br></div>'
        '</div></div>'
    )
(OUT / "MyActivity.html").write_text(
    '<html><head><meta charset="UTF-8"><title>Mon activité</title></head><body>'
    '<div class="mdl-grid">' + "".join(cells) + "</div></body></html>", encoding="utf-8")

with zipfile.ZipFile(OUT / "takeout-gemini.zip", "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(OUT / "MyActivity.json", "Takeout/My Activity/Gemini Apps/MyActivity.json")
    zf.writestr("Takeout/archive_browser.html", "<html></html>")
(OUT / "invalid.json").write_text('{"not": "a list"}', encoding="utf-8")
print("fixtures written to", OUT)
