# 📦🤖 Inventory and Purchasing Support Assistant (Group 6)

* 🎓 **Course:** LLM Fundamentals and AI Agent Development
* 🔗 **Repository:** `inventory-purchasing-agent`
* 🏗️ **Architecture:** Single-Agent LLM + Deterministic Python Tools

---

# 🇬🇧 ENGLISH DOCUMENTATION

## 1. 🎯 Project Objective

This project implements a **Single-Agent LLM-based AI Assistant** designed to support inventory management and purchasing operations for a single business and warehouse. Using inventory, dated demand, open purchase orders, and supplier datasets, the agent identifies net material requirements, evaluates eligible suppliers on a comparable cost and delivery basis, and prepares purchase requisition drafts.

> ⚠️ **Core Design Principle:** The LLM acts strictly as an orchestrator (interpreting user intent, asking clarifying questions, selecting tools, and explaining results with evidence). All numerical calculations, date projections, and eligibility checks are executed deterministically via Python code. Requisitions are logged into a test environment **only after explicit user approval** and never modify physical stock or trigger real orders.

---

## 2. 👥 Team Members & Roles

| 🆔 Student ID | 👤 Name | 🎯 Primary Role |
| :--- | :--- | :--- |
| **2204012301** | **İrem YILMAZ** | 📊 Data Architecture, Calculation Engine & Baseline |
| **2304010611** | **Hande Reyyan FİDAN** | 🧠 Agent Architecture, Tool Integration & State Management |
| **2404010546** | **Eren KAYNAK** | 🧪 Testing Suite, Demo Interface & Technical Report |

### 📋 Detailed Role Breakdown

#### 📊 1. İrem YILMAZ (`2204012301`) — Data Architecture, Calculation Engine & Baseline
* 🗄️ **Synthetic Data & Dictionary:** Designs and generates realistic synthetic datasets (products, physical/allocated stock, dated demand, open orders, suppliers) along with a comprehensive Data Dictionary.
* 🔍 **Retrieval Tools:** Implements inventory, demand, and open-order query functions with strict data timestamp and validity checks.
* 🧮 **Deterministic Calculation Engine:** Codes date-by-date inventory projections (preventing mid-horizon stockouts), anti-double counting logic, safety stock rules, and MOQ/pack multiple rounding.
* 📏 **Rule-Based Baseline:** Develops the non-LLM deterministic baseline script for benchmarking accuracy and cost efficiency.

#### 🧠 2. Hande Reyyan FİDAN (`2304010611`) — Agent Architecture, Tool Integration & State Management
* 🤖 **Single-Agent Orchestration:** Designs the LLM agent loop, system prompts, clarifying question flows, and context-aware follow-up handling.
* ⚖️ **Supplier Comparison & Requisition Tools:** Implements multi-currency/freight cost normalization, lead-time eligibility checks, and draft/test requisition logging.
* 🔄 **State & Human-in-the-Loop:** Manages draft versions, assumptions, and explicit user approval gates; performs real-time data freshness re-checks right before logging.
* 🛡️ **Security & Architecture:** Implements idempotency (preventing duplicate records), retry/step limits, prompt injection defenses against malicious supplier notes, and creates the system workflow diagram.

#### 🧪 3. Eren KAYNAK (`2404010546`) — Testing Suite, Demo Interface & Technical Report
* 📝 **20+ Edge-Case Scenarios:** Designs at least 20 test scenarios covering mid-horizon shortages, missing units, late open orders, currency/freight variations, withheld approvals, stale data, and prompt injections, paired with manually verified ground-truth results.
* 📈 **Automated Evaluation Suite:** Builds the evaluation runner comparing Agent vs. Baseline across task success rate, calculation accuracy, latency, token cost, and safe stopping behavior.
* 💻 **Interactive Demo UI:** Develops the live presentation interface (Streamlit / Chainlit) displaying chat interactions, tool calls, and approval summaries.
* 📄 **Technical Report & Docs:** Compiles the final technical report, setup guides, and evaluation tables.

---

## 3. ✨ Key Features & Architecture

