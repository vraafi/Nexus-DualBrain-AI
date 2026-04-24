import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def generate_video_with_reflection(driver, wait, prompt, download_dir, video_index):
    """
    Eksekusi prompt, unduh, dan lakukan evaluasi diri (Reflection Loop).
    Memeriksa keberadaan file dan memvalidasi file video (ukuran > 0 Byte).
    """
    max_reflections = 2
    for attempt in range(1, max_reflections + 1):
        print(f"[{attempt}/{max_reflections}] Mengeksekusi Prompt {video_index}: {prompt}")
        text_area = wait.until(EC.presence_of_element_located((By.XPATH, "//textarea | //input[@type='text']")))
        text_area.clear()
        text_area.send_keys(prompt)

        submit_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'generate') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'create')]")))
        submit_btn.click()

        print(f"Menunggu video {video_index} selesai digenerate...")
        time.sleep(30)

        download_btn = wait.until(EC.element_to_be_clickable((By.XPATH, f"(//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'download') or contains(@class, 'download')])[{video_index}]")))
        download_btn.click()
        print(f"Memicu unduhan video {video_index}.")
        time.sleep(10) # Waktu tunggu file tersimpan ke disk

        # REFLECTION LOOP: Validasi file video terbaru
        files = os.listdir(download_dir)
        mp4_files = [os.path.join(download_dir, f) for f in files if f.endswith('.mp4')]

        if mp4_files:
            latest_file = max(mp4_files, key=os.path.getctime)
            file_size = os.path.getsize(latest_file)
            print(f"Reflection: Mengecek ukuran file {latest_file} -> {file_size} bytes")
            if file_size > 10240: # Memastikan ukuran file > 10KB
                print(f"Video {video_index} lolos evaluasi (ukuran valid). Output berhasil divalidasi.")
                return latest_file
            else:
                print(f"Reflection Error: File video {video_index} terlalu kecil atau corrupted ({file_size} bytes). Re-planning dan mengulang pembuatan...")
                os.remove(latest_file)
        else:
             print(f"Reflection Error: File video {video_index} tidak ditemukan setelah proses unduhan. Mengulang pembuatan...")

    raise Exception(f"Gagal memproduksi video valid untuk prompt {video_index} setelah {max_reflections} reflection loop.")

def attempt_video_generation(product_data, download_dir):
    """
    Eksekusi satu kali navigasi ke platform video AI dengan Reflection Loop
    dan dynamic prompt integration.
    """
    product_name = product_data.get("product_name", "Produk Default")
    keyword = product_data.get("promotion_keyword", "Promo")

    # Gunakan prompt dinamis dari Gemma jika ada, fallback ke string template
    prompt_1 = product_data.get("video_prompt_1", f"{product_name} {keyword} Cinematic product shot, studio lighting, macro lens, very slow and smooth pan.")
    prompt_2 = product_data.get("video_prompt_2", f"{product_name} {keyword} Dynamic fast motion, tracking shot, zoom out, natural lighting.")

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

        video_1_path = generate_video_with_reflection(driver, wait, prompt_1, download_dir, 1)
        video_2_path = generate_video_with_reflection(driver, wait, prompt_2, download_dir, 2)

        return [video_1_path, video_2_path]

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
    test_data = {
        "product_name": "Test",
        "promotion_keyword": "Sale",
        "video_prompt_1": "Test Sale cinematic shot",
        "video_prompt_2": "Test Sale dynamic shot"
    }
    run_video_generation(test_data)
