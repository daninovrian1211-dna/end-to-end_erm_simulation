# Power BI Specification — ERM Dashboard PT Amanah Syariah Bank (fiktif)

> This project uses a fictional Islamic bank and fully synthetic data. All risk appetite thresholds, scenarios, sensitivities, and scoring rules are project-specific analytical assumptions created for educational and portfolio purposes. They do not represent any actual bank's internal limits, regulatory thresholds, or an official OJK risk profile rating.

File `.pbix` **tidak** digenerate. Dokumen ini adalah panduan merakit dashboard secara manual di Power BI Desktop dari `dashboard/model/*.csv` (hasil `make powerbi`) dan `dashboard/DAX_measures.md`.

## 1. Import & model

1. **Get Data → Text/CSV**, impor 13 file di `dashboard/model/`. Encoding UTF-8, delimiter koma, locale *English (United States)* agar desimal titik terbaca benar.
2. Tipe data:
   - Semua kolom `*_key` bertipe Whole Number.
   - `month_start` dan `month_end` bertipe Date.
   - `early_warning_flag`, `is_reporting_date`, dan `is_overdue` bertipe True/False.
3. Buat tabel kosong `_Measures`, lalu tempel seluruh measure dari `DAX_measures.md`.
4. **Jangan** pakai *Mark as date table*: `dim_date` hanya berisi 12 baris bulanan (bukan tanggal harian berurutan), sehingga Power BI menolaknya dan time intelligence tidak dipakai. Perbandingan antar bulan memakai `dim_date[month_index]`.
5. Urutkan `month_label` berdasarkan `month_index`, `dim_risk[risk_type]` berdasarkan `sort_order`, dan `dim_scenario[scenario]` berdasarkan `sort_order`.
6. Samakan tipe seluruh kolom `*_key` menjadi Whole Number sebelum membuat relasi.

### Relasi (single direction, dimensi → fakta, many-to-one)

| Fakta | Kolom | Dimensi |
|---|---|---|
| fact_kri_monthly | date_key, kri_key, risk_key | dim_date, dim_kri, dim_risk |
| fact_risk_score | date_key, scenario_key, risk_key | dim_date, dim_scenario, dim_risk |
| fact_enterprise | date_key, scenario_key | dim_date, dim_scenario |
| fact_stress | date_key, scenario_key, kri_key, risk_key | dim_date, dim_scenario, dim_kri, dim_risk |
| fact_capital | date_key, scenario_key | dim_date, dim_scenario |
| fact_actions | date_key, risk_key, kri_key, bu_key | dim_date, dim_risk, dim_kri, dim_business_unit |
| fact_emerging | date_key, primary_risk_key → risk_key, bu_key | dim_date, dim_risk, dim_business_unit |
| fact_interdependency | — | **Tanpa relasi.** Lima baris memiliki `source_risk_key` kosong (pemicu makro), dan visualnya tidak boleh ikut terfilter slicer. |
| — | — | **Jangan** hubungkan `dim_kri[risk_key]` ke `dim_risk` atau `dim_kri[bu_key]` ke `dim_business_unit`: tabel fakta sudah membawa `risk_key`/`bu_key` sendiri, sehingga relasi antar-dim membuat jalur ganda dan ditolak Power BI. |

Total relasi aktif: **21**, semuanya arah tunggal dim → fact (cardinality one-to-many).

Konvensi skenario: `Actual` berisi monitoring bulanan Okt-2025 s.d. Sep-2026. `Baseline`, `Adverse`, dan `Severe` berisi hasil stress pada `date_key = 202609`.

## 2. Panduan langkah demi langkah

Langkah perakitan rinci (tipe data, 21 relasi satu per satu, urutan measure, field well tiap visual, verifikasi angka, dan pemecahan masalah) ada di `docs/Panduan_PowerBI_ERM.pdf`.

## 3. Tema & warna

