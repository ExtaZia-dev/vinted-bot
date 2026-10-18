import asyncio
import json
import os
import random
import socket
import threading
import urllib.parse
from flask import Flask, jsonify, send_file
from playwright.async_api import async_playwright
import psycopg2
import requests

# ------------------------------------------------------------------
# CONFIGURATION SNIPESTUDIO
# ------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8829917220:AAE8WEpEr0lHgrM2UAw5Ls8IRmV50G6AZr4"
TELEGRAM_CHAT_ID = "7467187588"
DELAI_BOUCLE_SECONDES = 300  # Scan toutes les 5 minutes

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL")

# ------------------------------------------------------------------
# BASE DE DONNÉES (SUPABASE AVEC CONTOURNEMENT IPV4)
# ------------------------------------------------------------------
def get_db_connection():
    parsed_url = urllib.parse.urlparse(DATABASE_URL)
    hostname = parsed_url.hostname
    port = parsed_url.port or 6543
    
    ipv4_host = hostname
    try:
        addrs = socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM)
        if addrs:
            ipv4_host = addrs[0][4][0]
    except Exception as e:
        print(f"⚠️ [DB] Erreur résolution IPv4, utilisation du host par défaut: {e}", flush=True)

    return psycopg2.connect(
        host=ipv4_host,
        port=port,
        database=parsed_url.path.lstrip('/'),
        user=parsed_url.username,
        password=parsed_url.password
    )

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
                condition_score TEXT DEFAULT '9.0/10',
                offre_recommandee REAL,
                msg_nego TEXT,
                studio_poses JSONB,
                date_ajout TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ [DB] Supabase connectée et initialisée pour SnipeStudio AI Full Suite !", flush=True)
    except Exception as e:
        print(f"❌ [DB] Erreur Init Supabase: {e}", flush=True)

