"""Reference calculation — acuan regresi untuk engine yang dibangun Cowork.
Semua angka di spec harus bisa direproduksi oleh skrip ini."""
import math, pandas as pd
from decimal import Decimal, ROUND_HALF_UP

FLOOR_GAP = 1.5
def r1(x): return float(Decimal(str(round(x, 10))).quantize(Decimal("0.1"), ROUND_HALF_UP))

def kri_score(x, d, c):
    if d == "lower":
        for i, t in enumerate(c, 1):
            if x <= t: return i
        return 5
    for i, t in enumerate(c, 1):
        if x >= t: return i
    return 5

RATING = [(1.5,"Low","Green"),(2.5,"Low to Moderate","Green"),(3.5,"Moderate","Amber"),(4.5,"Moderate to High","Red"),(99,"High","Red")]
def rating(s):
    for t,l,col in RATING:
        if s < t: return l, col

ra = pd.read_csv("risk_appetite.csv"); w = pd.read_csv("risk_weights.csv").set_index("risk_type")["materiality_weight"]
mac = pd.read_csv("macro_scenarios.csv").set_index("variable")
ov = pd.read_csv("judgment_overrides.csv")

def stressed(kri, v, s):
    m = mac[s]; dg = 5.0 - m.gdp_growth; bps = m.policy_rate_shift
    if kri=="CR01": return v + 0.20*dg + 0.10*bps/100
    if kri=="CR02": return v + 1.5*(0.20*dg + 0.10*bps/100)
    if kri=="CR03": return v + 0.40*dg
    if kri=="MR01": return v*(1+m.idr_depreciation/100)
    if kri=="MR02": return v*(100+bps)/100
    if kri=="LQ01":
        la = 1500 + 2000 + 7000*(1-(0.05+abs(m.sukuk_mv_shock_fvoci)/100))
        no = 8750 + m.deposit_runoff_30d_additional/100*48000
        return la/no*100
    if kri=="LQ02": return 41000/(48000*(1-m.deposit_decline_3m/100))*100 if s!="baseline" else v
    if kri=="LQ03": return v/(1-m.deposit_decline_3m/100)
    if kri=="LQ04": return v + 0.25*m.deposit_decline_3m
    if kri=="LQ05": return max(v, m.deposit_decline_3m)
    if kri in("OR01","OR03","OR05"): return v*(1+m.operational_event_uplift/100)
    if kri=="OR02": return math.ceil(v*(1+m.operational_event_uplift/100))
    if kri=="ST01": return abs((15+v) - 2.0*dg - 15)
    if kri=="ST02": return v - 5.0*dg
    if kri=="ST03": return v + 2.0*dg
    if kri=="RP01": return v + m.complaint_volume_uplift
    if kri=="RR01": return v + 0.30*bps/100
    if kri=="RR02": return v + 0.20*bps/100
    if kri=="RR03": return v - 0.25*bps/100
    if kri=="IV02": return v + 0.8*dg
    if kri=="IV03": return max(v, abs(m.sukuk_mv_shock_fvoci))
    return v

out = {}
for s in ["baseline","adverse","severe"]:
    rows=[]
    for _,k in ra[ra.risk_type!="Capital Overlay"].iterrows():
        v = stressed(k.kri_id, k.value_target_2026_09, s)
        sc = kri_score(v, k.direction, [k.c1,k.c2,k.c3,k.c4])
        rows.append((k.risk_type,k.kri_id,round(v,2),sc,k.kri_weight))
    df = pd.DataFrame(rows,columns=["risk","kri","value","score","wt"])
    if s=="baseline":
        bad = df.merge(ra[["kri_id","target_score"]],left_on="kri",right_on="kri_id").query("score!=target_score")
        assert bad.empty, bad
    res={}
    for rk,g in df.groupby("risk"):
        wavg=(g.score*g.wt).sum(); model=max(wavg, g.score.max()-FLOOR_GAP)
        final=model
        o=ov[(ov.risk_type==rk)]
        if not o.empty: final=min(5.0,max(1.0,model+float(o.final_score.iloc[0]-o.model_score.iloc[0])))  # delta override dibawa ke semua skenario
        res[rk]=(r1(wavg),r1(model),r1(final))
    ent=sum(w[k]*v[2] for k,v in res.items())
    floor=max(v[2] for v in res.values())-1.5
    ent=max(ent,floor)
    if any(v[2]>=4.5 and w[k]>=0.10 for k,v in res.items()): ent=max(ent,3.5)
    breaches=(df.score>=4).sum(); limit=(df.score==5).sum()
    util=[]
    for _,k in ra[ra.risk_type!="Capital Overlay"].iterrows():
        v=df.set_index("kri").loc[k.kri_id,"value"]
        u = abs(v)/k.c4 if k.direction=="lower" else k.c4/v
        util.append((k.risk_type,min(u,1.5)*k.kri_weight))
    ud=pd.DataFrame(util,columns=["r","u"]).groupby("r").u.sum()
    rau=sum(ud[k]*w[k] for k in w.index)*100
    out[s]=(res,r1(ent),breaches,limit,rau,df)
    print(f"\n=== {s.upper()} ===")
    for rk in w.index: print(f"{rk:15s} wavg={res[rk][0]} model={res[rk][1]} final={res[rk][2]} {rating(res[rk][2])}")
    print("ENTERPRISE",r1(ent),rating(r1(ent)),"| KRI score>=4:",breaches,"| score 5:",limit,"| RAU %.0f%%"%rau)
    if s!="baseline": print(df[df.kri.isin(["CR01","LQ01","LQ02","MR02","OR01","ST02","RR03","IV03"])].to_string(index=False))

# capital overlay
for s in ["adverse","severe"]:
    m=mac[s]; dg=5-m.gdp_growth; bps=m.policy_rate_shift
    dnpf=0.20*dg+0.10*bps/100
    credit=dnpf/100*41000*0.45; inv=6000*abs(m.sukuk_mv_shock_fvoci)/100
    op=90*m.operational_event_uplift/100; ror=24000*bps/10000*0.5
    tot=credit+inv+op+ror; cap=7000-tot; atmr=40000*(1+m.rwa_uplift/100)
    print(f"\nCAP {s}: credit {credit:.0f} inv {inv:.0f} op {op:.0f} ror {ror:.0f} total {tot:.0f} -> modal {cap:.0f} ATMR {atmr:.0f} KPMM {cap/atmr*100:.1f}%")
