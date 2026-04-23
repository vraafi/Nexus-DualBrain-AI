import time
import os
import requests
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

GEMMA_API_KEY = os.environ.get("GEMMA_API_KEY", "")

def call_gemma_api(scraped_text):
    """
    Memanggil Google AI Studio API (model gemma-4-31b-it) menggunakan REST (tanpa google-generativeai library).
    """
    if not GEMMA_API_KEY:
        print("Peringatan: GEMMA_API_KEY tidak ditemukan.")
        return {"product_name": "Produk Default", "promotion_keyword": "Promo"}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent?key={GEMMA_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{
                "text": f"Ekstrak 1 nama produk tren teratas beserta keyword promosinya dari teks berikut. Balas hanya dengan format JSON strict {{\"product_name\": \"...\", \"promotion_keyword\": \"...\"}} tanpa markdown backticks:\n{scraped_text}"
            }]
        }]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            text_response = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            try:
                data = json.loads(text_response.strip())
                return data
            except Exception as e_json:
                print(f"Gagal parse JSON dari Gemma: {text_response}")
                return {"product_name": "Produk Default", "promotion_keyword": "Promo"}
        else:
            print(f"Gagal memanggil Gemma API. Status: {response.status_code}")
            return {"product_name": "Produk Default", "promotion_keyword": "Promo"}
    except Exception as e:
        print(f"Error pada API request Gemma: {e}")
        return {"product_name": "Produk Default", "promotion_keyword": "Promo"}

def attempt_research():
    """
    Eksekusi satu kali navigasi ke TikTok Creative Center.
    """
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(45)

        url = "https://ads.tiktok.com/business/creativecenter"
        print(f"Membuka URL: {url}")
        driver.get(url)

        wait = WebDriverWait(driver, 30)

        # Ambil keseluruhan teks tabel produk untuk diumpan ke LLM
        table_element = wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'table')] | //body"))
        )

        scraped_text = table_element.text
        if len(scraped_text) < 10:
            raise Exception("Teks yang discraping terlalu sedikit (mungkin gagal muat).")

        print("Teks berhasil diekstrak. Mengirim ke model Gemma...")
        llm_result = call_gemma_api(scraped_text)

        return llm_result

    except Exception as e:
        print(f"Terjadi error timeout atau kegagalan navigasi di Modul 1: {e}")
        raise e # Re-raise agar retry mechanism menangkapnya

    finally:
        if driver is not None:
            try:
                driver.quit()
                print("Browser tertutup sepenuhnya. Memori RAM dikosongkan.")
            except Exception as e:
                print(f"Gagal menutup browser: {e}")

def run_research():
    """
    Fungsi wrapper yang mengatur retry logic secara penuh.
    """
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(f"--- Modul 1 Percobaan {attempt}/{max_retries} ---")
            result = attempt_research()
            print(f"Modul 1 Berhasil: {result}")
            return result
        except Exception as e:
            print(f"Modul 1 Percobaan {attempt} gagal.")
            if attempt == max_retries:
                print("Batas retry tercapai. Modul 1 dihentikan.")
                return None
            print("Melakukan driver.quit() secara otomatis (terhandle di finally), lalu retry dalam 3 detik...")
            time.sleep(3)

if __name__ == "__main__":
    run_research()
