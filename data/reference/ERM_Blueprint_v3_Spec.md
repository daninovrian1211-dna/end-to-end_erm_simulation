# ERM Blueprint v3 — Specification (Fase 0)

**Enterprise Risk Management Framework: Risk Appetite, Monitoring & Stress Testing for an Islamic Bank**
Bank fiktif: **PT Amanah Syariah Bank (ASB)** — Bank Umum Syariah

> Dokumen ini adalah **sumber kebenaran tunggal** (single source of truth). Blueprint v2 tetap menjadi dokumen konsep; dokumen ini menggantikan seluruh angka contoh di v2. Jika ada konflik, **v3 yang berlaku**.
> File pendamping: `risk_appetite.csv`, `risk_weights.csv`, `macro_scenarios.csv`, `judgment_overrides.csv`, `reference_calc.py`, `reference_output.txt`.

---

## 0. Perubahan dari v2

| # | Masalah di v2 | Perbaikan di v3 |
|---|---|---|
| 1 | Angka contoh tidak konsisten (heatmap §16 vs §22, skor 2.7 vs 2.5, threshold NPF) | Satu set angka final (§4, §5), sudah diverifikasi oleh `reference_calc.py` |
| 2 | Status 3 warna dan skor 1–5 tidak punya aturan konversi | Skala 5 zona dengan 4 cut-point per KRI (§3.1) |
| 3 | Agregasi KRI → risk → enterprise tidak didefinisikan | Weighted average + floor rule + escalation rule (§3.2–3.5) |
| 4 | Judgment (contoh Reputation) tanpa aturan | Override terdokumentasi, maksimal ±1.0, dicatat terpisah dari model score (§3.3) |
| 5 | Transmisi stress hanya berupa panah | Aturan sensitivitas eksplisit per KRI (§5.2) |
| 6 | Tidak ada dampak ke permodalan | Capital Adequacy Overlay (KPMM sebelum/sesudah stress) (§5.5) |
| 7 | Data sintetis tiap file berdiri sendiri | Semua data diturunkan dari satu neraca jangkar (§2) |
| 8 | Periode data tidak jelas | 12 bulan: Okt-2025 s.d. Sep-2026, reporting date 30-Sep-2026, seed 42 |
| 9 | Terminologi konvensional ("interest rate") | Policy/benchmark rate, bagi hasil, displaced commercial risk, temuan DPS |
| 10 | Deposit outflow 5%/12% dipakai untuk indikator 30 hari (terlalu ekstrem) | Dipisah: run-off 30 hari (1%/3%) untuk SLSI, penurunan DPK 3 bulan (5%/12%) untuk FDR |
| 11 | Power BI diharapkan jadi `.pbix` otomatis | Cowork membuat star schema + DAX + spesifikasi layout; `.pbix` dirakit manual |

---

## 1. Scope

**In scope:** 10 risk type (taksonomi BUS), 43 KRI + 1 capital overlay, risk appetite engine, trend dan early warning, enterprise stress testing 3 skenario, agregasi enterprise, interdependency map, emerging risk register, management action tracker, Excel framework, dataset Power BI, executive report.

**Out of scope (dilarang dibangun):** PD/LGD/EAD model, ECL/CKPN/PSAK 71, VaR historis/Monte Carlo, ekonometrika, machine learning, perhitungan LCR/NSFR regulatori, model distribusi bagi hasil.

**Disclaimer (wajib di README dan report):**
> This project uses a fictional Islamic bank and fully synthetic data. All risk appetite thresholds, scenarios, sensitivities, and scoring rules are project-specific analytical assumptions created for educational and portfolio purposes. They do not represent any actual bank's internal limits, regulatory thresholds, or an official OJK risk profile rating.

---

## 2. Bank fiktif dan neraca jangkar

Semua dataset **harus rekonsiliasi** ke neraca ini pada reporting date (toleransi ±0,5%).

**Neraca ASB — 30 Sep 2026 (Rp miliar)**

| Aset | Nilai | Liabilitas & Ekuitas | Nilai |
|---|---:|---|---:|
| Kas & giro BI (GWM wajib 3.500; excess 1.500) | 5.000 | Giro wadiah | 8.000 |
| Penempatan pada bank lain | 2.000 | Tabungan (wadiah + mudharabah) | 16.000 |
| Portofolio sukuk (FVOCI 6.000; amortized cost 4.000; unencumbered 7.000) | 10.000 | Deposito mudharabah | 24.000 |
| Pembiayaan bruto | 41.000 | **Total DPK** | **48.000** |
| Cadangan kerugian (input statis, tidak dimodelkan) | (1.000) | Pendanaan lain | 4.000 |
| Aset lain | 3.000 | Liabilitas lain | 1.000 |
| | | Ekuitas | 7.000 |
| **Total aset** | **60.000** | **Total** | **60.000** |

**Parameter kunci (disimpan di `config/bank_profile.yaml`):**

