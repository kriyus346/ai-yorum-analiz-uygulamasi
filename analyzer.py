# analyzer.py
# -*- coding: utf-8 -*-

import warnings
warnings.filterwarnings("ignore") # Gereksiz uyarıları gizle

import os
import tempfile
import subprocess

import torch
from langdetect import detect
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# Hugging Face'den indirilecek Türkçe Duygu Analizi Modeli (BERT)
SENT_MODEL_NAME = "savasy/bert-base-turkish-sentiment-cased"

# Modeller bellekte (RAM) tutulacak değişkenler
sent_tokenizer = None
sent_model = None

print(">> NLP modülleri hazır. Modeller ihtiyaç olduğunda yüklenecek.")


# ---------------- SENTIMENT (DUYGU) MODELİ ---------------- #

def load_sentiment_model():
    """
    Sentiment modelini sadece ihtiyaç olduğunda yükler (Lazy Loading).
    Böylece program açılır açılmaz RAM'i doldurmaz.
    """
    global sent_tokenizer, sent_model
    if sent_model is not None and sent_tokenizer is not None:
        return # Zaten yüklüyse tekrar yükleme

    print(">> Sentiment modeli yükleniyor... (İlk seferde biraz uzun sürebilir)")
    try:
        sent_tokenizer = AutoTokenizer.from_pretrained(SENT_MODEL_NAME)
        sent_model = AutoModelForSequenceClassification.from_pretrained(SENT_MODEL_NAME)
        sent_model.eval() # Modeli değerlendirme moduna al (Eğitim modu değil)
        print(">> Sentiment modeli yüklendi.")
    except Exception as e:
        print(f"Sentiment modeli hatası: {e}")
        sent_tokenizer = None
        sent_model = None


def warmup_models():
    """
    app.py tarafından çağrılır. Analiz başlamadan önce modeli belleğe alarak
    kullanıcının bekleme süresini optimize eder.
    """
    load_sentiment_model()


# ---------------- ÇEVİRİ (AYRI PROCESS - subprocess) ---------------- #

def translate_with_hf_subprocess(text: str, src_lang: str) -> str:
    """
    Çeviri işlemi çok RAM tükettiği için ana programı yormamak adına
    ayrı bir Python işlemi (process) olarak 'translator_hf.py' dosyasını çalıştırır.
    """
    # Çevrilecek metni geçici bir dosyaya (.txt) yaz
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as f_in:
        f_in.write(text)
        in_path = f_in.name

    # Çeviri sonucunun yazılacağı boş bir geçici dosya oluştur
    out_fd, out_path = tempfile.mkstemp(suffix=".txt")
    os.close(out_fd)

    try:
        # Komut satırından: python translator_hf.py <girdi_dosyası> <çıktı_dosyası> <dil_kodu>
        cmd = ["python", "translator_hf.py", in_path, out_path, src_lang]
        print(">> analyzer: translator_hf.py çağrılıyor...", cmd)
        
        # İşlemi başlat ve bitmesini bekle
        subprocess.run(cmd, check=True)

        # Çevrilmiş metni dosyadan oku
        with open(out_path, "r", encoding="utf-8") as f_out:
            translated = f_out.read().strip()

        return translated or text # Çeviri boşsa orijinali döndür
    except Exception as e:
        print(f"Çeviri alt süreç hatası: {e}")
        return text
    finally:
        # İşlem bitince geçici dosyaları temizle (Disk kirliliğini önle)
        try:
            if os.path.exists(in_path): os.remove(in_path)
        except Exception: pass
        try:
            if os.path.exists(out_path): os.remove(out_path)
        except Exception: pass


def translate_if_needed(text: str) -> str:
    """
    Yorumun dilini algılar. Eğer Türkçe değilse çeviri sürecini başlatır.
    """
    try:
        lang = detect(text) # Dil algılama (Örn: 'en', 'fr', 'tr')
    except Exception:
        lang = "tr" # Hata olursa Türkçe varsay

    if lang == "tr":
        return text # Zaten Türkçeyse çevirme

    # Yabancı dildeyse çeviri fonksiyonuna gönder
    return translate_with_hf_subprocess(text, lang)


# ---------------- SENTIMENT PUANI HESAPLAMA ---------------- #

def get_sentiment_score(text: str) -> int:
    """
    Metni BERT modeline verir ve 0 ile 100 arasında bir 'Olumluluk Puanı' döndürür.
    """
    load_sentiment_model()
    if sent_model is None or sent_tokenizer is None:
        return 50  # Model yüklenemezse Nötr (50) puan ver

    # Metni modelin anlayacağı sayısal vektörlere çevir (Tokenization)
    inputs = sent_tokenizer(
        text,
        return_tensors="pt",
        padding=True,
        truncation=True,
    )
    
    # Modeli çalıştır (Gradyan hesaplama yapma, sadece tahmin)
    with torch.no_grad():
        outputs = sent_model(**inputs)

    # Çıktıyı olasılığa çevir (Softmax)
    probs = torch.nn.functional.softmax(outputs.logits, dim=1)[0]
    positive_score = float(probs[-1]) # Pozitif sınıfının olasılığı
    return int(positive_score * 100)


# ---------------- ANA ANALİZ FONKSİYONU ---------------- #

def analyze_comments(comments, total_reviews: int = 0, average_stars: float = 0.0):
    """
    Tüm süreci yöneten beyin fonksiyonu:
    1. Yorumları çevir
    2. Duygu analizi yap
    3. Puanları istatistiksel olarak dengele (Bayesian Smoothing)
    """
    if not comments:
        return {"final_score": 50, "details": []}

    processed = []
    scores = []

    for comment in comments:
        # Çok kısa (3 kelimeden az) yorumları analiz etme
        if len(comment.split()) < 3:
            continue

        # 1. Çeviri
        bg_text = translate_if_needed(comment)
        # 2. Puanlama
        score = get_sentiment_score(bg_text)

        processed.append(
            {
                "original": comment,
                "translated": bg_text,
                "score": score,
            }
        )
        scores.append(score)

    if not scores:
        return {"final_score": 50, "details": processed}

    # -- PUAN HESAPLAMA ALGORİTMASI --

    # Adım 1: Yapay zekanın verdiği puanların ortalaması
    avg_ai_score = sum(scores) / len(scores)

    # Adım 2: Bayesian Düzeltme (Smoothing)
    # Az sayıda yorum varsa puana hemen güvenme, onu genel ortalamaya (60) yaklaştır.
    # Yorum sayısı arttıkça (m=10 eşiğini geçtikçe) yapay zeka puanına daha çok güven.
    count = len(scores)
    C = 60  # Varsayılan güvenli puan
    m = 10  # Güven eşiği (yorum sayısı)
    bayesian_score = (count / (count + m)) * avg_ai_score + (m / (count + m)) * C

    # Adım 3: Sitedeki Yıldız Puanını Dahil Et
    # Sonuç sadece yapay zekaya değil, sitedeki yıldızlara da bağlı olsun.
    if average_stars > 0:
        star_score = (average_stars / 5.0) * 100
        # %70 Yapay Zeka, %30 Site Puanı ağırlığı
        final_score = (bayesian_score * 0.7) + (star_score * 0.3)
    else:
        final_score = bayesian_score

    return {
        "final_score": int(final_score),
        "details": processed,
    }