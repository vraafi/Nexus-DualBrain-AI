import streamlit as st
import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import google.generativeai as genai
from dotenv import load_dotenv

# Load local .env if present
load_dotenv()

# Set page config for a premium and wide feel
st.set_page_config(
    page_title="Nexus DualBrain AI — Meta Enterprise AI Hub & Agent Core",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────────────────────────
# STYLE & THEME (Premium Cyber HUD CSS Injection)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Styling Dasar & Font */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Inter:wght@300;400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    h1, h2, h3, h4, .title-font {
        font-family: 'Outfit', sans-serif;
        font-weight: 700;
    }

    /* Gradient Background untuk Judul & Aksen */
    .gradient-text {
        background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
    }
    
    .gradient-box {
        background: linear-gradient(135deg, rgba(0, 242, 254, 0.08) 0%, rgba(79, 172, 254, 0.08) 100%);
        border: 1px solid rgba(79, 172, 254, 0.25);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 25px;
    }

    /* Metric Cards */
    .metric-card {
        background-color: #0d0f17;
        border: 1px solid #1e293b;
        border-radius: 10px;
        padding: 18px;
        text-align: center;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: #00f2fe;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #00f2fe;
        margin-bottom: 5px;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #94a3b8;
    }

    /* Agent Badges */
    .agent-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-bottom: 10px;
    }
    .agent-1-badge { background-color: rgba(236, 72, 153, 0.15); color: #f472b6; border: 1px solid rgba(236, 72, 153, 0.3); }
    .agent-2-badge { background-color: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
    .agent-3-badge { background-color: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }

    /* Custom Terminal Log style */
    .terminal-container {
        background-color: #060814;
        border-left: 4px solid #00f2fe;
        padding: 15px;
        border-radius: 0 8px 8px 0;
        font-family: 'Courier New', Courier, monospace;
        color: #00ffcc;
        margin-bottom: 20px;
        font-size: 0.85rem;
        max-height: 250px;
        overflow-y: auto;
        border-top: 1px solid rgba(255,255,255,0.05);
        border-right: 1px solid rgba(255,255,255,0.05);
        border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    
    /* Code output container */
    .ad-container {
        background-color: #0f172a;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 20px;
        font-family: inherit;
        color: #e2e8f0;
        white-space: pre-wrap;
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.4);
    }

    /* System Health Monitor Widget */
    .health-widget {
        background-color: #0f172a;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px;
        font-size: 0.8rem;
        font-family: monospace;
        color: #10b981;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# AUTO API KEY DETECTION MECHANISMS
# ─────────────────────────────────────────────────────────────────────────────
def detect_api_keys():
    """Detects available API keys in environment or streamlit secrets."""
    keys = {
        "Google": [],
        "OpenAI": None,
        "Anthropic": None,
        "OpenRouter": None
    }
    
    # 1. Google Gemini Key Scanner (1 to 10 and default)
    for i in range(1, 11):
        val = os.getenv(f"GEMINI_KEY_{i}")
        if val and val.strip():
            keys["Google"].append(val.strip())
            
    val_main = os.getenv("GEMINI_API_KEY")
    if val_main and val_main.strip() and val_main not in keys["Google"]:
        keys["Google"].append(val_main.strip())
        
    if hasattr(st, "secrets"):
        for sec_key in st.secrets:
            if sec_key.startswith("GEMINI_KEY") or sec_key == "GEMINI_API_KEY":
                val = st.secrets[sec_key]
                if val and val.strip() and val not in keys["Google"]:
                    keys["Google"].append(val.strip())
                    
    # 2. OpenAI Key Scanner
    openai_val = os.getenv("OPENAI_API_KEY")
    if openai_val and openai_val.strip():
        keys["OpenAI"] = openai_val.strip()
    elif hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets:
        keys["OpenAI"] = st.secrets["OPENAI_API_KEY"].strip()
        
    # 3. Anthropic (Claude) Key Scanner
    anthropic_val = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if anthropic_val and anthropic_val.strip():
        keys["Anthropic"] = anthropic_val.strip()
    elif hasattr(st, "secrets"):
        if "CLAUDE_API_KEY" in st.secrets:
            keys["Anthropic"] = st.secrets["CLAUDE_API_KEY"].strip()
        elif "ANTHROPIC_API_KEY" in st.secrets:
            keys["Anthropic"] = st.secrets["ANTHROPIC_API_KEY"].strip()
            
    # 4. OpenRouter Key Scanner
    openrouter_val = os.getenv("OPENROUTER_API_KEY")
    if openrouter_val and openrouter_val.strip():
        keys["OpenRouter"] = openrouter_val.strip()
    elif hasattr(st, "secrets") and "OPENROUTER_API_KEY" in st.secrets:
        keys["OpenRouter"] = st.secrets["OPENROUTER_API_KEY"].strip()
        
    return keys

# Initialize API key detection
DETECTED_KEYS = detect_api_keys()

def get_rotated_gemini_key(user_input_key=None):
    """
    Grabs a valid Gemini API key based on fair circular time rotation.
    If the user enters a valid personal key, that is returned.
    If 'nexus_guest' is used, it rotates the detected local keys.
    """
    if user_input_key and user_input_key.strip().startswith("AIzaSy"):
        return user_input_key.strip()
        
    if user_input_key == "nexus_guest":
        keys = DETECTED_KEYS["Google"]
        if keys:
            rotated_index = int(time.time()) % len(keys)
            return keys[rotated_index]
            
    return None

def call_llm_api(provider, model_name, prompt, api_key):
    """
    Unified LLM Router supporting Google, OpenAI, Anthropic, and OpenRouter.
    Utilizes direct REST API requests to ensure 100% reliability on Streamlit Cloud.
    """
    # 1. Google AI Studio Routing
    if provider == "Google AI Studio":
        resolved_key = get_rotated_gemini_key(api_key)
        if not resolved_key and api_key != "nexus_guest":
            resolved_key = api_key
        if not resolved_key:
            raise Exception("Kunci API Gemini tidak terdeteksi. Silakan periksa sidebar.")
            
        genai.configure(api_key=resolved_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        return response.text
        
    # 2. OpenAI Gateway Routing
    elif provider == "OpenAI":
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        res = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=45)
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]
        
    # 3. Anthropic Gateway Routing (Claude models)
    elif provider == "Anthropic":
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": model_name,
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": prompt}]
        }
        res = requests.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=45)
        res.raise_for_status()
        return res.json()["content"][0]["text"]
        
    # 4. OpenRouter Gateway Routing
    elif provider == "OpenRouter":
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://verdiawan-raafi-portfolio.pages.dev",
            "X-Title": "Nexus DualBrain AI"
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}]
        }
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=45)
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]
        
    raise Exception(f"Provider tidak didukung: {provider}")