| Parameter | Nilai |
|---|---|
| Modal KPMM / ATMR | 7.000 / 40.000 → KPMM 17,5% |
| Gross income tahunan | 5.600 |
| Porsi pembiayaan UMKM | 30% (12.300) |
| Target pertumbuhan pembiayaan YoY (RKB) | 15% |
| Jumlah obligor | ±6.000 (UMKM ±5.500; korporasi ±500) |
| Jumlah rekening deposan | ±250.000 (dataset: 20 deposan terbesar + agregat segmen) |
| Random seed | 42 |
| Periode | 2025-10 s.d. 2026-09 (12 bulan) |

Neraca bulan-bulan sebelumnya diturunkan mundur secara konsisten dengan tren KRI (§4), misalnya pembiayaan tumbuh sesuai ST01 dan DPK turun sesuai LQ05.

---

## 3. Metodologi skoring

### 3.1 KRI score (1–5)

Setiap KRI memiliki arah (`lower` atau `higher` better) dan 4 cut-point `c1..c4`.

Untuk `lower`: x ≤ c1 → 1; ≤ c2 → 2; ≤ c3 → 3; ≤ c4 → 4; selain itu → 5.
Untuk `higher`: x ≥ c1 → 1; ≥ c2 → 2; ≥ c3 → 3; ≥ c4 → 4; selain itu → 5.

| Skor | Zona | Makna governance | Warna |
|---|---|---|---|
| 1 | Strong | Jauh di dalam appetite | Green |
| 2 | Within appetite | c2 = **Risk Appetite** | Green |
| 3 | Watch | Di atas appetite, di bawah c3 = **Early Warning Trigger** | Amber |
| 4 | Tolerance breach | Melewati trigger, di bawah c4 = **Risk Limit** | Red |
| 5 | Limit breach | Melewati limit → eskalasi ke Direksi/RMC | Red |

KRI dengan nilai bertanda (misalnya gap, sensitivitas) dihitung dalam **nilai absolut**.

### 3.2 Risk score per risk type

```
weighted   = Σ (kri_score × kri_weight)          # bobot per risk = 1,00
floor      = max(kri_score) − 1,5
model      = max(weighted, floor)
final      = model + override_delta              # dibatasi 1,0–5,0
```

Floor rule mencegah satu KRI kritis tersamarkan oleh rata-rata. Contohnya Market adverse: weighted 2,9, tetapi MR02 bernilai 5, sehingga model score = 3,5.

### 3.3 Judgment override

Override hanya boleh ±1,0, wajib dicatat di `judgment_overrides.csv` (rationale, approver, masa berlaku), dan delta-nya dibawa ke semua skenario stress. Dashboard selalu menampilkan **model score dan final score berdampingan**.

Contoh v3: Compliance model 3,3 → final 3,6 (arah naik, konservatif). KRI belum menangkap potensi temuan pemeriksaan atas akad yang tidak sesuai opini DPS.

Kasus Reputation dari v2 (volume komplain naik 25%, tetapi rasio severe stabil) **tidak lagi memerlukan override**. Bobot KRI sudah menanganinya: RP01 = 4, tetapi risk score 2,6 (Amber, bukan Red).

### 3.4 Risk rating

Rating diterapkan pada skor yang dibulatkan 1 desimal (ROUND_HALF_UP).

| Skor | Rating | Warna |
|---|---|---|
| < 1,5 | Low | Green |
| 1,5 – < 2,5 | Low to Moderate | Green |
| 2,5 – < 3,5 | Moderate | Amber |
| 3,5 – < 4,5 | Moderate to High | Red |
| ≥ 4,5 | High | Red |

Label rating terinspirasi skala peringkat risiko yang lazim di perbankan Indonesia, tetapi **bukan replika metodologi penilaian tingkat kesehatan bank**.

### 3.5 Enterprise risk score

```
enterprise = Σ (final_risk_score × materiality_weight)     # risk_weights.csv
enterprise = max(enterprise, max(final_risk_score) − 1,5)  # floor enterprise
jika ada risk dengan bobot ≥ 0,10 dan skor ≥ 4,5 → enterprise minimal 3,5
```

| Risk | Bobot | Risk | Bobot |
|---|---:|---|---:|
| Credit | 0,25 | Compliance | 0,08 |
| Liquidity | 0,15 | Reputation | 0,06 |
| Operational | 0,12 | Market | 0,05 |
| Rate of Return | 0,10 | Legal | 0,04 |
| Strategic | 0,08 | Investment | 0,07 |

Bobot mencerminkan materialitas neraca ASB (pembiayaan 68% aset; DPK 80% pendanaan; deposito mudharabah 50% DPK).

### 3.6 Indikator pendukung

**Limit Utilization (RAU)** per KRI = |x| / c4 (lower) atau c4 / x (higher), dengan batas atas 150%. Nilai diagregasi dengan bobot KRI, lalu bobot materialitas.

**Breach count**: jumlah KRI dengan skor ≥ 4 (tolerance breach), dan jumlah skor = 5 ditampilkan terpisah (limit breach).

**Trend**: Δ = rata-rata 3 bulan terakhir − rata-rata 3 bulan sebelumnya, dinormalisasi terhadap |c4 − c1|. Jika perubahan ke arah memburuk lebih dari 10%, labelnya *Deteriorating*; jika membaik lebih dari 10%, labelnya *Improving*; selain itu *Stable*.

