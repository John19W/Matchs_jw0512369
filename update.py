#!/usr/bin/env python3
"""Mise à jour automatique, lancée chaque jour par GitHub Actions :
 - matchs à venir (API football-data.org, clé gratuite) -> fixtures.json
 - résultats des 5 championnats (football-data.co.uk)   -> data/*.csv
 - saisons passées (confrontations directes)            -> data/hist.json
"""
import difflib, json, os, re, sys, unicodedata, urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
JOURS = 7     # jours de matchs à venir
ARRIERE = 14  # jours passés gardés (matchs terminés, pour comparer prédictions et résultats)
LIGUES = {"PL": "Premier League", "FL1": "Ligue 1", "PD": "La Liga", "SA": "Serie A", "BL1": "Bundesliga"}
CSV = ["E0", "F1", "SP1", "I1", "D1"]

# Noms d'équipes utilisés par l'outil (ceux de football-data.co.uk), par championnat
EQUIPES = {
    "Ligue 1": ["Angers", "Auxerre", "Brest", "Le Havre", "Le Mans", "Lens", "Lille", "Lorient", "Lyon", "Marseille",
                "Monaco", "Nice", "Paris FC", "Paris SG", "Rennes", "Strasbourg", "Toulouse", "Troyes"],
    "Premier League": ["Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Chelsea", "Coventry",
                       "Crystal Palace", "Everton", "Fulham", "Hull", "Ipswich", "Leeds", "Liverpool", "Man City",
                       "Man United", "Newcastle", "Nott'm Forest", "Sunderland", "Tottenham"],
    "La Liga": ["Alaves", "Ath Bilbao", "Ath Madrid", "Barcelona", "Betis", "Celta", "Elche", "Espanol", "Getafe",
                "La Coruna", "Levante", "Malaga", "Osasuna", "Real Madrid", "Santander", "Sevilla", "Sociedad",
                "Valencia", "Vallecano", "Villarreal"],
    "Serie A": ["Atalanta", "Bologna", "Cagliari", "Como", "Fiorentina", "Frosinone", "Genoa", "Inter", "Juventus",
                "Lazio", "Lecce", "Milan", "Monza", "Napoli", "Parma", "Roma", "Sassuolo", "Torino", "Udinese", "Venezia"],
    "Bundesliga": ["Augsburg", "Bayern Munich", "Dortmund", "Ein Frankfurt", "Elversberg", "FC Koln", "Freiburg",
                   "Hamburg", "Hoffenheim", "Leverkusen", "M'gladbach", "Mainz", "Paderborn", "RB Leipzig",
                   "Schalke 04", "Stuttgart", "Union Berlin", "Werder Bremen"],
}
# Noms de l'API qui ne ressemblent pas assez à ceux de l'outil (clé = nom simplifié)
ALIAS = {
    "paris saint germain": "Paris SG", "manchester city": "Man City", "manchester united": "Man United",
    "tottenham hotspur": "Tottenham", "newcastle united": "Newcastle", "nottingham forest": "Nott'm Forest",
    "brighton hove albion": "Brighton", "leeds united": "Leeds", "hull city": "Hull", "ipswich town": "Ipswich",
    "coventry city": "Coventry", "olympique lyonnais": "Lyon", "olympique de marseille": "Marseille",
    "as monaco": "Monaco", "ogc nice": "Nice", "rc lens": "Lens", "losc lille": "Lille", "stade rennais": "Rennes",
    "stade brestois 29": "Brest", "rc strasbourg alsace": "Strasbourg", "club atletico de madrid": "Ath Madrid",
    "atletico madrid": "Ath Madrid", "athletic club": "Ath Bilbao", "real betis balompie": "Betis",
    "celta de vigo": "Celta", "rcd espanyol de barcelona": "Espanol", "real sociedad de futbol": "Sociedad",
    "rayo vallecano de madrid": "Vallecano", "deportivo alaves": "Alaves", "deportivo la coruna": "La Coruna",
    "racing de santander": "Santander", "fc internazionale milano": "Inter", "internazionale": "Inter",
    "ac milan": "Milan", "as roma": "Roma", "ssc napoli": "Napoli", "us sassuolo calcio": "Sassuolo",
    "como 1907": "Como", "fc bayern munchen": "Bayern Munich", "borussia dortmund": "Dortmund",
    "bayer 04 leverkusen": "Leverkusen", "borussia monchengladbach": "M'gladbach",
    "eintracht frankfurt": "Ein Frankfurt", "1 fc koln": "FC Koln", "vfb stuttgart": "Stuttgart",
    "hamburger sv": "Hamburg", "sv werder bremen": "Werder Bremen", "1 fc union berlin": "Union Berlin",
    "fc schalke 04": "Schalke 04", "sv elversberg": "Elversberg", "sc paderborn 07": "Paderborn",
    "tsg 1899 hoffenheim": "Hoffenheim", "1 fsv mainz 05": "Mainz", "sc freiburg": "Freiburg",
}
TOUS = {n: lg for lg, noms in EQUIPES.items() for n in noms}