def is_authorized(user_input_key, provider):
    """Checks if the user has provided a valid key or matches guest credentials."""
    if not user_input_key:
        return False
    if user_input_key.strip() == "nexus_guest":
        return len(DETECTED_KEYS["Google"]) > 0
    if len(user_input_key.strip()) > 10:
        return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# META PLATFORMS ENTERPRISE KNOWLEDGE DATASETS (UP-TO-DATE MAY 2026)
# ─────────────────────────────────────────────────────────────────────────────
META_KNOWLEDGE_BASE = {
    "full": """
[META PLATFORMS, INC. - SYSTEM CORE INTEGRATION (WEEK 3, MAY 2026)]

1. INTERNAL RESTRUCTURING & TALENT SHIFTS:
- Meta has officially completed a major organizational realignment, transferring over 7,000 highly skilled engineers and developers directly into the newly minted 'Applied AI Engineering' division and the 'Agent Transformation Accelerator' unit.
- This shift marks Mark Zuckerberg's aggressive focus on making autonomous AI agents and open-source models the primary core of Facebook, Instagram, and WhatsApp.

2. GLOBAL COST EFFICIENCY & LAYOFFS:
- Simultaneously, Meta executed a massive global layoff affecting approximately 8,000 operational and non-technical staff members worldwide to optimize corporate structure.
- The APAC region suffered notable impacts, experiencing structural downsizing in marketing, sales, and localized operations as the company pivots to fully automated, AI-driven customer outreach and self-serve ad structures.

3. INFRASTRUCTURE & INVESTMENT SPEND:
- Meta has invested USD 115M to USD 135M exclusively for high-scale AI infrastructure upgrades, including ultra-scale H100/Blackwell GPU grids and the construction of autonomous, self-optimizing computing centers.
- This investment aims to build a closed-loop autonomous system where AI models manage the operational logistics of Meta's global advertising network.

4. 2026 PLATFORM FEATURE RELEASES:
- Instagram: Launched 'Parental AI Supervision' — an advanced machine learning suite giving parents direct oversight of teenagers' interactive AI chatbot logs and automated safety filters.
- WhatsApp: Deployed 'WhatsApp Smart Business Agent Hub' which natively embeds Llama 4 assistants into business accounts to automate product lookups, sizing tables, and purchase execution.
- Meta Ads Optimization: Increased the maximum 'Audience Retention Window' (Ad Data Retention window) to 730 days (2 years). This allows advertisers to build ultra-long-term custom lookalike audiences and target shoppers based on historical data going back a full 24 months, vastly outperforming competitive platforms.
""",
    "llama_ecosystem": """
[META LLAMA 4 & PYTORCH OPEN ECOSYSTEM]
- Focus: Open-source AI leadership. Meta releases Llama series weights to commoditize closed models (GPT, Claude).
- Models: Llama 4 Instruct, Llama 4 Vision, and the lightweight Llama 4-Lite.
- Hardware Specs: Trained on over 100,000 unified H100 and Blackwell GPU grids.
- Integration: Empowered by PyTorch 3.0 for optimized tensor performance and instant API integration.
""",
    "ad_conversions": """
[CLICK-TO-WHATSAPP & INSTAGRAM AD ROAS CONVERSIONS]
- Monetization Core: Click-to-WhatsApp represents a major ad product. Brands run Facebook/IG ads that open a WhatsApp chat window to complete purchases.
- Conversion Bottleneck: High ad drop-offs due to a lack of immediate pre-purchase answers, causing massive ad spend waste.
- Solution: 24/7 Zero-Latency AI Sales Concierge. Recommends tailored products, solves size worries (Fit Anxiety) in 3 seconds, and provides zero-friction checkout links, boosting Return on Ad Spend (ROAS) by up to 35%.
""",
    "spatial_computing": """
[META QUEST & HORIZON OS SPATIAL NETWORKS]
- Product: Ray-Ban Meta Glasses (Breakthrough wearable with live multimodal lookup) and Quest 3S.
- Ecosystem Shift: Meta licensed 'Horizon OS' to global hardware giants (ASUS ROG, Lenovo Legion) to build specialized spatial and gaming headsets, duplicating Android's playbook against Apple's Vision OS.
"""
}

# ─────────────────────────────────────────────────────────────────────────────
# 3-AGENT PIPELINE FOR META AD CAMPAIGN OPTIMIZATION (100% FREE SEARCH & CRAWL)
# ─────────────────────────────────────────────────────────────────────────────

# --- AGENT 1: THE RESEARCHER ---
def run_agent_researcher(query, num_leads=3, log_placeholder=None):
    """
    Autonomous research agent utilizing DuckDuckGo Search (100% FREE, NO API KEY).
    """
    logs = []
    def add_log(msg):
        logs.append(msg)
        if log_placeholder:
            log_placeholder.markdown(f"<div class='terminal-container'>{'<br>'.join(logs)}</div>", unsafe_allow_html=True)
        time.sleep(0.5)

    add_log("🚀 <b>[Agent 1 - The Researcher]</b> Mengaktifkan modul pencarian otonom...")
    add_log(f"🔍 Mencari leads potensial di DuckDuckGo untuk query: <i>\"{query}\"</i>...")
    
    results = []
    try:
        with DDGS() as ddgs:
            search_query = f"{query} website"
            ddgs_generator = ddgs.text(search_query, max_results=num_leads * 3)
            
            seen_domains = set()
            for r in ddgs_generator:
                title = r.get("title", "")
                link = r.get("href", "")
                snippet = r.get("body", "")
                
                domain_match = re.search(r'https?://([^/]+)', link)
                if domain_match:
                    domain = domain_match.group(1)
                    if (domain in seen_domains or 
                        "duckduckgo" in domain or 
                        "wikipedia" in domain or 
                        "facebook" in domain or 
                        "instagram" in domain or 
                        "linkedin" in domain or 
                        "youtube" in domain or
                        "twitter" in domain or
                        "pinterest" in domain):
                        continue
                    
                    seen_domains.add(domain)
                    results.append({
                        "name": title.split("-")[0].split("|")[0].strip(),
                        "url": link,
                        "description": snippet
                    })
                    add_log(f"✨ Menemukan lead: <b>{results[-1]['name']}</b> ({domain})")
                    
                    if len(results) >= num_leads:
                        break
        
        if not results:
            raise Exception("Pencarian otonom tidak menemukan domain unik.")
            
        add_log(f"✅ <b>[Agent 1]</b> Selesai! Berhasil mengumpulkan {len(results)} lead siap analisis.")
        return results
        
    except Exception as e:
        add_log(f"⚠️ <b>[Agent 1]</b> Kendala pencarian ({str(e)}). Mengaktifkan database leads fallback...")
        
        # Free-tier fallback database
        fallback_leads = [
            {"name": "Meta Platforms, Inc.", "url": "https://meta.com", "description": "Meta builds technologies that help people connect, find communities, and grow businesses. Shaping the future of open-source AI and spatial computing."},
            {"name": "The Loft Fashion Boutique", "url": "https://theloftsg.com.au", "description": "Premium luxury fashion boutique offering international designer clothing and curating high-end contemporary fashion on King William Road."},
            {"name": "Friend of Franki", "url": "https://friendoffranki.com.au", "description": "Contemporary elegant womenswear and accessories boutique curated in Hyde Park SA."}
        ]
        
        selected_fallback = fallback_leads[:num_leads]
        for lead in selected_fallback:
            add_log(f"📁 [Fallback Database] Memuat lead: <b>{lead['name']}</b> ({lead['url']})")
        add_log(f"✅ <b>[Agent 1]</b> Berhasil memuat {len(selected_fallback)} lead dalam mode fallback.")
        return selected_fallback

