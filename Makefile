PYTHON ?= python3
RUN = PYTHONPATH=src $(PYTHON) -m

.PHONY: all data engine excel powerbi report test reference clean-output

all: data engine report test          ## pipeline lengkap

data:                                 ## generator data sintetis → data/raw (seed 42)
	$(RUN) erm.generator

engine:                               ## KRI, skoring, stress, capital overlay, actions → data/output
	$(RUN) erm engine

excel:                                ## excel/ERM_Framework.xlsx (formula dihitung ulang via LibreOffice bila tersedia)
	$(RUN) erm excel

powerbi:                              ## star schema → dashboard/model/*.csv
	$(RUN) erm powerbi

report: excel powerbi                 ## Excel + Power BI package + report/ERM_Executive_Report.pdf
	$(RUN) erm report

test:                                 ## acceptance test (spec §12 + konsistensi deliverable)
	$(PYTHON) -m pytest -q

reference:                            ## jalankan reference_calc.py (acuan regresi)
	cd data/reference && $(PYTHON) reference_calc.py
