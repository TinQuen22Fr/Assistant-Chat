"""Google Takeout import: Gemini Apps activity (MyActivity.json / MyActivity.html, raw or zipped)."""
import hashlib
import html as html_lib
import io
import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

MAX_UPLOAD_BYTES = 250 * 1024 * 1024
CONVERSATION_GAP = timedelta(minutes=30)
MAX_GROUP_ENTRIES = 300
CHUNK = 1 << 20
PROMPT_PREFIXES = ("Prompted ", "Requête : ", "Requête: ", "Requête ", "Vous avez demandé : ", "Asked ", "Prompt : ")
ACTIVITY_FILE_RE = re.compile(r"(myactivity|monactivit[ée]|mon_activit[ée])\.(json|html?)$", re.I)
WS_RE = re.compile(r"[\u00a0\u202f\u2009]")


class TakeoutError(Exception):
    pass


@dataclass
class Entry:
    time: str  # ISO 8601 UTC
    prompt: str
    response: str
    files: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return hashlib.sha1(f"{self.time}|{self.prompt[:500]}".encode()).hexdigest()[:24]


# ---------- HTML → Markdown ----------

def html_to_md(raw: str) -> str:
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", raw or "")
    s = re.sub(r"(?is)<pre[^>]*>(.*?)</pre>",
               lambda m: "\n```\n" + html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() + "\n```\n", s)
    s = re.sub(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>", lambda m: "\n\n" + "#" * int(m.group(1)) + " " + m.group(2) + "\n\n", s)
    s = re.sub(r'(?is)<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"[\2](\1)", s)
    s = re.sub(r"(?i)<li[^>]*>", "\n- ", s)
    s = re.sub(r"(?i)</?(strong|b)>", "**", s)
    s = re.sub(r"(?i)</?(em|i)>", "*", s)
    s = re.sub(r"(?i)</?code[^>]*>", "`", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|ul|ol|table|tr|blockquote)>", "\n\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = WS_RE.sub(" ", html_lib.unescape(s))
    s = re.sub(r"[ \t]+\n", "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def _strip_prefix(title: str) -> str | None:
    t = WS_RE.sub(" ", title or "").strip()
    for p in PROMPT_PREFIXES:
        if t.startswith(p):
            return t[len(p):].strip()
    return None


# ---------- dates ----------

MONTHS = {
    "jan": 1, "january": 1, "janv": 1, "janvier": 1, "feb": 2, "february": 2, "févr": 2, "fevr": 2, "février": 2,
    "mar": 3, "march": 3, "mars": 3, "apr": 4, "april": 4, "avr": 4, "avril": 4, "may": 5, "mai": 5,
    "jun": 6, "june": 6, "juin": 6, "jul": 7, "july": 7, "juil": 7, "juillet": 7, "aug": 8, "august": 8,
    "août": 8, "aout": 8, "sep": 9, "sept": 9, "september": 9, "septembre": 9, "oct": 10, "october": 10,
    "octobre": 10, "nov": 11, "november": 11, "novembre": 11, "dec": 12, "december": 12, "déc": 12, "décembre": 12,
}
TZ_OFFSETS = {"UTC": 0, "GMT": 0, "WET": 0, "BST": 1, "CET": 1, "WEST": 1, "CEST": 2, "EET": 2, "EEST": 3,
              "EST": -5, "EDT": -4, "CST": -6, "CDT": -5, "MST": -7, "MDT": -6, "PST": -8, "PDT": -7}
TIME_RE = r"(?P<H>\d{1,2}):(?P<M>\d{2}):(?P<S>\d{2})\s*(?P<ampm>[AaPp]\.?[Mm]\.?)?\s*(?P<tz>[A-Z]{2,5}(?:[+-]\d{1,2}(?::?\d{2})?)?)?"
DATE_EN = re.compile(r"^(?P<mon>[A-Za-z]{3,9})\.? (?P<d>\d{1,2}), (?P<y>\d{4}),? (?:at )?" + TIME_RE + r"\s*$")
DATE_EU = re.compile(r"^(?P<d>\d{1,2}) (?P<mon>[^\W\d_]{3,10})\.? (?P<y>\d{4}),? (?:à |at )?" + TIME_RE + r"\s*$")


def _tz_offset(tz: str | None) -> timedelta:
    if not tz:
        return timedelta(0)
    m = re.match(r"^([A-Z]{2,5})(?:([+-])(\d{1,2})(?::?(\d{2}))?)?$", tz)
    if not m:
        return timedelta(0)
    if m.group(2):
        sign = 1 if m.group(2) == "+" else -1
        return sign * timedelta(hours=int(m.group(3)), minutes=int(m.group(4) or 0))
    return timedelta(hours=TZ_OFFSETS.get(m.group(1), 0))


def parse_display_date(text: str) -> datetime | None:
    t = WS_RE.sub(" ", html_lib.unescape(text)).strip()
    m = DATE_EN.match(t) or DATE_EU.match(t)
    if not m:
        return None
    month = MONTHS.get(m.group("mon").lower().rstrip("."))
    if not month:
        return None
    hour = int(m.group("H"))
    ampm = (m.group("ampm") or "").lower().replace(".", "")
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    local = datetime(int(m.group("y")), month, int(m.group("d")), hour, int(m.group("M")), int(m.group("S")))
    return (local - _tz_offset(m.group("tz"))).replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


# ---------- JSON (streamed) ----------

def iter_json_array(stream) -> Iterator[dict]:
    decoder = json.JSONDecoder()
    buf, pos, started, eof = "", 0, False, False
    while True:
        if not eof:
            chunk = stream.read(CHUNK)
            eof = not chunk
            buf = buf[pos:] + (chunk or "")
            pos = 0
        if not started:
            stripped = buf.lstrip("\ufeff \t\r\n")
            if not stripped:
                if eof:
                    raise TakeoutError("Le fichier JSON est vide.")
                continue
            if stripped[0] != "[":
                raise TakeoutError("JSON invalide : une liste d'activités Gemini est attendue.")
            buf, pos, started = stripped[1:], 0, True
        while True:
            while pos < len(buf) and buf[pos] in " \t\r\n,":
                pos += 1
            if pos < len(buf) and buf[pos] == "]":
                return
            if pos >= len(buf):
                break
            try:
                obj, end = decoder.raw_decode(buf, pos)
            except json.JSONDecodeError:
                if eof:
                    raise TakeoutError("JSON invalide ou tronqué.")
                break
            pos = end
            if isinstance(obj, dict):
                yield obj
        if eof:
            raise TakeoutError("JSON tronqué : fin de liste manquante.")


def entry_from_json(obj: dict) -> Entry | None:
    prompt = _strip_prefix(obj.get("title", ""))
    if prompt is None:
        subs = [s.get("value") or s.get("name") or "" for s in obj.get("subtitles") or [] if isinstance(s, dict)]
        prompt = "\n".join(s for s in subs if s).strip()
    response = "\n\n".join(html_to_md(i.get("html", "")) for i in obj.get("safeHtmlItem") or [] if isinstance(i, dict))
    files = [f if isinstance(f, str) else (f.get("name") or "") for f in obj.get("attachedFiles") or []]
    try:
        when = datetime.fromisoformat(str(obj.get("time", "")).replace("Z", "+00:00"))
    except ValueError:
        return None
    if not prompt and not response.strip():
        return None
    return Entry(_iso(when), prompt, response.strip(), [f for f in files if f])


# ---------- HTML (streamed by activity cell) ----------

CELL_MARK = '<div class="outer-cell'
BODY_CELL_RE = re.compile(r'<div class="content-cell[^"]*mdl-typography--body-1(?![^"]*text-right)[^"]*">', re.I)
NEXT_CELL_RE = re.compile(r'<div class="content-cell', re.I)
BR_RE = re.compile(r"<br\s*/?>", re.I)


def entry_from_html_cell(cell: str) -> Entry | None:
    start = BODY_CELL_RE.search(cell)
    if not start:
        return None
    nxt = NEXT_CELL_RE.search(cell, start.end())
    body = cell[start.end(): nxt.start() if nxt else len(cell)]
    body = body[: body.rfind("</div>")] if "</div>" in body else body
    parts = BR_RE.split(body)
    for i, part in enumerate(parts):
        when = parse_display_date(re.sub(r"<[^>]+>", "", part))
        if when:
            head = html_lib.unescape(re.sub(r"<[^>]+>", "", "\n".join(parts[:i]))).strip()
            file_re = r"(?:Attached|Fichier joint|Pièce jointe)\s*:\s*([^\n<]+)"
            files = re.findall(file_re, head)
            prompt = _strip_prefix(re.sub(file_re, "", head).strip())
            response = html_to_md("<br>".join(parts[i + 1:]))
            prompt = prompt if prompt is not None else ""
            if not prompt and not response:
                return None
            return Entry(_iso(when), prompt, response, [f.strip() for f in files])
    return None


def iter_html_entries(stream) -> Iterator[Entry]:
    buf = ""
    seen_cell = False
    while True:
        chunk = stream.read(CHUNK)
        buf += chunk or ""
        cells = buf.split(CELL_MARK)
        buf = cells.pop() if chunk else ""
        for c in cells[1:] if not seen_cell else cells:
            e = entry_from_html_cell(c)
            if e:
                yield e
        if cells:
            seen_cell = True
        if not chunk:
            if buf:
                e = entry_from_html_cell(buf)
                if e:
                    yield e
            return


# ---------- sources ----------

def _open_member(path: Path) -> tuple[io.TextIOBase, str]:
    with open(path, "rb") as fh:
        is_zip = fh.read(4) == b"PK\x03\x04"
    if is_zip:
        try:
            zf = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            raise TakeoutError("Archive .zip invalide ou corrompue.")
        names = [n for n in zf.namelist() if ACTIVITY_FILE_RE.search(n)]
        gem = [n for n in names if re.search(r"gemini|bard", n, re.I)] or names
        if not gem:
            raise TakeoutError("Aucun fichier d'activité Gemini trouvé dans l'archive "
                               "(attendu : Takeout/My Activity/Gemini Apps/MyActivity.json ou .html).")
        name = sorted(gem, key=lambda n: (not n.lower().endswith(".json"), len(n)))[0]
        return io.TextIOWrapper(zf.open(name), encoding="utf-8", errors="replace"), \
            "json" if name.lower().endswith(".json") else "html"
    stream = open(path, "r", encoding="utf-8", errors="replace")
    head = stream.read(2048).lstrip("\ufeff \t\r\n")
    stream.seek(0)
    if head.startswith("["):
        return stream, "json"
    if head.startswith("<"):
        return stream, "html"
    stream.close()
    raise TakeoutError("Format non reconnu. Importez l'archive Takeout (.zip), MyActivity.json ou MyActivity.html.")


def parse_takeout(path: Path) -> list[Entry]:
    stream, kind = _open_member(path)
    with stream:
        if kind == "json":
            entries = [e for e in (entry_from_json(o) for o in iter_json_array(stream)) if e]
        else:
            entries = list(iter_html_entries(stream))
    if not entries:
        raise TakeoutError("Aucune conversation Gemini trouvée dans ce fichier.")
    return entries


def group_entries(entries: list[Entry]) -> list[dict]:
    unique = {e.key: e for e in entries}
    ordered = sorted(unique.values(), key=lambda e: e.time)
    groups: list[list[Entry]] = []
    last = None
    for e in ordered:
        t = datetime.fromisoformat(e.time)
        if not groups or t - last > CONVERSATION_GAP or len(groups[-1]) >= MAX_GROUP_ENTRIES:
            groups.append([])
        groups[-1].append(e)
        last = t
    out = []
    for g in groups:
        first_prompt = next((e.prompt for e in g if e.prompt), "") or "Discussion importée"
        title = re.sub(r"\s+", " ", first_prompt).strip()
        out.append({
            "key": g[0].key,
            "title": title[:70] + ("…" if len(title) > 70 else ""),
            "start": g[0].time,
            "end": g[-1].time,
            "entries": [{**asdict(e), "key": e.key} for e in g],
        })
    return out
