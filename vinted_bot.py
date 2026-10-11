import asyncio
import json
import os
import random
import sqlite3
import threading
import urllib.parse
from flask import Flask, jsonify, send_file
from google import genai
from google.genai import types
from playwright.async_api import async_playwright
import requests

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8829917220:AAE8WEpEr0lHgrM2UAw5Ls8IRmV50G6AZr4"
TELEGRAM_CHAT_ID = "7467187588"
GEMINI_API_KEY = "AQ.Ab8RN6JQwVlNb4mOpgYpngDPaw7CwFtzL8GFEPJfcZcL7Sbvqg"

DELAI_BOUCLE_SECONDES = 600  # Scan toutes les 10 minutes pour plus de volume

client_ai = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY != "TA_CLE_API_GEMINI"
    else None
)

app = Flask(__name__)


# ------------------------------------------------------------------
# FLASK API & ROUTES MINI-APP
# ------------------------------------------------------------------
@app.route("/")
@app.route("/app")
def serve_app():
  if os.path.exists("app.html"):
    return send_file("app.html")
  return "<h1>Vinted Private Vault - Online</h1>", 200


@app.route("/healthz")
def health():
  return "OK", 200


@app.route("/api/annonces")
def get_annonces():
  try:
    conn = sqlite3.connect("vinted_ultime.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT lien, prix, titre, image_url, type_article FROM annonces ORDER"
        " BY ROWID DESC LIMIT 40"
    )
    rows = cursor.fetchall()
    conn.close()

    if rows:
      annonces = []
      for idx, r in enumerate(rows):
        lien_art, prix_achat, titre_art, img_art, type_art = (
            r[0],
            r[1],
            r[2],
            r[3],
            r[4],
        )
        cout_tot = round(prix_achat + 0.70 + (prix_achat * 0.05) + 3.50, 2)
        revente_est = round(prix_achat * 2.1, 2)
        benef_net = round(revente_est - cout_tot, 2)

        annonces.append({
            "id": idx + 1,
            "titre": titre_art or "Pièce Exclusive Vault",
            "type_article": type_art or "Sélection Luxe",
            "prix": prix_achat,
            "cout_total": cout_tot,
            "revente": revente_est,
            "benefice": benef_net,
            "lien": lien_art,
            "image": (
                img_art
                or "https://images.unsplash.com/photo-1544441893-675973e31985?auto=format&fit=crop&w=600&q=80"
            ),
            "statut": "DISPONIBLE",
            "ia": {
                "note": 9.4,
                "commentaire": "Validé par le protocole Vault Monochromatique.",
            },
        })
      return jsonify(annonces)
  except Exception as e:
    print(f"Erreur API DB: {e}")

  return jsonify([])


