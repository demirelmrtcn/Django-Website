from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re
import time


def clean_price(price_text):
    """ '1.299,90 TL' -> 1299.90 (float) çevirir """
    if not price_text:
        return 0.0
    price_text = str(price_text)
    clean_str = re.sub(r'[^\d.,]', '', price_text)
    if ',' in clean_str and '.' in clean_str:
        clean_str = clean_str.replace('.', '').replace(',', '.')
    elif ',' in clean_str:
        clean_str = clean_str.replace(',', '.')
    try:
        return float(clean_str)
    except ValueError:
        return 0.0


def get_product_details(url):
    # --- GÜÇLENDİRİLMİŞ SELENIUM AYARLARI ---
    chrome_options = Options()
    # Temel Headless Ayarları
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    # LOG SUSTURMA KOMUTLARI (Terminal Temizliği İçin)
    chrome_options.add_argument("--log-level=3")  # Sadece FATAL hataları göster
    chrome_options.add_argument("--silent")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])  # Konsol çıktılarını engelle

    # WebGL ve Grafik Hatalarını Engelleme
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-webgl")
    chrome_options.add_argument("--disable-gl-drawing-for-tests")

    # Bot Korumasını Aşma
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option('useAutomationExtension', False)

    # Konsol hatalarını gizle (PHONE_REGISTRATION_ERROR vb.)
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])

    driver = None
    data = {"site": "", "title": "", "price": 0.0, "original_price": 0.0, "seller": "-"}

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.get(url)

        # Trendyol için Akıllı Bekleme (3 saniye yerine element yüklenene kadar bekle)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)  # JS render için ufak ek bekleme
        except:
            pass

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # --- HEPSIBURADA ---
        if "hepsiburada" in url:
            data["site"] = "Hepsiburada"

            # 1. BAŞLIK
            h1 = soup.find("h1", {"id": "product-name"})
            if not h1:
                h1 = soup.find("h1")
            data["title"] = h1.get_text(strip=True) if h1 else "Hepsiburada Ürünü"

            # 2. FİYAT (Sadece BuyBox içine bakacağız, yan menüye değil)
            # data-test-id="price-current-price" en güvenilir olandır.
            price_elem = soup.find("div", {"data-test-id": "default-price"})
            if not price_elem:
                # Sepet alanı alternatifi
                price_elem = soup.find("span", {"data-bind": "markupText:'currentPriceBeforePoint'"})

            if price_elem:
                data["price"] = clean_price(price_elem.get_text())

            # ORİJİNAL FİYAT (İndirimsiz hali)
            old_price_elem = soup.find("div", {"data-test-id": "price-old-price"})
            if old_price_elem:
                data["original_price"] = clean_price(old_price_elem.get_text())

            # 3. SATICI
            seller_elem = soup.find("span", {"class": "seller-name"})
            if not seller_elem:
                seller_elem = soup.find("a", {"class": "merchant-link"})

            if seller_elem:
                # Bazen satıcı adı linkin içindedir
                data["seller"] = seller_elem.get_text(strip=True)
            else:
                # Satıcı alanı bazen "Satıcı:" yazısının yanındadır
                seller_text = soup.find(string=re.compile("Satıcı:"))
                if seller_text and seller_text.parent:
                    data["seller"] = seller_text.parent.find_next("a").get_text(strip=True)

        # --- AMAZON ---
        elif "amazon" in url or "amzn.eu" in url:
            data["site"] = "Amazon"

            title = soup.find(id='productTitle')
            data["title"] = title.get_text(strip=True) if title else "Amazon Ürünü"

            # FİYAT
            price_elem = soup.find("span", {"class": "a-price-whole"})
            fraction_elem = soup.find("span", {"class": "a-price-fraction"})

            if price_elem:
                whole = price_elem.get_text(strip=True).replace('.', '').replace(',', '')
                fraction = fraction_elem.get_text(strip=True) if fraction_elem else "00"
                data["price"] = float(f"{whole}.{fraction}")
            else:
                offscreen = soup.find("span", {"class": "a-offscreen"})
                if offscreen:
                    data["price"] = clean_price(offscreen.get_text())

            # ORİJİNAL FİYAT (Üstü çizili)
            old_price_span = soup.select_one("span.a-price.a-text-price span.a-offscreen")
            if old_price_span:
                data["original_price"] = clean_price(old_price_span.get_text())

            # SATICI (Kullanıcının Belirttiği Özel Class + Yedekler)
            grid_container = soup.select_one(".offer-display-features-container")
            if not grid_container:
                grid_container = soup.select_one(".odf-grid-max-50-50-columns")

            if grid_container:
                # Kutunun içindeki tüm yazıları sırayla listeye alıyoruz.
                # Örn 1: ['Gönderici', 'Amazon', 'Satıcı', 'Ny212Trading', 'Ödeme', ...]
                # Örn 2: ['Gönderici / Satıcı', 'Amazon.com.tr', 'Hediye...', ...]
                texts = [t.strip() for t in grid_container.stripped_strings if t.strip()]

                for i, text in enumerate(texts):
                    # Durum 1: "Satıcı" kelimesini bulursak, bir sonraki eleman Satıcı Adıdır.
                    # (Gönderici / Satıcı değil, sadece "Satıcı" yazıyorsa)
                    if text == "Satıcı" and i + 1 < len(texts):
                        data["seller"] = texts[i + 1]
                        break

                    # Durum 2: "Gönderici / Satıcı" yazıyorsa, bir sonraki eleman Satıcı Adıdır.
                    elif "Gönderici / Satıcı" in text and i + 1 < len(texts):
                        data["seller"] = texts[i + 1]
                        break

            # YEDEK YÖNTEMLER (Eğer yukarıdaki grid yoksa)
            if data["seller"] == "-":
                # Eski Merchant Info Kutusu
                seller_div = soup.find(id="merchant-info")
                if seller_div:
                    text = seller_div.get_text(strip=True)
                    if "Satıcı:" in text:
                        data["seller"] = text.split("Satıcı:")[-1].strip().split()[0]
                    elif "Sold by" in text:
                        data["seller"] = text.split("Sold by")[-1].strip()
                    elif seller_div.find("a"):
                        data["seller"] = seller_div.find("a").get_text(strip=True)

            # Buybox Mobil/Alternatif
            if data["seller"] == "-":
                bb_seller = soup.find("span", {"class": "offer-display-group-text"})
                if bb_seller:
                    data["seller"] = bb_seller.get_text(strip=True)
        else:
            print(f"UYARI: Desteklenmeyen site ({url})")
            return None

        if data["price"] == 0.0:
            return None

        return data

    except Exception as e:
        print(f"SCRAPING HATASI: {str(e)}")
        return None
    finally:
        if driver:
            driver.quit()