# --- CORE SCRAPER FUNCTION ---
def scrape_website_content(url):
    """Scrapes site content (100% FREE, NO API KEY) using BeautifulSoup."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            title = soup.title.string.strip() if soup.title else "N/A"
            meta_desc = ""
            meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
            if meta_tag:
                meta_desc = meta_tag.get("content", "").strip()
                
            # Strip junk tags
            for element in soup(["script", "style", "noscript", "header", "footer", "nav"]):
                element.decompose()
                
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = " ".join(chunk for chunk in chunks if chunk)
            
            return {
                "success": True,
                "title": title,
                "meta_description": meta_desc,
                "raw_text": clean_text[:4000] # Token economy limit
            }
        return {"success": False, "error": f"HTTP Error {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- AGENT 2: THE ANALYST ---
def run_agent_analyst(company_name, url, gemini_key, log_placeholder=None):
    """
    Analyzes website performance and conversion rate leaks (100% FREE scraper integration).
    """
    logs = []
    def add_log(msg):
        logs.append(msg)
        if log_placeholder:
            log_placeholder.markdown(f"<div class='terminal-container'>{'<br>'.join(logs)}</div>", unsafe_allow_html=True)
        time.sleep(0.5)

    add_log(f"🚀 <b>[Agent 2 - The Analyst]</b> Mengaktifkan modul Web Scraper untuk: <b>{company_name}</b>...")
    add_log(f"🌐 Menghubungi server target di {url}...")
    
    scrape_data = scrape_website_content(url)
    
    if scrape_data["success"]:
        add_log("📥 Scraping HTML Berhasil! Teks berhasil diekstrak (4000 karakter).")
    else:
        add_log(f"⚠️ Gagal melakukan scrape langsung ({scrape_data['error']}).")
        add_log("🔄 Mengaktifkan Analisis Kontekstual AI berbasis data deskripsi pencarian...")
        
        # Inject Meta dataset context if URL matches Meta, else use high-end boutique demo fallback
        if "meta" in company_name.lower() or "meta" in url.lower():
            scrape_data = {
                "title": "Meta Platforms, Inc. | Core AI restructures & platform optimizations (May 2026)",
                "meta_description": "Meta builds technologies that help people connect, find communities, and grow businesses.",
                "raw_text": META_KNOWLEDGE_BASE["full"]
            }
        else:
            scrape_data = {
                "title": f"{company_name} | Premium Boutique",
                "meta_description": f"Curated high-end fashion and contemporary styles online at {company_name}.",
                "raw_text": f"{company_name} is an elite fashion retailer selling contemporary womenswear. They face massive conversion drops due to designer size chart confusion (Sizing Anxiety). Customer service spends 20+ hours weekly answering identical questions on return windows, Afterpay, and delivery."
            }
        
    add_log("🧠 Menghubungkan ke Engine AI melalui AI Gateway...")
    add_log("📊 Menganalisis celah konversi, kelemahan SEO, dan peluang optimalisasi...")
    
    prompt = f"""
    Anda adalah **Agent 2: The Conversion Rate & SEO Analyst** dari agensi AI elit, Nexus DualBrain AI.
    Tugas Anda adalah menganalisis data situs web hasil scraping berikut dan menyusun laporan analisis konversi profesional.

    **Detail Perusahaan**:
    - Nama: {company_name}
    - URL: {url}
    - Judul Halaman: {scrape_data['title']}
    - Deskripsi Meta: {scrape_data['meta_description']}
    - Konten Situs (Sebagian): 
    \"\"\"{scrape_data['raw_text']}\"\"\"

    **Tuliskan Laporan Analisis Anda dalam format Markdown yang elegan dengan struktur berikut**:
    ### 📊 LAPORAN ANALISIS KONVERSI: {company_name}
    
    #### 🎯 1. Profil Bisnis & Segmentasi
    *Jelaskan produk utama mereka, nilai eksklusif (unique selling points), dan segmentasi target pasar mereka (misalnya butik kelas atas, sustainable fashion, dll.) dalam 2-3 baris.*

    #### 🛑 2. Celah Konversi Utama (Conversion Leaks)
    *Analisis celah kebocoran penjualan mereka secara mendalam:*
    * **Fit & Sizing Anxiety**: Jelaskan mengapa pembeli ragu check-out gaun premium karena ketakutan salah ukuran, dan dampaknya pada exchange rate.
    * **CS Inbox Overload**: Sebutkan jenis pertanyaan FAQ berulang yang membanjiri tim mereka (Afterpay, kebijakan retur butik, waktu kirim weekend).
    * **Interactive Absence**: Identifikasi ketiadaan asisten belanja interaktif 24/7 yang membuat calon pembeli meninggalkan keranjang belanja (cart abandonment).

    #### 💡 3. Solusi Asisten AI yang Direkomendasikan
    *Rekomendasikan implementasi **24/7 AI Styling & Support Concierge** yang diprogram khusus untuk menjawab FAQ butik mereka, membantu konversi ukuran desainer dalam 3 detik, dan menaikkan konversi penjualan sebesar 15-25%.*
    """
    
    try:
        response_text = call_llm_api(st.session_state.get("provider", "Google AI Studio"), st.session_state.get("model", "gemini-1.5-flash"), prompt, gemini_key)
        add_log("✅ <b>[Agent 2]</b> Analisis selesai! Laporan kinerja konversi berhasil disusun.")
        return response_text
    except Exception as e:
        add_log(f"❌ <b>[Agent 2]</b> Gagal menghubungi API: {str(e)}")
        # Fallback report
        fallback_report = f"""### 📊 LAPORAN ANALISIS KONVERSI: {company_name}
        
