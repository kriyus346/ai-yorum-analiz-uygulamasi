# app.py
# -*- coding: utf-8 -*-

import sys
import traceback

# PyQt5: Masaüstü uygulaması arayüzü oluşturmak için kullanılan kütüphane
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QProgressBar,
    QMessageBox,
    QTextEdit,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

# Hata Yönetimi: Eğer scraper veya analyzer dosyaları eksikse programın çökmesini engeller.
try:
    from scraper import get_reviews  # Web kazıma fonksiyonu
    from analyzer import analyze_comments, warmup_models  # YZ analiz fonksiyonları
except ImportError:
    print("HATA: 'scraper.py' veya 'analyzer.py' dosyası eksik!")
    sys.exit(1)


# --- ARKA PLAN İŞÇİSİ (WORKER THREAD) ---
# Arayüzün (UI) donmaması için ağır işlemler (Scraping ve AI Analizi)
# ana döngüden ayrı bir "Thread" (iş parçacığı) içinde çalıştırılır.
class WorkerThread(QThread):
    finished = pyqtSignal(dict)  # İşlem başarıyla biterse veriyi (dictionary) ana ekrana yollar.
    error = pyqtSignal(str)      # Hata olursa hata mesajını (string) yollar.

    def __init__(self, url: str):
        super().__init__()
        self.url = url  # Analiz edilecek ürün linki

    def run(self):
        """Thread .start() komutuyla çağrıldığında çalışan ana fonksiyon"""
        try:
            # 1. ADIM: Yorumları Web'den Çek (Scraping)
            # max_reviews=None diyerek limit koymadan çekebildiği kadarını almasını söylüyoruz.
            data = get_reviews(self.url, max_reviews=None)
            comments = data.get("comments", [])

            # Eğer hiç yorum çekilemediyse hata sinyali gönder ve durdur.
            if not comments:
                self.error.emit("Yorum bulunamadı. Linki kontrol edin.")
                return

            # 2. ADIM: Yorumları Yapay Zeka ile Analiz Et
            # (analyze_comments fonksiyonu hem çeviri hem de duygu analizi yapar)
            result = analyze_comments(
                comments,
                total_reviews=data.get("total_reviews", 0),
                average_stars=data.get("average_stars", 0.0),
            )

            # Siteden toplam yorum sayısı çekilemediyse, elimizdeki yorum sayısını toplam kabul et.
            total_site_reviews = data.get("total_reviews", len(comments))

            # 3. ADIM: Sonuçları Ana Ekrana Gönder
            self.finished.emit(
                {
                    "score": result["final_score"],  # 0-100 arası yapay zeka puanı
                    "reviews": result["details"],    # Yorumların tek tek analiz detayları
                    "total_count": total_site_reviews, # Toplam yorum sayısı
                    "site_stars": data.get("average_stars", 0.0), # Sitedeki yıldız puanı
                }
            )

        except Exception as e:
            # Beklenmedik bir hata olursa konsola yazdır ve arayüze bildir.
            traceback.print_exc()
            self.error.emit(str(e))


