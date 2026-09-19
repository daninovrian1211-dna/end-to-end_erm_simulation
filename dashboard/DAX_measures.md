# DAX Measures — ERM Dashboard PT Amanah Syariah Bank (fiktif)

Semua measure ditulis untuk model star schema di `dashboard/model/*.csv` (lihat `powerbi_spec.md` untuk relasi).
Buat satu tabel kosong `_Measures` sebagai wadah measure.

**Konvensi**

- Monitoring bulanan memakai `dim_scenario[scenario] = "Actual"`. Stress memakai `Baseline`, `Adverse`, `Severe` pada tanggal Sep-2026.
- Jika slicer skenario tidak dipilih, measure memakai `Actual`.
- Skor dihitung dalam presisi penuh. Tampilan dibulatkan 1 desimal (ROUND_HALF_UP). DAX `ROUND` membulatkan menjauhi nol, jadi untuk skor positif hasilnya sama. Tambahan `1E-9` mencegah representasi biner (misal 2,65 tersimpan 2,6499999…) turun ke bawah.
- Warna: Green `#2E7D32`, Amber `#F9A825`, Red `#C62828`.

---

## Measure pembantu

### Selected Scenario
```dax
Selected Scenario =
IF (
    ISFILTERED ( dim_scenario[scenario] ),
    SELECTEDVALUE ( dim_scenario[scenario], "Actual" ),
    "Actual"
)
```

### Selected Date Key
```dax
Selected Date Key =
MAX ( dim_date[date_key] )
```

### Risk Final Score
```dax
Risk Final Score =
VAR _scen = [Selected Scenario]
VAR _date = [Selected Date Key]
RETURN
    CALCULATE (
        AVERAGE ( fact_risk_score[final_score] ),
        dim_scenario[scenario] = _scen,
        dim_date[date_key] = _date
    )
```

### Risk Model Score
```dax
Risk Model Score =
VAR _scen = [Selected Scenario]
VAR _date = [Selected Date Key]
RETURN
    CALCULATE (
        AVERAGE ( fact_risk_score[model_score] ),
        dim_scenario[scenario] = _scen,
        dim_date[date_key] = _date
    )
```

### Override Delta
```dax
Override Delta =
[Risk Final Score] - [Risk Model Score]
```

### Risk Score Color
```dax
Risk Score Color =
VAR s = ROUND ( [Risk Final Score] + 1E-9, 1 )
RETURN
    SWITCH ( TRUE (), ISBLANK ( [Risk Final Score] ), BLANK (), s < 2.5, "#2E7D32", s < 3.5, "#F9A825", "#C62828" )
```

### KRI Value
```dax
KRI Value =
CALCULATE ( AVERAGE ( fact_kri_monthly[value] ), dim_date[date_key] = [Selected Date Key] )
```

### KRI Score
```dax
KRI Score =
CALCULATE ( AVERAGE ( fact_kri_monthly[score] ), dim_date[date_key] = [Selected Date Key] )
```

### Emerging Risk Count
```dax
Emerging Risk Count =
CALCULATE ( COUNTROWS ( fact_emerging ), fact_emerging[status] IN { "Monitor", "Watch", "Act" } )
```

### Waterfall Contribution
```dax
Waterfall Contribution =
CALCULATE (
    SUM ( fact_risk_score[contribution_delta] ),
    dim_scenario[scenario] = [Selected Scenario]
)
```

---

## Measure minimum (spec §9)

### 1. Enterprise Score
```dax
Enterprise Score =
VAR _scen = [Selected Scenario]
VAR _date = [Selected Date Key]
RETURN
    CALCULATE (
        AVERAGE ( fact_enterprise[enterprise_score] ),
        dim_scenario[scenario] = _scen,
        dim_date[date_key] = _date
    )
```
Tampilan kartu: `ROUND ( [Enterprise Score] + 1E-9, 1 )`, format `0.0`.

### 2. Enterprise Rating
```dax
Enterprise Rating =
VAR s = ROUND ( [Enterprise Score] + 1E-9, 1 )
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( [Enterprise Score] ), BLANK (),
        s < 1.5, "Low",
        s < 2.5, "Low to Moderate",
        s < 3.5, "Moderate",
        s < 4.5, "Moderate to High",
        "High"
    )
```

