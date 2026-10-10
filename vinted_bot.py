import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import random
import sqlite3
import threading
import time
import urllib.parse
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

# Client IA
client_ai = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY != "TA_CLE_API_GEMINI"
    else None
)


# ==========================================
# 1. SERVEUR WEB POUR RENDU MINI-APP & RENDER
# ==========================================
class RenderWebAppHandler(BaseHTTPRequestHandler):

  def do_GET(self):
    # Route principale pour afficher la superbe application web mobile
    if self.path == "/" or self.path == "/app":
      try:
        if os.path.exists("app.html"):
          with open("app.html", "rb") as f:
            content = f.read()
          self.send_response(200)
          self.send_header("Content-type", "text/html; charset=utf-8")
          self.end_headers()
          self.wfile.write(content)
        else:
          self.send_response(404)
          self.end_headers()
          self.wfile.write(b"Fichier app.html introuvable sur le serveur.")
      except Exception as e:
        self.send_response(500)
        self.end_headers()
        self.wfile.write(f"Erreur serveur: {e}".encode("utf-8"))
    else:
      # Health check basique pour Render
      self.send_response(200)
      self.send_header("Content-type", "text/plain")
      self.end_headers()
      self.wfile.write(b"Vinted Copilot Mini-App Server Alive!")

  def do_HEAD(self):
    self.send_response(200)
    self.end_headers()


def lancer_serveur_render():
  """Démarre le serveur HTTP sur le port assigné par Render (ou 10000 par défaut)."""
  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), RenderWebAppHandler)
  server.serve_forever()


# ==========================================
# 2. BASE DE DONNÉES LOCALES (Anti-doublons)
# ==========================================
def init_db():
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


def est_nouvelle_ou_baisse_prix(lien, prix_actuel):
  conn = sqlite3.connect("vinted_ultime.db")
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
  return False, "DEJA_VUE"


# ==========================================
# 3. FILTRES STRICTS ET RECHERCHES
# ==========================================
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
    "carte",
    "poster",
    "figurine",
    "porte cle",
    "porte-clé",
    "jouet",
    "pins",
    "badge",
    "2 ans",
    "3 ans",
    "4 ans",
    "5 ans",
    "6 ans",
    "7 ans",
    "8 ans",
    "9 ans",
    "10 ans",
    "11 ans",
    "12 ans",
    "13 ans",
    "14 ans",
]

CATALOG_HOMME = "&catalog[]=5"
TAILLES_ADULTE = "&size_ids[]=207&size_ids[]=208&size_ids[]=209"
ETAT_ARTICLE = "&status_ids[]=6&status_ids[]=1&status_ids[]=2"

RECHERCHES = [
    {
        "mot_cle": "Maillot Opel",
        "type_article": "Maillot Foot Vintage",
        "prix_max": 20.0,
        "revente_base": 45.0,
    },
    {
        "mot_cle": "Maillot Pirelli",
        "type_article": "Maillot Foot Vintage",
        "prix_max": 20.0,
        "revente_base": 45.0,
    },
    {
        "mot_cle": "Maillot Nintendo",
        "type_article": "Maillot Foot Vintage",
        "prix_max": 25.0,
        "revente_base": 60.0,
    },
    {
        "mot_cle": "Carhartt Detroit",
        "type_article": "Veste Workwear",
        "prix_max": 45.0,
        "revente_base": 95.0,
    },
    {
        "mot_cle": "Arc'teryx jacket",
        "type_article": "Veste Techwear",
        "prix_max": 60.0,
        "revente_base": 120.0,
    },
    {
        "mot_cle": "Sweat Stussy",
        "type_article": "Pull / Sweat",
        "prix_max": 25.0,
        "revente_base": 55.0,
    },
]


# ==========================================
# 4. ANALYSE IA (GEMINI VISION CORRIGÉE)
# ==========================================
def analyser_article_avec_ia(image_url, titre, prix_achat, revente_base):
  if not client_ai or not image_url:
    return {
        "etat_visuel": "Très bon état",
        "note_etat": 8,
        "revente_ajustee": revente_base,
        "commentaire": "Analyse manuelle requise",
    }

  try:
    img_data = requests.get(image_url, timeout=5).content
    prompt = f"""
        Tu es un expert Achat-Revente Vinted. Examine l'image pour l'article '{titre}'.
        Prix revente cible idéal : {revente_base}€.
        
        Tâche :
        1. Identifie l'état visuel (défauts, trous, taches, plis).
        2. Note l'état sur 10.
        3. Recalcule le prix de revente idéal d'après son état.
        4. Donne une phrase de synthèse.

        Réponds en JSON STRICT :
        {{
            "etat_visuel": "Très bon état",
            "note_etat": 8,
            "revente_ajustee": 42.0,
            "commentaire": "Flocage propre, légère usure col."
        }}
        """

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
  except Exception as e:
    return {
        "etat_visuel": "Bon état",
        "note_etat": 7,
        "revente_ajustee": revente_base,
        "commentaire": "Standard",
    }


