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

DELAI_BOUCLE_SECONDES = 900  # Scan toutes les 15 minutes

client_ai = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY != "TA_CLE_API_GEMINI"
    else None
)

# ------------------------------------------------------------------
# SERVEUR FLASK SÉCURISÉ (ANTI-502 BAD GATEWAY)
# ------------------------------------------------------------------
app = Flask(__name__)


@app.route("/")
@app.route("/app")
def serve_app():
  if os.path.exists("app.html"):
    return send_file("app.html")
  return "<h1>Vinted Copilot Private Vault actif</h1>", 200


@app.route("/healthz")
def health():
  return "OK", 200


@app.route("/api/annonces")
def get_annonces():
  try:
    conn = sqlite3.connect("vinted_ultime.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT lien, prix, titre FROM annonces ORDER BY ROWID DESC LIMIT 20"
    )
    rows = cursor.fetchall()
    conn.close()

    if rows:
      annonces = []
      for idx, r in enumerate(rows):
        prix_achat = r[1]
        cout_tot = round(prix_achat + 0.70 + (prix_achat * 0.05) + 3.50, 2)
        revente_est = round(prix_achat * 2.0, 2)
        benef_net = round(revente_est - cout_tot, 2)

        annonces.append({
            "id": idx + 1,
            "titre": r[2] or "Article Trending Vinted",
            "type_article": "Pépite Trouvée",
            "prix": prix_achat,
            "cout_total": cout_tot,
            "revente": revente_est,
            "benefice": benef_net,
            "lien": r[0],
            "image": (
                "https://images.unsplash.com/photo-1544441893-675973e31985?auto=format&fit=crop&w=600&q=80"
            ),
            "statut": "NOUVELLE",
            "ia": {
                "note": 9.0,
                "commentaire": "Détecté en direct lors du dernier scan.",
            },
        })
      return jsonify(annonces)
  except Exception as e:
    print(f"Erreur DB API: {e}")

  # FALLBACK DE SECOURS (Si DB vide)
  return jsonify([
      {
          "id": 1,
          "titre": "Doudoune Sans Manche Ralph Lauren",
          "type_article": "Ralph Lauren",
          "prix": 35.0,
          "cout_total": 39.20,
          "revente": 70.0,
          "benefice": 30.80,
          "lien": "https://www.vinted.fr",
          "image": (
              "https://images.unsplash.com/photo-1548883354-7622d03aca27?auto=format&fit=crop&w=600&q=80"
          ),
          "statut": "NOUVELLE",
          "ia": {
              "note": 9.5,
              "commentaire": "Logo brodé impeccable, aucun défaut.",
          },
      },
      {
          "id": 2,
          "titre": "Veste Carhartt Detroit Vintage",
          "type_article": "Carhartt",
          "prix": 40.0,
          "cout_total": 44.20,
          "revente": 85.0,
          "benefice": 40.80,
          "lien": "https://www.vinted.fr",
          "image": (
              "https://images.unsplash.com/photo-1551028719-00167b16eac5?auto=format&fit=crop&w=600&q=80"
          ),
          "statut": "NOUVELLE",
          "ia": {
              "note": 9.0,
              "commentaire": "Patine très demandée sur le marché.",
          },
      },
  ])


