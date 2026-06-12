import json

with open("db/live_state.json") as f:
    ls = json.load(f)
with open("db/cms_agents.json") as f:
    cms = json.load(f)

def band(sla):
    if sla >= 95: return "EXCELLENT"
    if sla >= 90: return "HEALTHY"
    if sla >= 80: return "WARNING"
    if sla >= 70: return "CRITICAL"
    return "SEVERE"

# All skills set to 90-95% range — varied values for realism
hk_sla = {
    "TS_HK_ProDB":    92.1,
    "TS_HK_ProCNX":   91.4,
    "TS_HK_Elite":    93.8,
    "TS_HK_LicKeys":  90.6,
    "TS_HK_VICHW":    94.2,
    "TS_HK_CritAcct": 91.9,
}
tw_sla = {
    "TS_TW_ProDB":    90.8,
    "TS_TW_ProCNX":   92.5,
    "TS_TW_Elite":    91.3,
    "TS_TW_LicKeys":  94.7,
    "TS_TW_VICHW":    90.3,
    "TS_TW_CritAcct": 93.1,
}

# headcount, on_aux, avail  (on_calls = headcount - on_aux - avail)
hk_cfg = {
    "TS_HK_ProDB":    (11, 2, 4),
    "TS_HK_ProCNX":   (10, 2, 3),
    "TS_HK_Elite":    (9,  2, 3),
    "TS_HK_LicKeys":  (10, 2, 3),
    "TS_HK_VICHW":    (9,  1, 4),
    "TS_HK_CritAcct": (8,  2, 3),
}
tw_cfg = {
    "TS_TW_ProDB":    (11, 2, 4),
    "TS_TW_ProCNX":   (10, 2, 3),
    "TS_TW_Elite":    (9,  2, 3),
    "TS_TW_LicKeys":  (10, 2, 3),
    "TS_TW_VICHW":    (9,  1, 4),
    "TS_TW_CritAcct": (8,  2, 3),
}

hk_names = ["Chan_MW","Lee_HB","Wong_SY","Lam_KT","Ng_YF",
             "Cheung_BL","Ho_RC","Yuen_FK","Tsang_PX","Ip_WL","Mok_CJ"]
tw_names = ["Chen_YT","Lin_HJ","Wang_SY","Liu_CW","Huang_MX",
             "Wu_BL","Cheng_FH","Chou_KM","Tsai_YC","Hsu_LW","Kuo_ZR"]

def make_state(skill, sla, hc, aux, avail):
    return {
        "sla": sla,
        "band": band(sla),
        "queue": 0,
        "ocw": "00:00",
        "avail": avail,
        "on_calls": hc - aux - avail,
        "on_aux": aux,
        "headcount": hc,
        "breached": False,
        "breach_reasons": [],
        "lever_fired": None,
        "last_move": [],
        "last_ask": [],
        "last_hold": [],
        "a2_note": "",
        "root_cause": "",
    }

def make_cms(skill, names, aux, calls, avail):
    agents = []
    pool = names[:aux + calls + avail]
    for i, name in enumerate(pool):
        if i < aux:
            agents.append({"name": name, "state": "AUX", "aux_reason": "AUX 2",
                            "aux_key": "AUX2", "aux_name": "Break",
                            "time_minutes": round(3.5 + i * 2.5, 1), "skill": skill})
        elif i < aux + calls:
            agents.append({"name": name, "state": "ACD", "aux_reason": "-",
                            "aux_key": "", "aux_name": "-",
                            "time_minutes": round(5.0 + (i - aux) * 1.8, 1), "skill": skill})
        else:
            agents.append({"name": name, "state": "AVAIL", "aux_reason": "-",
                            "aux_key": "", "aux_name": "-",
                            "time_minutes": round(1.2 + (i - aux - calls) * 0.7, 1), "skill": skill})
    return agents

# Apply HK
for skill, sla in hk_sla.items():
    hc, aux, avail = hk_cfg[skill]
    ls["hk"]["skills"][skill] = make_state(skill, sla, hc, aux, avail)
    cms["hk"][skill] = make_cms(skill, hk_names, aux, hc - aux - avail, avail)

ls["hk"]["breached_count"] = 0
ls["hk"]["levers_fired"] = {}

# Apply TW
for skill, sla in tw_sla.items():
    hc, aux, avail = tw_cfg[skill]
    ls["tw"]["skills"][skill] = make_state(skill, sla, hc, aux, avail)
    cms["tw"][skill] = make_cms(skill, tw_names, aux, hc - aux - avail, avail)

ls["tw"]["breached_count"] = 0
ls["tw"]["levers_fired"] = {}

with open("db/live_state.json", "w") as f:
    json.dump(ls, f, indent=2, ensure_ascii=False)
with open("db/cms_agents.json", "w") as f:
    json.dump(cms, f, indent=2, ensure_ascii=False)

print("=== HK ===")
for s, d in ls["hk"]["skills"].items():
    print(f"  {s}: {d['sla']}%  {d['band']}  queue={d['queue']}  avail={d['avail']}  on_aux={d['on_aux']}  hc={d['headcount']}")
print()
print("=== TW ===")
for s, d in ls["tw"]["skills"].items():
    print(f"  {s}: {d['sla']}%  {d['band']}  queue={d['queue']}  avail={d['avail']}  on_aux={d['on_aux']}  hc={d['headcount']}")