**Early warning (emerging breach)**: KRI dengan skor ≤ 3 yang, berdasarkan proyeksi linear (OLS 6 bulan terakhir), melewati cut-point berikutnya dalam ≤ 3 bulan.

---

## 4. KRI catalogue dan hasil baseline (Sep-2026)

Detail lengkap (unit, frekuensi, owner) ada di `risk_appetite.csv`. Kolom *Awal* = Okt-2025, *Target* = Sep-2026. Generator wajib menghasilkan nilai Sep-2026 yang **menghasilkan skor persis sama** dengan kolom Skor.

### Credit — skor 3,0 (Moderate, Amber)
| ID | KRI | Arah | c1/c2/c3/c4 | Bobot | Awal → Target | Skor |
|---|---|---|---|---:|---|---:|
| CR01 | NPF gross (%) | lower | 2,0/2,5/3,0/3,5 | 0,35 | 2,3 → 2,8 | 3 |
| CR02 | NPF UMKM (%) | lower | 3/4/5/6 | 0,15 | 4,2 → 5,3 | 4 |
| CR03 | Kol-2 DPD 1–90 (%) | lower | 4/6/8/10 | 0,15 | 5,0 → 6,5 | 3 |
| CR04 | Top-10 obligor (% pembiayaan) | lower | 15/20/25/30 | 0,15 | 17,5 → 18,1 | 2 |
| CR05 | Sektor terbesar (% pembiayaan) | lower | 15/20/25/30 | 0,20 | 19,0 → 21,4 | 3 |

### Market — skor 2,3 (Low to Moderate, Green)
| ID | KRI | Arah | Cut-point | Bobot | Awal → Target | Skor |
|---|---|---|---|---:|---|---:|
| MR01 | PDN (% modal) | lower | 5/10/15/20 | 0,40 | 6,0 → 7,2 | 2 |
| MR02 | Sensitivitas sukuk FVOCI +100 bps (% modal, abs) | lower | 1/2/3/4 | 0,30 | 1,6 → 2,1 | 3 |
| MR03 | Repricing gap ≤1 thn (% aset, abs) | lower | 5/10/15/20 | 0,30 | 7,5 → 8,5 | 2 |

### Liquidity — skor 2,7 (Moderate, Amber, tren memburuk)
| ID | KRI | Arah | Cut-point | Bobot | Awal → Target | Skor |
|---|---|---|---|---:|---|---:|
| LQ01 | SLSI (%) | higher | 125/110/105/100 | 0,35 | 128 → 116 | 2 |
| LQ02 | FDR (%) | lower | 85/90/95/100 | 0,15 | 82,0 → 85,4 | 2 |
| LQ03 | Top-20 deposan (% DPK) | lower | 15/20/25/30 | 0,20 | 20,5 → 22,0 | 3 |
| LQ04 | Negative maturity gap ≤1 bln (% aset) | lower | 5/7,5/10/12,5 | 0,15 | 6,5 → 10,5 | 4 |
| LQ05 | Penurunan DPK 3 bulan (%) | lower | 2/4/6/8 | 0,15 | 1,0 → 4,5 | 3 |

**SLSI (Synthetic Liquidity Stress Indicator)** — bukan LCR regulatori:
```
Liquid assets = excess GWM 1.500 + penempatan 2.000 + sukuk unencumbered 7.000 × (1 − haircut 5%) = 10.150
Net outflow 30 hari = run-off giro 30% + tabungan 12% + deposito 12% + pendanaan lain 25% − inflow (cap) = 8.750
SLSI = 10.150 / 8.750 = 116%
```

### Operational — skor 3,6 (Moderate to High, Red)
| ID | KRI | Arah | Cut-point | Bobot | Awal → Target | Skor |
|---|---|---|---|---:|---|---:|
| OR01 | Insiden/bulan | lower | 10/15/20/25 | 0,20 | 12 → 21 | 4 |
| OR02 | High-severity (rolling 3 bln) | lower | 1/2/4/6 | 0,25 | 1 → 3 | 3 |
| OR03 | Loss rolling 12 bln (% gross income) | lower | 0,5/1,0/1,5/2,0 | 0,25 | 0,9 → 1,6 | 4 |
| OR04 | Repeat incident rate (%) | lower | 3/5/7/10 | 0,15 | 4 → 8 | 4 |
| OR05 | Melewati SLA (%) | lower | 5/10/15/20 | 0,15 | 8 → 12 | 3 |

Storyline: root cause dominan adalah *process failure* pada operasi transaksi digital, dengan lonjakan sejak Jun-2026.

### Strategic — skor 3,3 (Moderate, Amber)
| ID | KRI | Arah | Cut-point | Bobot | Awal → Target | Skor |
|---|---|---|---|---:|---|---:|
| ST01 | Deviasi growth pembiayaan vs target 15% (pp, abs) | lower | 2/4/6/8 | 0,30 | 3 → 7 (growth 22%) | 4 |
| ST02 | Laba YTD vs RKB (%) | higher | 100/95/90/85 | 0,30 | 99 → 93 | 3 |
| ST03 | Cost to income (%) | lower | 75/80/85/90 | 0,25 | 78 → 82 | 3 |
| ST04 | Inisiatif strategis terlambat (%) | lower | 10/20/30/40 | 0,15 | 10 → 25 | 3 |