def simple(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]", " ", s).split())


def sans_fc(s):
    return " ".join(w for w in simple(s).split() if w not in {"fc", "cf", "afc", "sc", "ac", "as", "ssc", "us", "cd", "ud", "rcd", "club", "calcio"})


INDEX = {sans_fc(n): n for n in TOUS}
ALIAS2 = {sans_fc(k): v for k, v in ALIAS.items()}


def nom_outil(equipe):
    """Nom de l'API -> nom de l'outil, ou None si l'équipe n'est pas dans les 5 championnats."""
    for cand in (equipe.get("name", ""), equipe.get("shortName", "")):
        if sans_fc(cand) in ALIAS2:
            return ALIAS2[sans_fc(cand)]
    for cand in (equipe.get("shortName", ""), equipe.get("name", "")):
        k = sans_fc(cand)
        if k in INDEX:
            return INDEX[k]
    return None


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "matchs-du-jour"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def matchs(token, debut=None):
    debut = debut or date.today()
    fin = debut + timedelta(days=JOURS)
    cur, ms = debut - timedelta(days=ARRIERE), []
    while cur <= fin:  # l'API gratuite limite chaque requête à ~10 jours : on découpe
        to = min(cur + timedelta(days=9), fin)
        url = ("https://api.football-data.org/v4/matches?dateFrom=%s&dateTo=%s&competitions=PL,FL1,PD,SA,BL1,CL"
               % (cur, to))
        ms += json.loads(get(url, {"X-Auth-Token": token})).get("matches", [])
        cur = to + timedelta(days=1)
    data = {"matches": ms}
    items, inconnus = [], set()
    for m in data.get("matches", []):
        st = m.get("status")
        if st not in ("SCHEDULED", "TIMED", "IN_PLAY", "PAUSED", "FINISHED"):
            continue
        h, a = m["homeTeam"], m["awayTeam"]
        nh, na = nom_outil(h), nom_outil(a)
        coupe = m["competition"]["code"] == "CL"
        if coupe:
            L = TOUS.get(nh) or TOUS.get(na)
            if not L:
                continue  # aucune des deux équipes n'a d'historique dans l'outil
        else:
            L = LIGUES.get(m["competition"]["code"])
            for eq, n in ((h, nh), (a, na)):
                if n is None:
                    inconnus.add(eq.get("name"))
        dt = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).astimezone(TZ)
        it = {"d": dt.strftime("%Y-%m-%d"), "t": dt.strftime("%H:%M"), "L": L,
              "h": nh or h.get("shortName") or h["name"], "a": na or a.get("shortName") or a["name"]}
        if coupe:
            it["C"] = "Ligue des champions"
        if st in ("IN_PLAY", "PAUSED"):
            it["live"] = True
        if st in ("IN_PLAY", "PAUSED", "FINISHED"):
            ft = (m.get("score") or {}).get("fullTime") or {}
            if ft.get("home") is not None and ft.get("away") is not None:
                it["s"] = [ft["home"], ft["away"]]
            if st == "FINISHED":
                it["f"] = 1
        items.append(it)
    items.sort(key=lambda x: (x["d"], x["t"]))
    if inconnus:
        print("Équipes non reconnues (ajouter dans ALIAS si besoin) :", sorted(inconnus))
    return items


