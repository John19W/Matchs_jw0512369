# Test OddsPapi n°2 : lignes de tirs / cartons / corners sur de vrais matchs, chez nos books.
# La clé est lue dans le secret GitHub ODDSPAPI_KEY. Elle n'est jamais écrite ni affichée.
import os, json, time, datetime, urllib.request, urllib.parse, urllib.error

KEY = os.environ.get("ODDSPAPI_KEY", "")
BASE = "https://api.oddspapi.io/v4"
LEAGUES = ["premier league", "serie a", "la liga", "laliga", "bundesliga", "ligue 1",
           "champions league", "europa league", "conference league", "eredivisie", "primeira"]
KEYS = ("shot", "booking", "card", "corner")
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

# Books : on cherche les versions FRANCE (.fr) de nos books, sinon la version de base
st, d = get("/bookmakers")
allslugs = [b.get("slug") for b in rows(d) if isinstance(b, dict) and b.get("slug")]
NAMES = ["bet365", "unibet", "winamax", "betify", "betclic", "celsius", "pecbet"]
found = {n: sorted(x for x in allslugs if n in x.lower()) for n in NAMES}
out["slugs_found"] = found
BOOKS = []
for n in ["bet365", "unibet", "winamax", "betify"]:
    fr = [x for x in found[n] if x.lower().endswith(".fr") or x.lower() in (n + "-fr", n + "_fr")]
    base = [x for x in found[n] if x.lower() == n]
    BOOKS += fr + base
BOOKS = list(dict.fromkeys(BOOKS))
out["books_used"] = BOOKS

# Catalogue des marchés utiles : id -> (type, nom, ligne)
st, d = get("/markets")
info = {}
allinfo = {}
for m in rows(d):
    if not isinstance(m, dict): continue
    allinfo[str(m.get("marketId"))] = (m.get("marketType"), m.get("marketName"), m.get("handicap"), bool(m.get("playerProp")))
    t = str(m.get("marketType", "")).lower()
    if not m.get("playerProp") and any(k in t for k in KEYS):
        info[str(m.get("marketId"))] = (m.get("marketType"), m.get("marketName"), m.get("handicap"))
out["markets_catalog"] = {"status": st, "kept": len(info),
                          "types": sorted({v[0] for v in info.values() if v[0]})}

# Matchs des grands championnats (aujourd'hui + demain)
today = datetime.datetime.utcnow().date()
st, d = get("/fixtures", sportId=10, **{"from": str(today), "to": str(today + datetime.timedelta(days=2))})
fx = [f for f in rows(d) if isinstance(f, dict) and f.get("hasOdds")]
TOP = {"england", "italy", "spain", "germany", "france"}
def is_top(f):
    cat = str(f.get("categoryName", "")).lower()
    tn = str(f.get("tournamentName", "")).lower()
    if any(x in tn for x in ("women", "u21", "u19", "u23", "reserve", "youth", "cup", "2.", "ii")): return False
    return cat in TOP and any(x in tn for x in ("premier league", "serie a", "laliga", "la liga", "bundesliga", "ligue 1"))
big = [f for f in fx if is_top(f)]
out["fixtures"] = {"status": st, "with_odds": len(fx), "big_leagues": len(big),
                   "big_list": [[f.get("categoryName"), f.get("tournamentName"), f.get("participant1Name"), f.get("participant2Name")] for f in big[:12]]}
pick = big[:6]

# Cotes de ces matchs chez nos 4 books
out["odds"] = []
for f in pick:
    fid = f.get("fixtureId")
    st, d = get("/odds", fixtureId=fid, bookmakers=",".join(BOOKS))
    bo = d.get("bookmakerOdds", {}) if isinstance(d, dict) else {}
    res = {}
    for slug, b in bo.items():
        mk = (b or {}).get("markets") or {}
        lines = {}
        for mid, mdata in mk.items():
            if mid in info:
                typ, name, hcp = info[mid]
                lines.setdefault(typ, []).append(hcp)
        types = {}
        for mid in mk:
            a = allinfo.get(mid)
            if a and not a[3]: types[a[0]] = types.get(a[0], 0) + 1
        res[slug] = {"nb_marches_total": len(mk), "types_presents": types, "lignes": {k: sorted(set(v), key=lambda x: (x is None, x)) for k, v in lines.items()}}
    out["odds"].append({"match": [f.get("participant1Name"), f.get("participant2Name"), f.get("startTime")],
                        "tournament": f.get("tournamentName"), "status": st, "error": d.get("error") if isinstance(d, dict) else None, "books": res})

os.makedirs("data", exist_ok=True)
with open("data/test_odds.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print("Test terminé. Résumé écrit dans data/test_odds.json")