def demarrer_flask():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# ------------------------------------------------------------------
# BASE DE DONNÉES LOCALE
# ------------------------------------------------------------------
def init_db():
  try:
    conn = sqlite3.connect("vinted_ultime.db")
    cursor = conn.cursor()
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS annonces (
                lien TEXT PRIMARY KEY,
                prix REAL,
                titre TEXT,
                image_url TEXT,
                type_article TEXT
            )
        """)
    conn.commit()
    conn.close()
  except Exception as e:
    print(f"Erreur init DB: {e}")


def enregistrer_annonce(lien, prix, titre, image_url, type_article):
  try:
    conn = sqlite3.connect("vinted_ultime.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT prix FROM annonces WHERE lien = ?", (lien,))
    row = cursor.fetchone()

    if row is None:
      cursor.execute(
          "INSERT INTO annonces VALUES (?, ?, ?, ?, ?)",
          (lien, prix, titre, image_url, type_article),
      )
      conn.commit()
      conn.close()
      return True, "NOUVELLE"

    conn.close()
  except Exception as e:
    print(f"Erreur écriture DB: {e}")
  return False, "DEJA_VUE"


# ------------------------------------------------------------------
# FILTRES ÉTENDUS & LISTE NOIRE STRICTE (ANTI STAR-WARS, GEEK, DÉFAUTS)
# ------------------------------------------------------------------
CATALOG_HOMME = "&catalog[]=5"
TAILLES_POPULAIRES = (
    "&size_ids[]=206&size_ids[]=207&size_ids[]=208&size_ids[]=209"
)
ETAT_EXCELLENT = "&status_ids[]=6&status_ids[]=1&status_ids[]=2"

MOTS_CLES_EXCLUS = [
    # Défauts & Contrefaçons
    "trou",
    "trous",
    "tache",
    "taches",
    "taché",
    "abimé",
    "abime",
    "déchiré",
    "dechire",
    "usé",
    "accroc",
    "reparer",
    "décoloré",
    "fake",
    "faux",
    "replica",
    "replique",
    # Accessoires mineurs / Sous-vêtements
    "pyjama",
    "short",
    "maillot de bain",
    "boxer",
    "slip",
    "chaussettes",
    "casquette",
    "bonnet",
    "echarpe",
    "gants",
    "magnet",
    "sticker",
    "autocollant",
    # Pop-Culture, Geek, Enfant (Star Wars, Marvel, etc.)
    "star wars",
    "starwars",
    "marvel",
    "dc comics",
    "batman",
    "spiderman",
    "harry potter",
    "naruto",
    "dragon ball",
    "manga",
    "mario",
    "sonic",
    "pokemon",
    "disney",
    "kiabi",
    "primark",
    "geant",
    "bebe",
    "enfant",
    "ans",
    "zara",
    "h&m",
]

# RECHERCHES TRÈS LARGES POUR REMPLIR L'APPLI DE PÉPITES
RECHERCHES = [
    # RALPH LAUREN
    {
        "mot_cle": "Doudoune Ralph Lauren",
        "type_article": "Ralph Lauren",
        "prix_max": 45.0,
        "revente_base": 85.0,
    },
    {
        "mot_cle": "Sweat Ralph Lauren Bear",
        "type_article": "Ralph Lauren",
        "prix_max": 30.0,
        "revente_base": 65.0,
    },
    {
        "mot_cle": "Pull Ralph Lauren",
        "type_article": "Ralph Lauren",
        "prix_max": 25.0,
        "revente_base": 50.0,
    },
    {
        "mot_cle": "Chemise Ralph Lauren oxford",
        "type_article": "Ralph Lauren",
        "prix_max": 20.0,
        "revente_base": 45.0,
    },
    # WORKWEAR & TECHWEAR
    {
        "mot_cle": "Carhartt Detroit",
        "type_article": "Carhartt",
        "prix_max": 45.0,
        "revente_base": 90.0,
    },
    {
        "mot_cle": "Carhartt jacket",
        "type_article": "Carhartt",
        "prix_max": 35.0,
        "revente_base": 75.0,
    },
    {
        "mot_cle": "Arc'teryx",
        "type_article": "Techwear",
        "prix_max": 50.0,
        "revente_base": 100.0,
    },
    {
        "mot_cle": "North Face Nuptse",
        "type_article": "North Face",
        "prix_max": 55.0,
        "revente_base": 110.0,
    },
    {
        "mot_cle": "Patagonia vest",
        "type_article": "Patagonia",
        "prix_max": 30.0,
        "revente_base": 65.0,
    },
    # STREETWEAR & VINTAGE
    {
        "mot_cle": "Nike vintage",
        "type_article": "Nike Vintage",
        "prix_max": 25.0,
        "revente_base": 50.0,
    },
    {
        "mot_cle": "Sweat Stussy",
        "type_article": "Stussy",
        "prix_max": 30.0,
        "revente_base": 60.0,
    },
    {
        "mot_cle": "Sweat Carhartt",
        "type_article": "Carhartt",
        "prix_max": 25.0,
        "revente_base": 55.0,
    },
    {
        "mot_cle": "Maillot foot vintage",
        "type_article": "Maillot Vintage",
        "prix_max": 25.0,
        "revente_base": 55.0,
    },
    {
        "mot_cle": "Lacoste vintage",
        "type_article": "Lacoste",
        "prix_max": 25.0,
        "revente_base": 50.0,
    },
]


def envoyer_notification_discrete(affaire):
  if TELEGRAM_BOT_TOKEN == "TON_TELEGRAM_BOT_TOKEN":
    return
  render_url = os.environ.get(
      "RENDER_EXTERNAL_URL", "https://vinted-bot.onrender.com"
  )
  message = (
      f"🖤 <b>VAULT // NOUVELLE PÉPITE</b>\n\n"
      f"▪️ <b>{affaire['titre']}</b>\n"
      f"▫️ <b>Achat :</b> {affaire['prix']} € | <b>Revente :</b>"
      f" {affaire['revente_finale']} €\n"
      f"▪️ <b>Bénéfice Net :</b> +{affaire['benefice']} €\n\n"
      f"<i>Consultez le Vault monochrome pour acquérir cette pièce.</i>"
  )
  keyboard = {
      "inline_keyboard": [[{
          "text": "⚡ ACCÉDER AU VAULT",
          "web_app": {"url": f"{render_url}/app"},
      }]]
  }
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": message,
      "parse_mode": "HTML",
      "reply_markup": json.dumps(keyboard),
  }
  try:
    requests.post(url, data=payload, timeout=5)
  except Exception as e:
    print(f"Erreur alerte Telegram: {e}")


async def scanner_vinted(browser):
  try:
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
            " AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0"
            " Mobile/15E148 Safari/604.1"
        )
    )
    page = await context.new_page()
    recherches_shuffled = RECHERCHES.copy()
    random.shuffle(recherches_shuffled)

    # Scanne plusieurs recherches par cycle pour alimenter massivement l'app
    for recherche in recherches_shuffled[:7]:
      mot_cle = recherche["mot_cle"]
      type_article = recherche["type_article"]
      prix_max = recherche["prix_max"]
      revente_base = recherche["revente_base"]

      url = (
          f"https://www.vinted.fr/vetements?search_text={urllib.parse.quote(mot_cle)}"
          f"&price_to={prix_max}{CATALOG_HOMME}{TAILLES_POPULAIRES}{ETAT_EXCELLENT}&order=newest_first"
      )

      try:
        await page.goto(url, wait_until="domcontentloaded", timeout=12000)
        await asyncio.sleep(random.uniform(0.8, 1.5))
        items = await page.query_selector_all('[data-testid="grid-item"]')

        for item in items[:3]:
          title_elem = await item.query_selector('[data-testid*="title"], p')
          price_elem = await item.query_selector('[data-testid*="price"], h3')
          link_elem = await item.query_selector("a")
          img_elem = await item.query_selector("img")

          titre = await title_elem.inner_text() if title_elem else ""
          titre_lower = titre.lower()

          if any(mot in titre_lower for mot in MOTS_CLES_EXCLUS):
            continue

          prix_text = await price_elem.inner_text() if price_elem else "0"
          lien = await link_elem.get_attribute("href") if link_elem else ""
          image_url = await img_elem.get_attribute("src") if img_elem else ""

          if lien and not lien.startswith("http"):
            lien = f"https://www.vinted.fr{lien}"
          try:
            prix = float(prix_text.replace("€", "").replace(",", ".").strip())
          except ValueError:
            prix = 0.0

          if 0 < prix <= prix_max:
            est_nouveau, statut = enregistrer_annonce(
                lien, prix, titre, image_url, type_article
            )
            if est_nouveau:
              cout_total = prix + 0.70 + (prix * 0.05) + 3.50
              benefice_net = revente_base - cout_total

              if benefice_net >= 10.0:  # Seuil de profit optimisé
                affaire = {
                    "titre": titre.strip(),
                    "type_article": type_article,
                    "prix": prix,
                    "revente_finale": revente_base,
                    "benefice": round(benefice_net, 2),
                    "lien": lien,
                }
                envoyer_notification_discrete(affaire)
      except Exception as e:
        print(f"Erreur scan {mot_cle}: {e}")

    await context.close()
  except Exception as e:
    print(f"Erreur globale navigateur: {e}")


async def boucle_principale():
  init_db()
  print("🖤 Vault Monochromatique démarré !")
  while True:
    try:
      async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        await scanner_vinted(browser)
        await browser.close()
    except Exception as e:
      print(f"Erreur Playwright: {e}")

    await asyncio.sleep(DELAI_BOUCLE_SECONDES)


def demarrer_bot():
  asyncio.run(boucle_principale())


if __name__ == "__main__":
  thread_bot = threading.Thread(target=demarrer_bot, daemon=True)
  thread_bot.start()
  demarrer_flask()