def csv_resultats():
    aujourdhui = date.today()
    y = aujourdhui.year if aujourdhui.month >= 7 else aujourdhui.year - 1
    saison = "%02d%02d" % (y % 100, (y + 1) % 100)
    os.makedirs("data", exist_ok=True)
    for c in CSV:
        try:
            contenu = get("https://www.football-data.co.uk/mmz4281/%s/%s.csv" % (saison, c))
            if b"HomeTeam" in contenu[:2000]:
                open("data/%s.csv" % c, "wb").write(contenu)
        except Exception as e:  # on garde l'ancien fichier si le site est indisponible
            print("CSV", c, "non mis à jour :", e)


SAISONS_ARRIERE = 15  # nombre de saisons passées gardées pour l'historique des confrontations


def historique():
    """Saisons passées (football-data.co.uk) -> data/hist.json, pour les confrontations directes.
    Une saison terminée ne change plus : on ne télécharge que celles qui manquent."""
    import csv, io
    aujourdhui = date.today()
    y = aujourdhui.year if aujourdhui.month >= 7 else aujourdhui.year - 1  # saison en cours (déjà dans data/*.csv)
    voulues = ["%02d%02d" % ((a % 100), ((a + 1) % 100)) for a in range(y - SAISONS_ARRIERE, y)]
    fichier = "data/hist.json"
    try:
        hist = json.load(open(fichier, encoding="utf-8"))
    except Exception:
        hist = {"seasons": [], "rows": []}
    deja = set(hist.get("seasons", []))
    rows = hist.get("rows", [])
    nouveau = False
    for saison in voulues:
        for c in CSV:
            cle = saison + "/" + c
            if cle in deja:
                continue
            try:
                brut = get("https://www.football-data.co.uk/mmz4281/%s/%s.csv" % (saison, c))
            except Exception as e:
                if "404" in str(e):
                    deja.add(cle)  # la saison n'existe pas pour ce championnat : inutile de réessayer
                else:
                    print("Historique", cle, "non téléchargé :", e)
                continue
            try:
                texte = brut.decode("utf-8-sig")
            except UnicodeDecodeError:
                texte = brut.decode("latin-1")
            for r in csv.DictReader(io.StringIO(texte)):
                h, a, hg, ag, dt = (r.get("HomeTeam") or "").strip(), (r.get("AwayTeam") or "").strip(), \
                    r.get("FTHG", ""), r.get("FTAG", ""), (r.get("Date") or "").strip()
                m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", dt)
                if not (h and a and m and hg.isdigit() and ag.isdigit()):
                    continue
                an = int(m.group(3))
                an += 2000 if an < 100 and an < 70 else (1900 if an < 100 else 0)
                rows.append([h, a, int(hg), int(ag), "%04d-%02d-%02d" % (an, int(m.group(2)), int(m.group(1)))])
            deja.add(cle)
            nouveau = True
    if nouveau or not os.path.exists(fichier):
        rows.sort(key=lambda r: r[4])
        json.dump({"seasons": sorted(deja), "rows": rows}, open(fichier, "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))
        print(len(rows), "matchs d'historique dans", fichier)


if __name__ == "__main__":
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        sys.exit("Clé API absente : ajoute le secret FOOTBALL_DATA_TOKEN (voir GUIDE.md).")
    items = matchs(token)
    json.dump({"updated": datetime.now(TZ).strftime("%d/%m/%Y %H:%M"), "items": items},
              open("fixtures.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(len(items), "matchs écrits dans fixtures.json")
    csv_resultats()
    historique()
