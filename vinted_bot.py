import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import time
import requests
from google import genai
from playwright.sync_api import sync_playwright

# ==========================================
# PETIT SERVEUR WEB POUR RENDER (Garde le service actif)
# ==========================================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Vinted is alive and running!")


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()


# Lancement du serveur web en arrière-plan
threading.Thread(target=run_web_server, daemon=True).start()


# ==========================================
# TES IDENTIFIANTS ET CLÉS
# ==========================================
TELEGRAM_BOT_TOKEN = "8829917220:AAE8WEpEr0lHgrM2UAw5Ls8IRmV50G6AZr4"
TELEGRAM_CHAT_ID = "7467187588"
GEMINI_API_KEY = "AQ.Ab8RN6JQwVlNb4mOpgYpngDPaw7CwFtzL8GFEPJfcZcL7Sbvqg"

# Initialisation du client Gemini AI
client = genai.Client(api_key=GEMINI_API_KEY)


def send_telegram_message(text, photo_url=None):
    """Envoie un message ou une photo d'alerte sur Telegram"""
    if photo_url:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": photo_url,
            "caption": text,
            "parse_mode": "Markdown",
        }
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
        }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Erreur d'envoi Telegram : {e}")


def analyze_with_gemini(image_url, title, price):
    """Utilise l'IA Gemini pour estimer la rentabilité de l'article"""
    try:
        prompt = (
            f"Analyse cet article Vinted.\nTitre: {title}\nPrix affiché: {price}€"
            "\nEn te basant sur l'image et les informations, estime le prix de"
            " revente potentiel sur le marché, calcule le profit estimé, et donne"
            " ton avis (Bonne affaire / À éviter) de manière très concise."
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=[prompt, image_url]
        )
        return response.text
    except Exception as e:
        return f"Erreur d'analyse IA : {e}"


def run_bot():
    print("Lancement du bot Vinted...")
    send_telegram_message(
        "🤖 *Le bot Vinted est bien démarré et en veille sur Render !*"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        seen_items = set()

        while True:
            try:
                url = (
                    "https://www.vinted.fr/catalog?search_text=sneakers&order=newest_first"
                )
                page.goto(url, timeout=60000)
                time.sleep(5)

                items = page.locator(
                    "//div[@data-testid='grid-item']"
                ).all()[:5]

                for item in items:
                    try:
                        title_elem = item.locator(
                            "//p[@data-testid*='title']"
                        ).inner_text()
                        price_elem = item.locator(
                            "//p[@data-testid*='price']"
                        ).inner_text()
                        link_elem = item.locator("a").get_attribute("href")
                        img_elem = item.locator("img").get_attribute("src")

                        item_id = link_elem if link_elem else title_elem

                        if item_id not in seen_items:
                            seen_items.add(item_id)

                            ai_analysis = analyze_with_gemini(
                                img_elem, title_elem, price_elem
                            )

                            message = (
                                f"🔥 *Nouvelle opportunité détectée !*\n\n"
                                f"📦 *Article :* {title_elem}\n"
                                f"💰 *Prix :* {price_elem}\n\n"
                                f"🤖 *Analyse Gemini :*\n{ai_analysis}\n\n"
                                f"🔗 [Voir l'annonce sur Vinted](https://www.vinted.fr{link_elem})"
                            )

                            send_telegram_message(message, photo_url=img_elem)
                            time.sleep(2)

                    except Exception as inner_e:
                        continue

            except Exception as e:
                print(f"Erreur lors du scan : {e}")

            time.sleep(900)


if __name__ == "__main__":
    run_bot()