Insight: growth 22% terlihat bagus, tetapi deviasi +7 pp dari target merupakan sinyal risiko karena kemungkinan terjadi pelonggaran underwriting (terhubung ke CR02).

### Compliance — model 3,3 → final 3,6 (override, Red)
| ID | KRI | Arah | Cut-point | Bobot | Awal → Target | Skor |
|---|---|---|---|---:|---|---:|
| CP01 | Pelanggaran regulasi (rolling 3 bln) | lower | 1/3/5/7 | 0,20 | 2 → 4 | 3 |
| CP02 | High-severity overdue remediasi | lower | 0/1/2/3 | 0,30 | 1 → 3 | 4 |
| CP03 | Repeat breach rate (%) | lower | 5/10/15/20 | 0,20 | 8 → 12 | 3 |
| CP04 | Temuan DPS terbuka >90 hari | lower | 0/1/2/4 | 0,30 | 1 → 2 | 3 |

### Legal — skor 2,2 (Low to Moderate, Green)
| ID | KRI | Arah | Cut-point | Bobot | Awal → Target | Skor |
|---|---|---|---|---:|---|---:|
| LG01 | Kasus terbuka | lower | 5/10/15/20 | 0,30 | 7 → 8 | 2 |
| LG02 | Kasus high-risk | lower | 0/1/2/3 | 0,30 | 1 → 1 | 2 |
| LG03 | Potensi eksposur (% modal) | lower | 0,5/1/2/3 | 0,20 | 0,7 → 0,8 | 2 |
| LG04 | Aging >365 hari (%) | lower | 10/20/30/40 | 0,20 | 18 → 22 | 3 |

### Reputation — skor 2,6 (Moderate, Amber)
| ID | KRI | Arah | Cut-point | Bobot | Awal → Target | Skor |
|---|---|---|---|---:|---|---:|
| RP01 | Growth komplain MoM (%) | lower | 5/10/20/30 | 0,20 | 5 → 25 | 4 |
| RP02 | Rasio komplain severe (%) | lower | 2/4/6/8 | 0,35 | 3,2 → 3,5 | 2 |
| RP03 | Melewati SLA (%) | lower | 5/10/15/20 | 0,25 | 8 → 9 | 2 |
| RP04 | Negative sentiment (%) | lower | 10/20/30/40 | 0,20 | 15 → 22 | 3 |

### Rate of Return — skor 3,1 (Moderate, Amber)
| ID | KRI | Arah | Cut-point | Bobot | Awal → Target | Skor |
|---|---|---|---|---:|---|---:|
| RR01 | Gap bagi hasil deposito vs benchmark pasar (pp) | lower | 0/0,25/0,50/0,75 | 0,30 | 0,20 → 0,45 | 3 |
| RR02 | Gap return ekspektasi vs realisasi deposan (pp) | lower | 0,2/0,4/0,6/0,8 | 0,30 | 0,3 → 0,7 (5,4% vs 4,7%) | 4 |
| RR03 | NIM syariah (%) | higher | 5,0/4,5/4,0/3,5 | 0,20 | 4,8 → 4,4 | 3 |
| RR04 | Pembiayaan margin tetap tenor >3 thn (%) | lower | 30/40/50/60 | 0,20 | 36 → 38 | 2 |

Karakter syariah: RR01 dan RR02 mengukur tekanan **displaced commercial risk**, yaitu dorongan bagi bank untuk mengorbankan porsi bagi hasilnya agar deposan tidak berpindah.

### Investment — skor 2,2 (Low to Moderate, Green)
| ID | KRI | Arah | Cut-point | Bobot | Awal → Target | Skor |
|---|---|---|---|---:|---|---:|
| IV01 | Penerbit non-sovereign terbesar (%) | lower | 5/10/15/20 | 0,25 | 8 → 8 | 2 |
| IV02 | Rating di bawah idA (%) | lower | 2/5/8/12 | 0,30 | 3 → 3 | 2 |
| IV03 | Penurunan MV FVOCI 3 bln (%) | lower | 1/2/3/5 | 0,25 | 0,5 → 1,2 | 2 |
| IV04 | Modified duration (tahun) | lower | 3/4/5/6 | 0,20 | 4,0 → 4,3 | 3 |

### Ringkasan Enterprise Risk Profile — baseline Sep-2026

| Risk | Skor | Warna |
|---|---:|---|
| Credit | 3,0 | 🟡 |
| Market | 2,3 | 🟢 |
| Liquidity | 2,7 | 🟡 |
| Operational | 3,6 | 🔴 |
| Strategic | 3,3 | 🟡 |
| Compliance | 3,6 (model 3,3) | 🔴 |
| Legal | 2,2 | 🟢 |
| Reputation | 2,6 | 🟡 |
| Rate of Return | 3,1 | 🟡 |
| Investment | 2,2 | 🟢 |
| **Enterprise** | **3,0 — Moderate** | 🟡 |