| Token | Hex | Pemakaian |
|---|---|---|
| Green | `#2E7D32` | Skor < 2,5; zona Strong/Within appetite |
| Amber | `#F9A825` | Skor 2,5 – < 3,5; zona Watch |
| Red | `#C62828` | Skor ≥ 3,5; zona Tolerance/Limit breach |
| Navy (teks judul) | `#1F2A44` | Judul halaman, header tabel |
| Grey (garis) | `#9E9E9E` | Gridline, garis referensi |

Font Segoe UI. Judul halaman 20 pt, judul visual 12 pt, isi 10 pt. Setiap halaman memuat footer disclaimer singkat: "Fictional bank · synthetic data · project-specific assumptions".

Slicer global (disinkronkan di semua halaman kecuali halaman 4): `dim_date[month_label]`, dengan default Sep-2026.

---

## Halaman 1 — Enterprise Overview

| # | Visual | Field | Filter / format |
|---|---|---|---|
| 1 | Card | `Enterprise Score` (tampilan 0.0) | Warna data label: `Risk Score Color` versi enterprise |
| 2 | Card | `Enterprise Rating` | — |
| 3 | Card | `Limit Utilization %` | Format 0% |
| 4 | Card (multi-row) | `Tolerance Breaches`, `Limit Breaches` | Label "Breach ≥4 / =5" |
| 5 | Card | `Emerging Risk Count` | — |
| 6 | Matrix (heatmap) | Baris `dim_risk[risk_type]`; nilai `Risk Model Score`, `Risk Final Score`, `Override Delta` | Conditional formatting background berdasarkan field value `Risk Score Color` pada kolom final; `dim_risk[risk_type] <> "Capital Overlay"`; scenario = Actual |
| 7 | Bar chart (horizontal) | Sumbu `dim_risk[risk_type]`; nilai `Risk Final Score` | Top 3 berdasarkan `Risk Final Score` (filter Top N) — "Top 3 driver" |
| 8 | Text box | Narasi: model vs final (override Compliance +0,3), jumlah KRI *Deteriorating* (`Deteriorating KRI Count`) | Dinamis lewat measure di smart narrative |

## Halaman 2 — Risk Appetite

| # | Visual | Field | Filter / format |
|---|---|---|---|
| 1 | Slicer | `dim_risk[risk_type]` (single select) | Tanpa Capital Overlay |
| 2 | Slicer | `dim_kri[kri_name]` | Ter-filter oleh risk type |
| 3 | Line chart | Sumbu `dim_date[month_label]`; nilai `KRI Value`; garis konstan `dim_kri[risk_appetite]` (c2), `dim_kri[early_warning_trigger]` (c3), `dim_kri[risk_limit]` (c4) | Actual hitam; appetite hijau putus-putus; trigger amber; limit merah |
| 4 | Table | `dim_kri[kri_id]`, `kri_name`, `unit`, `direction`, `KRI Value`, `risk_appetite`, `early_warning_trigger`, `risk_limit`, `KRI Score`, `fact_kri_monthly[utilization]` | Background `KRI Score` via `fact_kri_monthly[color_hex]`; data bars pada utilization (maks 150%) |
| 5 | Gauge | `Limit Utilization %` | Min 0, target 100% |

## Halaman 3 — Risk Trend & Early Warning

| # | Visual | Field | Filter / format |
|---|---|---|---|
| 1 | Matrix | Baris `dim_risk[risk_type]`; kolom `dim_date[month_label]`; nilai `fact_risk_score[final_score_display]` | scenario = Actual; background dari `fact_risk_score[color_hex]`; abaikan slicer tanggal (Edit interactions → none) |
| 2 | Line chart | Sumbu bulan; nilai `fact_enterprise[enterprise_score]`, `fact_enterprise[tolerance_breaches]` (sumbu sekunder) | scenario = Actual |
| 3 | Table "Deteriorating KRI" | `dim_kri[kri_id]`, `kri_name`, `KRI Value`, `KRI Score`, `KRI Score MoM Δ` | `fact_kri_monthly[trend_label] = "Deteriorating"`; tanggal = slicer |
| 4 | Table "Emerging breach" | `dim_kri[kri_id]`, `kri_name`, `KRI Value`, `KRI Score`, `fact_kri_monthly[trend_label]` | `fact_kri_monthly[early_warning_flag] = True` |
| 5 | Card | `Deteriorating KRI Count` | — |