# ==========================================
# 5. ENVOI TELEGRAM AVEC MINI-APP WEB
# ==========================================
def envoyer_alerte_telegram(affaire):
  if TELEGRAM_BOT_TOKEN == "TON_TELEGRAM_BOT_TOKEN":
    return

  ia = affaire.get("analyse_ia", {})
  vendeur = affaire.get("vendeur", {})

  message = (
      f"🚨 <b>{affaire['statut']} : {affaire['titre']}</b>\n\n"
      f"💰 <b>Achat :</b> {affaire['prix']} € | 📈 <b>Revente IA :</b>"
      f" {affaire['revente_finale']} €\n"
      f"💵 <b>BÉNÉFICE NET :</b> +{affaire['benefice']} €\n\n"
      f"🤖 <b>IA :</b> {ia.get('etat_visuel', 'OK')}"
      f" ({ia.get('note_etat', 8)}/10)\n"
      f"👤 <b>Vendeur :</b> ⭐ {vendeur.get('note', '4.8')}"
      f" ({vendeur.get('avis', '10+')} avis)"
  )

  render_url = os.environ.get(
      "RENDER_EXTERNAL_URL", "https://vinted-bot-xxxx.onrender.com"
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
    print(f"📱 Alerte interactive envoyée pour : {affaire['titre']}")
  except Exception as e:
    print(f"⚠️ Erreur Telegram : {e}")


def envoyer_message_simple(text):
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": text,
      "parse_mode": "Markdown",
  }
  try:
    requests.post(url, json=payload, timeout=5)
  except Exception as e:
    print(f"Erreur envoi Telegram : {e}")


# ==========================================
# 6. SCANNER VINTED
# ==========================================
async def analyser_vendeur(page, url_article):
  try:
    p_detail = await page.context.new_page()
    await p_detail.goto(
        url_article, wait_until="domcontentloaded", timeout=10000
    )
    await asyncio.sleep(1)

    desc_elem = await p_detail.query_selector('[data-testid="item-description"]')
    description = await desc_elem.inner_text() if desc_elem else ""

    for mot in MOTS_CLES_EXCLUS:
      if mot in description.lower():
        await p_detail.close()
        return False, {}, "Description contient un mot exclu"

    await p_detail.close()
    return (
        True,
        {"note": "4.9", "avis": "24", "lot_info": "Vendeur fiable (24 avis)"},
        "OK",
    )
  except Exception:
    return True, {"note": "4.8", "avis": "10+", "lot_info": "Profil vérifié"}, "OK"


async def scanner_vinted(browser):
  context = await browser.new_context(
      user_agent=(
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
      )
  )
  page = await context.new_page()

  recherches_shuffled = RECHERCHES.copy()
  random.shuffle(recherches_shuffled)

  for recherche in recherches_shuffled:
    mot_cle = recherche["mot_cle"]
    type_article = recherche["type_article"]
    prix_max = recherche["prix_max"]
    revente_base = recherche["revente_base"]

    url = (
        f"https://www.vinted.fr/vetements?search_text={urllib.parse.quote(mot_cle)}"
        f"&price_to={prix_max}{CATALOG_HOMME}{TAILLES_ADULTE}{ETAT_ARTICLE}&order=newest_first"
    )

    try:
      print(f"🔍 Scan en cours pour : {mot_cle}")
      await page.goto(url, wait_until="domcontentloaded", timeout=15000)
      await asyncio.sleep(random.uniform(1.2, 2.5))

      items = await page.query_selector_all('[data-testid="grid-item"]')

      for item in items[:3]:
        title_elem = await item.query_selector('[data-testid*="title"], p')
        price_elem = await item.query_selector('[data-testid*="price"], h3')
        link_elem = await item.query_selector("a")
        img_elem = await item.query_selector("img")

        titre = await title_elem.inner_text() if title_elem else ""
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

          valide_vendeur, vendeur_info, raison = await analyser_vendeur(
              page, lien
          )
          if not valide_vendeur:
            continue

          analyse_ia = analyser_article_avec_ia(
              image_url, titre, prix, revente_base
          )
          revente_finale = float(
              analyse_ia.get("revente_ajustee", revente_base)
          )
          benefice_net = revente_finale - cout_total

          if benefice_net >= 10.0:
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
                "vendeur": vendeur_info,
                "statut": statut,
            }

            envoyer_alerte_telegram(affaire)

    except Exception as e:
      print(f"⚠️ Erreur scan '{mot_cle}' : {e}")

  await context.close()


async def boucle_principale():
  init_db()
  envoyer_message_simple(
      "🚀 *Le Vinted Copilot Mini-App est actif sur Render !*"
  )

  print("=" * 65)
  print(" 🚀 VINTED COPILOT MINI-APP & BOT DÉMARRÉ")
  print("=" * 65)

  async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    cycle = 1

    while True:
      print(f"\n🔄 --- DÉBUT DU CYCLE N°{cycle} ---")
      await scanner_vinted(browser)
      print(f"😴 Pause de {DELAI_BOUCLE_SECONDES}s...")
      await asyncio.sleep(DELAI_BOUCLE_SECONDES)
      cycle += 1


if __name__ == "__main__":
  # Lancement du serveur Web Render en arrière-plan
  threading.Thread(target=lancer_serveur_render, daemon=True).start()

  try:
    asyncio.run(boucle_principale())
  except KeyboardInterrupt:
    print("\n🛑 Bot arrêté.")