Hero metrics: Limit Utilization **68%** · Tolerance breach **9 KRI** · Limit breach **0** · Emerging risk (register) **3**.

---

## 5. Enterprise stress testing

### 5.1 Skenario (`macro_scenarios.csv`)

| Variabel | Baseline | Adverse | Severe |
|---|---:|---:|---:|
| GDP growth (%) | 5,0 | 2,0 | −1,0 |
| Inflasi (%) | 3,0 | 4,5 | 6,0 |
| Policy rate shift (bps) | 0 | +100 | +250 |
| Depresiasi IDR (%) | 0 | 10 | 25 |
| Run-off DPK tambahan 30 hari (% DPK) | 0 | 1,0 | 3,0 |
| Penurunan DPK 3 bulan (% DPK) | 0 | 5 | 12 |
| Shock MV sukuk FVOCI (%) | 0 | −5 | −15 |
| Uplift insiden operasional (%) | 0 | +20 | +50 |
| Uplift growth komplain (pp) | 0 | +30 | +60 |
| Uplift ATMR (%) | 0 | +2 | +5 |

Horizon analisis 12 bulan, statis (neraca tidak bereaksi), tanpa management action. Hasilnya adalah indikasi *gross stress impact*.

### 5.2 Aturan transmisi (ΔGDP = 5,0 − GDP skenario; Δbps = policy rate shift)

| KRI | Aturan | Rasional singkat |
|---|---|---|
| CR01 | + 0,20 × ΔGDP + 0,10 × Δbps/100 | Perlambatan ekonomi dan beban cicilan naik |
| CR02 | + 1,5 × (Δ CR01) | UMKM lebih sensitif |
| CR03 | + 0,40 × ΔGDP | Kol-2 bergerak lebih dulu |
| MR01 | × (1 + depresiasi) | Revaluasi posisi valas |
| MR02 | × (100 + Δbps)/100 | Sensitivitas pada shock total |
| LQ01 | Hitung ulang: haircut sukuk = 5% + |MV shock|; net outflow + run-off tambahan × 48.000 | Run-off dan penurunan nilai collateral |
| LQ02 | 41.000 / (48.000 × (1 − penurunan DPK 3 bln)) | Pembiayaan tetap, DPK turun |
| LQ03 | ÷ (1 − penurunan DPK 3 bln) | Deposan besar dianggap bertahan |
| LQ04 | + 0,25 × penurunan DPK 3 bln | Pendanaan jangka pendek menyusut |
| LQ05 | = max(baseline, penurunan DPK 3 bln) | |
| OR01, OR03, OR05 | × (1 + uplift) | |
| OR02 | ceil(× (1 + uplift)) | Integer |
| ST01 | growth aktual − 2,0 × ΔGDP, lalu dihitung deviasi vs 15% | Growth melambat, deviasi bisa **mengecil** |
| ST02 | − 5,0 × ΔGDP | Tekanan laba |
| ST03 | + 2,0 × ΔGDP | |
| RP01 | + uplift komplain | |
| RR01 | + 0,30 × Δbps/100 | Bagi hasil bank tertinggal dari benchmark |
| RR02 | + 0,20 × Δbps/100 | |
| RR03 | − 0,25 × Δbps/100 | Kompresi margin (margin murabahah tetap) |
| IV02 | + 0,8 × ΔGDP | Downgrade rating |
| IV03 | = max(baseline, |MV shock|) | |
| Lainnya (CR04–05, MR03, OR04, ST04, CP*, LG*, RP02–04, RR04, IV01, IV04) | Tidak berubah | Tidak sensitif makro dalam project ini (dinyatakan sebagai limitation) |

Semua koefisien adalah **asumsi analitis project**, disimpan di `config/stress_parameters.yaml`, dan dapat diubah tanpa mengubah kode.

### 5.3 Hasil yang diharapkan (acuan regresi)

| Risk | Baseline | Adverse | Severe |
|---|---:|---:|---:|
| Credit | 3,0 | 3,5 | 4,0 |
| Market | 2,3 | 3,5 | 3,5 |
| Liquidity | 2,7 | 3,0 | 4,5 |
| Operational | 3,6 | 3,8 | 4,5 |
| Strategic | 3,3 | 3,5 | 4,1 |
| Compliance | 3,6 | 3,6 | 3,6 |
| Legal | 2,2 | 2,2 | 2,2 |
| Reputation | 2,6 | 3,5 | 3,5 |
| Rate of Return | 3,1 | 3,7 | 4,2 |
| Investment | 2,2 | 3,0 | 3,5 |
| **Enterprise** | **3,0 Moderate** | **3,4 Moderate** | **4,0 Moderate to High** |
| Limit Utilization | 68% | 78% | 93% |
| KRI skor ≥4 / skor 5 | 9 / 0 | 14 / 6 | 21 / 14 |

Contoh nilai KRI hasil stress: SLSI 116% → 106% → 89%; FDR 85,4% → 89,9% → 97,1%; NPF 2,8% → 3,5% → 4,25%; NIM 4,4% → 4,15% → 3,78%.

