"""Bot Telegram: notizie estere di calciomercato sulla AS Roma.
Usa solo la libreria standard di Python. Pensato per GitHub Actions."""
import html
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import re
from googlenewsdecoder import gnewsdecoder

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SEEN_FILE = "seen.json"
MAX_MESSAGES_PER_RUN = 10

# (lingua, paese, edizione, query di ricerca)
EDITIONS = [
    ("en-GB", "GB", "GB:en", '"AS Roma" (transfer OR signing OR loan OR bid OR deal)'),
    ("en-US", "US", "US:en", '"AS Roma" (transfer OR signing OR loan OR bid OR deal)'),
    ("es-ES", "ES", "ES:es", '"AS Roma" (fichaje OR traspaso OR cesión OR oferta)'),
    ("fr-FR", "FR", "FR:fr", '"AS Roma" (mercato OR transfert OR prêt OR offre)'),
    ("de-DE", "DE", "DE:de", '"AS Roma" (Transfer OR Wechsel OR Leihe OR Angebot)'),
    ("pt-PT", "PT", "PT:pt-150", '"AS Roma" (transferência OR contratação OR empréstimo)'),
    ("pt-BR", "BR", "BR:pt-419", '"AS Roma" (transferência OR contratação OR empréstimo)'),
    ("tr-TR", "TR", "TR:tr", '"AS Roma" (transfer OR bonservis OR kiralık)'),
    ("nl-NL", "NL", "NL:nl", '"AS Roma" (transfer OR overgenomen OR huur)'),
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, encoding="utf-8") as f:
            return json.load(f), False
    return [], True  # primo avvio


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen[-3000:], f, ensure_ascii=False)


def get_articles():
    articles = {}
    for hl, gl, ceid, query in EDITIONS:
        q = urllib.parse.quote(query + " when:1d")
        url = f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"
        try:
            root = ET.fromstring(fetch(url))
        except Exception as e:
            print(f"Errore su {hl}: {e}")
            continue
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link).strip()
            src = item.find("source")
            src_name = src.text if src is not None else ""
            src_url = src.get("url", "") if src is not None else ""
            if "roma" not in title.lower():
                continue
            host = urllib.parse.urlparse(src_url).hostname or ""
            if host.endswith(".it"):
                continue  # salta siti italiani
            articles[guid] = {"title": title, "link": link, "source": src_name, "lang": hl}
    return articles


def send(text):
    data = urllib.parse.urlencode(
        {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": "false"}
    ).encode()
    urllib.request.urlopen(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data, timeout=30
    )

def cita_testate_italiane(link):
    try:
        res = gnewsdecoder(link, interval=1)
        if not res.get("status"):
            return False
        page = fetch(res["decoded_url"]).decode("utf-8", errors="ignore").lower()
        page = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", page, flags=re.S)
        return any(k in page for k in ITALIAN_MENTIONS)
    except Exception:
        return False  # se non riesco a leggere, lascio passare


def main():
    seen, first_run = load_seen()
    seen_set = set(seen)
    articles = get_articles()
    new = [(g, a) for g, a in articles.items() if g not in seen_set]
    print(f"Trovati {len(articles)} articoli, {len(new)} nuovi")

    if first_run:
        # al primo avvio non invio il passato: segno tutto come visto
        send("✅ Bot AS Roma Mercato attivo! Da ora ti avviso sulle nuove notizie estere.")
    else:
        da_inviare = [(g, a) for g, a in new if not cita_testate_italiane(a["link"])]
        for g, a in da_inviare[:MAX_MESSAGES_PER_RUN]:
            msg = (
                f"🐺 <b>{html.escape(a['title'])}</b>\n"
                f"🌍 {html.escape(a['source'])} ({a['lang']})\n"
                f"{a['link']}"
            )
            try:
                send(msg)
                time.sleep(1)
            except Exception as e:
                print(f"Errore invio: {e}")

    seen.extend(g for g, _ in new)
    save_seen(seen)


if __name__ == "__main__":
    main()
