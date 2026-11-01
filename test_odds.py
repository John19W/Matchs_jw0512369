# Test OddsPapi n°4 : comparer les lignes de cartons de Betify avec celles vues sur le site.
# La clé est lue dans le secret GitHub ODDSPAPI_KEY. Elle n'est jamais écrite ni affichée.
import os, json, time, datetime, urllib.request, urllib.parse, urllib.error

KEY = os.environ.get("ODDSPAPI_KEY", "")
BASE = "https://api.oddspapi.io/v4"
TEAM = "sassuolo"
out = {"generated": datetime.datetime.utcnow().isoformat() + "Z"}

def get(path, **params):
    params["apiKey"] = KEY
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    time.sleep(1.2)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"error": "HTTP " + str(e.code), "body": e.read().decode("utf-8", "ignore")[:300]}
    except Exception as e:
        return 0, {"error": type(e).__name__}

def rows(d):
    if isinstance(d, list): return d
    if isinstance(d, dict):
        for k in ("data", "bookmakers", "markets", "fixtures"):
            if isinstance(d.get(k), list): return d[k]
    return []

# Catalogue : id -> (type, ligne, {id sortie: nom})
st, d = get("/markets")
cat = {}
for m in rows(d):
    if isinstance(m, dict) and not m.get("playerProp"):
        cat[str(m.get("marketId"))] = (m.get("marketType"), m.get("handicap"),
                                       {str(o.get("outcomeId")): o.get("outcomeName") for o in m.get("outcomes", []) if isinstance(o, dict)})

# Le match
today = datetime.datetime.utcnow().date()
st, d = get("/fixtures", sportId=10, **{"from": str(today), "to": str(today + datetime.timedelta(days=1))})
fx = [f for f in rows(d) if isinstance(f, dict) and TEAM in json.dumps(f).lower()]
out["fixtures_trouves"] = [[f.get("participant1Name"), f.get("participant2Name"), f.get("startTime"), f.get("tournamentName")] for f in fx]

out["odds"] = []
for f in fx[:1]:
    st, d = get("/odds", fixtureId=f.get("fixtureId"), bookmakers="betify")
    bo = (d.get("bookmakerOdds", {}) if isinstance(d, dict) else {}).get("betify", {})
    mk = (bo or {}).get("markets") or {}
    res = []
    for mid, md in mk.items():
        typ, hcp, names = cat.get(mid, (None, None, {}))
        if typ and ("booking" in typ or "shot" in typ):
            prices = []
            for oid, o in (md.get("outcomes") or {}).items():
                try: prices.append([names.get(oid, oid), o["players"]["0"]["price"]])
                except Exception: pass
            res.append([typ, hcp, prices])
    res.sort(key=lambda x: (str(x[0]), x[1] if x[1] is not None else 0))
    out["odds"].append({"match": [f.get("participant1Name"), f.get("participant2Name")], "status": st,
                        "error": d.get("error") if isinstance(d, dict) else None,
                        "nb_marches_betify": len(mk), "cartons_et_tirs": res})

os.makedirs("data", exist_ok=True)
with open("data/test_odds.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print("Test terminé. Résumé écrit dans data/test_odds.json")