# --- ANA PENCERE TASARIMI ---
class ModernApp(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Pencere özelliklerini ve stil ayarlarını yükler."""
        self.setWindowTitle("AI Ürün Analizi")
        self.setGeometry(200, 200, 600, 700) # x, y, genişlik, yükseklik

        # CSS Benzeri Stil Tanımlamaları (Koyu Tema)
        self.setStyleSheet(
            """
            QWidget { background-color: #181825; color: #cdd6f4; font-family: 'Segoe UI'; }
            QLineEdit {
                background-color: #313244; border: 2px solid #89b4fa;
                border-radius: 10px; padding: 10px; color: white; font-size: 14px;
            }
            QPushButton {
                background-color: #89b4fa; color: #1e1e2e; border-radius: 10px;
                padding: 12px; font-weight: bold; font-size: 15px;
            }
            QPushButton:hover { background-color: #b4befe; }
            QProgressBar {
                border: 2px solid #fab387; border-radius: 8px; text-align: center;
            }
            QProgressBar::chunk { background-color: #fab387; }
            QTextEdit {
                background-color: #1e1e2e; border: 1px solid #45475a;
                border-radius: 8px; padding: 10px; font-size: 13px; color: #a6adc8;
            }
        """
        )

        # QStackedWidget: Sayfalar arası geçiş yapmamızı sağlar (Home -> Loading -> Result)
        self.stack = QStackedWidget()
        self.layout = QVBoxLayout()

        self.page_home = self.ui_home()       # 1. Sayfa: Giriş
        self.page_loading = self.ui_loading() # 2. Sayfa: Yükleniyor
        self.page_result = self.ui_result()   # 3. Sayfa: Sonuçlar

        self.stack.addWidget(self.page_home)
        self.stack.addWidget(self.page_loading)
        self.stack.addWidget(self.page_result)

        self.layout.addWidget(self.stack)
        self.setLayout(self.layout)

    # ---------- SAYFA 1: GİRİŞ EKRANI ----------
    def ui_home(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_title = QLabel("Ürün / Yorum Analizi")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setFont(QFont("Segoe UI", 18, QFont.Bold))

        # Kullanıcıyı yönlendiren açıklama metni
        lbl_desc = QLabel(
            "Amazon ürün sayfası linkini gir,\n"
            "yorumları yapay zeka ile analiz edelim."
        )
        lbl_desc.setAlignment(Qt.AlignCenter)
        lbl_desc.setWordWrap(True)

        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("Amazon ürün linkini buraya yapıştır...")

        btn_start = QPushButton("Analize Başla")
        btn_start.clicked.connect(self.start_analysis) # Butona basınca start_analysis çalışır

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_desc)
        layout.addWidget(self.input_url)
        layout.addWidget(btn_start)
        layout.addStretch() # Elemanları yukarı itmek için boşluk

        page.setLayout(layout)
        return page

    # ---------- SAYFA 2: YÜKLENİYOR EKRANI ----------
    def ui_loading(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(10)

        lbl_main = QLabel("Analiz Yapılıyor...")
        lbl_main.setAlignment(Qt.AlignCenter)
        lbl_main.setFont(QFont("Segoe UI", 18, QFont.Bold))

        # Kullanıcıya işlemin uzun sürebileceğini bildiren metin
        lbl_sub = QLabel("Yorum sayısına bağlı olarak bu işlem biraz zaman alabilir.\nLütfen bekleyin.")
        lbl_sub.setAlignment(Qt.AlignCenter)
        lbl_sub.setFont(QFont("Segoe UI", 10))
        lbl_sub.setStyleSheet("color: #a6adc8;")

        # İlerleme çubuğu (Range 0-0 olduğu için sonsuz döngü animasyonu yapar)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)

        layout.addStretch()
        layout.addWidget(lbl_main)
        layout.addWidget(lbl_sub)
        layout.addSpacing(20)
        layout.addWidget(self.progress)
        layout.addStretch()

        page.setLayout(layout)
        return page

    # ---------- SAYFA 3: SONUÇ EKRANI ----------
    def ui_result(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_title = QLabel("Analiz Sonucu")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setFont(QFont("Segoe UI", 18, QFont.Bold))

        # Büyük puan göstergesi (Örn: %85)
        self.lbl_score = QLabel("%0")
        self.lbl_score.setAlignment(Qt.AlignCenter)
        self.lbl_score.setFont(QFont("Segoe UI", 32, QFont.Bold))

        # Detay bilgileri (Yorum sayısı ve site puanı)
        self.lbl_info = QLabel("Okunan Yorum: 0 | Site Puanı: 0.0")
        self.lbl_info.setAlignment(Qt.AlignCenter)

        # Analiz edilen yorumların detaylarını gösterecek metin alanı (Salt okunur)
        self.txt_reviews = QTextEdit()
        self.txt_reviews.setReadOnly(True)

        btn_back = QPushButton("Yeni Link Analiz Et")
        btn_back.clicked.connect(self.go_home) # Ana sayfaya dönüş

        layout.addWidget(lbl_title)
        layout.addWidget(self.lbl_score)
        layout.addWidget(self.lbl_info)
        layout.addWidget(self.txt_reviews)
        layout.addWidget(btn_back)

        page.setLayout(layout)
        return page

    # ---------- FONKSİYONLAR ----------
    def go_home(self):
        """Ana sayfaya döner ve girdiyi temizler."""
        self.stack.setCurrentIndex(0)

    def start_analysis(self):
        """Analiz işlemini başlatır."""
        url = self.input_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Uyarı", "Lütfen bir ürün linki girin.")
            return

        self.stack.setCurrentIndex(1) # Yükleniyor sayfasına geç

        try:
            # Modelleri önceden yüklemeyi dene (hızlandırma amaçlı)
            warmup_models()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Modeller yüklenirken hata oluştu:\n{e}")
            self.stack.setCurrentIndex(0)
            return

        # Thread'i oluştur ve başlat
        self.worker = WorkerThread(url)
        self.worker.finished.connect(self.display_result) # Başarılı olursa display_result çalışsın
        self.worker.error.connect(self.display_error)     # Hata olursa display_error çalışsın
        self.worker.start()

    def display_result(self, data: dict):
        """Thread'den gelen sonuçları ekrana basar."""
        score = data.get("score", 0)
        reviews = data.get("reviews", [])

        # Puana göre renk belirleme (Yeşil, Sarı, Kırmızı)
        if score >= 75:
            color = "#a6e3a1"
        elif score >= 50:
            color = "#f9e2af"
        else:
            color = "#f38ba8"

        self.lbl_score.setText(f"%{score}")
        self.lbl_score.setStyleSheet(
            f"color: {color}; font-size: 72px; font-weight: bold;"
        )

        self.lbl_info.setText(
            f"Okunan Yorum: {data.get('total_count', 0)} | "
            f"Site Puanı: {data.get('site_stars', 0.0)}"
        )

        # Yorumları puanlarına göre sıralayıp (En iyi ve En kötü) göster
        text = ""
        text += "--- 👍 NEDEN SEVİLDİ? ---\n"
        # En yüksek puanlı 3 yorum
        for r in sorted(reviews, key=lambda x: x["score"], reverse=True)[:3]:
            text += f"[{r['score']}] {r['translated']}\n\n"

        text += "\n--- 👎 NEDEN ELEŞTİRİLDİ? ---\n"
        # En düşük puanlı 3 yorum
        for r in sorted(reviews, key=lambda x: x["score"])[:3]:
            text += f"[{r['score']}] {r['translated']}\n\n"

        self.txt_reviews.setText(text)
        self.stack.setCurrentIndex(2) # Sonuç sayfasına geç

    def display_error(self, msg: str):
        """Hata mesajını kullanıcıya gösterir."""
        self.stack.setCurrentIndex(0) # Ana sayfaya dön
        QMessageBox.critical(self, "Hata", msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ModernApp()
    window.show()
    sys.exit(app.exec_())