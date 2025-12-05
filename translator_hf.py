# translator_hf.py
# -*- coding: utf-8 -*-

import sys
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
import torch

# Facebook'un çok dilli çeviri modeli (Hugging Face'den)
MODEL_NAME = "facebook/m2m100_418M"


def main():
    # Komut satırı argümanlarını kontrol et
    # Kullanım: python translator_hf.py <girdi.txt> <cikti.txt> <kaynak_dil>
    if len(sys.argv) < 4:
        print("Kullanım: python translator_hf.py <input_txt> <output_txt> <src_lang>", file=sys.stderr)
        sys.exit(1)

    in_path = sys.argv[1]   # Okunacak dosya yolu
    out_path = sys.argv[2]  # Yazılacak dosya yolu
    src_lang = sys.argv[3]  # Kaynak dil kodu (örn: 'en')

    print(">> translator_hf: model yükleniyor...")
    tokenizer = M2M100Tokenizer.from_pretrained(MODEL_NAME)
    model = M2M100ForConditionalGeneration.from_pretrained(MODEL_NAME)
    model.eval()
    print(">> translator_hf: model yüklendi.")

    # Girdi dosyasını oku
    with open(in_path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    # Dosya boşsa işlem yapma
    if not text:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("")
        sys.exit(0)

    # Metni modele uygun formata getir (Tokenization)
    tokenizer.src_lang = src_lang
    encoded = tokenizer(text, return_tensors="pt")
    
    # Çeviri işlemini yap (Hedef dil zorla 'tr' yani Türkçe olarak ayarlandı)
    with torch.no_grad():
        generated = model.generate(
            **encoded,
            forced_bos_token_id=tokenizer.get_lang_id("tr"),
        )
    
    # Sayısal çıktıları tekrar metne çevir (Decode)
    translated = tokenizer.batch_decode(generated, skip_special_tokens=True)[0]

    # Sonucu çıktı dosyasına yaz
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(translated)

    print(">> translator_hf: çeviri tamamlandı.")


if __name__ == "__main__":
    main()