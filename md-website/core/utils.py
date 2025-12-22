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
import json


def clean_price(price_text):
    """ '1.299,90 TL' -> 1299.90 (float) çevirir """
    if not price_text:
        return 0.0
    price_text = str(price_text)
    clean_str = re.sub(r'[^\d.,]', '', price_text)
    
    # TÜRK FORMAT DESTEĞİ
    if ',' in clean_str and '.' in clean_str:
        # Hem virgül hem nokta var: Nokta binlik ayırıcı, virgül ondalık
        # Örnek: "5.250,00" = 5250.00
        clean_str = clean_str.replace('.', '').replace(',', '.')
    elif ',' in clean_str:
        # Sadece virgül var: Ondalık ayırıcı
        # Örnek: "5250,00" = 5250.00
        clean_str = clean_str.replace(',', '.')
    elif '.' in clean_str:
        # Sadece nokta var: Pozisyona göre karar ver
        parts = clean_str.split('.')
        if len(parts) == 2 and len(parts[1]) == 2:
            # Son kısım tam 2 basamaksa, ondalık olabilir
            # Örnek: "52.50" = 52.50
            pass  # Nokta ondalık, değiştirme
        elif len(parts[-1]) == 3 or len(parts) > 2:
            # Son kısım 3 basamaksa veya birden fazla nokta varsa, binlik ayırıcı
            # Örnek: "5.250" = 5250 veya "1.250.000" = 1250000
            clean_str = clean_str.replace('.', '')
        # Belirsiz durumda (örn "52.5"), nokta ondalık kabul edilir
    
    try:
        return float(clean_str)
    except ValueError:
        return 0.0