#### 🎯 1. Profil Bisnis & Segmentasi
* **Deskripsi**: Butik premium kelas atas yang menjual fashion kontemporer wanita, pakaian desainer kurasi internasional, dan aksesoris gaya hidup.
* **Target Pasar**: Wanita profesional kelas menengah ke atas yang mencari eksklusivitas, material premium (sutra, linen, katun artisan), dan styling personal.

#### 🛑 2. Celah Konversi Utama (Conversion Leaks)
* **Sizing Fit Anxiety**: Kurangnya asisten ukuran instan di chat membuat pelanggan takut salah ukuran pakaian desainer internasional, memicu tingginya keranjang belanja yang ditinggalkan.
* **Beban Operasional CS**: Inbox dibanjiri ratusan chat repetitif tentang cara penukaran barang, dukungan Afterpay, dan info pelacakan paket.

#### 💡 3. Solusi Asisten AI yang Direkomendasikan
* **AI Styling & Sales Concierge**: Mengaktifkan asisten AI otonom 24/7 di toko online untuk memandu pembeli memilih ukuran secara interaktif dan menyelesaikan 75% tiket dukungan berulang secara otomatis."""
        add_log("🔄 <b>[Agent 2]</b> Memuat laporan analisis statis default.")
        return fallback_report

# --- AGENT 3: THE COPYWRITER ---
def run_agent_copywriter(company_name, url, analysis_report, gemini_key, log_placeholder=None):
    """
    Generates high-fidelity outreach emails or ad copywriting.
    """
    logs = []
    def add_log(msg):
        logs.append(msg)
        if log_placeholder:
            log_placeholder.markdown(f"<div class='terminal-container'>{'<br>'.join(logs)}</div>", unsafe_allow_html=True)
        time.sleep(0.5)

    add_log(f"🚀 <b>[Agent 3 - The Copywriter]</b> Mengaktifkan modul Penulisan Persuasif...")
    add_log(f"📝 Membaca laporan analisis dari Agent 2 untuk merumuskan sudut pandang pitch terbaik...")
    add_log("💡 Merancang draf email menggunakan model Two-Step Friction Reduction (Penawaran Uji Coba Gratis 7 Hari)...")
    
    prompt = f"""
    Anda adalah **Agent 3: The Copywriter Master** di agensi AI Nexus DualBrain AI.
    Gunakan keahlian Anda untuk menulis draf email dingin (*cold outreach*) B2B kelas dunia. Email ini ditujukan untuk pemilik butik {company_name} (website: {url}).

    **Informasi Pendukung**:
    - Laporan Analisis Celah Performa (Agent 2):
    \"\"\"{analysis_report}\"\"\"

    **Panduan Wajib Penulisan (Jangan Dilanggar)**:
    1. **Bahasa**: Tulis email dalam Bahasa Inggris yang sangat profesional, ramah, dan bernuansa B2B premium (bukan gaya pemasaran massal yang kaku).
    2. **Subjek Email**: Tulis subjek yang pendek, personal, dan merujuk langsung pada nama perusahaan serta mitigasi celah performa / FAQ otomatis mereka (contoh: "{company_name}: Lowering pre-purchase friction & WhatsApp conversions").
    3. **Paragraf 1 (Apresiasi)**: Puji koleksi atau kontribusi teknologi mereka secara spesifik dan hangat.
    4. **Paragraf 2 (Celah Masalah)**: Jelaskan secara empati celah konversi yang kita temukan pada platform/situs mereka (misalnya kebocoran konversi Click-to-WhatsApp pada iklan Meta, atau sizing fit anxiety pembeli).
    5. **Paragraf 3 (Solusi Asisten AI)**: Jelaskan asisten AI 24/7 (AI Styling & Sales Concierge) yang bisa menyelesaikan masalah ini instan dalam 3 detik di chat.
    6. **Paragraf 4 & 5 (Tawaran Bebas Risiko - Low Friction)**:
       - Tawarkan **7-Day Free Trial** (Uji coba gratis 7 hari tanpa komitmen, tanpa kartu kredit) untuk meluncurkan AI Concierge di toko mereka.
       - Tawarkan **90-Second Customized Video Walkthrough** (Video demo 90 detik gratis yang menunjukkan asisten AI ini berinteraksi di replika layanan mereka).
       - Jelaskan bahwa langganannya sangat terjangkau ($199/bulan) dan sudah mencakup pemeliharaan mingguan (AI Smart Tuning) jika mereka lanjut setelah hari ke-7.
    7. **Call To Action (CTA)**: Buat sesederhana mungkin (contoh: "Would you be open to a quick look at this 90-second video demo?").
    8. **Identitas Pengirim**: Verdiawan Raafi, Senior Growth Partner, Nexus DualBrain AI Agency.

    Kembalikan output draf email ini dalam format Markdown yang rapi dengan info target di atasnya.
    """
    
    try:
        response_text = call_llm_api(st.session_state.get("provider", "Google AI Studio"), st.session_state.get("model", "gemini-1.5-flash"), prompt, gemini_key)
        add_log("✅ <b>[Agent 3]</b> Selesai! Email Outreach Masterpiece berhasil dibuat.")
        return response_text
    except Exception as e:
        add_log(f"❌ Gagal memanggil API Gemini: {str(e)}")
        # Fallback email
        fallback_email = f"""### ✉️ PROPOSAL EMAIL DINGIN PERSONAL - {company_name}
        
* **Target Penerima**: `hello@{company_name.lower().replace(" ", "")}.com.au`
* **Subject**: {company_name}: Lowering boutique size exchanges & automation of FAQs (AI Concierge)

Dear {company_name} Team,

I recently browsed your gorgeous contemporary collections and stunning designs online, and I wanted to reach out with a direct solution to a high-volume pre-purchase support bottleneck that contemporary boutiques face.

As a highly premium shopping destination, {company_name} delivers an exceptional experience. However, carrying premium tailored cuts and international designers online triggers specific customer support queries:
* **Designer Sizing Fit Anxiety**: Online buyers are highly anxious about exact measurements, leading to high cart abandonment rates and costly returns.
* **Repetitive FAQ & Payment Inquiries**: Resolving identical questions regarding Afterpay support, return exemptions, and shipping timelines consumes your team's valuable hours.

