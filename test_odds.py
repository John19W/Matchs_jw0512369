# Test OddsPapi : quels books et quels marchés (tirs, cartons) sont disponibles ?
# La clé est lue dans le secret GitHub ODDSPAPI_KEY. Elle n'est jamais écrite ni affichée.
import os, json, time, datetime, urllib.request, urllib.parse, urllib.error

KEY = os.environ.get("ODDSPAPI_KEY", "")
BASE = "https://api.oddspapi.io/v4"
WANTED = ["bet365", "betclic", "unibet", "winamax", "betify", "celsius", "pecbet"]
KEYWORDS = ["shot", "card", "booking", "corner"]
out = {"generated": datetime.datetime.utcnow().isoformat() + "Z", "steps": {}}

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

def rows(data):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for k in ("data", "bookmakers", "markets", "fixtures"):
            if isinstance(data.get(k), list): return data[k]
    return []

# 1. Bookmakers : retrouver les slugs de nos books
st, data = get("/bookmakers")
books = rows(data)
found = {}
for w in WANTED:
    found[w] = [b.get("slug") for b in books if isinstance(b, dict) and w in json.dumps(b).lower()][:6]
out["steps"]["bookmakers"] = {"status": st, "total": len(books), "found": found}
slugs = sorted({s for v in found.values() for s in v if s})

# 2. Marchés : garder ceux qui parlent de tirs, cartons, corners
st, data = get("/markets")
mk = [m for m in rows(data) if any(k in json.dumps(m).lower() for k in KEYWORDS)]
out["steps"]["markets"] = {"status": st, "kept": mk[:150]}

# 3. Matchs de foot avec cotes (aujourd'hui et demain)
today = datetime.datetime.utcnow().date()
st, data = get("/fixtures", sportId=10, **{"from": str(today), "to": str(today + datetime.timedelta(days=1))})
fx = [f for f in rows(data) if isinstance(f, dict) and f.get("hasOdds")]
out["steps"]["fixtures"] = {"status": st, "with_odds": len(fx)}

# 4. Cotes de 3 matchs chez nos books
out["steps"]["odds"] = []
for f in fx[:3]:
    fid = f.get("fixtureId")
    st, d = get("/odds", fixtureId=fid, bookmakers=",".join(slugs[:25]))
    bo = d.get("bookmakerOdds", {}) if isinstance(d, dict) else {}
    out["steps"]["odds"].append({
        "fixtureId": fid,
        "match": [f.get("participant1Name"), f.get("participant2Name"), f.get("startTime")],
        "status": st,
        "markets_per_book": {s: sorted((b.get("markets") or {}).keys()) for s, b in bo.items()},
    })

os.makedirs("data", exist_ok=True)
with open("data/test_odds.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print("Test terminé. Résumé écrit dans data/test_odds.json")
