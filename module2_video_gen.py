import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def attempt_video_generation(product_data, download_dir):
    """
    Eksekusi satu kali navigasi ke platform video AI.
    Tidak ada singkatan (dummy comments), semua interaksi elemen GUI ditulis penuh.
    """
    product_name = product_data.get("product_name", "Produk Default")
    keyword = product_data.get("promotion_keyword", "Promo")

    prompt_1 = f"{product_name} {keyword} Cinematic product shot, studio lighting, macro lens, very slow and smooth pan."
    prompt_2 = f"{product_name} {keyword} Dynamic fast motion, tracking shot, zoom out, natural lighting."

    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        prefs = {"download.default_directory": download_dir,
                 "download.prompt_for_download": False,
                 "directory_upgrade": True}
        options.add_experimental_option("prefs", prefs)

        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(60)
        wait = WebDriverWait(driver, 30)

        primary_url = "https://veo3.example.com"
        fallback_url = "https://seedream.example.com"
        target_url = primary_url

        print(f"Mencoba membuka situs utama: {target_url}")
        driver.get(target_url)
        time.sleep(5)

        try:
            error_element = driver.find_element(By.XPATH, "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'quota') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'credit')]")
            print("Peringatan: Kuota/credit habis pada platform Veo 3.")

            print("Melakukan fallback ke platform Seedream.")
            driver.quit()

            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(60)
            wait = WebDriverWait(driver, 30)

            target_url = fallback_url
            driver.get(target_url)
            time.sleep(5)
            print("Berhasil membuka platform alternatif.")
        except Exception:
            print("Tidak ditemukan error kuota. Melanjutkan.")
            pass

        print(f"Mengeksekusi Prompt 1: {prompt_1}")
        text_area = wait.until(EC.presence_of_element_located((By.XPATH, "//textarea | //input[@type='text']")))
        text_area.clear()
        text_area.send_keys(prompt_1)

        submit_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'generate') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'create')]")))
        submit_btn.click()

        print("Menunggu video 1 selesai digenerate (asumsi 30 detik)...")
        time.sleep(30)

        download_btn_1 = wait.until(EC.element_to_be_clickable((By.XPATH, "(//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'download') or contains(@class, 'download')])[1]")))
        download_btn_1.click()
        print("Memicu unduhan video 1.")
        time.sleep(10) # Waktu tunggu file tersimpan ke disk

        print(f"Mengeksekusi Prompt 2: {prompt_2}")
        text_area = wait.until(EC.presence_of_element_located((By.XPATH, "//textarea | //input[@type='text']")))
        text_area.clear()
        text_area.send_keys(prompt_2)

        submit_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'generate') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'create')]")))
        submit_btn.click()

        print("Menunggu video 2 selesai digenerate (asumsi 30 detik)...")
        time.sleep(30)

        download_btn_2 = wait.until(EC.element_to_be_clickable((By.XPATH, "(//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'download') or contains(@class, 'download')])[1]")))
        download_btn_2.click()
        print("Memicu unduhan video 2.")
        time.sleep(10)

        # Cari file mp4 di direktori unduhan
        files = os.listdir(download_dir)
        mp4_files = [os.path.join(download_dir, f) for f in files if f.endswith('.mp4')]

        if len(mp4_files) >= 2:
            # Sort by creation time to get the newest ones
            mp4_files.sort(key=os.path.getctime, reverse=True)
            return [mp4_files[1], mp4_files[0]] # Mengembalikan video 1 (lama) lalu video 2 (baru)
        elif len(mp4_files) == 1:
            print("Peringatan: Hanya 1 file video yang ditemukan.")
            return mp4_files
        else:
            raise Exception("Tidak ada file video yang terunduh.")

    except Exception as e:
        print(f"Terjadi error atau halaman gagal dimuat di Modul 2: {e}")
        raise e

    finally:
        if driver is not None:
            try:
                driver.quit()
                print("Browser pada Modul 2 tertutup sepenuhnya. RAM terbebas.")
            except Exception as e:
                print(f"Gagal menutup browser: {e}")

def run_video_generation(product_data):
    """
    Fungsi wrapper yang mengatur retry logic secara penuh untuk Modul 2.
    """
    if not product_data:
        print("Data produk kosong. Membatalkan Modul 2.")
        return None

    download_dir = os.path.join(os.getcwd(), "downloads")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(f"--- Modul 2 Percobaan {attempt}/{max_retries} ---")
            result = attempt_video_generation(product_data, download_dir)
            print(f"Modul 2 Berhasil, file path: {result}")
            return result
        except Exception as e:
            print(f"Modul 2 Percobaan {attempt} gagal.")
            if attempt == max_retries:
                print("Batas retry tercapai. Modul 2 dihentikan.")
                return None
            print("Melakukan driver.quit() secara otomatis (terhandle di finally), lalu retry dalam 3 detik...")
            time.sleep(3)

if __name__ == "__main__":
    test_data = {"product_name": "Test", "promotion_keyword": "Sale"}
    run_video_generation(test_data)