def enregistrer_annonce(lien, prix, titre, image_url, type_article, condition_score, offre_recommandee, msg_nego, studio_poses):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
                INSERT INTO annonces (lien, prix, titre, image_url, type_article, condition_score, offre_recommandee, msg_nego, studio_poses)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (lien) DO NOTHING;
            """,
            (lien, prix, titre, image_url, type_article, condition_score, offre_recommandee, msg_nego, json.dumps(studio_poses)),
        )
        inserted = cursor.rowcount > 0
        conn.commit()
        cursor.close()
        conn.close()
        return inserted
    except Exception as e:
        print(f"❌ [DB] Erreur écriture Supabase: {e}", flush=True)
    return False

# ------------------------------------------------------------------
# AI ENGINE : DIAGNOSTIC, NÉGOCIATION & GENERATION STUDIO
# ------------------------------------------------------------------
def analyser_qualite_et_negociation(titre, prix, image_url):
    titre_lower = titre.lower()
    
    score = 9.5
    if any(m in titre_lower for m in ["très bon", "tres bon", "neuf"]):
        score = 9.8
    elif any(m in titre_lower for m in ["bon état", "bon etat"]):
        score = 8.8
    elif any(m in titre_lower for m in ["satisfaisant", "porté"]):
        score = 8.0
    condition_score = f"{score}/10"

    offre = max(round(prix * 0.82, 1), 5.0)
    msg_nego = f"Bonjour ! Votre {titre} me plaît beaucoup. Seriez-vous d'accord pour {offre}€ ? Envoi rapide assuré. Merci !"

    base_img = image_url or "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&w=600&q=80"
    studio_poses = [
        {"pose": "Face Studio", "url": base_img},
        {"pose": "Profil Détaillé", "url": base_img},
        {"pose": "Zoom Cadrage", "url": base_img},
        {"pose": "Mise en Scène Premium", "url": base_img}
    ]

    return condition_score, offre, msg_nego, studio_poses

# ------------------------------------------------------------------
# API FLASK (SNIPESTUDIO UI)
# ------------------------------------------------------------------
@app.route("/")
@app.route("/app")
def serve_app():
    if os.path.exists("app.html"):
        return send_file("app.html")
    return "<h1>SnipeStudio // AI Resell Engine Online</h1>", 200

@app.route("/healthz")
def health():
    return "OK", 200

@app.route("/api/annonces")
def get_annonces():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT lien, prix, titre, image_url, type_article, condition_score, offre_recommandee, msg_nego, studio_poses 
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
                cond_score, offre_rec, msg_n = r[5] or "9.2/10", r[6] or round(prix_achat * 0.85, 1), r[7] or ""
                poses = r[8] if r[8] else []

                frais_vinted = 0.70 + (prix_achat * 0.05)
                cout_total = round(prix_achat + frais_vinted + 3.50, 2)
                coef_revente = 2.2 if "Sneakers" in str(type_art) else 2.1
                revente_est = round(prix_achat * coef_revente, 2)
                if revente_est < prix_achat + 15.0:
                    revente_est = round(prix_achat + 20.0, 2)

                benef_net = round(revente_est - cout_total, 2)

                annonces.append({
                    "id": idx + 1,
                    "titre": titre_art or "Pièce Exclusive SnipeStudio",
                    "type_article": type_art or "Sélection Premium",
                    "prix": prix_achat,
                    "cout_total": cout_total,
                    "revente": revente_est,
                    "benefice": benef_net,
                    "lien": lien_art,
                    "image": img_art or "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&w=600&q=80",
                    "condition": cond_score,
                    "offre_nego": offre_rec,
                    "msg_nego": msg_n,
                    "studio_poses": poses
                })
            return jsonify(annonces)
    except Exception as e:
        print(f"❌ [API] Erreur lecture DB: {e}", flush=True)

    return jsonify([])

# ------------------------------------------------------------------
# CATALOGUES & RECHERCHES STRICTEMENT SOUS LES 20€
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
    {"mot_cle": "Nike Dunk Low", "type_article": "Sneakers", "prix_max": 20.0, "revente_base": 45.0, "cat": CATALOG_CHAUSSURES, "size": TAILLES_SNEAKERS},
    {"mot_cle": "Jordan 1 Low", "type_article": "Sneakers", "prix_max": 20.0, "revente_base": 45.0, "cat": CATALOG_CHAUSSURES, "size": TAILLES_SNEAKERS},
    {"mot_cle": "Adidas Campus 00s", "type_article": "Sneakers", "prix_max": 18.0, "revente_base": 40.0, "cat": CATALOG_CHAUSSURES, "size": TAILLES_SNEAKERS},
    {"mot_cle": "Sweat Ralph Lauren", "type_article": "Ralph Lauren", "prix_max": 15.0, "revente_base": 35.0, "cat": CATALOG_HOMME, "size": TAILLES_HABITS},
    {"mot_cle": "Pull Ralph Lauren torsadé", "type_article": "Ralph Lauren", "prix_max": 18.0, "revente_base": 40.0, "cat": CATALOG_HOMME, "size": TAILLES_HABITS},
    {"mot_cle": "Polo Ralph Lauren", "type_article": "Ralph Lauren", "prix_max": 12.0, "revente_base": 30.0, "cat": CATALOG_HOMME, "size": TAILLES_HABITS},
    {"mot_cle": "Carhartt WIP t-shirt", "type_article": "Carhartt", "prix_max": 15.0, "revente_base": 35.0, "cat": CATALOG_HOMME, "size": TAILLES_HABITS},
    {"mot_cle": "Carhartt sweat", "type_article": "Carhartt", "prix_max": 20.0, "revente_base": 45.0, "cat": CATALOG_HOMME, "size": TAILLES_HABITS},
    {"mot_cle": "Sweat Stussy", "type_article": "Streetwear", "prix_max": 18.0, "revente_base": 40.0, "cat": CATALOG_HOMME, "size": TAILLES_HABITS},
    {"mot_cle": "Corteiz t-shirt", "type_article": "Streetwear", "prix_max": 15.0, "revente_base": 35.0, "cat": CATALOG_HOMME, "size": TAILLES_HABITS},
    {"mot_cle": "Arc'teryx t-shirt", "type_article": "Techwear", "prix_max": 15.0, "revente_base": 35.0, "cat": CATALOG_HOMME, "size": TAILLES_HABITS},
    {"mot_cle": "The North Face tee", "type_article": "Techwear", "prix_max": 12.0, "revente_base": 30.0, "cat": CATALOG_HOMME, "size": TAILLES_HABITS},
]

def envoyer_notification_telegram(affaire):
    message = (
        f"🎯 <b>SNIPESTUDIO // NOUVELLE PÉPITE DÉTECTÉE</b>\n\n"
        f"▪️ <b>{affaire['titre']}</b>\n"
        f"▫️ <b>Achat :</b> {affaire['prix']} € | <b>Offre Nego :</b> {affaire['offre_nego']} €\n"
        f"▪️ <b>Bénéfice Net :</b> +{affaire['benefice']} €\n"
        f"⭐ <b>Condition IA :</b> {affaire['condition']}\n\n"
        f"<i>Ouvrez SnipeStudio pour verrouiller l'affaire.</i>"
    )
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://vinted-bot-dptd.onrender.com")
    keyboard = {"inline_keyboard": [[{"text": "⚡ ACCÉDER À SNIPESTUDIO", "web_app": {"url": f"{render_url}/app"}}]]}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML", "reply_markup": json.dumps(keyboard)}, timeout=5)
        print("📩 [TELEGRAM] Notification SnipeStudio envoyée !", flush=True)
    except Exception as e:
        print(f"❌ [TELEGRAM] Erreur d'envoi: {e}", flush=True)

async def scanner_vinted(browser):
    print("🔍 [SCRAPER] Démarrage d'un cycle de scan SnipeStudio AI (<20€)...", flush=True)
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
            print(f"👉 [SCAN] Recherche : '{mot_cle}' (max {prix_max}€)...", flush=True)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(random.uniform(0.8, 1.5))

                items = await page.query_selector_all('[data-testid="grid-item"]')
                print(f"   -> {len(items)} articles trouvés.", flush=True)

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
                        prix = float(prix_text.replace("€", "").replace(",", ".").replace(" ", "").strip())
                    except ValueError:
                        prix = 0.0

                    if 0 < prix <= prix_max and lien:
                        condition_score, offre_nego, msg_nego, studio_poses = analyser_qualite_et_negociation(titre, prix, image_url)
                        
                        est_nouveau = enregistrer_annonce(lien, prix, titre, image_url, type_article, condition_score, offre_nego, msg_nego, studio_poses)
                        if est_nouveau:
                            print(f"✨ [AI SNIPED] {titre} - {prix}€ | Condition: {condition_score}", flush=True)
                            frais = 0.70 + (prix * 0.05) + 3.50
                            benefice = round(revente_base - (prix + frais), 2)
                            
                            if benefice >= 8.0:
                                affaire = {
                                    "titre": titre.strip(),
                                    "prix": prix,
                                    "revente_finale": revente_base,
                                    "benefice": benefice,
                                    "lien": lien,
                                    "condition": condition_score,
                                    "offre_nego": offre_nego
                                }
                                envoyer_notification_telegram(affaire)

            except Exception as e:
                print(f"⚠️ [SCAN] Erreur sur '{mot_cle}': {e}", flush=True)

        await context.close()
    except Exception as e:
        print(f"❌ [SCRAPER] Erreur globale: {e}", flush=True)

def lancer_bot_async():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def run_loop():
        init_db()
        print("🚀 [SYSTEM] SnipeStudio Engine activé (Budget max < 20€) !", flush=True)

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
                print(f"❌ [PLAYWRIGHT] Erreur lancement: {e}", flush=True)

            print(f"💤 [SYSTEM] Pause de {DELAI_BOUCLE_SECONDES} secondes...", flush=True)
            await asyncio.sleep(DELAI_BOUCLE_SECONDES)

    loop.run_until_complete(run_loop())

bot_thread = threading.Thread(target=lancer_bot_async, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
