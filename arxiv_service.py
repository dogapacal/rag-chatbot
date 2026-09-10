import os
import requests
import xml.etree.ElementTree as ET

# İndirilen makale ID'lerini tutan hafıza seti
INDIRILEN_MAKALELER = set()
INDIRILEN_MAKALELER.clear()

# Takip edeceğimiz hedef konular
HEDEF_KONULAR = [
    'all:"retrieval augmented generation"',
    'all:"large language models"',
    'all:"ai agents"',
    'all:"model quantization" OR all:"local llm"'
]

def arxiv_gunluk_tara_ve_indir(process_pdf_func=None, metadata_func=None):
    """
    Belirlenen konularda en son çıkan makaleleri tarar,
    yeni olanları indirir ve varsa RAG boru hattına gönderir.
    """
    klasor = "auto_collected_papers"
    os.makedirs(klasor, exist_ok=True)
    headers = {"User-Agent": "AcademicAssistant/1.0"}

    yeni_indirilenler = []

    for konu in HEDEF_KONULAR:
        print(f"\n🔍 [arXiv] Taranıyor: {konu}", flush=True)
        parametreler = {
            "search_query": konu,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": 2  # Her konudan sadece en taze 2 makale
        }

        try:
            cevap = requests.get(
                "https://export.arxiv.org/api/query",
                params=parametreler,
                headers=headers,
                timeout=15
            )
            if cevap.status_code != 200:
                print(f"⚠️ [arXiv] API hatası ({konu}): {cevap.status_code}", flush=True)
                continue

            root = ET.fromstring(cevap.text)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', ns)

            for entry in entries:
                makale_id = entry.find('atom:id', ns).text.strip()
                baslik = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
                ozet_alani = entry.find('atom:summary', ns)
                ozet_metni = ozet_alani.text.strip().replace('\n', ' ') if ozet_alani is not None else ""

                if makale_id in INDIRILEN_MAKALELER:
                    print(f"  ℹ️ Zaten kayıtlı: {baslik[:35]}...", flush=True)
                    continue

                print(f"  ✨ YENİ: {baslik}", flush=True)
                pdf_url = makale_id.replace('http://', 'https://').replace('/abs/', '/pdf/') + '.pdf'

                pdf_cevap = requests.get(pdf_url, headers=headers, stream=True, timeout=30)
                if pdf_cevap.status_code == 200:
                    temiz_id = makale_id.split('/')[-1]
                    dosya_yolu = os.path.join(klasor, f"{temiz_id}.pdf")

                    with open(dosya_yolu, "wb") as f:
                        for parca in pdf_cevap.iter_content(chunk_size=16384):
                            f.write(parca)

                    INDIRILEN_MAKALELER.add(makale_id)
                    yeni_indirilenler.append((dosya_yolu, baslik))
                    print(f"  📥 Diske yazıldı: {dosya_yolu}", flush=True)

                    # Qdrant adımını ayrı try-except içine alıyoruz; hata verse bile dosya diski terk etmez
                    if process_pdf_func:
                        try:
                            print(f"  ⚙️ Qdrant için işleniyor: {baslik[:30]}...", flush=True)
                            process_pdf_func(dosya_yolu, meta={"kaynak": "arxiv_otomasyon", "baslik": baslik})
                        except Exception as q_err:
                            print(f"  ⚠️ Qdrant kayıt hatası ({temiz_id}): {q_err}", flush=True)

                    if metadata_func:
                        try:
                            metadata_func(temiz_id, baslik, konu, ozet_metni)
                        except Exception as m_err:
                            print(f"  ⚠️ Metadata kayıt hatası ({temiz_id}): {m_err}", flush=True)

        except Exception as e:
            print(f"  ❌ Hata ({konu}): {e}", flush=True)

    print(f"\n🏁 [arXiv] Tarama bitti. Toplam {len(yeni_indirilenler)} yeni makale sisteme eklendi.", flush=True)