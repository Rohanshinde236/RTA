"""
Restore full live_state.json (all 10 regions) and update HK + TW
so every skill SLA is in the 90-95% HEALTHY range.
Also rebuilds cms_agents.json for HK and TW with matching healthy agent states.
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LS_PATH  = os.path.join(ROOT, "db", "live_state.json")
CMS_PATH = os.path.join(ROOT, "db", "cms_agents.json")

# ── helpers ──────────────────────────────────────────────────────────────────
def sk(sla, queue=0, ocw="00:00", avail=3, on_calls=6, on_aux=2,
       breached=False, reasons=None, lever=None, note="", root=""):
    band = ("EXCELLENT" if sla >= 95 else "HEALTHY" if sla >= 90
            else "WARNING" if sla >= 80 else "CRITICAL" if sla >= 70 else "SEVERE")
    hc = avail + on_calls + on_aux
    return {
        "sla": sla, "band": band, "queue": queue, "ocw": ocw,
        "avail": avail, "on_calls": on_calls, "on_aux": on_aux, "headcount": hc,
        "breached": breached, "breach_reasons": reasons or [],
        "lever_fired": lever, "last_move": [], "last_ask": [], "last_hold": [],
        "a2_note": note, "root_cause": root
    }

def region_block(name, display, poll_time, poll_no, skills_dict, breached_count, levers):
    return {
        "region_name": name, "region_display": display,
        "last_poll_time": poll_time, "poll_number": poll_no,
        "skills": skills_dict, "breached_count": breached_count,
        "levers_fired": levers
    }

def make_cms_agents(names, skill, on_aux=2):
    """Build a healthy CMS agent list: on_aux agents on short break, rest split ACD/AVAIL."""
    agents = []
    avail_start = on_aux + max(len(names) - on_aux, 0) // 2 + (1 if len(names) - on_aux > 0 else 0)
    for i, name in enumerate(names):
        if i < on_aux:
            agents.append({"name": name, "state": "AUX",
                           "aux_reason": "AUX 2", "aux_key": "AUX2", "aux_name": "Break",
                           "time_minutes": round(2.5 + i * 2.0, 1), "skill": skill})
        elif i < avail_start:
            agents.append({"name": name, "state": "ACD",
                           "aux_reason": "—", "aux_key": "", "aux_name": "—",
                           "time_minutes": round(5.0 + (i - on_aux) * 1.3, 1), "skill": skill})
        else:
            agents.append({"name": name, "state": "AVAIL",
                           "aux_reason": "—", "aux_key": "", "aux_name": "—",
                           "time_minutes": round(2.0 + (i - avail_start) * 0.5, 1), "skill": skill})
    return agents

# ── load existing (partial) live_state ───────────────────────────────────────
with open(LS_PATH, encoding="utf-8") as f:
    existing = json.load(f)

with open(CMS_PATH, encoding="utf-8") as f:
    cms = json.load(f)

# ── build full live_state ────────────────────────────────────────────────────
full = {}

# CN
full["cn"] = existing.get("cn") or region_block("CN","Client ProSupport CHN","17:30:38",17,{
    "TS_CN_ProDB":   sk(91.1, avail=4, on_calls=6, on_aux=2),
    "TS_CN_ProCNX":  sk(78.1, queue=3, ocw="00:49", avail=1, on_calls=7, on_aux=3, lever="Red"),
    "TS_CN_Elite":   sk(64.2, queue=7, ocw="01:36", avail=0, on_calls=7, on_aux=3,
                        breached=True, reasons=["BAND_CHANGED:WARNING->SEVERE","FALLING_3_POLLS:96.1->87.9->64.2"],
                        lever="Black", note="Proactive alert — agents overdue on break, no customer impact yet.",
                        root="AUX_HEAVY | STAFFING | VOLUME | OCW_BREACH | RECOVERING"),
    "TS_CN_LicKeys": sk(72.3, queue=4, ocw="00:55", avail=1, on_calls=6, on_aux=2, lever="Black"),
    "TS_CN_VICHW":   sk(88.4, avail=3, on_calls=5, on_aux=2, lever="Black"),
    "TS_CN_CritAcct":sk(99.0, avail=2, on_calls=4, on_aux=2),
}, 1, {"TS_CN_LicKeys_Amber":True,"TS_CN_VICHW_Amber":True,"TS_CN_VICHW_Red":True,
       "TS_CN_LicKeys_Black":True,"TS_CN_LicKeys_Red":True,"TS_CN_Elite_Amber":True,
       "TS_CN_VICHW_Black":True,"TS_CN_ProCNX_Red":True,"TS_CN_ProCNX_Amber":True,
       "TS_CN_Elite_Black":True,"TS_CN_Elite_Red":True})

# EMEA
full["emea"] = region_block("EMEA","Client ProSupport EMEA","17:31:36",19,{
    "TS_MLSCST_GER": sk(66.7, queue=6, ocw="01:21", avail=0, on_calls=4, on_aux=2,
                        breached=True, reasons=["BAND_CHANGED:WARNING->SEVERE","FALLING_3_POLLS:84.9->82.6->66.7"],
                        lever="Black", note="Proactive alert — agents overdue on break, no customer impact yet.",
                        root="AUX_HEAVY | STAFFING | VOLUME | OCW_BREACH | RECOVERING | STABLE"),
    "TS_MLSCST_SPA": sk(64.2, queue=7, ocw="01:38", avail=0, on_calls=5, on_aux=1,
                        breached=True, reasons=["BAND_CHANGED:CRITICAL->SEVERE","FALLING_3_POLLS:83.6->73.9->64.2"],
                        lever="Black"),
    "TS_MLSCST_FRA": sk(82.4, avail=1, on_calls=2, on_aux=2, lever="Black"),
    "TS_MLSCST_ITA": sk(84.9, avail=1, on_calls=2, on_aux=2, lever="Black"),
    "TS_MLSCST_NLD": sk(83.6, avail=1, on_calls=2, on_aux=1, lever="Black"),
    "TS_MLSCST_POL": sk(78.2, queue=2, ocw="00:29", avail=0, on_calls=4, on_aux=0,
                        breached=True, reasons=["BAND_CHANGED:WARNING->CRITICAL"],
                        lever="Black", note="Proactive alert — agents overdue on break, no customer impact yet.",
                        root="AUX_HEAVY | STAFFING | VOLUME | OCW_BREACH | RECOVERING"),
}, 3, {"TS_MLSCST_GER_Amber":True,"TS_MLSCST_SPA_Amber":True,"TS_MLSCST_FRA_Amber":True,
       "TS_MLSCST_ITA_Red":True,"TS_MLSCST_ITA_Amber":True,"TS_MLSCST_NLD_Black":True,
       "TS_MLSCST_NLD_Amber":True,"TS_MLSCST_NLD_Red":True,"TS_MLSCST_POL_Black":True,
       "TS_MLSCST_POL_Amber":True,"TS_MLSCST_POL_Red":True,"TS_MLSCST_GER_Red":True,
       "TS_MLSCST_SPA_Black":True,"TS_MLSCST_SPA_Red":True,"TS_MLSCST_FRA_Red":True,
       "TS_MLSCST_ITA_Black":True,"TS_MLSCST_FRA_Black":True,"TS_MLSCST_GER_Black":True})

# AU
full["au"] = region_block("AU","Client ProSupport AUS","17:30:37",16,{
    "TS_AU_ProDB":   sk(91.6, avail=3, on_calls=5, on_aux=2),
    "TS_AU_ProCNX":  sk(83.0, queue=2, ocw="00:30", avail=1, on_calls=6, on_aux=2, lever="Amber"),
    "TS_AU_Elite":   sk(66.5, queue=6, ocw="01:22", avail=0, on_calls=6, on_aux=2,
                        breached=True, reasons=["BAND_CHANGED:HEALTHY->SEVERE","FALLING_3_POLLS:95.1->93.8->66.5"],
                        lever="Black"),
    "TS_AU_LicKeys": sk(64.8, queue=7, ocw="01:35", avail=0, on_calls=6, on_aux=2,
                        breached=True, reasons=["BAND_CHANGED:CRITICAL->SEVERE","FALLING_3_POLLS:84.6->73.7->64.8"],
                        lever="Black"),
    "TS_AU_VICHW":   sk(87.4, avail=2, on_calls=3, on_aux=2, lever="Black"),
    "TS_AU_CritAcct":sk(99.0, avail=2, on_calls=3, on_aux=2),
}, 2, {"TS_AU_LicKeys_Amber":True,"TS_AU_VICHW_Red":True,"TS_AU_VICHW_Amber":True,
       "TS_AU_LicKeys_Red":True,"TS_AU_VICHW_Black":True,"TS_AU_ProCNX_Amber":True,
       "TS_AU_Elite_Black":True,"TS_AU_Elite_Amber":True,"TS_AU_Elite_Red":True,
       "TS_AU_LicKeys_Black":True})

# ── HK — ALL 6 SKILLS IN 90-95% HEALTHY BAND ────────────────────────────────
hk_skills_data = {
    "TS_HK_ProDB":   (91.8, dict(avail=4, on_calls=7, on_aux=2)),
    "TS_HK_ProCNX":  (92.4, dict(avail=3, on_calls=7, on_aux=2)),
    "TS_HK_Elite":   (90.6, dict(avail=3, on_calls=6, on_aux=2)),
    "TS_HK_LicKeys": (91.5, dict(avail=3, on_calls=5, on_aux=2)),
    "TS_HK_VICHW":   (93.5, dict(avail=4, on_calls=6, on_aux=2)),
    "TS_HK_CritAcct":(90.9, dict(avail=3, on_calls=6, on_aux=2)),
}
full["hk"] = region_block("HK","Client ProSupport HKG","17:31:34",16,
    {s: sk(v, **kw) for s,(v,kw) in hk_skills_data.items()}, 0, {})

# RTA
full["rta"] = existing.get("rta") or region_block("RTA","Client ProSupport IND","17:31:08",16,{
    "TS_CSTCE":      sk(88.6, avail=4, on_calls=10, on_aux=2, lever="Amber"),
    "TS_CSTElite":   sk(75.4, queue=4, ocw="01:02", avail=1, on_calls=10, on_aux=4,
                        breached=True, reasons=["BAND_CHANGED:HEALTHY->CRITICAL"],
                        lever="Red", note="Proactive alert — agents overdue on break, no customer impact yet.",
                        root="AUX_HEAVY | STAFFING | VOLUME | OCW_BREACH | RECOVERING"),
    "TS_LicKeys":    sk(62.5, queue=8, ocw="01:46", avail=0, on_calls=9, on_aux=4,
                        breached=True, reasons=["BAND_CHANGED:CRITICAL->SEVERE","FALLING_3_POLLS:84.6->78.2->62.5","QUEUE_DOUBLED:2->8"],
                        lever="Black"),
    "TS_VICHW":      sk(81.5, queue=2, ocw="00:27", avail=3, on_calls=8, on_aux=1, lever="Black"),
    "TS_CSTVCE":     sk(92.1, avail=4, on_calls=7, on_aux=3),
    "TS_CSTCritAcct":sk(99.0, avail=4, on_calls=7, on_aux=3),
}, 2, {"TS_LicKeys_Amber":True,"TS_VICHW_Amber":True,"TS_LicKeys_Red":True,
       "TS_VICHW_Black":True,"TS_VICHW_Red":True,"TS_LicKeys_Black":True,
       "TS_CSTCE_Amber":True,"TS_CSTElite_Red":True,"TS_CSTElite_Amber":True})

# MY
full["my"] = region_block("MY","Client ProSupport MYS","17:31:44",14,{
    "TS_MY_ProDB":   sk(71.8, queue=5, ocw="01:13", avail=0, on_calls=8, on_aux=4,
                        breached=True, reasons=["BAND_CHANGED:HEALTHY->CRITICAL"],
                        lever="Red", note="Proactive alert — agents overdue on break, no customer impact yet.",
                        root="AUX_HEAVY | STAFFING | VOLUME | OCW_BREACH | RECOVERING"),
    "TS_MY_ProCNX":  sk(61.2, queue=8, ocw="01:54", avail=0, on_calls=8, on_aux=3,
                        breached=True, reasons=["BAND_CHANGED:CRITICAL->SEVERE","QUEUE_DOUBLED:3->8"],
                        lever="Black"),
    "TS_MY_Elite":   sk(88.7, avail=3, on_calls=6, on_aux=1, lever="Black"),
    "TS_MY_LicKeys": sk(90.7, avail=3, on_calls=5, on_aux=2),
    "TS_MY_VICHW":   sk(93.8, avail=3, on_calls=6, on_aux=2),
    "TS_MY_CritAcct":sk(83.5, queue=1, ocw="00:20", avail=2, on_calls=6, on_aux=1, lever="Amber"),
}, 2, {"TS_MY_ProCNX_Amber":True,"TS_MY_Elite_Black":True,"TS_MY_Elite_Amber":True,
       "TS_MY_Elite_Red":True,"TS_MY_ProCNX_Black":True,"TS_MY_ProCNX_Red":True,
       "TS_MY_CritAcct_Amber":True,"TS_MY_ProDB_Red":True,"TS_MY_ProDB_Amber":True})

# KR
full["kr"] = region_block("KR","Client ProSupport KOR","17:30:37",14,{
    "TS_KR_ProDB":   sk(93.2, avail=4, on_calls=7, on_aux=2),
    "TS_KR_ProCNX":  sk(77.5, queue=4, ocw="00:56", avail=1, on_calls=8, on_aux=3, lever="Red"),
    "TS_KR_Elite":   sk(63.3, queue=7, ocw="01:41", avail=0, on_calls=8, on_aux=3,
                        breached=True, reasons=["BAND_CHANGED:HEALTHY->SEVERE"], lever="Black"),
    "TS_KR_LicKeys": sk(80.1, queue=3, ocw="00:41", avail=2, on_calls=7, on_aux=1, lever="Amber"),
    "TS_KR_VICHW":   sk(90.8, avail=3, on_calls=6, on_aux=2),
    "TS_KR_CritAcct":sk(94.3, avail=3, on_calls=5, on_aux=2),
}, 1, {"TS_KR_LicKeys_Amber":True,"TS_KR_ProCNX_Red":True,"TS_KR_ProCNX_Amber":True,
       "TS_KR_Elite_Black":True,"TS_KR_Elite_Amber":True,"TS_KR_Elite_Red":True})

# TH
full["th"] = region_block("TH","Client ProSupport THA","17:30:46",14,{
    "TS_TH_ProDB":   sk(84.7, queue=1, ocw="00:24", avail=2, on_calls=7, on_aux=2, lever="Amber"),
    "TS_TH_ProCNX":  sk(70.7, queue=5, ocw="01:17", avail=0, on_calls=7, on_aux=3,
                        breached=True, reasons=["BAND_CHANGED:HEALTHY->CRITICAL","FALLING_3_POLLS:91.9->90.1->70.7"],
                        lever="Red"),
    "TS_TH_Elite":   sk(62.4, queue=8, ocw="01:49", avail=0, on_calls=6, on_aux=3,
                        breached=True, reasons=["BAND_CHANGED:CRITICAL->SEVERE","FALLING_3_POLLS:89.7->77.0->62.4","QUEUE_DOUBLED:3->8"],
                        lever="Black"),
    "TS_TH_LicKeys": sk(87.1, avail=2, on_calls=4, on_aux=3, lever="Black"),
    "TS_TH_VICHW":   sk(93.9, avail=3, on_calls=5, on_aux=2),
    "TS_TH_CritAcct":sk(87.7, avail=2, on_calls=4, on_aux=2, lever="Black"),
}, 2, {"TS_TH_LicKeys_Amber":True,"TS_TH_CritAcct_Red":True,"TS_TH_CritAcct_Amber":True,
       "TS_TH_CritAcct_Black":True,"TS_TH_Elite_Red":True,"TS_TH_Elite_Amber":True,
       "TS_TH_LicKeys_Black":True,"TS_TH_LicKeys_Red":True,"TS_TH_Elite_Black":True,
       "TS_TH_ProDB_Amber":True,"TS_TH_ProCNX_Red":True,"TS_TH_ProCNX_Amber":True})

# ── TW — ALL 6 SKILLS IN 90-95% HEALTHY BAND ────────────────────────────────
tw_skills_data = {
    "TS_TW_ProDB":   (91.3, dict(avail=3, on_calls=6, on_aux=2)),
    "TS_TW_ProCNX":  (92.8, dict(avail=3, on_calls=5, on_aux=2)),
    "TS_TW_Elite":   (90.4, dict(avail=2, on_calls=5, on_aux=2)),
    "TS_TW_LicKeys": (94.2, dict(avail=3, on_calls=5, on_aux=2)),
    "TS_TW_VICHW":   (90.9, dict(avail=3, on_calls=4, on_aux=2)),
    "TS_TW_CritAcct":(91.7, dict(avail=2, on_calls=4, on_aux=2)),
}
full["tw"] = region_block("TW","Client ProSupport TWN","17:30:56",13,
    {s: sk(v, **kw) for s,(v,kw) in tw_skills_data.items()}, 0, {})

# BR
full["br"] = existing.get("br") or region_block("BR","Client ProSupport BRA","17:31:24",13,{
    "TS_BR_ProDB":   sk(65.0, queue=7, ocw="01:31", avail=0, on_calls=8, on_aux=4,
                        breached=True, reasons=["BAND_CHANGED:HEALTHY->SEVERE"], lever="Black"),
    "TS_BR_ProCNX":  sk(73.5, queue=5, ocw="01:09", avail=1, on_calls=8, on_aux=2,
                        breached=True, reasons=["BAND_CHANGED:HEALTHY->CRITICAL"],
                        lever="Red", note="Proactive alert — agents overdue on break, no customer impact yet.",
                        root="AUX_HEAVY | STAFFING | VOLUME | OCW_BREACH | RECOVERING"),
    "TS_BR_Elite":   sk(91.1, avail=3, on_calls=5, on_aux=2),
    "TS_BR_LicKeys": sk(91.6, avail=3, on_calls=4, on_aux=2),
    "TS_BR_VICHW":   sk(89.3, avail=3, on_calls=6, on_aux=2, lever="Black"),
    "TS_BR_CritAcct":sk(78.4, queue=3, ocw="00:42", avail=1, on_calls=7, on_aux=2, lever="Black"),
}, 2, {"TS_BR_CritAcct_Black":True,"TS_BR_CritAcct_Amber":True,"TS_BR_CritAcct_Red":True,
       "TS_BR_VICHW_Amber":True,"TS_BR_VICHW_Black":True,"TS_BR_VICHW_Red":True,
       "TS_BR_ProDB_Black":True,"TS_BR_ProDB_Amber":True,"TS_BR_ProDB_Red":True,
       "TS_BR_ProCNX_Red":True,"TS_BR_ProCNX_Amber":True})

# ── Write live_state.json ─────────────────────────────────────────────────────
with open(LS_PATH, "w", encoding="utf-8") as f:
    json.dump(full, f, indent=2, ensure_ascii=False)
print("live_state.json written. Regions:", list(full.keys()))

# ── Update cms_agents.json for HK and TW ─────────────────────────────────────
hk_names = ["Chan_KW","Wong_HM","Lee_PK","Lau_SY","Cheung_WL","Ng_TF",
            "Ho_CK","Yip_MH","Tam_YS","Chow_BW","Tsang_HK","Fong_RL","Kwok_SC"]
for skill, (sla, kw) in hk_skills_data.items():
    n = kw["avail"] + kw["on_calls"] + kw["on_aux"]
    cms["hk"][skill] = make_cms_agents(hk_names[:n], skill, on_aux=kw["on_aux"])

tw_names = ["Chen_YT","Lin_HJ","Wang_SY","Liu_CW","Huang_MX","Wu_BL",
            "Cheng_FH","Chou_KM","Tsai_YC","Hsu_LW","Kuo_ZR","Yang_TN"]
for skill, (sla, kw) in tw_skills_data.items():
    n = kw["avail"] + kw["on_calls"] + kw["on_aux"]
    cms["tw"][skill] = make_cms_agents(tw_names[:n], skill, on_aux=kw["on_aux"])

with open(CMS_PATH, "w", encoding="utf-8") as f:
    json.dump(cms, f, indent=2, ensure_ascii=False)
print("cms_agents.json updated for HK and TW.")

# ── Verify ────────────────────────────────────────────────────────────────────
print("\n=== HK skills ===")
for s, d in full["hk"]["skills"].items():
    print(f"  {s}: {d['sla']}%  {d['band']}  avail={d['avail']}  on_aux={d['on_aux']}")

print("\n=== TW skills ===")
for s, d in full["tw"]["skills"].items():
    print(f"  {s}: {d['sla']}%  {d['band']}  avail={d['avail']}  on_aux={d['on_aux']}")

print(f"\nHK breached_count: {full['hk']['breached_count']}")
print(f"TW breached_count: {full['tw']['breached_count']}")
print("\nCMS HK agent states:")
for s, agents in cms["hk"].items():
    states = {}
    for a in agents: states[a["state"]] = states.get(a["state"], 0) + 1
    print(f"  {s}: {states}")
print("CMS TW agent states:")
for s, agents in cms["tw"].items():
    states = {}
    for a in agents: states[a["state"]] = states.get(a["state"], 0) + 1
    print(f"  {s}: {states}")
