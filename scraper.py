# scraper.py
# -*- coding: utf-8 -*-

from playwright.sync_api import sync_playwright
import time
import re


def parse_number(text: str) -> int:
    """
    Siteden gelen '2.5k değerlendirme' veya '1,200 yorum' gibi karmaşık metinleri
    temizleyip saf sayıya (integer) çevirir.
    """
    if not text:
        return 0

    t = text.lower().strip()

    # "k" harfi varsa (Örn: 2.5k -> 2500)
    if "k" in t:
        try:
            t = t.replace(",", ".")
            num = float(re.findall(r"[\d\.]+", t)[0])
            return int(num * 1000)
        except Exception:
            return 0

    # Normal sayıları yakala (Nokta ve virgülleri temizle)
    digits = re.findall(r"\d+", t.replace(".", "").replace(",", ""))
    if digits:
        try:
            return int(digits[-1])
        except Exception:
            return 0

    return 0


def get_reviews(url: str, max_reviews: int | None = None):
    """
    Ana kazıma fonksiyonu.
    url: Gidilecek web sitesi adresi.
    max_reviews: En fazla kaç yorum çekileceği (None ise sınır yok).
    """
    print(f">> Scraper bağlanıyor: {url}")

    data = {"comments": [], "total_reviews": 0, "average_stars": 0.0}

    # Playwright tarayıcı motorunu başlat
    with sync_playwright() as p:
        # Headless=True: Tarayıcı penceresi açılmadan arka planda çalışır
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # Sayfaya git ve yüklenmesini bekle (Timeout: 60 saniye)
            page.goto(url, timeout=60000)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2) # Ekstra güvenlik beklemesi
        except Exception as e:
            print(f"Bağlantı hatası: {e}")
            browser.close()
            return data

        # ---------------- AMAZON İÇİN KAZIMA MANTIĞI ----------------
        if "amazon" in url:
            try:
                # 1. Ortalama Yıldız Puanını Çek (Örn: "4,8 üzerinden 5 yıldız")
                star_el = page.query_selector("span.a-icon-alt")
                if star_el:
                    raw = star_el.inner_text().strip()
                    # Metni parçala ve sadece puanı al (4.8)
                    first = raw.split(" ")[0].replace(",", ".")
                    try:
                        data["average_stars"] = float(first)
                    except Exception:
                        pass

                # 2. Toplam Yorum Sayısını Çek
                count_el = page.query_selector("#acrCustomerReviewText")
                if count_el:
                    data["total_reviews"] = parse_number(count_el.inner_text())

                # 3. Yorum Metinlerini Çek
                # Amazon'da yorumlar genellikle 'review-body' data-hook'u içinde olur.
                reviews = page.query_selector_all("span[data-hook='review-body']")
                for r in reviews:
                    t = r.inner_text().strip()
                    # Çok kısa ve anlamsız yorumları ele (en az 5 karakter)
                    if len(t) > 5:
                        data["comments"].append(t)
                        # Eğer limit varsa ve ulaşıldıysa döngüyü kır
                        if max_reviews is not None and len(data["comments"]) >= max_reviews:
                            break

            except Exception as e:
                print(f"Amazon scraper hatası: {e}")
        
        else:
            # Sadece Amazon destekleniyor, Hepsiburada kaldırıldı.
            print("HATA: Desteklenmeyen site veya Hepsiburada kaldırıldı.")

        browser.close()

    print(f">> Scraper tamamlandı. {len(data['comments'])} yorum çekildi.")
    return data