* 💬 **Request Interpretation & Clarification:** Identifies materials, planning horizon, required-by dates, and budget constraints; asks the user when critical parameters (e.g., units or dates) are missing.
* 🧮 **Deterministic Calculation Engine:**
  * Distinguishes physical, allocated/blocked, and available inventory (`Available = Physical - Allocated`).
  * Prevents double counting between allocated stock and horizon demand.
  * Performs **date-by-date inventory projections** to detect mid-horizon stockouts that aggregate balances might hide.
  * Applies safety stock targets, Minimum Order Quantities (MOQ), and pack multiples.
* 🚚 **Supplier Comparison:** Evaluates lead times (business/calendar days), budget compliance, currency conversions, and freight costs on a common basis. Rejects cheap options that fail mandatory delivery deadlines.
* 🔒 **State & Safety Management:**
  * Maintains retrieved records, assumptions, draft versions, and approval status in state.
  * **Data Freshness Check:** Re-verifies stock and pricing at the moment of approval; requests renewed approval if values have changed.
  * **Idempotency & Prompt Injection Defense:** Prevents duplicate requisition logging and ignores misleading instructions embedded inside supplier notes.

---

## 4. 📂 Folder Structure

```text
inventory-purchasing-agent/
├── 📁 data/                # Synthetic datasets (JSON/CSV/SQLite), generator script & data dictionary
├── 📁 src/
│   ├── 📁 tools/           # Tool functions: inventory, calculation, supplier comparison, requisition
│   ├── 📁 agent/           # Single-agent orchestration, prompts, state management & guardrails
│   └── 🐍 baseline.py      # Rule-based deterministic baseline for benchmarking
├── 📁 tests/               # 20+ test scenarios, ground-truth calculations & evaluation runner
├── 📁 docs/                # Architecture/workflow diagrams & technical report
├── 🖥️ app.py               # Interactive demo UI (Streamlit / Chainlit)
├── 🔑 .env.example         # Environment variable template (API keys)
├── 📦 requirements.txt     # Python dependencies
└── 📘 README.md            # Project documentation
```

---

## 5. 🚀 Setup & Installation

### 📌 Prerequisites
* 🐍 Python 3.10 or higher
* 🌿 Git
* 🔑 An LLM API Key (e.g., OpenAI or Google Gemini)

### 🛠️ Step-by-Step Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ylmzrem/inventory-purchasing-agent.git
   cd inventory-purchasing-agent
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Copy `.env.example` to `.env` and add your API key:
   ```bash
   cp .env.example .env
   ```

5. **Generate synthetic data (if not already present):**
   ```bash
   python data/generate_data.py
   ```

6. **Run the live demo application:**
   ```bash
   streamlit run app.py
   ```

7. **Run the evaluation test suite (Agent vs. Baseline):**
   ```bash
   python tests/run_evaluation.py
   ```

---
---

# 📦🤖 Stok ve Satın Alma Destek Asistanı (Grup 6)

* 🎓 **Ders:** LLM Fundamentals and AI Agent Development
* 🔗 **Depo:** `inventory-purchasing-agent`
* 🏗️ **Mimari:** Tek-Agent (Single-Agent) LLM + Deterministik Python Araçları

---

# 🇹🇷 TÜRKÇE DOKÜMANTASYON

## 1. 🎯 Projenin Amacı

Bu proje; tek bir işletme ve tek bir depo için stok yönetimi ve satın alma süreçlerini destekleyen **Tek-Agent (Single-Agent) mimarisine sahip LLM tabanlı bir Yapay Zeka Asistanı** geliştirmeyi amaçlamaktadır. Sistem; mevcut stok, tarihli talep, açık siparişler ve tedarikçi verilerini kullanarak net malzeme ihtiyaçlarını belirler, uygun tedarikçileri ortak maliyet ve teslim süresi temelinde karşılaştırır ve satın alma talebi taslağı hazırlar.

> ⚠️ **Temel Tasarım İlkesi:** LLM yalnızca orkestratör olarak kullanılır (kullanıcı isteğini anlama, eksik bilgiyi sorma, uygun araçları seçme ve sonuçları verilerle açıklama). Tüm sayısal hesaplamalar, tarih projeksiyonları ve uygunluk kontrolleri Python kodu üzerinden deterministik olarak yapılır. Satın alma talepleri **yalnızca kullanıcının açık onayından sonra** test ortamına kaydedilir; fiziksel stoğu artırmaz ve gerçek siparişe dönüşmez.

---

