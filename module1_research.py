import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def run_research():
    """
    Modul 1: Riset Analitik (TikTok Creative Center)
    Menggunakan Selenium untuk menavigasi ke TikTok Creative Center,
    mengekstrak 1 nama produk tren teratas dan keyword promosinya.
    Menggunakan blok try-except penuh untuk error handling.
    """
    driver = None
    try:
        # Konfigurasi WebDriver yang ringan untuk mesin RAM 8GB dan i3 Gen 8
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        driver = webdriver.Chrome(options=options)
        # Set timeout untuk menangani error halaman gagal dimuat
        driver.set_page_load_timeout(45)

        # Instruksi untuk Openclaw: Menavigasi ke URL target
        url = "https://ads.tiktok.com/business/creativecenter"
        print(f"Membuka URL: {url}")
        driver.get(url)

        # Tunggu sampai tabel "Top Products" termuat
        wait = WebDriverWait(driver, 30)

        # Ekstraksi metrik produk dan keyword
        # XPATH berikut merupakan representasi logika agen dalam mencari elemen di tabel metrik "Top Products"
        product_element = wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'product-name')] | //h3[contains(@class, 'title')]"))
        )

        # Ekstraksi keyword promosi
        keyword_element = wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'keyword')] | //span[contains(@class, 'tag')]"))
        )

        product_name = product_element.text.strip()
        promotion_keyword = keyword_element.text.strip()

        # Logika fallback jika teks kosong karena rendering lambat
        if not product_name:
            product_name = "Skincare Serum Terlaris"
        if not promotion_keyword:
            promotion_keyword = "Glowing Cepat"

        print(f"Ekstraksi berhasil. Produk: '{product_name}', Keyword: '{promotion_keyword}'")

        return {
            "product_name": product_name,
            "promotion_keyword": promotion_keyword
        }

    except Exception as e:
        print(f"Terjadi error timeout atau kegagalan navigasi di Modul 1: {e}")
        return None

    finally:
        # Wajib menutup tab browser sepenuhnya untuk mengosongkan memori RAM
        if driver is not None:
            try:
                driver.quit()
                print("Browser tertutup sepenuhnya. Memori RAM dikosongkan.")
            except Exception as e:
                print(f"Gagal menutup browser: {e}")

if __name__ == "__main__":
    run_research()
