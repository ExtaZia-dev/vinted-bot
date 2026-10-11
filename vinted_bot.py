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

DELAI_BOUCLE_SECONDES = 480  # Scan toutes les 8 minutes

app = Flask(__name__)

# Récupération de l'URL Supabase depuis l'environnement Render
DATABASE_URL = os.environ.get("DATABASE_URL")

# ------------------------------------------------------------------
# BASE DE DONNÉES PostgreSQL (SUPABASE PERMANENTE)
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
        print("Base de données Supabase connectée et initialisée !")
    except Exception as e:
        print(f"Erreur DB Init (Supabase): {e}")

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
        print(f"Erreur écriture DB Supabase: {e}")
    return False

# ------------------------------------------------------------------
# API FLASK POUR LA MINI-APP TELEGRAM
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
                lien_art, prix_achat, titre_art, img_art, type_art = (
                    r[0],
                    r[1],
                    r[2],
                    r[3],
                    r[4],
                )

                frais_vinted = 0.70 + (prix_achat * 0.05)
                frais_port = 3.50
                cout_total = round(prix_achat + frais_vinted + frais_port, 2)

                coef_revente = 2.2 if "Sneakers" in str(type_art) else 2.1
                revente_est = round(prix_achat * coef_revente, 2)
                if revente_est < prix_achat + 25.0:
                    revente_est = round(prix_achat + 30.0, 2)

                benef_net = round(revente_est - cout_total, 2)

                annonces.append({
                    "id": idx + 1,
                    "titre": titre_art or "Pièce Exclusive Vault",
                    "type_article": type_art or "Sélection Luxe",
                    "prix": prix_achat,
                    "cout_total": cout_total,
                    "revente": revente_est,
                    "benefice": benef_net,
                    "lien": lien_art,
                    "image": (
                        img_art
                        or "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&w=600&q=80"
                    ),
                })
            return jsonify(annonces)
    except Exception as e:
        print(f"Erreur API DB: {e}")

    return jsonify([])

# ------------------------------------------------------------------
# CONFIGURATION DES RECHERCHES & FILTRES
# ------------------------------------------------------------------
CATALOG_HOMME = "&catalog[]=5"
CATALOG_CHAUSSURES = "&catalog[]=1231"
TAILLES_HABITS = "&size_ids[]=206&size_ids[]=207&size_ids[]=208&size_ids[]=209"
TAILLES_SNEAKERS = "&size_ids[]=778&size_ids[]=779&size_ids[]=780&size_ids[]=781"
ETAT_EXCELLENT = "&status_ids[]=6&status_ids[]=1&status_ids[]=2"

MOTS_CLES_EXCLUS = [
    "trou", "trous", "tache", "taches", "taché", "abimé", "abime", "déchiré", "dechire", 
    "usé", "accroc", "reparer", "décoloré", "semelle usée", "fake", "faux", "replica", 
    "replique", "ua quality", "pyjama", "short", "maillot de bain", "boxer", "slip", 
    "chaussettes", "casquette", "bonnet", "echarpe", "gants", "star wars", "starwars", 
    "marvel", "dc comics", "batman", "spiderman", "harry potter", "naruto", "dragon ball", 
    "manga", "mario", "pokemon", "disney", "kiabi", "primark", "zara", "h&m"
]

RECHERCHES = [
    {
        "mot_cle": "Nike Dunk Low",
        "type_article": "Sneakers",
        "prix_max": 50.0,
        "revente_base": 100.0,
        "cat": CATALOG_CHAUSSURES,
        "size": TAILLES_SNEAKERS,
    },
    {
        "mot_cle": "Jordan 4",
        "type_article": "Sneakers",
        "prix_max": 80.0,
        "revente_base": 160.0,
        "cat": CATALOG_CHAUSSURES,
        "size": TAILLES_SNEAKERS,
    },
    {
        "mot_cle": "Doudoune Ralph Lauren",
        "type_article": "Ralph Lauren",
        "prix_max": 50.0,
        "revente_base": 110.0,
        "cat": CATALOG_HOMME,
        "size": TAILLES_HABITS,
    },
    {
        "mot_cle": "Carhartt Detroit Jacket",
        "type_article": "Carhartt",
        "prix_max": 50.0,
        "revente_base": 110.0,
        "cat": CATALOG_HOMME,
        "size": TAILLES_HABITS,
    },
]

def envoyer_notification_telegram(affaire):
    if TELEGRAM_BOT_TOKEN == "TON_TELEGRAM_BOT_TOKEN":
        return
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://vinted-bot.onrender.com")
    message = (
        f"🖤 <b>VAULT // NOUVELLE PÉPITE DETECTÉE</b>\n\n"
        f"▪️ <b>{affaire['titre']}</b>\n"
        f"▫️ <b>Achat :</b> {affaire['prix']} € | <b>Revente :</b> {affaire['revente_finale']} €\n"
        f"▪️ <b>Bénéfice Net :</b> +{affaire['benefice']} €\n\n"
        f"<i>Consultez le Vault pour verrouiller l'achat.</i>"
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        recherches_shuffled = RECHERCHES.copy()
        random.shuffle(recherches_shuffled)

        for recherche in recherches_shuffled:
            mot_cle = recherche["mot_cle"]
            type_article = recherche["type_article"]
            prix_max = recherche["prix_max"]
            revente_base = recherche["revente_base"]
            cat = recherche.get("cat", CATALOG_HOMME)
            size = recherche.get("size", TAILLES_HABITS)

            url = (
                f"https://www.vinted.fr/vetements?search_text={urllib.parse.quote(mot_cle)}"
                f"&price_to={prix_max}{cat}{size}{ETAT_EXCELLENT}&order=newest_first"
            )

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=12000)
                await asyncio.sleep(random.uniform(0.5, 1.0))
                items = await page.query_selector_all('[data-testid="grid-item"]')

                for item in items[:10]:
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
                        est_nouveau = enregistrer_annonce(
                            lien, prix, titre, image_url, type_article
                        )
                        if est_nouveau:
                            frais = 0.70 + (prix * 0.05) + 3.50
                            benefice_net = revente_base - (prix + frais)

                            if benefice_net >= 12.0:
                                affaire = {
                                    "titre": titre.strip(),
                                    "type_article": type_article,
                                    "prix": prix,
                                    "revente_finale": revente_base,
                                    "benefice": round(benefice_net, 2),
                                    "lien": lien,
                                }
                                envoyer_notification_telegram(affaire)
            except Exception as e:
                print(f"Erreur scan {mot_cle}: {e}")

        await context.close()
    except Exception as e:
        print(f"Erreur globale navigateur: {e}")

async def boucle_principale():
    init_db()
    print("🖤 Vault Ultimate Engine Active (Low Memory Mode)!")
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
                        "--disable-extensions",
                    ],
                )
                await scanner_vinted(browser)
                await browser.close()
        except Exception as e:
            print(f"Erreur Playwright: {e}")

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
