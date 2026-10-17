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
