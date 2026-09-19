"""Executive report PDF → report/ERM_Executive_Report.pdf.

Seluruh angka dibaca dari data/output (engine) dan register di data/reference melalui datastore;
tidak ada angka hasil yang diketik manual. Setiap angka yang dicetak pada narasi dicatat di
report/ERM_Executive_Report_facts.json (nilai + sumber) untuk verifikasi."""
from __future__ import annotations

import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,  # noqa: E402
                                TableStyle)

from . import actions, datastore, kri, scoring  # noqa: E402

REPORT_PATH = datastore.ROOT / "report" / "ERM_Executive_Report.pdf"
FACTS_PATH = datastore.ROOT / "report" / "ERM_Executive_Report_facts.json"
DISCLAIMER = ("This project uses a fictional Islamic bank and fully synthetic data. All risk appetite thresholds, scenarios, "
              "sensitivities, and scoring rules are project-specific analytical assumptions created for educational and "
              "portfolio purposes. They do not represent any actual bank's internal limits, regulatory thresholds, or an "
              "official OJK risk profile rating.")
STATUS = {"Green": "#2E7D32", "Amber": "#F9A825", "Red": "#C62828"}
TINT = {"Green": "#C8E6C9", "Amber": "#FFF3C4", "Red": "#F8CACA"}
NAVY, INK, MUTED, GRID = "#1F2A44", "#222222", "#6B6B6B", "#D9D9D9"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # palet kategorikal tervalidasi (urutan tetap)
SHORT = {"CR01": "NPF gross (%)", "CR02": "NPF UMKM (%)", "LQ01": "SLSI (%)", "LQ04": "Neg. maturity gap ≤1 bln",
         "OR01": "Insiden per bulan", "RP01": "Growth komplain MoM (%)"}
MONTHS_ID = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun", 7: "Jul", 8: "Ags", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"}


# ---------------------------------------------------------------- format & fakta
def id_num(x: float, d: int = 1) -> str:
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def mlabel(period: str) -> str:
    return f"{MONTHS_ID[int(period[5:])]}-{period[:4]}"


class Facts:
    def __init__(self):
        self.items: list[dict] = []

    def __call__(self, key: str, value, text: str, source: str) -> str:
        self.items.append(dict(key=key, value=value if not isinstance(value, np.generic) else value.item(),
                               text=text, source=source))
        return text

    def num(self, key: str, value: float, source: str, d: int = 1, suffix: str = "") -> str:
        return self(key, float(value), id_num(float(value), d) + suffix, source)

    def score(self, key: str, value: float, source: str) -> str:
        return self(key, float(value), id_num(scoring.r1(value), 1), source)


# ---------------------------------------------------------------- style
def _fonts():
    base = Path("/usr/share/fonts/truetype/dejavu")
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", str(base / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(base / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Oblique", str(base / "DejaVuSans-Oblique.ttf")))
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu-Oblique", boldItalic="DejaVu-Bold")
        return "DejaVu", "DejaVu-Bold"
    except Exception:  # pragma: no cover
        return "Helvetica", "Helvetica-Bold"


FONT, FONT_B = _fonts()
ST = {
    "title": ParagraphStyle("title", fontName=FONT_B, fontSize=20, leading=24, textColor=colors.HexColor(NAVY)),
    "subtitle": ParagraphStyle("subtitle", fontName=FONT, fontSize=10, leading=13, textColor=colors.HexColor(MUTED)),
    "h1": ParagraphStyle("h1", fontName=FONT_B, fontSize=14, leading=18, textColor=colors.HexColor(NAVY), spaceBefore=2, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName=FONT_B, fontSize=10.5, leading=14, textColor=colors.HexColor(NAVY), spaceBefore=6, spaceAfter=3),
    "body": ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12.5, textColor=colors.HexColor(INK), alignment=TA_LEFT),
    "bullet": ParagraphStyle("bullet", fontName=FONT, fontSize=9, leading=12.5, leftIndent=10, bulletIndent=0,
                             textColor=colors.HexColor(INK)),
    "small": ParagraphStyle("small", fontName=FONT, fontSize=7.5, leading=9.5, textColor=colors.HexColor(MUTED)),
    "cell": ParagraphStyle("cell", fontName=FONT, fontSize=7.5, leading=9.2, textColor=colors.HexColor(INK)),
    "cellb": ParagraphStyle("cellb", fontName=FONT_B, fontSize=7.5, leading=9.2, textColor=colors.HexColor(INK)),
    "tile_v": ParagraphStyle("tile_v", fontName=FONT_B, fontSize=18, leading=21, textColor=colors.HexColor(NAVY)),
    "tile_vs": ParagraphStyle("tile_vs", fontName=FONT_B, fontSize=12, leading=21, textColor=colors.HexColor(NAVY)),
    "tile_l": ParagraphStyle("tile_l", fontName=FONT, fontSize=7.5, leading=9.5, textColor=colors.HexColor(MUTED)),
}
W = A4[0] - 32 * mm


def P(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, ST[style])


def bullets(items: list[str]) -> list:
    return [Paragraph(t, ST["bullet"], bulletText="•") for t in items]


def table(data: list[list], col_widths: list[float], header_rows: int = 1, extra: list | None = None,
          font_size: float = 7.5) -> Table:
    wrapped = [[c if isinstance(c, (Paragraph, Image)) else Paragraph(str(c), ST["cellb"] if i < header_rows else ST["cell"])
                for c in row] for i, row in enumerate(data)]
    t = Table(wrapped, colWidths=col_widths, repeatRows=header_rows)
    style = [("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#E8EBF2")),
             ("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.6, colors.HexColor(NAVY)),
             ("LINEBELOW", (0, header_rows), (-1, -1), 0.25, colors.HexColor(GRID)),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2.2),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2), ("LEFTPADDING", (0, 0), (-1, -1), 3),
             ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    t.setStyle(TableStyle(style + (extra or [])))
    return t