### 5.4 Waterfall baseline → severe (kontribusi = Δ skor × bobot)

| Driver | Kontribusi |
|---|---:|
| Liquidity | +0,27 |
| Credit | +0,25 |
| Rate of Return | +0,11 |
| Operational | +0,11 |
| Investment | +0,09 |
| Strategic | +0,06 |
| Market | +0,06 |
| Reputation | +0,05 |
| **Total** | **≈ +1,0 (3,0 → 4,0)** |

### 5.5 Capital Adequacy Overlay (KPMM)

Bukan bagian dari 10 risk score. Ditampilkan di halaman stress sebagai jawaban atas pertanyaan "modal cukup atau tidak?".

```
Kerugian kredit   = ΔNPF × pembiayaan 41.000 × loss rate 45%   (asumsi tunggal, BUKAN model LGD/ECL)
Kerugian sukuk    = FVOCI 6.000 × |MV shock|
Kerugian op       = loss tahunan 90 × uplift
Biaya DCR         = deposito mudharabah 24.000 × Δbps × pass-through 50%
Modal stress      = 7.000 − total kerugian   (konservatif: laba berjalan tidak diperhitungkan)
ATMR stress       = 40.000 × (1 + uplift ATMR)
```

| | Baseline | Adverse | Severe |
|---|---:|---:|---:|
| Kerugian kredit | – | 129 | 268 |
| Kerugian sukuk FVOCI | – | 300 | 900 |
| Kerugian operasional | – | 18 | 45 |
| Biaya displaced commercial risk | – | 120 | 300 |
| **Total** | – | **567** | **1.513** |
| Modal | 7.000 | 6.433 | 5.487 |
| ATMR | 40.000 | 40.800 | 42.000 |
| **KPMM** | **17,5%** | **15,8%** | **13,1%** |
| Skor CAP01 (16/14/12/10,5) | 1 | 2 | 3 |

Insight: dalam skenario severe, driver terbesar erosi modal adalah **market value sukuk** (60%), bukan kredit. Temuan ini berguna saat interview karena menunjukkan pemahaman di luar credit risk.

---

## 6. Risk interdependency (`interdependency_edges.csv`)

| source | target | channel | strength (1–3) | evidence di project |
|---|---|---|---:|---|
| Macro downturn | Credit | GDP → NPF | 3 | CR01–03 |
| Macro downturn | Strategic | Laba & cost-to-income | 2 | ST02–03 |
| Macro downturn | Investment | Downgrade | 2 | IV02 |
| Policy rate ↑ | Market | Nilai sukuk | 3 | MR02 |
| Policy rate ↑ | Rate of Return | Gap bagi hasil | 3 | RR01–03 |
| Rate of Return | Liquidity | Deposan pindah (DCR) | 3 | RR01 → LQ05 |
| Market | Liquidity | Haircut collateral | 2 | LQ01 |
| Strategic | Credit | Growth agresif → kualitas UMKM | 2 | ST01 → CR02 |
| Operational | Reputation | Gangguan digital → komplain | 3 | OR01 → RP01 |
| Compliance | Reputation | Temuan syariah → kepercayaan | 2 | CP04 → RP04 |
| Liquidity | Strategic | Pendanaan mahal → laba | 1 | – |

Visual: network sederhana di Power BI (atau diagram statis) dengan ketebalan garis = strength. **Top enterprise driver**: policy rate ↑ yang mengalir ke Market, Rate of Return, dan Liquidity.

---

## 7. Emerging risk register (`emerging_risks.csv`)

Kolom: `er_id, risk_name, driver, description, likelihood(1–5), impact(1–5), velocity(1–5), priority_score = likelihood × impact × (velocity/5), linked_risk_types, early_signal, status(Monitor/Watch/Act), owner, next_review`.

| ID | Risk | Driver | L | I | V | Priority | Status |
|---|---|---|---:|---:|---:|---:|---|
| ER01 | Cyber risk | Digitalisasi kanal | 4 | 5 | 5 | 20,0 | Watch |
| ER02 | AI / model risk | Adopsi AI scoring & chatbot | 3 | 4 | 4 | 9,6 | Watch |
| ER03 | Climate risk | Fisik & transisi (sektor terbesar) | 3 | 4 | 2 | 4,8 | Monitor |

---

## 8. Data dictionary

### 8.1 Konvensi
Nominal dalam Rp miliar (kecuali disebut lain); `period` berformat `YYYY-MM`; tanggal ISO; ID berupa string berawalan; semua file UTF-8 CSV; tidak ada data pribadi nyata.

### 8.2 Input (generated)