## 2. 👥 Ekip Üyeleri ve Roller

| 🆔 Öğrenci No | 👤 Ad Soyad | 🎯 Ana Rol |
| :--- | :--- | :--- |
| **2204012301** | **İrem YILMAZ** | 📊 Veri Mimarisi, Hesaplama Motoru ve Baseline |
| **2304010611** | **Hande Reyyan FİDAN** | 🧠 Agent Mimarisi, Araç Entegrasyonu ve Durum Yönetimi |
| **2404010546** | **Eren KAYNAK** | 🧪 Test Süiti, Demo Arayüzü ve Teknik Rapor |

### 📋 Detaylı Görev Dağılımı

#### 📊 1. İrem YILMAZ (`2204012301`) — Veri Mimarisi, Hesaplama Motoru ve Baseline
* 🗄️ **Sentetik Veri ve Veri Sözlüğü:** Gerçekçi sentetik veri setlerini (ürünler, fiziksel/ayrılmış stok, tarihli talep, açık siparişler, tedarikçiler) ve kapsamlı Veri Sözlüğü'nü hazırlar.
* 🔍 **Sorgulama Araçları:** Veri tarihi ve geçerlilik kontrollerini içeren stok, talep ve açık sipariş sorgulama fonksiyonlarını kodlar.
* 🧮 **Deterministik Hesaplama Motoru:** Ara dönem stok tükenmelerini yakalayan gün bazlı stok projeksiyonunu, çift sayım önleme mantığını, emniyet stoku kurallarını ve MOQ/paket katı yuvarlamalarını yazar.
* 📏 **Kural Tabanlı Baseline:** Karşılaştırma (benchmark) testleri için LLM kullanmayan kural tabanlı baseline scriptini geliştirir.

#### 🧠 2. Hande Reyyan FİDAN (`2304010611`) — Agent Mimarisi, Araç Entegrasyonu ve Durum Yönetimi
* 🤖 **Tek-Agent Orkestrasyonu:** LLM agent döngüsünü, sistem promptlarını, eksik bilgi sorma akışlarını ve bağlam tabanlı takip sorularını tasarlar.
* ⚖️ **Tedarikçi Karşılaştırma ve Talep Araçları:** Döviz kuru/nakliye dahil maliyet normalizasyonunu, teslim süresi uygunluk kontrollerini ve taslak/test talep kaydı araçlarını kodlar.
* 🔄 **Durum (State) ve Onay Akışı:** Taslak sürümlerini, varsayımları ve açık kullanıcı onay mekanizmasını yönetir; kayıt anında verilerin değişip değişmediğini yeniden kontrol eder.
* 🛡️ **Güvenlik ve Mimari Şema:** Mükerrer kayıt önleme (idempotency), adım/tekrar deneme sınırları, tedarikçi notlarındaki prompt injection saldırılarına karşı korumaları ekler ve sistem iş akışı diyagramını çizer.

#### 🧪 3. Eren KAYNAK (`2404010546`) — Test Süiti, Demo Arayüzü ve Teknik Rapor
* 📝 **20+ Uç Durum Test Senaryosu:** Ara dönem stok bitmesi, eksik birim, geç açık sipariş, kur/nakliye farkları, onay reddi, onay öncesi veri değişimi ve prompt injection durumlarını kapsayan en az 20 senaryoyu ve elle doğrulanmış beklenen sonuçlarını hazırlar.
* 📈 **Otomatik Değerlendirme Paketi:** Agent ve Baseline sistemlerini görev başarı oranı, hesaplama doğruluğu, yanıt süresi, model maliyeti ve doğru durma davranışı açısından kıyaslayan test scriptini yazar.
* 💻 **Canlı Demo Arayüzü:** Sohbet akışını, arka plandaki araç çağrılarını ve onay özetlerini görselleştiren canlı sunum arayüzünü (Streamlit / Chainlit) geliştirir.
* 📄 **Teknik Rapor ve Dokümantasyon:** Nihai teknik raporu, kurulum kılavuzlarını ve test karşılaştırma tablolarını derler.

---

## 3. ✨ Temel Özellikler ve Mimari