def fig_image(fig, width: float) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    from PIL import Image as PILImage
    with PILImage.open(buf) as im:
        w, h = im.size
    buf.seek(0)
    img = Image(buf, width=width, height=width * h / w)
    return img


def _axes_style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#9E9E9E")
    ax.tick_params(colors=MUTED, labelsize=7)
    ax.grid(axis="y", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)


plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7.5, "axes.titlesize": 8.5, "axes.titleweight": "bold",
                     "axes.titlecolor": NAVY, "axes.labelcolor": MUTED})


# ---------------------------------------------------------------- report
def build(path: Path | str = REPORT_PATH, outputs: dict | None = None, ref: dict | None = None) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    o = outputs or datastore.load_outputs()
    ref = ref or datastore.load_reference()
    cfg = datastore.load_config()
    rep = cfg["bank_profile"]["reporting"]["period_end"]
    F = Facts()
    rw, ra = ref["risk_weights"], ref["risk_appetite"]
    risks = list(rw.risk_type)
    km, rs, ep = o["kri_monthly"], o["risk_scores_monthly"], o["enterprise_profile_monthly"]
    periods = sorted(ep.period.unique())
    first = periods[0]
    kmS = km[km.period == rep].set_index("kri_id")
    rsS = rs[rs.period == rep].set_index("risk_type")
    epS = ep[ep.period == rep].iloc[0]
    ep0 = ep[ep.period == first].iloc[0]
    se = o["stress_enterprise_summary"].set_index("scenario")
    srs = o["stress_risk_scores"].pivot(index="risk_type", columns="scenario", values="final_score")
    cap = o["capital_overlay"].set_index("scenario")
    act = o["management_actions"]
    names = ra.set_index("kri_id").kri_name
    units = ra.set_index("kri_id").unit
    story: list = []

    # ============ 1. Executive Summary
    story += [P("Enterprise Risk Management Report", "title"),
              P(f"PT Amanah Syariah Bank (fiktif) · Bank Umum Syariah · posisi {mlabel(rep)} · data sintetis", "subtitle"),
              Spacer(1, 8), P("1. Executive Summary", "h1")]
    ent_color = scoring.rating(epS.enterprise_score)[1]
    tiles = [
        (F.score("ent_score", epS.enterprise_score, "enterprise_profile_monthly.enterprise_score@rep"), "Enterprise risk score"),
        (F("ent_rating", epS.rating, epS.rating, "enterprise_profile_monthly.rating@rep"), "Rating"),
        (F("rau", float(epS.limit_utilization), f"{round(epS.limit_utilization):d}%", "enterprise_profile_monthly.limit_utilization@rep"), "Limit utilization"),
        (F("breach", int(epS.tolerance_breaches), f"{int(epS.tolerance_breaches)} / {int(epS.limit_breaches)}", "enterprise_profile_monthly.tolerance_breaches/limit_breaches@rep"), "KRI skor ≥4 / skor 5"),
        (F("emerging", int(epS.emerging_count), str(int(epS.emerging_count)), "enterprise_profile_monthly.emerging_count@rep"), "Emerging risk (register)"),
    ]
    tile_row = [[P(v, "tile_v" if len(v) <= 6 else "tile_vs"), P(lbl, "tile_l")] for v, lbl in tiles]
    tt = Table([[Table([[c[0]], [c[1]]], colWidths=[W / 5 - 6]) for c in tile_row]], colWidths=[W / 5] * 5)
    tt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor(GRID)),
                            ("LINEBEFORE", (1, 0), (-1, 0), 0.4, colors.HexColor(GRID)),
                            ("LINEABOVE", (0, 0), (0, 0), 3, colors.HexColor(STATUS[ent_color])),
                            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [tt, Spacer(1, 8)]

    top_risks = rsS.sort_values("final_score", ascending=False).head(3)
    top_txt = ", ".join(f"{r} ({F.score(f'top_{r}', v, f'risk_scores_monthly.final_score@{rep}:{r}')})"
                        for r, v in top_risks.final_score.items())
    comp = rsS.loc["Compliance"]
    sev, adv = se.loc["severe"], se.loc["adverse"]
    inv_share = float(cap.at["severe", "investment_loss"] / cap.at["severe", "total_loss"])
    loss_names = {'credit_loss': 'kerugian kredit', 'investment_loss': 'nilai pasar sukuk', 'op_loss': 'kerugian operasional', 'dcr_cost': 'biaya displaced commercial risk'}
    top_col = max(loss_names, key=lambda c: cap.at['severe', c])
    top_loss, top_share = loss_names[top_col], float(cap.at['severe', top_col] / cap.at['severe', 'total_loss'])
    cap01_limit = float(ra.set_index('kri_id').at['CAP01', 'c4'])
    inv_share_txt = f"{round(inv_share * 100):d}%"
    story += [P("Pesan kunci", "h2")] + bullets([
        f"Profil risiko enterprise berada pada <b>{F.score('ent_score_b', epS.enterprise_score, 'enterprise_profile_monthly.enterprise_score@rep')} "
        f"({epS.rating})</b>, naik dari {F.score('ent_score_first', ep0.enterprise_score, f'enterprise_profile_monthly.enterprise_score@{first}')} "
        f"pada {mlabel(first)}. Jumlah KRI yang melewati trigger (skor ≥ 4) naik dari {F('b_first', int(ep0.tolerance_breaches), str(int(ep0.tolerance_breaches)), f'enterprise_profile_monthly.tolerance_breaches@{first}')} "
        f"menjadi {F('b_rep', int(epS.tolerance_breaches), str(int(epS.tolerance_breaches)), 'enterprise_profile_monthly.tolerance_breaches@rep')}; " + ("belum ada limit breach." if int(epS.limit_breaches) == 0 else f"{int(epS.limit_breaches)} KRI melewati limit."),
        f"Risiko tertinggi: {top_txt}. Compliance memakai judgment override "
        f"{F.score('comp_model', comp.model_score, 'risk_scores_monthly.model_score@rep:Compliance')} → "
        f"{F.score('comp_final', comp.final_score, 'risk_scores_monthly.final_score@rep:Compliance')} karena KRI belum menangkap potensi temuan pemeriksaan atas akad yang belum sesuai opini DPS.",
        f"Likuiditas memburuk dalam 4 bulan terakhir: SLSI turun ke {F.num('slsi', kmS.at['LQ01', 'value'], 'kri_monthly.value@rep:LQ01', 1, '%')} dan penurunan DPK 3 bulan "
        f"{F.num('lq05', kmS.at['LQ05', 'value'], 'kri_monthly.value@rep:LQ05', 1, '%')}; negative maturity gap ≤1 bulan mencapai "
        f"{F.num('lq04', kmS.at['LQ04', 'value'], 'kri_monthly.value@rep:LQ04', 1, '%')} aset ({kmS.at['LQ04', 'zone'].lower()}).",
        f"Dalam skenario severe, enterprise score naik ke <b>{F.score('sev_ent', sev.enterprise_score, 'stress_enterprise_summary.enterprise_score:severe')} ({sev.rating})</b> "
        f"dengan {F('sev_b5', int(sev.limit_breaches), str(int(sev.limit_breaches)), 'stress_enterprise_summary.limit_breaches:severe')} limit breach. "
        f"KPMM turun dari {F.num('kpmm_base', cap.at['baseline', 'kpmm'], 'capital_overlay.kpmm:baseline', 1, '%')} menjadi "
        f"{F.num('kpmm_sev', cap.at['severe', 'kpmm'], 'capital_overlay.kpmm:severe', 1, '%')}; "
        f"{'modal tetap di atas limit CAP01' if cap.at['severe', 'kpmm'] >= cap01_limit else 'modal turun di bawah limit CAP01'}, dan driver erosi terbesar adalah {top_loss} "
        f"({F('top_loss_share', top_share, f'{round(top_share * 100):d}%', 'capital_overlay.max(loss)/total_loss:severe')} dari total kerugian).",
        f"Terdapat {F('act_live', int(act.status.isin(['Open', 'Overdue']).sum()), str(int(act.status.isin(['Open', 'Overdue']).sum())), 'management_actions.status in Open/Overdue')} management action aktif, "
        f"{F('act_overdue', int((act.status == 'Overdue').sum()), str(int((act.status == 'Overdue').sum())), 'management_actions.status=Overdue')} di antaranya overdue.",
    ])
    story += [Spacer(1, 6), P("Keputusan yang diminta dari RMC/Direksi", "h2")] + bullets([
        "Menyetujui prioritas remediasi untuk KRI tolerance breach (sheet 08 / halaman Management Actions), terutama action yang overdue.",
        "Mengkaji ulang laju pertumbuhan pembiayaan terhadap RKB dan standar underwriting UMKM.",
        "Menetapkan rencana kontinjensi likuiditas dan batas durasi portofolio sukuk FVOCI mengingat sensitivitas modal dalam skenario severe.",
    ])
    story += [Spacer(1, 10), P(DISCLAIMER, "small"), PageBreak()]

    # ============ 2. Framework
    story += [P("2. Framework", "h1"),
              P("Kerangka ERM ASB menghubungkan risk appetite, pemantauan KRI, stress testing, dan management action dalam satu "
                f"siklus. {len(risks)} risk type mengikuti taksonomi Bank Umum Syariah; setiap risk diukur dengan KRI berbobot, dan "
                "setiap KRI memiliki empat cut-point (strong, risk appetite, early warning trigger, risk limit).")]
    cnt = ra[ra.risk_type != "Capital Overlay"].groupby("risk_type").size()
    rows = [["Risk type", "Bobot materialitas", "Jumlah KRI", "Measurement approach", "Depth"]]
    for r in rw.itertuples():
        rows.append([r.risk_type, F.num(f"w_{r.risk_type}", r.materiality_weight, f"risk_weights.materiality_weight:{r.risk_type}", 2),
                     str(int(cnt[r.risk_type])), r.measurement_approach, r.depth])
    rows.append(["<b>Total</b>", F.num("w_total", rw.materiality_weight.sum(), "risk_weights.materiality_weight.sum", 2),
                 F("kri_total", int(cnt.sum()), str(int(cnt.sum())), "risk_appetite (tanpa Capital Overlay)"), "+ 1 capital overlay (CAP01)", ""])
    story += [Spacer(1, 4), table(rows, [W * .22, W * .18, W * .14, W * .26, W * .20])]
    story += [P("Skala skor dan tata kelola", "h2")]
    zone_rows = [["Skor", "Zona", "Makna governance", "Warna"],
                 ["1", "Strong", "Jauh di dalam appetite", "Green"], ["2", "Within appetite", "Nilai ≤ risk appetite (c2)", "Green"],
                 ["3", "Watch", "Di atas appetite, di bawah early warning trigger (c3)", "Amber"],
                 ["4", "Tolerance breach", f"Melewati trigger, di bawah risk limit (c4) → action {actions.DUE_DAYS[4]} hari", "Red"],
                 ["5", "Limit breach", f"Melewati limit → action {actions.DUE_DAYS[5]} hari + eskalasi Direksi/RMC", "Red"]]
    story += [table(zone_rows, [W * .08, W * .2, W * .57, W * .15],
                    extra=[("BACKGROUND", (3, i), (3, i), colors.HexColor(TINT[zone_rows[i][3]])) for i in range(1, 6)])]
    story += [P("Alur agregasi", "h2")] + bullets([
        "KRI score (1–5) dari cut-point → risk score = rata-rata tertimbang skor KRI, dengan <b>floor</b> max(skor) − 1,5 agar satu KRI kritis tidak tersamarkan.",
        "Judgment override maksimal ±1,0, terdokumentasi (rationale, approver, masa berlaku); model score dan final score selalu ditampilkan berdampingan.",
        "Enterprise score = Σ final score × bobot materialitas, dengan floor max − 1,5 dan eskalasi minimal 3,5 bila risk berbobot ≥ 0,10 mencapai skor ≥ 4,5.",
        "Stress testing menerapkan aturan transmisi makro per KRI (3 skenario), lalu skoring ulang dengan metodologi yang sama dan capital overlay KPMM.",
    ])
    story += [PageBreak()]

    # ============ 3. Risk Profile
    story += [P("3. Risk Profile", "h1"), P(f"Posisi {mlabel(rep)}: model score vs final score per risk type (tampilan 1 desimal).")]
    prow = [["Risk type", "Bobot", "Weighted", "Floor", "Model", "Override", "Final", "Rating"]]
    ext = []
    for i, r in enumerate(risks, start=1):
        x = rsS.loc[r]
        prow.append([r, id_num(rw.set_index("risk_type").at[r, "materiality_weight"], 2),
                     F.score(f"p_w_{r}", x.weighted_score, f"risk_scores_monthly.weighted_score@rep:{r}"),
                     F.score(f"p_f_{r}", x.floor_score, f"risk_scores_monthly.floor_score@rep:{r}"),
                     F.score(f"p_m_{r}", x.model_score, f"risk_scores_monthly.model_score@rep:{r}"),
                     F("p_o_" + r, float(x.override_delta), ("+" if x.override_delta > 0 else "") + id_num(x.override_delta, 1) if x.override_delta else "–",
                       f"risk_scores_monthly.override_delta@rep:{r}"),
                     F.score(f"p_final_{r}", x.final_score, f"risk_scores_monthly.final_score@rep:{r}"), x.rating])
        ext.append(("BACKGROUND", (6, i), (7, i), colors.HexColor(TINT[x.color])))
    prow.append(["<b>Enterprise</b>", "", "", "", "", "", F.score("p_ent", epS.enterprise_score, "enterprise_profile_monthly.enterprise_score@rep"), epS.rating])
    ext.append(("BACKGROUND", (6, len(prow) - 1), (7, len(prow) - 1), colors.HexColor(TINT[ent_color])))
    story += [Spacer(1, 3), table(prow, [W * .2, W * .09, W * .1, W * .09, W * .09, W * .1, W * .09, W * .24], extra=ext)]

    story += [P("Tren final risk score 12 bulan", "h2")]
    piv = rs.pivot(index="risk_type", columns="period", values="final_score").reindex(risks)
    hrow = [["Risk"] + [MONTHS_ID[int(p[5:])] for p in periods]]
    ext = []
    for i, r in enumerate(risks, start=1):
        cells = [r]
        for j, p in enumerate(periods, start=1):
            v = piv.at[r, p]
            cells.append(id_num(scoring.r1(v), 1))
            ext.append(("BACKGROUND", (j, i), (j, i), colors.HexColor(TINT[scoring.rating(v)[1]])))
        hrow.append(cells)
    erow = ["<b>Enterprise</b>"]
    for j, p in enumerate(periods, start=1):
        v = ep.set_index("period").at[p, "enterprise_score"]
        erow.append(id_num(scoring.r1(v), 1))
        ext.append(("BACKGROUND", (j, len(hrow)), (j, len(hrow)), colors.HexColor(TINT[scoring.rating(v)[1]])))
    hrow.append(erow)
    story += [table(hrow, [W * .16] + [W * .07] * 12, extra=ext + [("ALIGN", (1, 0), (-1, -1), "CENTER")])]
    story += [Spacer(1, 4), P("Warna mengikuti rating: Green < 2,5 · Amber 2,5–3,5 · Red ≥ 3,5 (skor dibulatkan 1 desimal). "
                              f"Override Compliance hanya berlaku pada periode {mlabel(rep)} sesuai masa berlaku di register override.", "small")]

    # enterprise trend (two small charts, no dual axis)
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.0))
    x = np.arange(len(periods))
    labels = [MONTHS_ID[int(p[5:])] for p in periods]
    ax = axes[0]
    ax.plot(x, ep.enterprise_score, color=NAVY, linewidth=2, marker="o", markersize=3)
    for thr in (2.5, 3.5):
        ax.axhline(thr, color="#9E9E9E", linewidth=0.8, linestyle="--")
    ax.set_title("Enterprise risk score")
    ax.set_ylim(1, 5)
    ax.annotate(id_num(scoring.r1(epS.enterprise_score)), (x[-1], epS.enterprise_score), textcoords="offset points",
                xytext=(-4, 6), ha="right", fontsize=7, color=INK)
    ax = axes[1]
    ax.bar(x, ep.tolerance_breaches, color=STATUS["Red"], width=0.6)
    ax.set_title("Jumlah KRI skor ≥ 4 (tolerance breach)")
    ax.annotate(str(int(epS.tolerance_breaches)), (x[-1], epS.tolerance_breaches), textcoords="offset points", xytext=(0, 3),
                ha="center", fontsize=7, color=INK)
    for ax in axes:
        _axes_style(ax)
        ax.set_xticks(x, labels)
    story += [Spacer(1, 6), fig_image(fig, W), PageBreak()]

    # ============ 4. Appetite Monitoring
    story += [P("4. Risk Appetite Monitoring", "h1"),
              P("Nilai aktual KRI utama terhadap risk appetite (c2), early warning trigger (c3), dan risk limit (c4).")]
    focus = ["CR01", "CR02", "LQ01", "LQ04", "OR01", "RP01"]
    fig, axes = plt.subplots(2, 3, figsize=(7.2, 4.0))
    for ax, kid in zip(axes.flat, focus):
        s = km[km.kri_id == kid].sort_values("period")
        r = ra.set_index("kri_id").loc[kid]
        ax.plot(x, s.value, color=NAVY, linewidth=2)
        ax.axhline(r.c2, color=STATUS["Green"], linewidth=1, linestyle="--")
        ax.axhline(r.c3, color=STATUS["Amber"], linewidth=1, linestyle="--")
        ax.axhline(r.c4, color=STATUS["Red"], linewidth=1, linestyle="--")
        ax.set_title(f"{kid} · {SHORT[kid]}", loc="left")
        _axes_style(ax)
        ax.set_xticks(x[::3], labels[::3])
        ax.annotate(id_num(s.value.iloc[-1], 1), (x[-1], s.value.iloc[-1]), textcoords="offset points", xytext=(0, 4),
                    ha="right", fontsize=7, color=INK)
    handles = [plt.Line2D([], [], color=NAVY, linewidth=2), plt.Line2D([], [], color=STATUS["Green"], linestyle="--"),
               plt.Line2D([], [], color=STATUS["Amber"], linestyle="--"), plt.Line2D([], [], color=STATUS["Red"], linestyle="--")]
    fig.legend(handles, ["Aktual", "Risk appetite (c2)", "Early warning trigger (c3)", "Risk limit (c4)"], loc="lower center",
               ncol=4, frameon=False, fontsize=7)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    story += [fig_image(fig, W)]
    story += [P(f"KRI di atas trigger pada {mlabel(rep)}", "h2")]
    br = kmS[(kmS.score >= 4) & (kmS.risk_type != "Capital Overlay")].sort_values(["score", "utilization"], ascending=False)
    brow = [["KRI", "Nama", "Nilai", "Appetite", "Trigger", "Limit", "Skor", "Utilisasi", "Trend"]]
    ext = []
    for i, (kid, k) in enumerate(br.iterrows(), start=1):
        r = ra.set_index("kri_id").loc[kid]
        brow.append([kid, names[kid], F.num(f"br_{kid}", k.value, f"kri_monthly.value@rep:{kid}", 2) + f" {units[kid]}",
                     id_num(r.c2, 2), id_num(r.c3, 2), id_num(r.c4, 2), str(int(k.score)),
                     F("ut_" + kid, float(k.utilization), f"{round(k.utilization * 100):d}%", f"kri_monthly.utilization@rep:{kid}"),
                     k.trend_label])
        ext.append(("BACKGROUND", (6, i), (6, i), colors.HexColor(TINT[k.color])))
    story += [table(brow, [W * .065, W * .235, W * .14, W * .085, W * .08, W * .075, W * .065, W * .085, W * .17], extra=ext)]
    story += [Spacer(1, 3), P("Utilisasi = |nilai| / limit (arah lower) atau limit / nilai (arah higher), maksimal 150%.", "small"), PageBreak()]

    # ============ 5. Key Developments
    story += [P("5. Key Developments", "h1")]
    k0 = km[km.period == first].set_index("kri_id")

    def chg(kid, d=2, suf=""):
        return (f"{F.num(f'kd0_{kid}', k0.at[kid, 'value'], f'kri_monthly.value@{first}:{kid}', d, suf)} → "
                f"{F.num(f'kd1_{kid}', kmS.at[kid, 'value'], f'kri_monthly.value@rep:{kid}', d, suf)}")

    kri_jun = km[km.period == "2026-05"].set_index("kri_id") if "2026-05" in periods else k0
    story += bullets([
        f"<b>Kualitas pembiayaan menurun bertahap.</b> NPF gross {chg('CR01', 2, '%')} dan NPF UMKM {chg('CR02', 2, '%')} "
        f"(skor {int(kmS.at['CR02', 'score'])}). Pertumbuhan pembiayaan melampaui RKB (deviasi {chg('ST01', 1, ' pp')}), "
        "mengindikasikan pelonggaran underwriting pada segmen UMKM.",
        f"<b>Lonjakan insiden operasional digital sejak Jun-2026.</b> Insiden per bulan {F.num('or01_may', kri_jun.at['OR01', 'value'], 'kri_monthly.value@2026-05:OR01', 0)} "
        f"pada Mei-2026 menjadi {F.num('or01_rep', kmS.at['OR01', 'value'], 'kri_monthly.value@rep:OR01', 0)} pada {mlabel(rep)}; kerugian rolling 12 bulan "
        f"{chg('OR03', 2, '% GI')}. Root cause dominan: process failure pada operasi transaksi digital.",
        f"<b>Tekanan likuiditas pada 4 bulan terakhir.</b> SLSI {chg('LQ01', 1, '%')}, FDR {chg('LQ02', 1, '%')}, dan negative maturity gap ≤1 bulan "
        f"{chg('LQ04', 1, '% aset')}. Deposan besar relatif bertahan sehingga konsentrasi top-20 naik ({chg('LQ03', 1, '% DPK')}).",
        f"<b>Displaced commercial risk meningkat.</b> Gap bagi hasil deposito vs benchmark {chg('RR01', 2, ' pp')} dan gap ekspektasi vs realisasi deposan "
        f"{chg('RR02', 2, ' pp')}; NIM {chg('RR03', 2, '%')}.",
        f"<b>Komplain melonjak pada Ags–Sep 2026</b> terkait gangguan mobile banking: pertumbuhan komplain MoM "
        f"{F.num('rp01_rep', kmS.at['RP01', 'value'], 'kri_monthly.value@rep:RP01', 1, '%')} (skor {int(kmS.at['RP01', 'score'])}), "
        f"sementara rasio komplain severe relatif stabil ({chg('RP02', 1, '%')}) sehingga Reputation tetap Amber.",
        f"<b>Kepatuhan syariah.</b> Pelanggaran high-severity yang melewati target remediasi {chg('CP02', 0)}; sebagian terkait akad "
        f"pembiayaan yang belum sesuai opini DPS (lihat rationale judgment override). Temuan DPS terbuka >90 hari: {F.num('cp04', kmS.at['CP04', 'value'], 'kri_monthly.value@rep:CP04', 0)}.",
    ])
    det = kmS[(kmS.trend_label == "Deteriorating") & (kmS.risk_type != "Capital Overlay")]
    ew = kmS[kmS.early_warning_flag.astype(bool)]
    story += [P(f"KRI Deteriorating ({F('n_det', len(det), str(len(det)), 'kri_monthly.trend_label=Deteriorating@rep')}) dan early warning "
                f"({F('n_ew', len(ew), str(len(ew)), 'kri_monthly.early_warning_flag@rep')})", "h2")]
    erow = [["KRI", "Nama", "Nilai", "Skor", "Trend", "Early warning"]]
    for kid, k in pd.concat([det, ew[~ew.index.isin(det.index)]]).sort_values("score", ascending=False).iterrows():
        erow.append([kid, names[kid], id_num(k.value, 2) + f" {units[kid]}", str(int(k.score)), k.trend_label,
                     "Ya" if bool(k.early_warning_flag) else "–"])
    story += [table(erow, [W * .08, W * .42, W * .16, W * .07, W * .15, W * .12])]
    story += [Spacer(1, 3), P("Trend: rata-rata 3 bulan terakhir vs 3 bulan sebelumnya, dinormalisasi |c4 − c1| (ambang ±10%). "
                              "Early warning: skor ≤ 3 dan proyeksi OLS 6 bulan melewati cut-point berikutnya dalam ≤ 3 bulan.", "small"),
              PageBreak()]

    # ============ 6. Stress Testing + KPMM
    mac = ref["macro_scenarios"].set_index("variable")
    story += [P("6. Enterprise Stress Testing dan Capital Overlay", "h1"),
              P("Horizon 12 bulan, neraca statis, tanpa management action (gross stress impact). Aturan transmisi per KRI dan "
                "koefisien adalah asumsi analitis project.")]
    mrow = [["Variabel makro", "Baseline", "Adverse", "Severe"]]
    for var, lbl in [("gdp_growth", "GDP growth (%)"), ("policy_rate_shift", "Policy rate shift (bps)"),
                     ("idr_depreciation", "Depresiasi IDR (%)"), ("deposit_decline_3m", "Penurunan DPK 3 bulan (%)"),
                     ("sukuk_mv_shock_fvoci", "Shock MV sukuk FVOCI (%)"), ("operational_event_uplift", "Uplift insiden operasional (%)")]:
        mrow.append([lbl] + [id_num(mac.at[var, s], 1) for s in datastore.SCENARIOS])
    story += [table(mrow, [W * .46, W * .18, W * .18, W * .18], extra=[("ALIGN", (1, 0), (-1, -1), "RIGHT")])]
    story += [P("Hasil skoring per skenario", "h2")]
    srow = [["Risk type", "Baseline", "Adverse", "Severe", "Δ severe"]]
    ext = []
    for i, r in enumerate(risks, start=1):
        cells = [r]
        for j, s in enumerate(datastore.SCENARIOS, start=1):
            v = srs.at[r, s]
            cells.append(F.score(f"st_{r}_{s}", v, f"stress_risk_scores.final_score:{s}:{r}"))
            ext.append(("BACKGROUND", (j, i), (j, i), colors.HexColor(TINT[scoring.rating(v)[1]])))
        d = srs.at[r, "severe"] - srs.at[r, "baseline"]
        cells.append(("+" if d > 0 else "") + id_num(d, 2) if abs(d) > 1e-9 else "–")
        srow.append(cells)
    n = len(srow)
    srow.append(["<b>Enterprise</b>"] + [F.score(f"st_ent_{s}", se.at[s, "enterprise_score"], f"stress_enterprise_summary.enterprise_score:{s}")
                                        + f" {se.at[s, 'rating']}" for s in datastore.SCENARIOS] + [""])
    srow.append(["Limit utilization"] + [F("st_rau_" + s, float(se.at[s, "limit_utilization"]), f"{round(se.at[s, 'limit_utilization']):d}%",
                                           f"stress_enterprise_summary.limit_utilization:{s}") for s in datastore.SCENARIOS] + [""])
    srow.append(["KRI skor ≥4 / skor 5"] + [F("st_b_" + s, int(se.at[s, "tolerance_breaches"]),
                                              f"{int(se.at[s, 'tolerance_breaches'])} / {int(se.at[s, 'limit_breaches'])}",
                                              f"stress_enterprise_summary.tolerance_breaches/limit_breaches:{s}") for s in datastore.SCENARIOS] + [""])
    for j, s in enumerate(datastore.SCENARIOS, start=1):
        ext.append(("BACKGROUND", (j, n), (j, n), colors.HexColor(TINT[scoring.rating(se.at[s, "enterprise_score"])[1]])))
    ext.append(("LINEABOVE", (0, n), (-1, n), 0.6, colors.HexColor(NAVY)))
    story += [table(srow, [W * .28, W * .2, W * .2, W * .2, W * .12], extra=ext + [("ALIGN", (1, 0), (-1, -1), "CENTER")])]

    wf = o["stress_waterfall"].query("to_scenario == 'severe'")
    drv = wf[wf.step.between(1, len(risks)) & (wf.contribution.abs() > 1e-12)]
    fig, ax = plt.subplots(figsize=(3.6, 3.3))
    base_v = float(wf[wf.step == 0].contribution.iloc[0])
    end_v = float(wf.cumulative.iloc[-1])
    labels_w = ["Baseline"] + list(drv.driver) + ["Severe"]
    bottoms = [0] + list(drv.cumulative - drv.contribution) + [0]
    heights = [base_v] + list(drv.contribution) + [end_v]
    cols = [NAVY] + [STATUS["Red"] if h > 0 else STATUS["Green"] for h in drv.contribution] + [NAVY]
    yy = np.arange(len(labels_w))[::-1]
    ax.barh(yy, heights, left=bottoms, color=cols, height=0.62)
    for yi, b, h in zip(yy, bottoms, heights):
        txt = id_num(h, 2) if yi in (yy[0], yy[-1]) else ("+" + id_num(h, 2))
        ax.text(b + h + 0.03, yi, txt, va="center", fontsize=6.5, color=INK)
    ax.set_yticks(yy, labels_w)
    ax.set_xlim(0, end_v + 0.7)
    ax.set_title("Waterfall enterprise score: baseline → severe", loc="left")
    _axes_style(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.5)
    ax.grid(axis="y", visible=False)
    wf_img = fig_image(fig, W * 0.49)
    crow = [["", "Baseline", "Adverse", "Severe"]]
    for col, lbl, d in [("credit_loss", "Kerugian kredit (ΔNPF × pembiayaan × loss rate)", 0), ("investment_loss", "Kerugian sukuk FVOCI", 0),
                        ("op_loss", "Kerugian operasional", 0), ("dcr_cost", "Biaya displaced commercial risk", 0),
                        ("total_loss", "<b>Total kerugian</b>", 0), ("capital", "Modal", 0), ("atmr", "ATMR", 0)]:
        crow.append([lbl] + [("–" if (col.endswith("loss") or col == "dcr_cost") and cap.at[s, col] == 0 else
                              F.num(f"cap_{col}_{s}", cap.at[s, col], f"capital_overlay.{col}:{s}", d)) for s in datastore.SCENARIOS])
    crow.append(["<b>KPMM</b>"] + [F.num(f"cap_kpmm_{s}", cap.at[s, "kpmm"], f"capital_overlay.kpmm:{s}", 1, "%") for s in datastore.SCENARIOS])
    crow.append(["Skor CAP01 (16 / 14 / 12 / 10,5)"] + [str(int(cap.at[s, "cap_score"])) for s in datastore.SCENARIOS])
    cap_tbl = table(crow, [W * .46, W * .18, W * .18, W * .18], extra=[("ALIGN", (1, 0), (-1, -1), "RIGHT")])

    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    xs = np.arange(3)
    bottom = np.zeros(3)
    for (col, lbl), c in zip([("credit_loss", "Kredit"), ("investment_loss", "Sukuk FVOCI"), ("op_loss", "Operasional"),
                              ("dcr_cost", "DCR")], SERIES):
        vals = np.array([cap.at[s, col] for s in datastore.SCENARIOS])
        ax.bar(xs, vals, bottom=bottom, color=c, width=0.55, label=lbl, edgecolor="white", linewidth=1)
        bottom += vals
    for xi, tot in zip(xs, bottom):
        if tot > 0:
            ax.text(xi, tot + 25, id_num(tot, 0), ha="center", fontsize=7, color=INK)
    ax.set_xticks(xs, ["Baseline", "Adverse", "Severe"])
    ax.set_title("Kerugian stress (Rp miliar)", loc="left")
    ax.legend(frameon=False, fontsize=6.5, loc="upper left")
    _axes_style(ax)
    ax.set_ylim(0, bottom.max() * 1.18)
    loss_img = fig_image(fig, W * 0.49)
    story += [Spacer(1, 6), Table([[wf_img, loss_img]], colWidths=[W * 0.5, W * 0.5],
                                  style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]),
              P("Capital Adequacy Overlay (KPMM)", "h2"), cap_tbl]
    story += [P(f"Insight: pada skenario severe, driver terbesar erosi modal adalah {top_loss} "
                f"({round(top_share * 100):d}% total kerugian)"
                + (", lebih besar dari kerugian kredit. " if top_col != "credit_loss" else ". ") +
                "Loss rate kredit adalah asumsi tunggal, bukan model kerugian kredit; laba berjalan tidak diperhitungkan (konservatif).", "small"),
              PageBreak()]

    # ============ 7. Interdependency + 8. Emerging Risks
    ed = ref["interdependency_edges"]
    story += [P("7. Risk Interdependency", "h1"),
              P("Jalur transmisi antar-risiko yang dibuktikan oleh KRI dan aturan stress. Ketebalan garis menunjukkan kekuatan (1–3).")]
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    pos = {"Macro downturn": (0.0, 0.78), "Policy rate ↑": (0.0, 0.18), "Credit": (0.45, 0.97), "Strategic": (0.45, 0.72),
           "Investment": (0.45, 0.50), "Market": (0.45, 0.28), "Rate of Return": (0.45, 0.02), "Liquidity": (0.88, 0.22),
           "Operational": (0.72, 0.97), "Reputation": (0.97, 0.80), "Compliance": (0.72, 0.58)}
    for e in ed.itertuples():
        (x0, y0), (x1, y1) = pos[e.source], pos[e.target]
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="-|>", color="#7A869A", lw=0.8 + 1.2 * (e.strength - 1),
                                    shrinkA=18, shrinkB=18, connectionstyle="arc3,rad=0.08"))
    for node, (xn, yn) in pos.items():
        if node in rsS.index:
            col = rsS.at[node, "color"]
            face, edge = TINT[col], STATUS[col]
            label = f"{node}\n{id_num(scoring.r1(rsS.at[node, 'final_score']))}"
        else:
            face, edge, label = "#E8EBF2", NAVY, node
        ax.text(xn, yn, label, ha="center", va="center", fontsize=7, color=INK,
                bbox=dict(boxstyle="round,pad=0.35", facecolor=face, edgecolor=edge, linewidth=1))
    ax.set_xlim(-0.12, 1.08)
    ax.set_ylim(-0.08, 1.08)
    ax.axis("off")
    story += [fig_image(fig, W * 0.92)]
    irow = [["Source", "Target", "Channel", "Strength", "Evidence"]]
    for e in ed.sort_values("strength", ascending=False, kind="mergesort").itertuples():
        irow.append([e.source, e.target, e.channel, str(int(e.strength)), e.evidence])
    story += [table(irow, [W * .2, W * .18, W * .34, W * .1, W * .18])]
    story += [P("Top enterprise driver: kenaikan policy rate mengalir ke Market (nilai sukuk), Rate of Return (gap bagi hasil), "
                "dan Liquidity (deposan berpindah).", "small")]

    er = ref["emerging_risks"].sort_values("priority_score", ascending=False)
    story += [P("8. Emerging Risks", "h1")]
    rrow = [["ID", "Risk", "Driver", "L", "I", "V", "Priority", "Status", "Early signal", "Owner"]]
    for e in er.itertuples():
        rrow.append([e.er_id, e.risk_name, e.driver, str(e.likelihood), str(e.impact), str(e.velocity),
                     F.num(f"er_{e.er_id}", e.priority_score, f"emerging_risks.priority_score:{e.er_id}", 1), e.status,
                     e.early_signal, e.owner])
    story += [table(rrow, [W * .065, W * .1, W * .13, W * .035, W * .035, W * .035, W * .075, W * .08, W * .265, W * .18])]
    story += [P("Priority = likelihood × impact × (velocity / 5). Register ditinjau berkala; status Monitor → Watch → Act.", "small"),
              PageBreak()]

    # ============ 9. Management Actions
    story += [P("9. Management Actions", "h1"),
              P(f"Aturan otomatis: setiap KRI dengan skor 4 menghasilkan action jatuh tempo {actions.DUE_DAYS[4]} hari; skor 5 menghasilkan action {actions.DUE_DAYS[5]} hari "
                "dan eskalasi ke Direksi/RMC. Teks action diambil dari action library per KRI.")]
    counts = act.status.value_counts()
    sum_row = [["Status", "Open", "Overdue", "Closed", "Total"],
               ["Jumlah"] + [F(f"act_{s}", int(counts.get(s, 0)), str(int(counts.get(s, 0))), f"management_actions.status={s}")
                             for s in ("Open", "Overdue", "Closed")] + [F("act_total", len(act), str(len(act)), "management_actions.count")]]
    story += [table(sum_row, [W * .2] * 5, extra=[("ALIGN", (1, 0), (-1, -1), "CENTER")]), Spacer(1, 6)]
    arow = [["ID", "Periode", "KRI", "Temuan", "Action", "Owner", "Due", "Status"]]
    ext = []
    for i, a in enumerate(act.sort_values(["status", "due_date"], key=lambda c: c.map({"Overdue": 0, "Open": 1, "Closed": 2}).fillna(3) if c.name == "status" else c).itertuples(), start=1):
        arow.append([a.action_id, mlabel(a.period), a.kri_id, a.finding, a.recommended_action, a.owner, a.due_date, a.status])
        tint = {"Overdue": TINT["Red"], "Open": TINT["Amber"], "Closed": TINT["Green"]}.get(a.status)
        if tint:
            ext.append(("BACKGROUND", (7, i), (7, i), colors.HexColor(tint)))
    story += [table(arow, [W * .1, W * .095, W * .06, W * .215, W * .215, W * .11, W * .105, W * .1], extra=ext)]
    story += [PageBreak()]

    # ============ 10. Methodology, Limitations & Disclaimer
    story += [P("10. Methodology, Limitations & Disclaimer", "h1"), P("Metodologi", "h2")] + bullets([
        f"Data: bank fiktif dengan neraca jangkar {mlabel(rep)} (total aset Rp {id_num(cfg['bank_profile']['balance_sheet_2026_09']['assets']['total_assets'], 0)} miliar), "
        f"{len(periods)} bulan data sintetis ({mlabel(first)} – {mlabel(rep)}), seed {cfg['bank_profile']['reporting']['random_seed']}, direkonsiliasi ke neraca.",
        f"KRI dihitung dari data granular (obligor, holding sukuk, event, kasus, komplain), bukan dari nilai target; nilai KRI dibulatkan {kri.VALUE_DECIMALS} desimal sebelum skoring.",
        "Skoring presisi penuh; pembulatan 1 desimal ROUND_HALF_UP hanya untuk rating dan tampilan. Aturan eskalasi enterprise memakai presisi penuh.",
        "Stress testing: aturan transmisi makro per KRI diterapkan pada nilai KRI posisi reporting date, skoring ulang dengan fungsi yang sama, override dibawa ke semua skenario.",
        f"SLSI adalah indikator likuiditas sintetis dengan net outflow 30 hari {id_num(cfg['bank_profile']['slsi']['net_outflow_30d_anchor'], 0)} sebagai anchor posisi reporting date, bukan LCR regulatori.",
        "Hasil engine diuji dengan acceptance test otomatis (rekonsiliasi, regresi terhadap reference calculation, monotonic, reproducibility, scope guard).",
    ])
    story += [P("Limitation", "h2")] + bullets([
        "Tidak memodelkan PD/LGD/EAD, ECL/CKPN (PSAK 71), VaR, Monte Carlo, ekonometrika, machine learning, maupun LCR/NSFR regulatori.",
        "Stress statis tanpa reaksi neraca dan management action; KRI non-makro (antara lain konsentrasi, kepatuhan, hukum) dianggap tidak berubah.",
        "Loss rate kredit, koefisien transmisi, dan bobot adalah asumsi analitis project; kalibrasi terhadap data historis tidak dilakukan.",
        f"Trend membutuhkan {2 * scoring.TREND_WINDOW} bulan data sehingga {2 * scoring.TREND_WINDOW - 1} bulan pertama berlabel insufficient history; early warning berbasis proyeksi linear sederhana.",
        "Label rating terinspirasi skala peringkat risiko perbankan Indonesia, tetapi bukan replika metodologi penilaian tingkat kesehatan bank. "
        "Status rujukan regulasi pada Excel framework (sheet 09) diverifikasi per 17-Sep-2026 dan dapat berubah; LCR/NSFR regulatori BUS (POJK 20 Tahun 2025) tidak dimodelkan.",
    ])
    story += [P("Disclaimer", "h2"), P(DISCLAIMER, "body")]

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(16 * mm, 10 * mm, "PT Amanah Syariah Bank (fiktif) · ERM Executive Report · fictional bank, synthetic data")
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"Halaman {doc.page}")
        canvas.setStrokeColor(colors.HexColor(NAVY))
        canvas.setLineWidth(1.2)
        canvas.line(16 * mm, A4[1] - 12 * mm, A4[0] - 16 * mm, A4[1] - 12 * mm)
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title="ERM Executive Report — PT Amanah Syariah Bank (fiktif)",
                            author="ERM Framework (portfolio project)")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    FACTS_PATH.write_text(json.dumps(F.items, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"path": str(path), "facts": len(F.items)}