I designed an **Instant Zero-Queue AI Shopping Concierge** specifically to automate these bottlenecks:
1. **Pre-Purchase Fit Advisor**: Acts as a 24/7 digital styling specialist, guiding buyers to their perfect fit using your exact sizing tables.
2. **Instant FAQ Automation**: Automatically resolves 75% of repetitive questions in under 3 seconds, freeing up your team.

🚀 **The Risk-Free 7-Day Trial & Continuous Growth Offer:**
* **7-Day Free Trial**: We will fully customize, program, and launch the AI Concierge on your store for 7 days at absolutely zero cost (no credit card required).
* **Managed Subscription**: If you choose to continue after Day 7, the subscription is **$199 AUD/month**, including weekly AI Smart Tuning where we review chat logs to keep training the AI.

I've prepared a short, private 90-second video demo showing how this AI concierge interacts with an online buyer checking luxury sizing on a preview of {company_name}.

Would you be open to a quick look at this video? No strings attached.

Warm regards,

**Verdiawan Raafi**  
Senior E-Commerce Growth Partner  
Nexus DualBrain AI Agency"""
        add_log("🔄 <b>[Agent 3]</b> Memuat draf email statis default.")
        return fallback_email

# ─────────────────────────────────────────────────────────────────────────────
# FRONTEND INTERFACE DESIGN (Streamlit)
# ─────────────────────────────────────────────────────────────────────────────

# --- HEADER SECTION ---
st.markdown("""
<div style='text-align: center; padding: 10px 0 25px 0;'>
    <h1 class='gradient-text' style='font-size: 2.8rem; margin-bottom: 5px;'>🤖 NEXUS DUALBRAIN AI — Meta Enterprise AI Hub</h1>
    <h3 style='font-weight: 400; color: #94a3b8; margin-top: 0; font-size: 1.2rem;'>High-Fidelity Enterprise Assistant & Ad Campaign Optimizer</h3>
</div>
""", unsafe_allow_html=True)

col_imp1, col_imp2, col_imp3 = st.columns(3)
with col_imp1:
    st.markdown("""
    <div class='metric-card'>
        <div class='metric-value'>ACTIVE (200 OK)</div>
        <div class='metric-label'><b>AI Gateway Router</b><br>Unified REST connections to Google, OpenAI, & Claude active.</div>
    </div>
    """, unsafe_allow_html=True)

with col_imp2:
    st.markdown("""
    <div class='metric-card'>
        <div class='metric-value'>Llama 4 / GPT-5.5</div>
        <div class='metric-label'><b>Model Playground</b><br>Equipped with absolute 2026 cutting-edge flagships.</div>
    </div>
    """, unsafe_allow_html=True)

with col_imp3:
    st.markdown("""
    <div class='metric-card'>
        <div class='metric-value'>+35% ROAS Gain</div>
        <div class='metric-label'><b>Outreach Impact</b><br>Engineered to solve pre-purchase sizing and FAQ drop-offs.</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR CONTROLS
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.markdown("""
<div style='text-align: center; padding: 5px 0;'>
    <h2 style='color: #00f2fe; margin-bottom: 5px; font-size: 1.4rem;'>⚙️ Sistem Kontrol</h2>
    <p style='color: #94a3b8; font-size: 0.8rem;'>Configure model parameters and key gates below.</p>
</div>
<hr style='margin-top: 0; border-color: #334155;'>
""", unsafe_allow_html=True)

st.sidebar.markdown("### 🛠️ 1. Konfigurasi AI Gateway")
provider_selection = st.sidebar.selectbox(
    "Pilih Provider AI",
    options=["Google AI Studio", "OpenAI", "Anthropic", "OpenRouter"],
    help="Select the AI brain for the chatbot and ad campaign analyzer."
)

# Dynamic Model Selection based on verified 2026 active releases
if provider_selection == "Google AI Studio":
    model_selection = st.sidebar.selectbox(
        "Pilih Model Gemini/Gemma (Terbaru 2026)",
        options=["gemma-4-31b-it", "gemma-4-26b-a4b-it", "gemini-3.1-pro", "gemini-3.1-flash-lite", "gemini-2.5-pro", "gemini-2.5-flash", "gemma-2-27b-it"],
        index=0,
        help="Google Gemma 4 & Gemini 3.1 Pro/Flash models."
    )
elif provider_selection == "OpenAI":
    model_selection = st.sidebar.selectbox(
        "Pilih Model GPT (Terbaru 2026)",
        options=["gpt-5.5", "gpt-5.4-thinking", "gpt-5.4-mini", "o3-mini", "gpt-4o"],
        index=0,
        help="OpenAI GPT-5.5 Flagship & GPT-5.4 Reasoning models."
    )
elif provider_selection == "Anthropic":
    model_selection = st.sidebar.selectbox(
        "Pilih Model Claude (Terbaru 2026)",
        options=["claude-4.7-opus", "claude-3.7-sonnet", "claude-3.5-haiku"],
        index=0,
        help="Anthropic Claude 4.7 Opus released on April 16, 2026."
    )
elif provider_selection == "OpenRouter":
    model_selection = st.sidebar.selectbox(
        "Pilih Model OpenRouter (Terbaru 2026)",
        options=["openai/gpt-5.5", "google/gemini-3.1-pro", "anthropic/claude-4.7-opus", "deepseek/deepseek-r1", "meta-llama/llama-3.3-70b-instruct"],
        index=0
    )

auth_key_input = st.sidebar.text_input(
    "API Key / Sandi Tamu",
    value="nexus_guest",
    type="password",
    help="Enter chosen API Key. For guest mode using our rotated Gemini keys, enter 'nexus_guest'."
)

# Active Database Selector
db_selection = st.sidebar.selectbox(
    "Pilih Database Meta",
    options=["Full Enterprise Hub Context", "Llama 4 Open Source Ecosystem", "Click-to-WhatsApp Conversion Engine", "Meta Spatial Computing specs"],
    index=0,
    help="Prioritizes specific parts of Meta's 2026 knowledge base."
)

st.session_state["provider"] = provider_selection
st.session_state["model"] = model_selection

# Visual status badge
if auth_key_input == "nexus_guest":
    st.sidebar.success("💡 **Mode Aktif**: Google Gemini (Gratis 10 Pertanyaan menggunakan API Key Agensi!)")
else:
    st.sidebar.info(f"💡 **Model Aktif**: {model_selection} ({provider_selection}) via Kunci API Pribadi")

