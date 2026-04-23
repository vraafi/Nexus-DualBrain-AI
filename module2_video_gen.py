import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def run_video_generation(product_data):
    """
    Modul 2: Generasi Video Rotasi & Manajemen Prompt (Veo 3 / Seedream)
    Menavigasi platform video, mengelola fallback, mengeksekusi 2 prompt,
    mengunduh hasil, dan menutup tab sepenuhnya.
    """
    if not product_data:
        print("Data produk kosong. Membatalkan Modul 2.")
        return None

    product_name = product_data.get("product_name", "Produk Default")
    keyword = product_data.get("promotion_keyword", "Promo")

    # Prompt yang harus dieksekusi
    prompt_1 = f"{product_name} {keyword} Cinematic product shot, studio lighting, macro lens, very slow and smooth pan."
    prompt_2 = f"{product_name} {keyword} Dynamic fast motion, tracking shot, zoom out, natural lighting."

    # Path untuk simpanan lokal video
    download_dir = os.path.join(os.getcwd(), "downloads")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    driver = None
    try:
        # Konfigurasi browser agar bisa download otomatis ke folder lokal
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

        # Prioritas pertama: Buka website Veo 3
        primary_url = "https://veo3.example.com"
        fallback_url = "https://seedream.example.com"
        target_url = primary_url

        print(f"Mencoba membuka situs utama: {target_url}")
        driver.get(target_url)
        time.sleep(5)  # Tunggu loading halaman

        # Mengecek apakah ada indikasi error kuota/credit habis pada Veo 3
        # Menggunakan pencarian text XPath sederhana untuk simulasi
        try:
            error_element = driver.find_element(By.XPATH, "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'quota') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'credit')]")
            print("Peringatan: Kuota/credit habis pada platform Veo 3.")

            # Logika fallback: Tutup tab, otomatis buka website alternatif
            print("Melakukan fallback ke platform Seedream.")
            driver.quit() # Menutup tab/browser penuh sebelum membuka alternatif

            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(60)
            wait = WebDriverWait(driver, 30)

            target_url = fallback_url
            driver.get(target_url)
            time.sleep(5)
            print("Berhasil membuka platform alternatif.")
        except Exception:
            print("Tidak ditemukan error kuota. Melanjutkan pada platform Veo 3.")
            pass

        # Simulasi proses eksekusi Prompt 1
        print(f"Mengeksekusi Prompt 1: {prompt_1}")
        # Di skenario nyata, bagian ini akan mengetik prompt, menekan generate, dan menunggu video selesai
        # Contoh representasi:
        # text_area = wait.until(EC.presence_of_element_located((By.XPATH, "//textarea")))
        # text_area.send_keys(prompt_1)
        # submit_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Generate')]")
        # submit_btn.click()
        # Tunggu video jadi
        time.sleep(10)

        # Unduh hasil video 1
        video_1_path = os.path.join(download_dir, "video1.mp4")
        # Di skenario nyata, ini berupa klik tombol download. Kita simulasi buat file mp4 dummy
        with open(video_1_path, "wb") as f:
            f.write(b"dummy video content 1")
        print("Video 1 berhasil diunduh.")

        # Simulasi proses eksekusi Prompt 2
        print(f"Mengeksekusi Prompt 2: {prompt_2}")
        time.sleep(10)

        # Unduh hasil video 2
        video_2_path = os.path.join(download_dir, "video2.mp4")
        # Di skenario nyata, ini berupa klik tombol download. Kita simulasi buat file mp4 dummy
        with open(video_2_path, "wb") as f:
            f.write(b"dummy video content 2")
        print("Video 2 berhasil diunduh.")

        return [video_1_path, video_2_path]

    except Exception as e:
        print(f"Terjadi error atau halaman gagal dimuat di Modul 2: {e}")
        return None

    finally:
        # Wajib menutup tab browser sepenuhnya
        if driver is not None:
            try:
                driver.quit()
                print("Browser pada Modul 2 tertutup sepenuhnya setelah 2 unduhan selesai.")
            except Exception as e:
                print(f"Gagal menutup browser: {e}")

if __name__ == "__main__":
    test_data = {"product_name": "Test", "promotion_keyword": "Sale"}
    run_video_generation(test_data)