| File | Grain | Kolom utama |
|---|---|---|
| `balance_sheet_monthly.csv` | period × line_item | period, line_item, category (asset/liability/equity), sub_category, amount |
| `capital_monthly.csv` | period | period, capital_kpmm, atmr, gross_income_ttm, profit_ytd, profit_budget_ytd |
| `financing_portfolio.csv` | period × obligor | period, obligor_id, segment (UMKM/Korporasi), sector, akad (murabahah/musyarakah/mudharabah/ijarah), outstanding, collectibility (1–5), dpd, margin_type (fixed/floating), remaining_tenor_months, origination_period |
| `deposits_monthly.csv` | period × segment | period, product (giro_wadiah/tabungan/deposito_mudharabah), balance, equivalent_rate, market_benchmark_rate, runoff_assumption |
| `top_depositors.csv` | period × depositor | period, depositor_id, product, balance, rank |
| `maturity_profile.csv` | period × bucket | period, bucket (≤1m, 1–3m, 3–12m, >12m), assets_maturing, liabilities_maturing, rsa, rsl |
| `market_positions.csv` | period × currency | period, currency, fx_assets, fx_liabilities, off_balance, net_position |
| `investment_portfolio.csv` | period × holding | period, holding_id, issuer, issuer_type (sovereign/corporate), instrument (SBSN/sukuk korporasi), classification (FVOCI/AC), rating, face_value, market_value, modified_duration, maturity_date, encumbered_flag |
| `rate_of_return_monthly.csv` | period | period, financing_yield, expected_depositor_return, actual_depositor_return, profit_distribution_ratio, nim |
| `operational_events.csv` | event | event_id, period, event_date, event_type (Basel 7 kategori), business_unit, channel, severity (Low/Medium/High), gross_loss, recovery, net_loss, root_cause, repeat_flag, sla_days, resolution_days, status |
| `compliance_events.csv` | event | breach_id, period, source (regulator/internal audit/DPS), regulation_ref, severity, business_unit, target_remediation_date, closed_date, repeat_flag, status |
| `legal_cases.csv` | case | case_id, open_period, case_type, counterparty_type, severity, potential_loss, provisioned_flag, status, closed_period |
| `complaints.csv` | complaint | complaint_id, period, channel, category, severity, sla_days, resolution_days, status |
| `sentiment_monthly.csv` | period × source | period, source (media/sosmed), mentions, negative_mentions |
| `strategic_monthly.csv` | period | period, financing_growth_yoy, financing_growth_target, cost_to_income, initiatives_total, initiatives_delayed |

### 8.3 Konfigurasi (tidak digenerate, disediakan)
`risk_appetite.csv`, `risk_weights.csv`, `macro_scenarios.csv`, `judgment_overrides.csv`, `config/bank_profile.yaml`, `config/stress_parameters.yaml`, `interdependency_edges.csv`, `emerging_risks.csv`, `management_actions.csv`.

### 8.4 Output engine

| File | Grain | Kolom |
|---|---|---|
| `kri_monthly.csv` | period × kri | period, kri_id, risk_type, value, score, zone, color, utilization, trend_label, early_warning_flag |
| `risk_scores_monthly.csv` | period × risk | period, risk_type, weighted_score, floor_score, model_score, override_delta, final_score, rating, color |
| `enterprise_profile_monthly.csv` | period | period, enterprise_score, rating, limit_utilization, tolerance_breaches, limit_breaches, emerging_count |
| `stress_results.csv` | scenario × kri | scenario, kri_id, risk_type, base_value, stressed_value, base_score, stressed_score |
| `stress_risk_scores.csv` | scenario × risk | scenario, risk_type, model_score, final_score, rating, contribution_delta |
| `capital_overlay.csv` | scenario | scenario, credit_loss, investment_loss, op_loss, dcr_cost, total_loss, capital, atmr, kpmm, cap_score |
| `management_actions.csv` | action | action_id, period, risk_type, kri_id, finding, severity, recommended_action, owner, due_date, status, trigger_rule |

**Aturan otomatis action**: setiap KRI dengan skor ≥ 4 menghasilkan action (skor 4 → 30 hari; skor 5 → 14 hari dan eskalasi Direksi). Teks action diambil dari library per KRI (`action_library.csv`), tidak dikarang bebas.

---

## 9. Power BI specification

**Star schema:** `dim_date`, `dim_risk`, `dim_kri`, `dim_scenario`, `dim_business_unit` · `fact_kri_monthly`, `fact_risk_score`, `fact_enterprise`, `fact_stress`, `fact_capital`, `fact_actions`, `fact_emerging`, `fact_interdependency`.

**Measure DAX minimum:** `Enterprise Score`, `Enterprise Rating`, `Limit Utilization %`, `Tolerance Breaches`, `Limit Breaches`, `KRI Score MoM Δ`, `Deteriorating KRI Count`, `Stress Δ vs Baseline`, `KPMM Stressed`, `Overdue Actions`.

| Page | Isi |
|---|---|
| 1 Enterprise Overview | Hero: skor 3,0 Moderate · RAU 68% · breach 9/0 · emerging 3; heatmap 10 risk (model vs final); top 3 driver |
| 2 Risk Appetite | Per KRI: actual vs appetite (c2) vs trigger (c3) vs limit (c4); 12 bulan; slicer risk type |
| 3 Risk Trend & Early Warning | Matriks skor risk × bulan; daftar KRI *Deteriorating* dan *emerging breach* |
| 4 Enterprise Stress | Tabel 3 skenario, waterfall §5.4, KPMM overlay |
| 5 Interdependency | Network/flow §6 + narasi driver |
| 6 Management Action | Tracker (owner, due, status, overdue) + emerging risk register |