## Halaman 4 — Enterprise Stress

Slicer tanggal tidak berlaku. Filter halaman: `dim_scenario[scenario] <> "Actual"`.

| # | Visual | Field | Filter / format |
|---|---|---|---|
| 1 | Matrix | Baris `dim_risk[risk_type]`; kolom `dim_scenario[scenario]`; nilai `fact_risk_score[final_score_display]` | Background `fact_risk_score[color_hex]`; subtotal baris enterprise lewat visual terpisah |
| 2 | Table | Kolom `dim_scenario[scenario]`; `Enterprise Score`, `Enterprise Rating`, `Limit Utilization %`, `Tolerance Breaches`, `Limit Breaches` | — |
| 3 | Waterfall | Kategori `dim_risk[risk_type]`; nilai `Waterfall Contribution` | Slicer skenario single select (default Severe); urut menurun; warna naik = Red |
| 4 | Clustered column | Sumbu `dim_scenario[scenario]`; nilai `KPMM Stressed` | Garis konstan 16%, 14%, 12%, 10,5%; label 0.0% |
| 5 | Stacked bar | Sumbu skenario; nilai `fact_capital[credit_loss]`, `investment_loss`, `op_loss`, `dcr_cost` | Tooltip `total_loss`, `capital`, `atmr` |
| 6 | Table | `dim_kri[kri_id]`, `kri_name`, `fact_stress[base_value]`, `fact_stress[stressed_value]`, `base_score`, `stressed_score`, `score_delta` | `score_delta <> 0`; urut `score_delta` menurun |
| 7 | Text box | Insight: porsi kerugian sukuk terhadap total erosi modal severe (`investment_loss / total_loss`) | — |

## Halaman 5 — Interdependency

| # | Visual | Field | Filter / format |
|---|---|---|---|
| 1 | Network / Force-Directed Graph (custom visual AppSource) atau diagram statis | Source `fact_interdependency[source]`; target `fact_interdependency[target]`; bobot `strength` | Ketebalan garis = strength (1–3); node macro driver abu-abu, node risk mengikuti `Risk Score Color` |
| 2 | Table | `source`, `target`, `channel`, `strength`, `evidence` | Urut strength menurun |
| 3 | Text box | Narasi top enterprise driver: policy rate ↑ → Market, Rate of Return, Liquidity | — |

Alternatif tanpa custom visual: Sankey chart (AppSource) dengan `source` → `target` dan nilai `strength`.

## Halaman 6 — Management Action

| # | Visual | Field | Filter / format |
|---|---|---|---|
| 1 | Card | `Open Actions`, `Overdue Actions` | Overdue merah bila > 0 |
| 2 | Table tracker | `fact_actions[action_id]`, `dim_date[month_label]`, `dim_risk[risk_type]`, `dim_kri[kri_id]`, `finding`, `severity`, `recommended_action`, `dim_business_unit[business_unit]`, `due_date`, `days_to_due`, `status` | Background status: Overdue merah, Open amber, Closed hijau |
| 3 | Donut | Legend `fact_actions[status]`; nilai count `action_id` | — |
| 4 | Table emerging risk register | `fact_emerging[er_id]`, `risk_name`, `driver`, `likelihood`, `impact`, `velocity`, `priority_score`, `status`, `early_signal`, `next_review` | Data bars pada priority_score |
| 5 | Scatter | X `likelihood`, Y `impact`, ukuran `velocity`, legend `status` | Garis bantu 3/3 |

---

## Checklist perakitan

- [ ] Angka kartu halaman 1 pada Sep-2026 sama dengan `data/output/enterprise_profile_monthly.csv`.
- [ ] Tabel skenario halaman 4 sama dengan `stress_enterprise_summary.csv` dan `capital_overlay.csv`.
- [ ] Warna mengikuti token di atas, tanpa warna default Power BI.
- [ ] Footer disclaimer ada di setiap halaman.