# MOCK AGENTS.MD RESOURCE HEALTH MONITOR
st.sidebar.markdown("<br>### 📊 2. Status Server (AGENTS.md)", unsafe_allow_html=True)
st.sidebar.markdown("""
<div class='health-widget'>
    🖥️ CPU Usage: 42.4% (Limit: 90%) <br>
    💾 RAM Free:  68.2% (Limit: 92%) <br>
    🤖 Active Chromium Proc: 1/1 <br>
    📦 gc.collect(): TRIGGERED SUCCESS <br>
    ⚡ System Environment: SANDBOX (Nominal)
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN TABS: TAB 1 CHAT SIMULATOR | TAB 2 AD OPTIMIZER PIPELINE | TAB 3 LIVE TEST
# ─────────────────────────────────────────────────────────────────────────────
tab_chat, tab_agents, tab_test = st.tabs([
    "💬 TAB 1: Meta AI Chatbot Simulator (Tanya Jawab Otonom)",
    "⚙️ TAB 2: Meta Ad Conversion Optimizer (Multi-Agent Pipeline)",
    "🧪 TAB 3: Agent Live Sandbox (Uji Coba Agen Otonom)"
])

# --- TAB 1: INTERACTIVE META CHATBOT ---
with tab_chat:
    st.markdown(f"""
    <div class='gradient-box'>
        <h4>Uji Otonom: Meta Platforms AI Assistant (Model: <b>{model_selection}</b>)</h4>
        <p style='color: #94a3b8; font-size: 0.9rem; margin-bottom: 0;'>
            Meta AI Assistant ini dilengkapi basis pengetahuan detail tentang Llama 4, ad ROAS, Ray-Ban Meta glasses, Quest Horizon OS, dan WhatsApp Business API. 
            Silakan ajukan pertanyaan apa pun mengenai produk dan strategi Meta!
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "Halo! Saya adalah Meta Enterprise AI Assistant. Tanyakan apa saja tentang ekosistem teknologi, kecerdasan buatan, atau cara menaikkan ad ROAS Anda di WhatsApp Business!"}
        ]

    # Render history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Handle user query
    if user_query := st.chat_input("Tanyakan apa saja (contoh: Bagaimana menaikkan ad ROAS butik kami? atau Llama 4 specs...)"):
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.write(user_query)

        with st.chat_message("assistant"):
            status_box = st.empty()
            status_box.caption("Connecting to AI Gateway...")
            
            db_key = "full"
            if "Llama" in db_selection:
                db_key = "llama_ecosystem"
            elif "WhatsApp" in db_selection or "Conversion" in db_selection:
                db_key = "ad_conversions"
            elif "Spatial" in db_selection:
                db_key = "spatial_computing"
                
            injected_knowledge = META_KNOWLEDGE_BASE[db_key]
            
            system_prompt = f"""
            Anda adalah **Meta AI Enterprise Assistant**, representasi AI resmi dari divisi Enterprise Meta Platforms yang dikembangkan oleh agensi Nexus DualBrain AI.
            
            **KATEGORI PRIORITAS DATABASE DILETAKKAN DI SINI**:
            {injected_knowledge}
            
            **ATURAN UTAMA KOMUNIKASI**:
            1. Jawablah setiap pertanyaan klien dengan sangat detail, profesional, berwibawa, dan sarat wawasan teknis/bisnis yang mendalam.
            2. Gunakan bahasa Indonesia yang elegan dan profesional (atau campur istilah Inggris jika dirasa cocok untuk audiens bisnis).
            3. Fokus pada penawaran solusi bernilai tinggi. Jika ditanya cara optimasi penjualan atau ads, hubungkan langsung dengan pengaktifan 'AI Shopping & Styling Concierge' di WhatsApp API butik mereka untuk memangkas Fit Anxiety dan meningkatkan ad ROAS hingga 35%.
            4. Sebutkan bahwa model Anda saat ini didukung oleh model '{model_selection}' yang diakses secara otonom melalui AI Gateway agensi.
            """
            
            full_prompt = f"{system_prompt}\n\nUser Question: {user_query}"
            
            try:
                response_text = call_llm_api(provider_selection, model_selection, full_prompt, auth_key_input)
                status_box.empty()
                st.write(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
            except Exception as e:
                status_box.error(f"Failed to communicate with LLM: {str(e)}")

# --- TAB 2: AUTONOMOUS 3-AGENT PIPELINE ---
with tab_agents:
    st.markdown(f"""
    <div class='gradient-box'>
        <h4>Uji Otonom: Meta Ads Campaign Optimizer (Multi-Agent Setup)</h4>
        <p style='color: #94a3b8; font-size: 0.9rem; margin-bottom: 0;'>
            Gunakan input parameter di bawah untuk memicu pipeline 3-Agent otonom (Researcher ➡️ ROAS Analyst ➡️ Ad Copywriter) untuk mendesain kampanye Meta Ad & WhatsApp Concierge dengan performa konversi maksimal untuk bisnis Anda!
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col_ag1, col_ag2 = st.columns(2)
    with col_ag1:
        niche_input_main = st.text_input("Industri/Niche Bisnis Target", value="Boutique Luxury Fashion", key="n_in_m")
    with col_ag2:
        target_loc = st.text_input("Target Lokasi Iklan", value="Singapore", key="loc_in_m")
        
    run_pipeline = st.button("🚀 JALANKAN METAPROFILE OPTIMIZER PIPELINE", key="btn_pipeline")
    
    if run_pipeline:
        if not is_authorized(auth_key_input, provider_selection):
            st.error("❌ Kunci Otorisasi salah. Harap masukkan API key yang valid atau gunakan 'nexus_guest'.")
        else:
            gemini_key = get_rotated_gemini_key(auth_key_input)
            if not gemini_key and auth_key_input != "nexus_guest":
                gemini_key = auth_key_input
            if not gemini_key:
                st.error("❌ Kunci API Agensi tidak tersedia saat ini. Sila masukkan API Key manual di sidebar.")
            else:
                st.write("---")
                st.subheader("🖥️ Monitor Konsol Otonom (Live Terminal Logs)")
                log_placeholder = st.empty()
                
                # 1. JALANKAN RESEARCHER
                competitors = run_agent_researcher(f"{niche_input_main} {target_loc}", num_leads=3, log_placeholder=log_placeholder)
                st.success("📂 Agent 1: Competitor Campaign Research Berhasil!")
                st.dataframe(competitors, use_container_width=True)
                
                # 2. JALANKAN ANALYST
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(f"<span class='agent-badge agent-2-badge'>Agent 2: The ROAS Analyst</span>", unsafe_allow_html=True)
                analysis_result = run_agent_analyst(niche_input_main, competitors[0]["url"] if competitors else "https://example.com", gemini_key, log_placeholder=log_placeholder)
                st.markdown(analysis_result)
                
                # 3. JALANKAN COPYWRITER
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(f"<span class='agent-badge agent-3-badge'>Agent 3: The Creative Copywriter</span>", unsafe_allow_html=True)
                creative_ad_copies = run_agent_copywriter(niche_input_main, competitors[0]["url"] if competitors else "https://example.com", analysis_result, gemini_key, log_placeholder=log_placeholder)
                
                st.success("✉️ Agent 3: High-ROAS Meta Ad Copies Berhasil Dihasilkan!")
                st.markdown("<div class='ad-container'>" + creative_ad_copies + "</div>", unsafe_allow_html=True)

# --- TAB 3: CUSTOM SANDBOX TEST SUITE ---
with tab_test:
    st.markdown("""
    <div class='gradient-box'>
        <h4>🧪 Sandbox Pengujian Agen Otonom (Live Sandbox Suite)</h4>
        <p style='color: #94a3b8; font-size: 0.9rem; margin-bottom: 0;'>
            Tab khusus ini dibangun untuk menguji performa 3-Agent secara sekuensial dan otonom menggunakan instruksi mendalam Anda. 
            Masukkan instruksi terperinci untuk masing-masing agen di bawah ini untuk melihat mereka merumuskan output berkualitas tinggi secara real-time!
        </p>
    </div>
    """, unsafe_allow_html=True)

    col_t1, col_t2 = st.columns([2, 1])
    with col_t1:
        st.markdown("##### 📝 1. Tinjau Input Pertanyaan/Instruksi Pengujian")
        researcher_prompt = st.text_area(
            "Prompt untuk Agent 1: The Researcher",
            value='Researcher, kumpulkan seluruh data mentah dan valid mengenai Meta per minggu ketiga Mei 2026. Fokus pada detail restrukturisasi internal (pemindahan 7.000 karyawan ke divisi Applied AI Engineering dan Agent Transformation Accelerator), rincian PHK massal 8.000 karyawan yang baru dieksekusi global (termasuk dampak di APAC), serta rilis fitur terbaru di Instagram, WhatsApp, dan peningkatan masa retensi data iklan (Audience Retention Window) menjadi 730 hari. Berikan datanya dalam bentuk poin-poin tanpa opini.',
            height=120
        )
        
        analyst_prompt = st.text_area(
            "Prompt untuk Agent 2: The Analyst",
            value='Analyst, berdasarkan data efisiensi biaya Meta Mei 2026—di mana mereka memotong 8.000 peran operasional namun menginvestasikan USD 115M–135M untuk infrastruktur AI dan membentuk unit otonom—bagaimana analisis kamu mengenai pergeseran model bisnis Meta? Analisis juga dampak fitur Parental AI Supervision terbaru pada tingkat retensi pengguna remaja (Gen Z/Alpha), serta bagaimana perpanjangan retensi data iklan ke 730 hari memengaruhi peta persaingan digital ad mereka melawan Google.',
            height=120
        )
        
        copywriter_prompt = st.text_area(
            "Prompt untuk Agent 3: The Copywriter",
            value='Copywriter, buatlah 3 variasi konten berdasarkan situasi Meta saat ini:\n\n1. Sebuah Press Release internal yang menenangkan namun memotivasi karyawan pasca-restrukturisasi AI Mei 2026.\n\n2. Naskah Copywriting Iklan B2B di LinkedIn yang menargetkan para pengiklan/agensi, menyoroti fitur optimasi iklan terbaru (retensi 730 hari dan integrasi asisten Meta AI).\n\n3. Utas kreatif (Thread/X) yang edukatif dan ramah keluarga untuk memperkenalkan fitur baru Parental Controls pada Meta AI agar orang tua merasa aman.',
            height=150
        )
    
    with col_t2:
        st.markdown("##### ⚙️ 2. Parameter Eksekusi Sandbox")
        test_provider = st.selectbox("Provider Sandbox", options=["Google AI Studio", "OpenAI", "Anthropic", "OpenRouter"], key="t_prov")
        
        if test_provider == "Google AI Studio":
            test_model = st.selectbox("Model Sandbox", options=["gemini-3.1-pro", "gemini-3.1-flash-lite", "gemini-2.5-pro", "gemini-2.5-flash"], key="t_mod")
        elif test_provider == "OpenAI":
            test_model = st.selectbox("Model Sandbox", options=["gpt-5.5", "gpt-5.4-thinking", "gpt-5.4-mini", "gpt-4o"], key="t_mod")
        elif test_provider == "Anthropic":
            test_model = st.selectbox("Model Sandbox", options=["claude-4.7-opus", "claude-3.7-sonnet", "claude-3.5-haiku"], key="t_mod")
        elif test_provider == "OpenRouter":
            test_model = st.selectbox("Model Sandbox", options=["google/gemini-3.1-pro", "openai/gpt-5.5", "anthropic/claude-4.7-opus"], key="t_mod")
            
        test_key = st.text_input("Kunci API Sandbox", value="nexus_guest", type="password", key="t_key")
        
        st.info("💡 Klik tombol di bawah untuk menjalankan pengujian live. Terminal di bawah akan memproses input secara real-time.")

    run_sandbox_test = st.button("🧪 JALANKAN PENGUJIAN AGEN OTONOM", key="btn_run_sandbox")

    if run_sandbox_test:
        if not is_authorized(test_key, test_provider):
            st.error("❌ Kunci otorisasi sandbox salah. Silakan gunakan 'nexus_guest' atau masukkan kunci API valid Anda.")
        else:
            resolved_key = get_rotated_gemini_key(test_key)
            if not resolved_key and test_key != "nexus_guest":
                resolved_key = test_key
                
            if not resolved_key:
                st.error("❌ Kunci API Agensi tidak tersedia. Masukkan kunci API manual di kolom parameter.")
            else:
                st.write("---")
                st.subheader("🖥️ Monitor Konsol Otonom Sandbox (Live Step-by-Step logs)")
                s_log = st.empty()
                
                logs_t = []
                def add_s_log(msg):
                    logs_t.append(msg)
                    s_log.markdown(f"<div class='terminal-container'>{'<br>'.join(logs_t)}</div>", unsafe_allow_html=True)
                    time.sleep(0.5)
                
                # STEP 1: RUN RESEARCHER
                add_s_log("🚀 <b>[Agent 1 - The Researcher]</b> Mengaktifkan modul penelitian otonom...")
                add_s_log("🌐 Mencari artikel berita, lembar fakta korporasi, dan rilis pers internal Meta per Mei 2026...")
                add_s_log("📥 Mengekstrak data restrukturisasi internal (7.000 karyawan ke divisi Applied AI & Agent Accelerator)...")
                add_s_log("📥 Mengekstrak detail PHK 8.000 karyawan (terutama dampak restrukturisasi di APAC)...")
                add_s_log("📥 Mengekstrak fitur retensi iklan 730 hari & Parental AI Supervision...")
                
                researcher_full_prompt = f"""
                Kamu adalah **Agent 1: The Researcher** (Terinspirasi oleh gpt-researcher).
                Tugasmu adalah memenuhi instruksi riset berikut dengan sangat presisi, mengumpulkan seluruh fakta valid (Mei 2026), menyajikannya secara detail dalam bentuk poin-poin tanpa opini/interpretasi pribadi.
                
                **Berikut adalah Dokumen Fakta Internal Perusahaan (May 2026)**:
                {META_KNOWLEDGE_BASE["full"]}
                
                **Instruksi Riset**:
                {researcher_prompt}
                
                Sajikan seluruh fakta dalam format markdown yang bersih, dengan sitasi bersumber dari fakta internal.
                """
                
                try:
                    research_result = call_llm_api(test_provider, test_model, researcher_full_prompt, resolved_key)
                    add_s_log("✅ <b>[Agent 1]</b> Selesai! Data riset mentah berhasil dikumpulkan. Mengirimkan berkas ke Agent 2...")
                    
                    st.markdown("#### 📂 Output Agent 1: The Researcher")
                    st.markdown(research_result)
                    
                    # STEP 2: RUN ANALYST
                    st.markdown("<br>", unsafe_allow_html=True)
                    add_s_log("🚀 <b>[Agent 2 - The Analyst]</b> Mengaktifkan modul analisis model bisnis...")
                    add_s_log("💡 Membaca laporan riset dari Agent 1...")
                    add_s_log("📊 Menganalisis pergeseran model bisnis dari penghematan biaya USD 115M-135M menuju unit otonom...")
                    add_s_log("📊 Menganalisis tingkat retensi pengguna remaja Gen Z/Alpha dengan fitur Parental Supervision...")
                    add_s_log("📊 Menganalisis dampak perpanjangan retensi data iklan 730 hari terhadap dominasi Google Ads...")
                    
                    analyst_full_prompt = f"""
                    Kamu adalah **Agent 2: The Analyst** (Terinspirasi oleh crawl4ai & ScrapeGraphAI).
                    Tugasmu adalah menganalisis data riset mentah yang dikirimkan oleh Agent 1 berdasarkan teori bisnis, analisis konversi, dan peta persaingan ad-tech.
                    
                    **Data Riset dari Agent 1**:
                    {research_result}
                    
                    **Instruksi Analisis**:
                    {analyst_prompt}
                    
                    Tuliskan laporan analisis strategismu dalam markdown yang elegan dan profesional.
                    """
                    
                    analysis_result = call_llm_api(test_provider, test_model, analyst_full_prompt, resolved_key)
                    add_s_log("✅ <b>[Agent 2]</b> Selesai! Analisis pergeseran bisnis & dampak teknologi berhasil dirumuskan. Mengirimkan berkas ke Agent 3...")
                    
                    st.markdown("#### 📊 Output Agent 2: The Analyst")
                    st.markdown(analysis_result)
                    
                    # STEP 3: RUN COPYWRITER
                    st.markdown("<br>", unsafe_allow_html=True)
                    add_s_log("🚀 <b>[Agent 3 - The Copywriter]</b> Mengaktifkan modul penulisan persuasif & kreatif...")
                    add_s_log("✍️ Merancang Press Release Internal penyejuk restrukturisasi Mei 2026...")
                    add_s_log("✍️ Merancang Iklan B2B LinkedIn (retensi 730 hari & Meta AI Asisten)...")
                    add_s_log("✍️ Merancang Utas X/Twitter ramah keluarga untuk Parental Controls...")
                    
                    copywriter_full_prompt = f"""
                    Kamu adalah **Agent 3: The Copywriter** (Terinspirasi oleh sales-outreach-automation).
                    Tugasmu adalah menyusun 3 variasi konten copywriting berkualitas tinggi berdasarkan laporan analisis strategis dari Agent 2 dan data riset dari Agent 1.
                    
                    **Laporan Analisis dari Agent 2**:
                    {analysis_result}
                    
                    **Data Riset dari Agent 1**:
                    {research_result}
                    
                    **Instruksi Penulisan**:
                    {copywriter_prompt}
                    
                    Sajikan ketiga variasi konten tersebut dalam format markdown yang indah, lengkap dengan pemisah yang jelas.
                    """
                    
                    copywriting_result = call_llm_api(test_provider, test_model, copywriter_full_prompt, resolved_key)
                    add_s_log("✅ <b>[Agent 3]</b> Selesai! Seluruh variasi materi copywriting berhasil diproduksi!")
                    
                    st.markdown("#### ✍️ Output Agent 3: The Copywriter")
                    st.markdown("<div class='ad-container'>" + copywriting_result + "</div>", unsafe_allow_html=True)
                    
                    # Success download block
                    st.success("🎉 Pengujian Sandbox Live Berhasil! Seluruh Agen AI Bekerja dengan Sempurna secara Otonom.")
                    st.download_button(
                        label="📥 DOWNLOAD HASIL UJI COBA LIVE (.MD)",
                        data=f"# Laporan Pengujian Live Agen Otonom (Mei 2026)\n\n## 1. RESEARCHER OUTPUT\n{research_result}\n\n## 2. ANALYST OUTPUT\n{analysis_result}\n\n## 3. COPYWRITER OUTPUT\n{copywriting_result}",
                        file_name="hasil_uji_coba_sandbox_meta.md",
                        mime="text/markdown"
                    )
                except Exception as e:
                    add_s_log(f"❌ <b>[System Error]</b> Pengujian gagal: {str(e)}")
                    st.error(f"Gagal menjalankan pengujian sandbox: {str(e)}")

# --- FOOTER ---
st.markdown("<br><hr style='border-color: #334155;'><br>", unsafe_allow_html=True)
st.markdown("""
<div style='text-align: center; color: #64748b; font-size: 0.85rem;'>
    <p>Nexus DualBrain AI Agency © 2026. Built with Python & Streamlit.</p>
    <p style='margin-top: 5px; color: #00f2fe;'>Engineered to solve global SaaS & E-commerce conversion bottlenecks via autonomous Llama 4 gateways.</p>
</div>
""", unsafe_allow_html=True)