def get_json_ld(soup):
    """ Sayfadaki JSON-LD verilerini tarar ve ürün fiyatı/bilgisi döndürür """
    try:
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.get_text(strip=True))
                # Bazen data bir liste olabilir
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') == 'Product':
                            return item
                elif isinstance(data, dict):
                    if data.get('@type') == 'Product':
                        return data
                    # Bazen Product, @graph içinde olabilir
                    if '@graph' in data:
                        for item in data['@graph']:
                            if item.get('@type') == 'Product':
                                return item
            except:
                continue
    except:
        pass
    return None



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
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    
    # Hataları ve logları suppress et
    chrome_options.add_argument("--log-level=3")  # FATAL only
    chrome_options.add_argument("--disable-logging")

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

        # --- ZARA ---
        elif "zara" in url:
            data["site"] = "Zara"
            data["seller"] = "Zara"

            # 1. BAŞLIK
            h1 = soup.find("h1")
            data["title"] = h1.get_text(strip=True) if h1 else "Zara Ürünü"

            # 2. FİYAT
            # Zara genelde 'money-amount__main' veya 'price-current__amount' kullanır
            price_elem = soup.select_one(".money-amount__main")
            if not price_elem:
                price_elem = soup.select_one(".price-current__amount .money-amount__main")
            
            # İndirimli fiyat kontrolü (sale price)
            if not price_elem:
                price_elem = soup.select_one("span.price-current__amount")

            if price_elem:
                data["price"] = clean_price(price_elem.get_text())


        # --- GRATIS ---
        elif "gratis" in url:
            data["site"] = "Gratis"
            data["seller"] = "Gratis"

            # 1. BAŞLIK
            h1 = soup.find("h1")
            if not h1:
                # Meta tag'den dene
                meta_title = soup.find("meta", property="og:title")
                if meta_title:
                    data["title"] = meta_title.get("content", "Gratis Ürünü")
                else:
                    data["title"] = "Gratis Ürünü"
            else:
                data["title"] = h1.get_text(strip=True)

            # 2. FİYATLAR - Gratis dual pricing sistemi
            # div class="my-10 flex flex-col" altında iki fiyat var:
            # - Normal fiyat (yüksek)
            # - Gratis Kart fiyatı (indirimli, düşük)
            
            price_container = soup.find("div", class_=lambda x: x and ("my-10" in x and "flex" in x))
            
            if price_container:
                # Tüm fiyatları bul
                price_elements = price_container.find_all(string=re.compile(r'\d+[.,]\d+'))
                prices = []
                
                for price_text in price_elements:
                    price_val = clean_price(price_text)
                    if price_val > 0:
                        prices.append(price_val)
                
                if len(prices) >= 2:
                    # İki fiyat var - büyük olan normal, küçük olan Gratis Kart
                    prices.sort(reverse=True)  # Büyükten küçüğe sırala
                    data["original_price"] = prices[0]  # Normal fiyat (yüksek)
                    data["price"] = prices[1]           # Gratis Kart fiyatı (düşük) - BU TAKİP EDİLECEK
                elif len(prices) == 1:
                    # Tek fiyat var
                    data["price"] = prices[0]
            
            # Alternatif: Eğer price container bulunamadıysa
            if data["price"] == 0:
                # Genel fiyat araması
                price_divs = soup.find_all("div", class_=lambda x: x and "price" in x.lower())
                for pdiv in price_divs:
                    price_text = pdiv.get_text()
                    price_val = clean_price(price_text)
                    if price_val > 0:
                        data["price"] = price_val
                        break

        # --- TRENDYOL ---
        elif "trendyol" in url or "ty.gl" in url:
            data["site"] = "Trendyol"
            
            # 1. BAŞLIK
            h1 = soup.find("h1")
            if not h1:
                # Meta tag'den dene
                meta_title = soup.find("meta", property="og:title")
                if meta_title:
                    title_content = meta_title.get("content", "Trendyol Ürünü")
                    # " - Fiyatı, Yorumları" kısmını temizle
                    data["title"] = title_content.split(" - ")[0] if " - " in title_content else title_content
                else:
                    data["title"] = "Trendyol Ürünü"
            else:
                data["title"] = h1.get_text(strip=True)

            # 2. FİYAT - div class="price-wrapper" altında
            price_wrapper = soup.find("div", class_="price-wrapper")
            
            # TRENDYOL PLUS KONTROLÜ
            plus_price_content = soup.find("div", class_="ty-plus-price-content")
            
            if plus_price_content:
                # Trendyol Plus ürünü - iki fiyat var
                # Normal fiyat (347,99 ₺) - yüksek - TAKİP EDİLECEK
                # Plus fiyatı (313,19 ₺) - düşük - sadece bilgi
                
                # Normal fiyatı bul - "ty-plus-price-original-price" class'ından
                normal_price_elem = plus_price_content.find(class_=lambda x: x and "original-price" in x.lower())
                if normal_price_elem:
                    normal_price_val = clean_price(normal_price_elem.get_text())
                    if normal_price_val > 0:
                        data["price"] = normal_price_val  # Normal fiyat (347,99) - TAKİP EDİLECEK ✅
                        print(f"DEBUG: Trendyol Plus Normal Fiyat: {normal_price_val}")
                
                # Plus fiyatını bul - "ty-plus-price-discounted-container" class'ından
                plus_discounted_container = soup.find("div", class_="ty-plus-price-discounted-container")
                if plus_discounted_container:
                    plus_price_text = plus_discounted_container.get_text()
                    plus_price_match = re.search(r'([0-9.,]+)\s*(?:TL|₺)', plus_price_text)
                    if plus_price_match:
                        plus_price_val = clean_price(plus_price_match.group(1))
                        print(f"DEBUG: Trendyol Plus Fiyatı: {plus_price_val}")
                        # Plus fiyatı ayrı alan olarak sakla (seller name'e eklemeyeceğiz)
                        if plus_price_val > 0 and plus_price_val < data["price"]:
                            data["plus_price"] = plus_price_val  # Ayrı alan - template'de kullanılacak
                
            elif price_wrapper:
                # Normal Trendyol ürünü (Plus değil)
                # İndirimli fiyat öncelikli (genelde daha küçük gösterilir)
                discounted_price = price_wrapper.find(class_=lambda x: x and ("prc-dsc" in x or "discounted" in x.lower()))
                regular_price = price_wrapper.find(class_=lambda x: x and ("prc-slg" in x or "selling" in x.lower()))
                
                if discounted_price:
                    data["price"] = clean_price(discounted_price.get_text())
                    # Normal fiyat varsa onu da kaydet
                    if regular_price:
                        data["original_price"] = clean_price(regular_price.get_text())
                elif regular_price:
                    data["price"] = clean_price(regular_price.get_text())
                else:
                    # Herhangi bir fiyat elemanı bul
                    price_elements = price_wrapper.find_all(string=re.compile(r'\d+[.,]\d+'))
                    for price_text in price_elements:
                        price_val = clean_price(price_text)
                        if price_val > 0:
                            data["price"] = price_val
                            break
            
            # Alternatif fiyat araması
            if data["price"] == 0:
                # class'ında "price" geçen tüm elemanları tara
                price_elems = soup.find_all(class_=lambda x: x and "price" in x.lower())
                for elem in price_elems:
                    price_text = elem.get_text()
                    if "tl" in price_text.lower() or "₺" in price_text:
                        price_val = clean_price(price_text)
                        if price_val > 0:
                            data["price"] = price_val
                            break
            
            # 3. SATICI BİLGİSİ
            # XPath: //*[@id="envoy"]/div/div[1]/div[1]
            # CSS: #envoy > div > div:first-child > div:first-child
            envoy_section = soup.find(id="envoy")
            
            if envoy_section:
                # "Bu ürün Bioworld tarafından gönderilecektir." metnini bul
                text_content = envoy_section.get_text()
                # "tarafından gönderilecektir" ile "Bu ürün" arasındaki kelime(leri) çek
                # Satıcı adı birden fazla kelime olabilir: "Trend Alaçatı Stili"
                seller_match = re.search(r'Bu ürün\s+(.+?)\s+tarafından gönderilecektir', text_content)
                if seller_match:
                    data["seller"] = seller_match.group(1).strip()  # "Bioworld" veya "Trend Alaçatı Stili"
                else:
                    data["seller"] = "Trendyol"
            else:
                # Alternatif: merchant/seller class'ı
                seller_elem = soup.find(class_=lambda x: x and ("merchant" in x.lower() or "seller" in x.lower()))
                if seller_elem:
                    seller_text = seller_elem.get_text(strip=True)
                    # Sadece ilk satırı/kelimeyi al (rating vb. bilgiler sonra gelir)
                    seller_text = re.split(r'[\d.,]+', seller_text)[0].strip()
                    seller_text = seller_text.split()[0] if seller_text.split() else seller_text
                    data["seller"] = seller_text if seller_text else "Trendyol"
                else:
                    data["seller"] = "Trendyol"

        # --- SEPHORA ---
        elif "sephora" in url:
            data["site"] = "Sephora"
            data["seller"] = "Sephora"

            # 0. BOYUT VARYANTI KONTROLÜ (ÖNCELİK)
            # Sephora'da boyut seçimi JavaScript ile yapılır, seçili olan variant'ı bulmamız gerekir
            selected_variant_price = 0
            
            # Yöntem 1: Seçili/Aktif boyutun fiyatını bul
            # Genelde "selected", "active", "checked" gibi class'lar kullanılır
            size_containers = soup.find_all(["div", "button", "label"], class_=lambda x: x and ("size" in x.lower() or "sku" in x.lower() or "variant" in x.lower()))
            
            for container in size_containers:
                # Seçili/aktif elemanı kontrol et
                if any(cls in str(container.get('class', [])).lower() for cls in ['selected', 'active', 'checked', 'current']):
                    # Bu container içinde fiyat var mı?
                    price_in_variant = container.find(string=re.compile(r'\d+[.,]\d+'))
                    if price_in_variant:
                        variant_price = clean_price(price_in_variant)
                        if variant_price > 10:  # Geçerli bir fiyat
                            selected_variant_price = variant_price
                            break
            
            # Yöntem 2: Radio button veya checkbox ile seçili olan boyutu bul
            if selected_variant_price == 0:
                checked_inputs = soup.find_all("input", {"checked": True, "type": ["radio", "checkbox"]})
                for inp in checked_inputs:
                    # Bu input'un yanındaki label veya parent'ında fiyat var mı?
                    parent = inp.parent
                    if parent:
                        price_text = parent.find(string=re.compile(r'\d+[.,]\d+'))
                        if price_text:
                            variant_price = clean_price(price_text)
                            if variant_price > 10:
                                selected_variant_price = variant_price
                                break
            
            # Seçili varyant fiyatı bulunduysa, onu kullan
            if selected_variant_price > 0:
                data["price"] = selected_variant_price

            # 1. JSON-LD KONTROLÜ (Yedek strateji)
            if data["price"] == 0:
                json_ld = get_json_ld(soup)
                if json_ld:
                    # Başlık
                    if 'name' in json_ld:
                        data["title"] = json_ld['name']
                    
                    # Fiyat
                    offers = json_ld.get('offers')
                    if offers:
                        offer = offers[0] if isinstance(offers, list) and offers else offers
                        if isinstance(offer, dict) and 'price' in offer:
                            try:
                                data["price"] = float(offer['price'])
                            except:
                                data["price"] = clean_price(str(offer['price']))

            # 2. BAŞLIK (Eğer JSON-LD'den gelmediyse)
            if not data["title"]:
                h1 = soup.find("h1")
                if h1:
                    data["title"] = h1.get_text(" ", strip=True)
                else:
                    h1_alt = soup.find("span", {"data-at": "product_name"})
                    data["title"] = h1_alt.get_text(strip=True) if h1_alt else "Sephora Ürünü"

            # 3. FİYAT - ÇOK KATMANLI STRATEJI (Eğer varyant bulunamadıysa)
            if data["price"] == 0:
                # Strateji 1: Kullanıcının önerdiği class (ancak sadece taksitsiz olanı)
                price_divs = soup.find_all("div", class_="product-price")
                for pdiv in price_divs:
                    text = pdiv.get_text()
                    # Taksit içermeyen ve sadece fiyat olan elemanı bul
                    if "taksit" not in text.lower() and "x" not in text.lower():
                        # En büyük rakamı al (genelde asıl fiyattır)
                        numbers = re.findall(r'\d+[.,]\d+|\d+', text)
                        if numbers:
                            # En büyük sayıyı bul (genelde ana fiyat en büyüktür)
                            all_prices = []
                            for num_str in numbers:
                                val = clean_price(num_str)
                                if val > 0:
                                    all_prices.append(val)
                            if all_prices:
                                # En büyük fiyatı al (taksit değil, ana fiyat)
                                data["price"] = max(all_prices)
                                break
                
                # Strateji 2: data-comp="Price" container
                if data["price"] == 0:
                    price_container = soup.find("p", {"data-comp": "Price"})
                    if price_container:
                        # Tüm span'ları tara, en büyük fiyatı al
                        all_spans = price_container.find_all("span")
                        max_price = 0
                        for span in all_spans:
                            text = span.get_text(strip=True)
                            if "taksit" not in text.lower():
                                val = clean_price(text)
                                if val > max_price:
                                    max_price = val
                        if max_price > 0:
                            data["price"] = max_price

                # Strateji 3: Genel arama - en büyük fiyatı bul
                if data["price"] == 0:
                     # TL veya ₺ içeren tüm elemanları bul
                     all_price_elements = soup.find_all(string=re.compile(r'\d+[.,]\d+'))
                     max_price = 0
                     for elem in all_price_elements:
                         text = elem.strip()
                         # Taksit ibaresi olmayan ve makul büyüklükte fiyatları kontrol et
                         parent_text = elem.parent.get_text() if elem.parent else text
                         if "taksit" not in parent_text.lower() and "x" not in text.lower():
                             val = clean_price(text)
                             # Mantıklı fiyat aralığı (10 TL - 100,000 TL arası)
                             if 10 < val < 100000 and val > max_price:
                                 max_price = val
                     if max_price > 0:
                         data["price"] = max_price


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