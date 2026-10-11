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

        # Insertion avec gestion des doublons (ON CONFLICT DO NOTHING)
        cursor.execute(
            """
                INSERT INTO annonces (lien, prix, titre, image_url, type_article)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (lien) DO NOTHING;
            """,
            (lien, prix, titre, image_url, type_article),
        )

        # rowcount > 0 signifie que l'insertion a réussi (donc l'annonce est nouvelle)
        inserted = cursor.rowcount > 0
        conn.commit()
        cursor.close()
        conn.close()
        return inserted
    except Exception as e:
        print(f"Erreur écriture DB Supabase: {e}")
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
            SELECT lien, prix, titre, image_url, type_article, date_ajout 
            FROM annonces 
            ORDER BY date_ajout DESC 
            LIMIT 300
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        annonces = []
        if rows:
            for idx, r in enumerate(rows):
                lien_art, prix_achat, titre_art, img_art, type_art = r[0], r[1], r[2], r[3], r[4]

                frais_vinted = 0.70 + (prix_achat * 0.05)
                frais_port = 3.50
                cout_total = round(prix_achat + frais_vinted + frais_port, 2)

                annonces.append({
                    "id": idx,
                    "lien": lien_art,
                    "prix": prix_achat,
                    "titre": titre_art,
                    "image_url": img_art,
                    "type_article": type_art,
                    "cout_total": cout_total,
                    "date_ajout": str(r[5])
                })
        return jsonify(annonces)
    except Exception as e:
        print(f"Erreur API annonces: {e}")
        return jsonify([]), 500

# ------------------------------------------------------------------
# FONCTIONS TELEGRAM & SCRAPING (PLAYWRIGHT)
# ------------------------------------------------------------------
def envoyer_telegram(titre, prix, lien, image_url, type_article):
    try:
        frais_vinted = 0.70 + (prix * 0.05)
        frais_port = 3.50
        cout_total = round(prix + frais_vinted + frais_port, 2)
        
        message = (
            f"🚨 **Nouvelle pépite Vinted !**\n\n"
            f"🏷️ **{titre}**\n"
            f"📦 Type : {type_article}\n"
            f"💰 Prix article : {prix} €\n"
            f"💸 Coût total estimé : {cout_total} €\n"
            f"🔗 [Voir l'annonce]({lien})"
        )
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erreur envoi Telegram: {e}")

async def run_scraper():
    print("Démarrage du scraper Vinted (Supabase Cloud)...")
    while True:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                
                # Logique de scraping Vinted ici...
                
                await browser.close()
        except Exception as e:
            print(f"Erreur dans le scraper: {e}")
        
        await asyncio.sleep(DELAI_BOUCLE_SECONDES)

def demarrer_bot_en_arriere_plan():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_scraper())

if __name__ == "__main__":
    init_db()
    t = threading.Thread(target=demarrer_bot_en_arriere_plan, daemon=True)
    t.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