def demarrer_flask():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# ------------------------------------------------------------------
# BASE DE DONNÉES LOCALE SÉCURISÉE
# ------------------------------------------------------------------
def init_db():
  try:
    conn = sqlite3.connect("vinted_ultime.db")
    cursor = conn.cursor()
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS annonces (
                lien TEXT PRIMARY KEY,
                prix REAL,
                titre TEXT
            )
        """)
    conn.commit()
    conn.close()
  except Exception as e:
    print(f"Erreur init DB: {e}")


def est_nouvelle_ou_baisse_prix(lien, prix_actuel):
  try:
    conn = sqlite3.connect("vinted_ultime.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT prix FROM annonces WHERE lien = ?", (lien,))
    row = cursor.fetchone()

    if row is None:
      cursor.execute(
          "INSERT INTO annonces VALUES (?, ?, '')", (lien, prix_actuel)
      )
      conn.commit()
      conn.close()
      return True, "NOUVELLE"

    prix_ancien = row[0]
    if prix_actuel < prix_ancien:
      cursor.execute(
          "UPDATE annonces SET prix = ? WHERE lien = ?", (prix_actuel, lien)
      )
      conn.commit()
      conn.close()
      return True, f"BAISSE DE PRIX (-{round(prix_ancien - prix_actuel, 2)}€)"

    conn.close()
  except Exception as e:
    print(f"Erreur DB écriture: {e}")
  return False, "DEJA_VUE"


# ------------------------------------------------------------------
# FILTRES EXCLUSIFS, CIBLAGE HOMME & REVENTES RÉALISTES
# ------------------------------------------------------------------
CATALOG_HOMME = "&catalog[]=5"
TAILLES_POPULAIRES = (
    "&size_ids[]=206&size_ids[]=207&size_ids[]=208&size_ids[]=209"
)
ETAT_EXCELLENT = "&status_ids[]=6&status_ids[]=1&status_ids[]=2"

# Exclusions strictes (Anti-Défaut, Anti-Enfant, Anti-Pop Culture / Star Wars)
MOTS_CLES_EXCLUS = [
    "trou",
    "trous",
    "tache",
    "taches",
    "taché",
    "abimé",
    "abime",
    "déchiré",
    "dechire",
    "déchirure",
    "usé",
    "accroc",
    "reparer",
    "décoloré",
    "fake",
    "faux",
    "replica",
    "replique",
    "réplique",
    "magnet",
    "aimant",
    "sticker",
    "autocollant",
    "pyjama",
    "short",
    "maillot de bain",
    "sous-vêtement",
    "boxer",
    "slip",
    "chaussettes",
    "casquette",
    "bonnet",
    "echarpe",
    "gants",
    "mario",
    "sonic",
    "pokemon",
    "disney",
    "kiabi",
    "geant",
    "primark",
    "bebe",
    "enfant",
    "ans",
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
]

RECHERCHES = [
    {
        "mot_cle": "Doudoune Ralph Lauren",
        "type_article": "Ralph Lauren",
        "prix_max": 35.0,
        "revente_base": 70.0,
    },
    {
        "mot_cle": "Sweat Ralph Lauren Bear",
        "type_article": "Ralph Lauren",
        "prix_max": 25.0,
        "revente_base": 55.0,
    },
    {
        "mot_cle": "Pull Ralph Lauren cable",
        "type_article": "Ralph Lauren",
        "prix_max": 18.0,
        "revente_base": 40.0,
    },
    {
        "mot_cle": "Carhartt Detroit",
        "type_article": "Carhartt",
        "prix_max": 40.0,
        "revente_base": 85.0,
    },
    {
        "mot_cle": "Carhartt Active jacket",
        "type_article": "Carhartt",
        "prix_max": 30.0,
        "revente_base": 65.0,
    },
    {
        "mot_cle": "Arc'teryx jacket",
        "type_article": "Techwear",
        "prix_max": 45.0,
        "revente_base": 90.0,
    },
    {
        "mot_cle": "North Face Nuptse 700",
        "type_article": "North Face",
        "prix_max": 50.0,
        "revente_base": 95.0,
    },
    {
        "mot_cle": "Maillot Opel",
        "type_article": "Maillot Vintage",
        "prix_max": 20.0,
        "revente_base": 45.0,
    },
    {
        "mot_cle": "Maillot Pirelli",
        "type_article": "Maillot Vintage",
        "prix_max": 20.0,
        "revente_base": 45.0,
    },
    {
        "mot_cle": "Nike Center Logo",
        "type_article": "Nike Vintage",
        "prix_max": 20.0,
        "revente_base": 45.0,
    },
    {
        "mot_cle": "Sweat Stussy",
        "type_article": "Stussy",
        "prix_max": 25.0,
        "revente_base": 50.0,
    },
]


def analyser_article_avec_ia(image_url, titre, prix_achat, revente_base):
  if not client_ai or not image_url:
    return {
        "etat_visuel": "Très bon état",
        "note_etat": 8,
        "revente_ajustee": revente_base,
        "commentaire": "Analyse manuelle",
    }
  try:
    img_data = requests.get(image_url, timeout=4).content
    prompt = f"Analyse l'article '{titre}' (prix revente cible: {revente_base}€). Réponds en JSON strict : {{\"etat_visuel\": \"Très bon état\", \"note_etat\": 8, \"revente_ajustee\": {revente_base}, \"commentaire\": \"Superbe pièce\"}}"
    response = client_ai.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            types.Part.from_bytes(data=img_data, mime_type="image/jpeg"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )
    return json.loads(response.text)
  except Exception:
    return {
        "etat_visuel": "Bon état",
        "note_etat": 8,
        "revente_ajustee": revente_base,
        "commentaire": "Standard",
    }


def envoyer_alerte_telegram(affaire):
  if TELEGRAM_BOT_TOKEN == "TON_TELEGRAM_BOT_TOKEN":
    return
  ia = affaire.get("analyse_ia", {})
  message = (
      f"🚨 <b>{affaire['statut']} : {affaire['titre']}</b>\n\n"
      f"💰 <b>Achat :</b> {affaire['prix']} € | 📈 <b>Revente IA :</b>"
      f" {affaire['revente_finale']} €\n"
      f"💵 <b>BÉNÉFICE NET :</b> +{affaire['benefice']} €\n\n"
      f"🤖 <b>IA :</b> {ia.get('etat_visuel', 'OK')}"
      f" ({ia.get('note_etat', 8)}/10)"
  )
  render_url = os.environ.get(
      "RENDER_EXTERNAL_URL", "https://vinted-bot.onrender.com"
  )
  keyboard = {
      "inline_keyboard": [
          [
              {
                  "text": "📱 Ouvrir la Mini-App Vinted",
                  "web_app": {"url": f"{render_url}/app"},
              }
          ],
          [{"text": "🛒 Ouvrir la Fiche Vinted Direct", "url": affaire["lien"]}],
      ]
  }
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "photo": affaire.get("image_url", ""),
      "caption": message,
      "parse_mode": "HTML",
      "reply_markup": json.dumps(keyboard),
  }
  try:
    requests.post(url, data=payload, timeout=5)
  except Exception as e:
    print(f"Erreur Telegram: {e}")


async def scanner_vinted(browser):
  try:
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    page = await context.new_page()
    recherches_shuffled = RECHERCHES.copy()
    random.shuffle(recherches_shuffled)

    for recherche in recherches_shuffled[:4]:
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
        await asyncio.sleep(random.uniform(1.0, 2.0))
        items = await page.query_selector_all('[data-testid="grid-item"]')

        for item in items[:2]:
          title_elem = await item.query_selector('[data-testid*="title"], p')
          price_elem = await item.query_selector('[data-testid*="price"], h3')
          link_elem = await item.query_selector("a")
          img_elem = await item.query_selector("img")

          titre = await title_elem.inner_text() if title_elem else ""
          titre_lower = titre.lower()

          exclu_trouve = any(mot in titre_lower for mot in MOTS_CLES_EXCLUS)
          if exclu_trouve:
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

          est_valide_db, statut = est_nouvelle_ou_baisse_prix(lien, prix)
          if not est_valide_db:
            continue

          if 0 < prix <= prix_max:
            cout_total = prix + 0.70 + (prix * 0.05) + 3.50
            analyse_ia = analyser_article_avec_ia(
                image_url, titre, prix, revente_base
            )
            revente_finale = float(
                analyse_ia.get("revente_ajustee", revente_base)
            )
            benefice_net = revente_finale - cout_total

            if benefice_net >= 12.0:
              affaire = {
                  "titre": titre.strip(),
                  "type_article": type_article,
                  "prix": prix,
                  "cout_total": round(cout_total, 2),
                  "revente_finale": round(revente_finale, 2),
                  "benefice": round(benefice_net, 2),
                  "lien": lien,
                  "image_url": image_url,
                  "analyse_ia": analyse_ia,
                  "statut": statut,
              }
              envoyer_alerte_telegram(affaire)
      except Exception as e:
        print(f"Erreur scan {mot_cle}: {e}")

    await context.close()
  except Exception as e:
    print(f"Erreur globale navigateur: {e}")


async def boucle_principale():
  init_db()
  print("🚀 Bot Vinted anti-502 démarré !")
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
      print(f"Erreur instance Playwright: {e}")

    await asyncio.sleep(DELAI_BOUCLE_SECONDES)


def demarrer_bot():
  asyncio.run(boucle_principale())


if __name__ == "__main__":
  thread_bot = threading.Thread(target=demarrer_bot, daemon=True)
  thread_bot.start()
  demarrer_flask()