* 💬 **Talebi Anlama ve Eksik Bilgi Toplama:** Ürünleri, planlama dönemini, ihtiyaç tarihini ve bütçe sınırlarını belirler; tarih veya birim gibi kritik bilgiler eksikse kullanıcıya sorar.
* 🧮 **Deterministik Hesaplama Motoru:**
  * Fiziksel stok, ayrılmış/bloke stok ve kullanılabilir stoğu ayırt eder (`Kullanılabilir = Fiziksel - Ayrılmış`).
  * Ayrılmış stok ile dönem talebi arasındaki çift sayımı (double counting) önler.
  * Dönem sonu toplamının ara tarihteki stok yetersizliğini gizlememesi için **gün bazlı tarihli stok projeksiyonu** yapar.
  * Hedef emniyet stoku, Minimum Sipariş Miktarı (MOQ) ve paket katı yuvarlama kurallarını uygular.
* 🚚 **Tedarikçi Karşılaştırma:** Teslim sürelerini (iş/takvim günü), bütçe uygunluğunu, döviz kurlarını ve nakliye maliyetlerini ortak bir temelde değerlendirir. Zorunlu teslim tarihine yetişemeyen ucuz seçenekleri uygunmuş gibi seçmez.
* 🔒 **Durum (State) ve Güvenlik Yönetimi:**
  * Sorgulanan kayıtları, hesaplama varsayımlarını, taslak sürümlerini ve onay durumunu hafızada tutar.
  * **Veri Güncelliği Kontrolü:** Onay anında stok ve fiyat verilerini yeniden kontrol eder; değerler değiştiyse kayıt oluşturmayıp yeniden onay ister.
  * **Mükerrer İşlem ve Prompt Injection Koruması:** Aynı talebin birden fazla kez kaydedilmesini engeller ve tedarikçi notlarının içine gizlenmiş yanıltıcı komutları (prompt injection) yok sayar.

---

## 4. 📂 Klasör Yapısı

```text
inventory-purchasing-agent/
├── 📁 data/                # Sentetik veri setleri (JSON/CSV/SQLite), üretim scripti ve veri sözlüğü
├── 📁 src/
│   ├── 📁 tools/           # Araç fonksiyonları: stok, hesaplama, tedarikçi karşılaştırma, talep kaydı
│   ├── 📁 agent/           # Tek-agent döngüsü, sistem promptları, state yönetimi ve güvenlik kuralları
│   └── 🐍 baseline.py      # Kıyaslama (benchmark) için kural tabanlı baseline scripti
├── 📁 tests/               # 20+ test senaryosu, elle doğrulanmış sonuçlar ve değerlendirme scripti
├── 📁 docs/                # Mimari/iş akışı diyagramları ve kısa teknik rapor
├── 🖥️ app.py               # Canlı demo arayüzü (Streamlit / Chainlit)
├── 🔑 .env.example         # Ortam değişkenleri şablonu (API anahtarları)
├── 📦 requirements.txt     # Gerekli Python kütüphaneleri
└── 📘 README.md            # Proje dokümantasyonu
```

---

## 5. 🚀 Kurulum ve Çalıştırma

### 📌 Gereksinimler
* 🐍 Python 3.10 veya üzeri
* 🌿 Git
* 🔑 LLM API Anahtarı (OpenAI veya Google Gemini vb.)

### 🛠️ Adım Adım Kurulum

1. **Depoyu bilgisayarınıza klonlayın:**
   ```bash
   git clone https://github.com/ylmzrem/inventory-purchasing-agent.git
   cd inventory-purchasing-agent
   ```

2. **Sanal ortam (virtual environment) oluşturun ve aktif edin:**
   ```bash
   python -m venv venv
   # Windows için:
   venv\Scripts\activate
   # macOS/Linux için:
   source venv/bin/activate
   ```

3. **Gerekli kütüphaneleri yükleyin:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Ortam değişkenlerini ayarlayın:**
   `.env.example` dosyasını `.env` olarak kopyalayın ve API anahtarınızı ekleyin:
   ```bash
   cp .env.example .env
   ```

5. **Sentetik veri setini oluşturun (mevcut değilse):**
   ```bash
   python data/generate_data.py
   ```

6. **Canlı demo uygulamasını başlatın:**
   ```bash
   streamlit run app.py
   ```

7. **Değerlendirme ve test paketini çalıştırın (Agent vs. Baseline):**
   ```bash
   python tests/run_evaluation.py
   ```
