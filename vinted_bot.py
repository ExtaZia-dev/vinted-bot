import asyncio
import json
import os
import random
import threading
import urllib.parse
from flask import Flask, jsonify, send_file
from playwright.async_api import async_playwright
import psycopg2
import requests

# ------------------------------------------------------------------
# CONFIGURATION VAULT ULTIMATE & SUPABASE CLOUD
# ------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8829917220:AAE8WEpEr0lHgrM2UAw5Ls8IRmV50G6AZr4"
TELEGRAM_CHAT_ID = "7467187588"

DELAI_BOUCLE_SECONDES = 300  # Scan toutes les 5 minutes

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL")

# ------------------------------------------------------------------
# BASE DE DONNÉES PostgreSQL (SUPABASE)
# ------------------------------------------------------------------
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS annonces (
                lien TEXT PRIMARY KEY,
                prix REAL,
                titre TEXT,
                image_url TEXT,
                type_article TEXT,
                date_ajout TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ [DB] Supabase connectée et initialisée avec succès !")
    except Exception as e:
        print(f"❌ [DB] Erreur Init Supabase: {e}")

def enregistrer_annonce(lien, prix, titre, image_url, type_article):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
                INSERT INTO annonces (lien, prix, titre, image_url, type_article)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (lien) DO NOTHING;
            """,
            (lien, prix, titre, image_url, type_article),
        )
        inserted = cursor.rowcount > 0
        conn.commit()
        cursor.close()
        conn.close()
        return inserted
    except Exception as e:
        print(f"❌ [DB] Erreur écriture Supabase: {e}")
    return False

# ------------------------------------------------------------------
# API FLASK
# ------------------------------------------------------------------
@app.route("/")
@app.route("/app")
def serve_app():
    if os.path.exists("app.html"):
        return send_file("app.html")
    return "<h1>VAULT // Core System Online</h1>", 200

@app.route("/healthz")
def health():
    return "OK", 200

@app.route("/api/annonces")
def get_annonces():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT lien, prix, titre, image_url, type_article 
            FROM annonces 
            ORDER BY date_ajout DESC 
            LIMIT 300
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if rows:
            annonces = []
            for idx, r in enumerate(rows):
                lien_art, prix_achat, titre_art, img_art, type_art = r[0], r[1], r[2], r[3], r[4]
                frais_vinted = 0.70 + (prix_achat * 0.05)
                cout_total = round(prix_achat + frais_vinted + 3.50, 2)
                revente_est = round(prix_achat * 2.1, 2)
                if revente_est < prix_achat + 20.0:
                    revente_est = round(prix_achat + 25.0, 2)

                benef_net = round(revente_est - cout_total, 2)

                annonces.append({
                    "id": idx + 1,
                    "titre": titre_art or "Article Sélectionné",
                    "type_article": type_art or "Nouveauté",
                    "prix": prix_achat,
                    "cout_total": cout_total,
                    "revente": revente_est,
                    "benefice": benef_net,
                    "lien": lien_art,
                    "image": img_art or "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&w=600&q=80",
                })
            return jsonify(annonces)
    except Exception as e:
        print(f"❌ [API] Erreur lecture DB: {e}")

    return jsonify([])

# ------------------------------------------------------------------
# RECHERCHES ET SCRAPING
# ------------------------------------------------------------------
RECHERCHES = [
    {"mot_cle": "Nike Dunk", "type_article": "Sneakers", "prix_max": 60.0, "revente_base": 110.0},
    {"mot_cle": "Jordan 4", "type_article": "Sneakers", "prix_max": 90.0, "revente_base": 170.0},
    {"mot_cle": "Ralph Lauren", "type_article": "Vetement", "prix_max": 35.0, "revente_base": 75.0},
    {"mot_cle": "Carhartt", "type_article": "Vetement", "prix_max": 45.0, "revente_base": 90.0},
    {"mot_cle": "Stussy", "type_article": "Streetwear", "prix_max": 35.0, "revente_base": 75.0},
]

MOTS_CLES_EXCLUS = ["trou", "tache", "fake", "copie", "abime", "replique"]

def envoyer_notification_telegram(affaire):
    message = (
        f"🖤 <b>VAULT // NOUVELLE PÉPITE DETECTÉE</b>\n\n"
        f"▪️ <b>{affaire['titre']}</b>\n"
        f"▫️ <b>Achat :</b> {affaire['prix']} € | <b>Revente :</b> {affaire['revente_finale']} €\n"
        f"▪️ <b>Bénéfice Net :</b> +{affaire['benefice']} €\n\n"
        f"<i>Article sauvegardé dans le Vault.</i>"
    )
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://vinted-bot-dptd.onrender.com")
    keyboard = {"inline_keyboard": [[{"text": "⚡ ACCÉDER AU VAULT", "web_app": {"url": f"{render_url}/app"}}]]}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML", "reply_markup": json.dumps(keyboard)}, timeout=5)
        print("📩 [TELEGRAM] Notification envoyée !")
    except Exception as e:
        print(f"❌ [TELEGRAM] Erreur d'envoi: {e}")

async def scanner_vinted(browser):
    print("🔍 [SCRAPER] Démarrage d'un cycle de scan Vinted...")
    try:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
            }
        )
        page = await context.new_page()

        for recherche in RECHERCHES:
            mot_cle = recherche["mot_cle"]
            prix_max = recherche["prix_max"]
            type_article = recherche["type_article"]
            revente_base = recherche["revente_base"]

            url = f"https://www.vinted.fr/vetements?search_text={urllib.parse.quote(mot_cle)}&price_to={prix_max}&order=newest_first"
            print(f"👉 [SCAN] Recherche : '{mot_cle}' (max {prix_max}€)...")

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

                items = await page.query_selector_all('[data-testid="grid-item"]')
                print(f"   -> {len(items)} articles détectés sur la page.")

                for item in items[:8]:
                    title_elem = await item.query_selector('[data-testid*="title"], p')
                    price_elem = await item.query_selector('[data-testid*="price"], h3')
                    link_elem = await item.query_selector("a")
                    img_elem = await item.query_selector("img")

                    titre = await title_elem.inner_text() if title_elem else ""
                    if any(m in titre.lower() for m in MOTS_CLES_EXCLUS):
                        continue

                    prix_text = await price_elem.inner_text() if price_elem else "0"
                    lien = await link_elem.get_attribute("href") if link_elem else ""
                    image_url = await img_elem.get_attribute("src") if img_elem else ""

                    if lien and not lien.startswith("http"):
                        lien = f"https://www.vinted.fr{lien}"

                    try:
                        prix = float(prix_text.replace("€", "").replace(",", ".").replace(" ", "").strip())
                    except ValueError:
                        prix = 0.0

                    if 0 < prix <= prix_max and lien:
                        est_nouveau = enregistrer_annonce(lien, prix, titre, image_url, type_article)
                        if est_nouveau:
                            print(f"✨ [NOUVEAU] Article trouvé : {titre} - {prix}€")
                            frais = 0.70 + (prix * 0.05) + 3.50
                            benefice = round(revente_base - (prix + frais), 2)
                            
                            affaire = {
                                "titre": titre.strip(),
                                "prix": prix,
                                "revente_finale": revente_base,
                                "benefice": benefice,
                                "lien": lien
                            }
                            envoyer_notification_telegram(affaire)

            except Exception as e:
                print(f"⚠️ [SCAN] Erreur sur '{mot_cle}': {e}")

        await context.close()
    except Exception as e:
        print(f"❌ [SCRAPER] Erreur globale: {e}")

async def boucle_principale():
    init_db()
    print("🚀 [SYSTEM] Vault Engine activé !")
    while True:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--single-process",
                        "--no-zygote",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                await scanner_vinted(browser)
                await browser.close()
        except Exception as e:
            print(f"❌ [PLAYWRIGHT] Erreur lancement: {e}")

        print(f"💤 [SYSTEM] Pause de {DELAI_BOUCLE_SECONDES} secondes...")
        await asyncio.sleep(DELAI_BOUCLE_SECONDES)

def demarrer_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(boucle_principale())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    thread_bot = threading.Thread(target=demarrer_bot, daemon=True)
    thread_bot.start()
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
