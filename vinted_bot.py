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
                date_ajout TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ [DB] Supabase connectée et initialisée pour SnipeStudio !", flush=True)
    except Exception as e:
        print(f"❌ [DB] Erreur Init Supabase: {e}", flush=True)

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
        print(f"❌ [DB] Erreur écriture Supabase: {e}", flush=True)
    return False

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

# RECHERCHES STRICTEMENT BRIDÉES À MAX 20€
RECHERCHES =