Konsistensi warna: Green #2E7D32, Amber #F9A825, Red #C62828.

---

## 10. Excel framework (`ERM_Framework.xlsx`)

| Sheet | Isi |
|---|---|
| 01_Risk_Taxonomy | 10 risk: definisi, driver, measurement approach, depth, owner |
| 02_Risk_Appetite_Statement | Pernyataan kualitatif per risk + metrik utama |
| 03_KRI_Definitions | Formula, sumber data, frekuensi, owner |
| 04_Thresholds | Isi `risk_appetite.csv` + data validation |
| 05_Scoring_Methodology | §3 dalam bentuk tabel + contoh hitung dengan formula Excel hidup |
| 06_Risk_Assessment | Snapshot Sep-2026 (hasil engine) + kolom override |
| 07_Stress_Scenarios | §5.1–5.2 |
| 08_Management_Actions | Tracker |
| 09_Regulatory_Mapping | §11 |
| 10_Change_Log | Versi threshold dan approver (fiktif) |

---

## 11. Regulatory mapping — kandidat rujukan (WAJIB diverifikasi status berlaku sebelum dipakai)

| Area | Kandidat rujukan |
|---|---|
| Manajemen risiko BUS/UUS (10 jenis risiko) | POJK 65/POJK.03/2016 |
| Penilaian tingkat kesehatan BUS/UUS (RBBR) | POJK 8/POJK.03/2014 dan SEOJK 10/SEOJK.03/2014, periksa apakah sudah diganti |
| KPMM BUS | POJK 21/POJK.03/2014 dan perubahannya |
| Tata kelola syariah / DPS | Periksa regulasi tata kelola syariah BUS/UUS terbaru |
| Likuiditas (LCR/NSFR) dan PDN | Periksa ketentuan yang berlaku bagi BUS |

Pemetaan hanya menjelaskan **area yang diinspirasi**. Tidak ada klaim bahwa threshold project sama dengan ketentuan.

---

## 12. Acceptance tests (wajib lulus, dijalankan via `pytest`)

1. **Rekonsiliasi neraca**: total aset = liabilitas + ekuitas setiap bulan; nilai Sep-2026 sesuai §2 ±0,5%.
2. **Rekonsiliasi granular**: Σ outstanding `financing_portfolio` = pembiayaan bruto neraca; Σ holding = sukuk neraca; Σ produk DPK = DPK neraca.
3. **Skor baseline**: seluruh 43 KRI Sep-2026 menghasilkan `target_score` di `risk_appetite.csv`.
4. **Regresi**: risk, enterprise, RAU, breach count, dan KPMM untuk 3 skenario sama dengan `reference_output.txt` (toleransi ±0,05 skor; ±0,1 pp KPMM).
5. **Monotonic**: untuk setiap risk, severe ≥ adverse ≥ baseline, kecuali KRI yang didokumentasikan dapat membaik (ST01).
6. **Bobot**: bobot KRI per risk = 1,00; bobot materialitas = 1,00.
7. **Reproducible**: dua kali run dengan seed 42 menghasilkan file identik (hash sama).
8. **Scope guard**: tidak ada file atau fungsi bernama ecl, ckpn, pd_model, lgd, var_, monte_carlo, sklearn.
9. **Storyline tren**: LQ01, LQ04, OR01, OR04 berlabel *Deteriorating* pada Sep-2026; minimal satu KRI ber-flag early warning.

---

## 13. Struktur repository final

```
enterprise-risk-management/
├── README.md                    # framing: framework, bukan dashboard; disclaimer
├── config/                      # bank_profile.yaml, stress_parameters.yaml
├── data/
│   ├── reference/               # risk_appetite, risk_weights, macro_scenarios, overrides, edges, emerging, action_library
│   ├── raw/                     # hasil generator
│   └── output/                  # hasil engine
├── src/erm/
│   ├── generator/               # balance_sheet.py, credit.py, liquidity.py, ... calibrate.py
│   ├── validation.py
│   ├── kri.py                   # hitung 43 KRI dari data raw
│   ├── scoring.py               # §3
│   ├── stress.py                # §5
│   ├── capital.py               # §5.5
│   ├── actions.py
│   └── export_powerbi.py
├── tests/                       # §12
├── notebooks/                   # 01–05, hanya narasi dan visual; logika di src/
├── excel/ERM_Framework.xlsx
├── dashboard/                   # powerbi_spec.md, DAX_measures.md, (pbix dirakit manual)
├── regulatory/Regulatory_Mapping.xlsx
├── report/ERM_Executive_Report.pdf
└── Makefile                     # make data | make engine | make test | make report
```

---

## 14. Positioning (tidak berubah dari v2)

> Developed a simulated enterprise risk management framework for an Islamic bank, integrating multi-risk KRI monitoring, risk appetite and limit assessment, enterprise stress testing with capital overlay, risk interdependency analysis, and executive risk reporting using Python, Excel, and Power BI.