### 3. Limit Utilization %
```dax
Limit Utilization % =
VAR _scen = [Selected Scenario]
VAR _date = [Selected Date Key]
RETURN
    DIVIDE (
        CALCULATE (
            AVERAGE ( fact_enterprise[limit_utilization] ),
            dim_scenario[scenario] = _scen,
            dim_date[date_key] = _date
        ),
        100
    )
```
Format: `0%`.

### 4. Tolerance Breaches
```dax
Tolerance Breaches =
VAR _scen = [Selected Scenario]
VAR _date = [Selected Date Key]
RETURN
    IF (
        _scen = "Actual",
        CALCULATE (
            COUNTROWS ( fact_kri_monthly ),
            fact_kri_monthly[score] >= 4,
            dim_risk[risk_type] <> "Capital Overlay",
            dim_date[date_key] = _date
        ),
        CALCULATE (
            COUNTROWS ( fact_stress ),
            fact_stress[stressed_score] >= 4,
            dim_risk[risk_type] <> "Capital Overlay",
            dim_scenario[scenario] = _scen
        )
    ) + 0
```

### 5. Limit Breaches
```dax
Limit Breaches =
VAR _scen = [Selected Scenario]
VAR _date = [Selected Date Key]
RETURN
    IF (
        _scen = "Actual",
        CALCULATE (
            COUNTROWS ( fact_kri_monthly ),
            fact_kri_monthly[score] = 5,
            dim_risk[risk_type] <> "Capital Overlay",
            dim_date[date_key] = _date
        ),
        CALCULATE (
            COUNTROWS ( fact_stress ),
            fact_stress[stressed_score] = 5,
            dim_risk[risk_type] <> "Capital Overlay",
            dim_scenario[scenario] = _scen
        )
    ) + 0
```

### 6. KRI Score MoM Δ
```dax
KRI Score MoM Δ =
VAR _idx = CALCULATE ( MAX ( dim_date[month_index] ), dim_date[date_key] = [Selected Date Key] )
VAR _curr = [KRI Score]
VAR _prev =
    CALCULATE (
        AVERAGE ( fact_kri_monthly[score] ),
        FILTER ( ALL ( dim_date ), dim_date[month_index] = _idx - 1 )
    )
RETURN
    IF ( ISBLANK ( _prev ), BLANK (), _curr - _prev )
```

### 7. Deteriorating KRI Count
```dax
Deteriorating KRI Count =
CALCULATE (
    COUNTROWS ( fact_kri_monthly ),
    fact_kri_monthly[trend_label] = "Deteriorating",
    dim_risk[risk_type] <> "Capital Overlay",
    dim_date[date_key] = [Selected Date Key]
) + 0
```

### 8. Stress Δ vs Baseline
```dax
Stress Δ vs Baseline =
VAR _scen = [Selected Scenario]
VAR _stressed =
    CALCULATE ( AVERAGE ( fact_risk_score[final_score] ), dim_scenario[scenario] = _scen )
VAR _base =
    CALCULATE ( AVERAGE ( fact_risk_score[final_score] ), dim_scenario[scenario] = "Baseline" )
RETURN
    IF ( _scen IN { "Adverse", "Severe" }, _stressed - _base, BLANK () )
```
Di level enterprise (tanpa filter risk), gunakan varian:
```dax
Enterprise Stress Δ vs Baseline =
CALCULATE ( AVERAGE ( fact_enterprise[enterprise_score] ), dim_scenario[scenario] = [Selected Scenario] )
    - CALCULATE ( AVERAGE ( fact_enterprise[enterprise_score] ), dim_scenario[scenario] = "Baseline" )
```

### 9. KPMM Stressed
```dax
KPMM Stressed =
VAR _scen = [Selected Scenario]
VAR _s = IF ( _scen = "Actual", "Baseline", _scen )
RETURN
    DIVIDE ( CALCULATE ( AVERAGE ( fact_capital[kpmm] ), dim_scenario[scenario] = _s ), 100 )
```
Format: `0.0%`. Garis referensi: 16% (c1), 14% (c2), 12% (c3), 10,5% (c4) dari `dim_kri` baris `CAP01`.

### 10. Overdue Actions
```dax
Overdue Actions =
CALCULATE ( COUNTROWS ( fact_actions ), fact_actions[status] = "Overdue" ) + 0
```
Pelengkap:
```dax
Open Actions =
CALCULATE ( COUNTROWS ( fact_actions ), fact_actions[status] IN { "Open", "Overdue" } ) + 0
```
