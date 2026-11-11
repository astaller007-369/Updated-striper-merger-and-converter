import io
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st

COLS = "competition,season,date,home_team,away_team,home_goals,away_goals,home_shots_on_target,away_shots_on_target,home_big_chances,away_big_chances,home_box_touches,away_box_touches,home_corner_kicks,away_corner_kicks,home_fouled_in_final_third,away_fouled_in_final_third,home_accurate_crosses,away_accurate_crosses,home_successful_crosses_percentage,away_successful_crosses_percentage,home_accurate_long_balls,away_accurate_long_balls,home_successful_long_passes_percentage,away_successful_long_passes_percentage,home_final_third_entries,away_final_third_entries,home_dribbles_percentage,away_dribbles_percentage,home_tackles_won_percentage,away_tackles_won_percentage,home_ground_duels_percentage,away_ground_duels_percentage,home_aerial_duels_percentage,away_aerial_duels_percentage,home_goalkeeper_saves,away_goalkeeper_saves,home_xg,away_xg,home_xgot,away_xgot,home_xg_set_play,away_xg_set_play,home_xg_open_play,away_xg_open_play".split(",")

# Match identifiers - never copied, used only to line the files up.
NON_STAT_DEFAULT = ["date", "home_team", "away_team"]

# ---------- team-name conversion ----------
# Names come from the league .txt files in ./data (statsapi on the left, sportmonks on the right).
# A CSV is only touched when ALL its columns match one of the layouts below (same names, same order)
# AND the row's competition is in that layout's league list. Only the two team columns are changed,
# and only when the whole cell equals the name exactly - never part of a name.
NAME_LAYOUTS = [
    {   # right-hand (sportmonks) names in the CSV are replaced by the left-hand (statsapi) names.
        # Lines with a bracket instruction are NOT used here.
        "label": "league_country layout",
        "cols": "league_country,season,date,home_team,away_team,home_goals,away_goals,home_goalkeeper_saves,away_goalkeeper_saves,home_shots_on_target,away_shots_on_target,home_big_chances,away_big_chances,home_corner_kicks,away_corner_kicks,home_accurate_crosses,away_accurate_crosses,home_total_crosses,away_total_crosses,home_successful_crosses_percentage,away_successful_crosses_percentage,home_accurate_long_passes,away_accurate_long_passes,home_successful_long_passes_percentage,away_successful_long_passes_percentage,home_dribbles_percentage,away_dribbles_percentage,home_ground_duels_percentage,away_ground_duels_percentage,home_aerial_duels_percentage,away_aerial_duels_percentage,home_total_tackles,away_total_tackles,home_tackles_won,away_tackles_won,home_tackles_won_percentage,away_tackles_won_percentage,home_xg,away_xg,home_xgot,away_xgot,home_xg_set_play,away_xg_set_play,home_xg_open_play,away_xg_open_play".split(","),
        "comp": "league_country", "season": "season", "teams": ("home_team", "away_team"), "bracket": False,
        "leagues": {
            "Saudi Arabia Pro League": "Saudi_pro_league",
            "Czech Republic Chance Liga": "Czech_first_league",
            "Ukraine premier League": "Ukraine_premier_league",
            "Germany Bundesliga": "Bundesliga",
            "South Africa Premier League": "south_Africa",
            "Portugal Liga Portugal": "Portugal_liga_betclic",
            "Mexico Liga MX": "liga_mx_Apertura",
            "Norway Eliteserien": "eliteserien",
            "Romania Superliga": "romania",
            "Scotland Premiership": "Scottish_Premiership",
            "Serbia Super Liga": "serbia_superliga",
            "Spain La Liga": "laliga",
            "Sweden Allsvenskan": "allsveskan",
            "Turkey Super Lig": "turkey_super_lig",
            "Bulgaria First League": "bulgaria",
            "Croatia 1. HNL": "Croatia",
            "France Ligue 1": "Ligue_1_france",
            "Greece Super League": "greece",
            "Italy Serie A": "Italy_Serie_A",
            "Hungary NB I": "Hungary",
            "England Premier League": "England_premier_league",
            "Netherlands Eerste Divisie": "Eerste_divisive",
            "Netherlands Eredivisie": "eredivisie",
            "Russia Premier League": "russia_premier_league",
            "Brazil Serie B": "Brazil_serie_B",
            "Canada Premier League": "Canada_premier_league",
            "China Super League": "China_super_league",
            "Cyprus 1. Division": "Cyprus_first_division",
            "Germany 3. Liga": "Germany_3_liga",
            "Northern Ireland Premiership": "Northern_Ireland_premiership",
            "Saudi Arabia Division 1": "Saudi_1st_division",
            "Scotland Championship": "Scotland_championship",
            "United States USL Championship": "USA_USL_championship",
            "United Arab Emirates UAE Pro League": "UAE_pro_league",
            "Turkey 1. lig": "Turkey_1_lig",
            "Switzerland Challenge": "Switzerland_challenge_league",
            "Sweden Superettan": "Sweden_superettan",
        },
    },
    {   # ONLY lines with a bracket instruction are used here, e.g.
        # "Paris FC ... Paris (change Paris FC and use Paris)": Paris FC -> Paris
        "label": "competition layout",
        "cols": "competition,season,matchday,date,status,home_team,away_team,home_goals,away_goals,home_xg,away_xg,home_goalkeeper_saves,away_goalkeeper_saves,home_big_chances,away_big_chances,home_shots_on_target,away_shots_on_target,home_box_touches,away_box_touches,home_corner_kicks,away_corner_kicks,home_fouled_in_final_third,away_fouled_in_final_third,home_accurate_crosses,away_accurate_crosses,home_aerial_duels_won,away_aerial_duels_won,home_accurate_long_balls,away_accurate_long_balls,home_final_third_entries,away_final_third_entries,home_successful_dribbles,away_successful_dribbles,home_tackles_won,away_tackles_won,home_ground_duels_won,away_ground_duels_won".split(","),
        "comp": "competition", "season": "season", "teams": ("home_team", "away_team"), "bracket": True,
        "leagues": {
            "Scotland Scottish Premiership": "Scottish_Premiership",
            "Greece Stoiximan Super League": "greece",
            "France Ligue 1": "Ligue_1_france",
        },
    },
]
APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"


# ---------- helpers ----------
def norm(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def canon(s):
    """Normalised column name; 'long passes' and 'long balls' are the same thing."""
    c = norm(s).replace("long_passes", "long_balls")
    c = re.sub(r"long_pass(_|$)", r"long_balls\1", c)
    return "competition" if c == "league_country" else c  # old name -> new name


def is_xg(c):
    return "xg" in canon(c)


def empty(v):
    return v is None or str(v).strip() == ""


def rnd(col, v):
    """Strip decimals (round) everywhere except the xG family."""
    if is_xg(col) or not isinstance(v, str):
        return v
    m = re.match(r"^(-?\d+\.\d+)(%?)$", v.strip())
    return str(math.floor(float(m.group(1)) + 0.5)) + m.group(2) if m else v


def nt(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def nd(s):
    s = str(s).strip()
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)  # day first
    if m:
        return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    d = pd.to_datetime(s, errors="coerce")
    return s.lower() if pd.isna(d) else d.strftime("%Y-%m-%d")


def key(row, k):
    return f"{nd(row[k[0]])}|{nt(row[k[1]])}|{nt(row[k[2]])}"


def num(m, c):
    try:
        return float(str(m.get(c, "")).replace("%", ""))
    except ValueError:
        return None


def pct(n, d):
    return None if n is None or d is None or d <= 0 else math.floor(n / d * 100 + 0.5)


@st.cache_data(show_spinner=False)
def load(file_bytes):
    """Returns (dataframe, number of malformed lines that had to be skipped)."""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    bad = []
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except pd.errors.ParserError:
        # tolerant fallback: sniff delimiter, skip (and count) malformed lines
        bad.clear()
        df = pd.read_csv(
            io.StringIO(text), sep=None, engine="python", dtype=str,
            keep_default_na=False, skipinitialspace=True,
            on_bad_lines=lambda row: bad.append(row),  # returns None -> line skipped
        )
    for c in df.columns:
        df[c] = df[c].map(lambda v, c=c: rnd(c, v))
    return df, len(bad)



def nfc(s):
    return unicodedata.normalize("NFC", str(s)).strip()


def nk(s):
    """forgiving key for locating a name file: letters and digits only, lower case"""
    return re.sub(r"[^a-z0-9]", "", str(s).casefold())


def season_year(s):
    """'2024/25', '2024-2025', '2024' -> 2024"""
    m = re.search(r"\d{4}", str(s))
    return int(m.group()) if m else None


# Name files of lower divisions (everything else in data/ is a top-tier league). A top-tier league is never
# matched to one of these, and a second-tier league (e.g. "Netherlands Eerste Divisie") only to one of these.
LOWER_DIVISION = {"eerstedivisive", "belgiumchallengerboth", "ligue2", "ligaportugal2", "laliga2", "leaguetwoengland",
                  # lower-division leagues added later: file name key and competition name key
                  "brazilserieb", "germany3liga", "saudi1stdivision", "saudiarabiadivision1", "scotlandchampionship",
                  "usauslchampionship", "unitedstatesuslchampionship", "turkey1lig", "switzerlandchallengeleague",
                  "switzerlandchallenge", "swedensuperettan"}
_T2_WORDS = {"2", "two", "ii", "challenger", "eerste", "segunda", "second", "championship"}


def words(s):
    return set(re.findall(r"[a-z]+|\d+", str(s).casefold()))


def is_tier2(name):
    return nk(name) in LOWER_DIVISION or bool(words(name) & _T2_WORDS)


def name_files():
    """Every .txt under the app folder that is not hidden (data/ or anywhere else)."""
    skip = {"venv", "site-packages", "node_modules", "__pycache__"}
    out = []
    for p in APP_DIR.rglob("*.txt"):
        parts = p.relative_to(APP_DIR).parts
        if not any(x.startswith(".") or x in skip for x in parts):
            out.append(p)
    return sorted(out, key=lambda p: p.name.lower())


@st.cache_data(show_spinner=False)
def league_rules():
    """-> (rules, meta).  rules: {name-file key: [(season start year, csv name, new name, has_bracket), ...]}
    meta: {name-file key: {"name": file name without extension, "tier2": bool}}. Files with no name lines are ignored."""
    files = name_files()
    base = {f: re.sub(r"__\d+_?$", "", f.stem).strip("_") for f in files}
    rules, meta, seen = {}, {}, set()
    for f in files:
        year, found = -1, []                          # lines before any season heading apply to every season
        for line in f.read_bytes().decode("utf-8", errors="replace").replace("\ufeff", "").replace("\r", "").split("\n"):
            s = line.strip()
            if not s:
                continue
            if re.search(r"statsapi|starsapi|sportmonks", s, re.I):
                year = season_year(s) if season_year(s) is not None else year
                continue
            p = re.split(r"\s*\.{3,}[\s.]*", s)
            if len(p) != 2 or not p[0].strip() or not p[1].strip():
                continue                              # notes such as "all team names match"
            left, right, bracket = p[0].strip(), p[1].strip(), None
            if left.endswith(".") and not right.endswith(".") and re.search(r"\.\s+\.{3,}", s):
                left = left.rstrip(".")               # typo such as "FC Rostov. ........Rostov"
            m = re.search(r"\(([^)]*)\)\s*$", right)
            if m:
                bracket, right = m.group(1), right[:m.start()]
            right = re.sub(r"[\s-]+$", "", right)
            if re.search(r"\s{3,}", right):
                right = re.split(r"\s{3,}", right)[0].rstrip(". ")
            right = right.rstrip(", ")
            if bracket is None:
                found.append((year, nfc(right), left, False))          # right-hand name -> left-hand name
            else:
                m = re.search(r"change\s+(.+?)\s+(?:and use|to)\s+(.+?)\s*$", bracket, re.I)
                a_, b_ = (m.group(1), m.group(2)) if m else (left, right)
                found.append((year, nfc(a_), b_.strip(), True))        # name in the bracket instruction
        if found and tuple(found) not in seen:        # an identical copy of another file is skipped
            seen.add(tuple(found))
            k = nk(base[f])
            rules.setdefault(k, []).extend(found)
            meta[k] = {"name": base[f], "tier2": is_tier2(base[f])}
    return rules, meta


def pick_file(label, fkey, rules, meta, teams):
    """Find the name file for one league of the list. Returns (file key or None, how it was found)."""
    if nk(fkey) in rules:
        return nk(fkey), "expected file name"
    t2 = is_tier2(label)
    cand = {k: m for k, m in meta.items() if m["tier2"] == t2}
    L = words(label)
    best = []
    for k, m in cand.items():
        F = words(m["name"])
        LD, FD = {w for w in L if w.isdigit()}, {w for w in F if w.isdigit()}
        if LD and FD and LD != FD:                    # e.g. "Ligue 1" is not "Ligue 2"
            continue
        sc = len(L & F) / len(L | F)
        if nk(m["name"]) in nk(label) or nk(label) in nk(m["name"]):
            sc = max(sc, 0.9)
        if sc >= 0.5:
            best.append((sc, k))
    best.sort(reverse=True)
    if best and (len(best) == 1 or best[0][0] > best[1][0]):
        return best[0][1], "similar file name"
    hits = sorted(((len(teams & {nfc(x) for r in rules[k] for x in r[1:3]}), k) for k in cand), reverse=True)
    if hits and hits[0][0] >= 3 and (len(hits) == 1 or hits[0][0] > hits[1][0]):
        return hits[0][1], "team names"
    return None, ""


def convert_names(df):
    """Whole-cell team-name conversion. Returns (df, info). Unknown layouts are returned untouched.
    A row's league is its league_country / competition value, compared with the league list of the layout.
    Every season is converted; if a name is listed under several seasons the latest listing wins."""
    info = {"layout": None, "changes": Counter(), "skipped": Counter(), "missing": {}, "comps": Counter(),
            "files": [], "hint": ""}
    cols = [str(c).strip() for c in df.columns]
    lay = next((l for l in NAME_LAYOUTS if cols == l["cols"]), None)
    if lay is None:
        best = max(NAME_LAYOUTS, key=lambda l: len(set(cols) & set(l["cols"])))
        if len(set(cols) & set(best["cols"])) >= 0.6 * len(best["cols"]):
            miss = [c for c in best["cols"] if c not in cols]
            extra = [c for c in cols if c not in best["cols"]]
            info["hint"] = (f"Closest layout: {best['label']} - "
                            + ("same columns but a different order." if not miss and not extra
                               else f"missing {miss[:3]}, extra {extra[:3]}."))
        return df, info
    info["layout"] = lay["label"]
    (rules, meta), real = league_rules(), dict(zip(cols, df.columns))
    info["files"] = sorted(m["name"] + (" (2nd tier)" if m["tier2"] else "") for m in meta.values())
    leagues = {" ".join(k.split()).casefold(): (k, v) for k, v in lay["leagues"].items()}
    ccol, resolved, maps = real[lay["comp"]], {}, {}
    for comp in pd.unique(df[ccol]):
        hit = leagues.get(" ".join(str(comp).split()).casefold())
        if hit is None:
            resolved[comp] = None
            continue
        label, fkey = hit
        rows = df[df[ccol] == comp]
        teams = {nfc(v) for t in lay["teams"] for v in rows[real[t]]}
        fk, how = pick_file(label, fkey, rules, meta, teams)
        resolved[comp] = (label, fkey, fk, how)
        if fk is not None and label not in maps:
            maps[label] = {}
            for ry, a_, b_, br in sorted(rules[fk], key=lambda r: r[0]):    # later seasons win
                if br == lay["bracket"]:
                    maps[label][a_] = b_
    new = {t: list(df[real[t]]) for t in lay["teams"]}
    for n, comp in enumerate(df[ccol]):
        r = resolved[comp]
        if r is None:
            info["comps"][(str(comp), "not in the list", "", "")] += 1
            info["skipped"][f"competition not in the list: {comp}"] += 1
            continue
        label, fkey, fk, how = r
        info["comps"][(str(comp), label, meta[fk]["name"] if fk else "", how or "not found")] += 1
        if fk is None:
            info["missing"][label] = fkey
            continue
        mp = maps[label]
        for t in lay["teams"]:
            v = new[t][n]
            k = nfc(v)
            if k in mp and nfc(mp[k]) != k:
                info["changes"][(label, v, mp[k])] += 1
                new[t][n] = mp[k]
    df = df.copy()
    for t in lay["teams"]:
        df[real[t]] = new[t]
    return df, info


def show_conversion(info):
    if info["layout"] is None:
        st.caption("Team names: not converted - the columns don't match a known layout. " + info["hint"])
        return
    st.caption(f"Team names: {sum(info['changes'].values())} cells converted ({info['layout']}).")
    if info["missing"]:
        found = ", ".join(info["files"][:40]) if info["files"] else "none"
        st.warning("No name file could be matched to: " + ", ".join(sorted(info["missing"]))
                   + f". Name files found next to app.py: {len(info['files'])} ({found}). "
                   "Put the league .txt files in a data/ folder beside app.py.")
    with st.expander("Name conversion details"):
        if info["comps"]:
            st.dataframe(pd.DataFrame([(*k, v) for k, v in sorted(info["comps"].items())],
                                      columns=["Competition in the CSV", "League in the list", "Name file used", "Found by", "Rows"]),
                         use_container_width=True, hide_index=True)
        if info["changes"]:
            st.dataframe(pd.DataFrame([(*k, v) for k, v in sorted(info["changes"].items())],
                                      columns=["League", "Was", "Now", "Cells"]),
                         use_container_width=True, hide_index=True)


def detect(df, name):
    for c in df.columns:
        if canon(c) == name:
            return c
    return df.columns[0]


def standardise(out, key_cols, keep_extra=False):
    """Return `out` with exactly the standard columns (COLS) first, in order, with standard names.
    Missing standard columns are created blank. Other columns are kept after them only if asked."""
    first = {}
    for c in out.columns:
        first.setdefault(canon(c), c)
    for name, col in zip(("date", "home_team", "away_team"), key_cols):
        first[name] = col                      # the key columns picked take these slots
    out = out.copy()
    ordered, renamed = [], {}
    for c in COLS:
        col = first.get(canon(c))
        if col is None or col in ordered:
            out[c] = ""
            col = c
        ordered.append(col)
        if col != c:
            renamed[col] = c
    if keep_extra:
        ordered += [c for c in out.columns if c not in ordered]
    return out[ordered].rename(columns=renamed), renamed


# ---------- UI ----------
st.set_page_config(page_title="CSV Match Merger", page_icon="⚽", layout="wide")
st.title("⚽ CSV Match Merger")
st.caption("Upload two CSVs, copy missing stat metrics one way (matched by date + home team + "
           "away team), calculate percentages and export the result.")

convert_on = st.checkbox(
    "Convert team names (only CSVs with a known set of columns, only the leagues in the name conversion list)",
    value=True, help="Uses the league .txt files in the data/ folder. Whole team names only, never part of a name.")

c1, c2 = st.columns(2)
files, dfs, keys = [None, None], [None, None], [None, None]
for i, col in enumerate((c1, c2)):
    with col:
        st.subheader(f"CSV {i + 1}")
        files[i] = st.file_uploader("Upload CSV", type="csv", key=f"f{i}")
        if files[i]:
            dfs[i], nbad = load(files[i].getvalue())
            conv = convert_names(dfs[i]) if convert_on else None
            if conv:
                dfs[i] = conv[0]
            st.caption(f"{len(dfs[i])} rows · {len(dfs[i].columns)} columns "
                       "(decimals stripped except xG family)")
            if nbad:
                st.warning(f"{nbad} malformed line(s) in this file were skipped. Matches on those "
                           "lines will be missing - fix the source file if that matters.")
            if conv:
                show_conversion(conv[1])
            k1, k2, k3 = st.columns(3)
            cols = list(dfs[i].columns)
            keys[i] = [
                k1.selectbox("Date", cols, cols.index(detect(dfs[i], "date")), key=f"d{i}"),
                k2.selectbox("Home team", cols, cols.index(detect(dfs[i], "home_team")), key=f"h{i}"),
                k3.selectbox("Away team", cols, cols.index(detect(dfs[i], "away_team")), key=f"a{i}"),
            ]

if not all(d is not None for d in dfs):
    st.info("Upload both CSV files to continue.")
    st.stop()

# ---------- direction ----------
st.subheader("Copy direction")
direction = st.radio(
    "Copy stat metrics from → to",
    ["CSV 1 → CSV 2", "CSV 2 → CSV 1"],
    horizontal=True,
    help="Only empty cells in the destination file are filled. The source file is never changed.",
)
src, dst = (0, 1) if direction == "CSV 1 → CSV 2" else (1, 0)
st.caption(f"Empty stat cells in **CSV {dst + 1}** will be filled from **CSV {src + 1}**. "
           f"The output is CSV {dst + 1} with its own columns and rows, plus any essential columns it "
           "was missing. Nothing else is changed.")

# ---------- column mapping ----------
st.subheader("Stat columns to copy")
kc = {canon(c) for k in keys for c in k}
auto = []
for a in dfs[0].columns:
    if canon(a) in kc:
        continue
    b = next((x for x in dfs[1].columns if canon(x) == canon(a)), None)
    if b:
        auto.append({"CSV 1 column": a, "CSV 2 column": b})

sig = (tuple(dfs[0].columns), tuple(dfs[1].columns))
if st.session_state.get("sig") != sig:
    st.session_state["sig"] = sig
    st.session_state["map"] = pd.DataFrame(auto, columns=["CSV 1 column", "CSV 2 column"])
    st.session_state.pop("editor", None)

st.caption("Auto-matched by name. Edit, delete, or add rows (＋ at the bottom of the table). "
           "'Long balls' and 'long passes' are treated as the same column.")
if st.button("Reset to auto-match"):
    st.session_state["map"] = pd.DataFrame(auto, columns=["CSV 1 column", "CSV 2 column"])
    st.session_state.pop("editor", None)

mapping = st.data_editor(
    st.session_state["map"], num_rows="dynamic", use_container_width=True, key="editor",
    column_config={
        "CSV 1 column": st.column_config.SelectboxColumn(options=list(dfs[0].columns)),
        "CSV 2 column": st.column_config.SelectboxColumn(options=list(dfs[1].columns)),
    },
)

all_canon = sorted({canon(c) for d in dfs for c in d.columns})
non_stat = st.multiselect(
    "Non-stat columns (never copied, left exactly as they are)",
    all_canon,
    default=[c for c in NON_STAT_DEFAULT if c in all_canon],
    help="Add any other descriptive column here (e.g. venue, referee, round).",
)
essential = st.multiselect(
    "Essential columns (added to the destination if it doesn't have them)",
    COLS,
    default=[c for c in COLS if canon(c) not in set(non_stat)],
    help="Any of these missing from the destination file is added as a new column and filled "
         "from the source file. Other source-only columns are NOT added.",
)
overwrite = st.checkbox("Overwrite existing percentage values with recalculated ones")
keep_extra = st.checkbox(
    "Also keep other destination columns (placed after the 45 standard columns)", value=False,
    help="Off = the output has exactly the 45 standard columns, in the required order.")

# ---------- run ----------
if st.button("Copy stats, calculate & build final CSV", type="primary"):
    excluded = set(non_stat) | kc
    S = dfs[src].to_dict("records")
    D = dfs[dst].to_dict("records")
    src_name, dst_name = ("CSV 1 column", "CSV 2 column") if src == 0 else ("CSV 2 column", "CSV 1 column")

    # (source column, destination column) pairs - stat metrics only
    pairs = [
        (s, d) for s, d in zip(mapping[src_name], mapping[dst_name])
        if s in dfs[src].columns and d in dfs[dst].columns
        and canon(d) not in excluded and canon(s) not in excluded
    ]

    s_index = {}
    for r in S:
        s_index.setdefault(key(r, keys[src]), r)

    dst_col = {canon(c): c for c in dfs[dst].columns}
    src_col = {canon(c): c for c in dfs[src].columns}

    # essential columns the destination lacks -> appended (in COLS order), nothing else is added
    add_cols = [c for c in essential if canon(c) not in dst_col and canon(c) not in excluded]
    for c in add_cols:
        dst_col[canon(c)] = c
    matched = unmatched = filled = calc = 0

    for rd in D:
        for c in add_cols:
            rd[c] = ""
        rs = s_index.get(key(rd, keys[dst]))
        if rs is not None:
            matched += 1
            for s, d in pairs:
                if empty(rd[d]) and not empty(rs[s]):
                    rd[d] = rs[s]
                    filled += 1
            for c in add_cols:
                sc = src_col.get(canon(c))
                if sc is not None and not empty(rs[sc]):
                    rd[c] = rs[sc]
                    filled += 1
        else:
            unmatched += 1

        # canonical view used only to calculate percentages (inputs may come from either file)
        m = {canon(c): v for c, v in rd.items() if not empty(v)}
        if rs is not None:
            for c, v in rs.items():
                if canon(c) not in excluded and canon(c) not in m and not empty(v):
                    m[canon(c)] = v

        def put(c, v):
            """Write a calculated percentage into the destination row (if it has that column)."""
            global calc
            col = dst_col.get(c)
            if v is None or col is None:
                return
            if overwrite or empty(rd[col]):
                new = str(v)
                if rd[col] != new:
                    rd[col] = new
                    calc += 1

        for s_ in ("home", "away"):
            put(f"{s_}_tackles_won_percentage", pct(num(m, f"{s_}_tackles_won"), num(m, f"{s_}_total_tackles")))
            put(f"{s_}_successful_crosses_percentage", pct(num(m, f"{s_}_accurate_crosses"), num(m, f"{s_}_total_crosses")))
        for t in ("ground", "aerial"):
            h, a = num(m, f"home_{t}_duels_won"), num(m, f"away_{t}_duels_won")
            if h is not None and a is not None and h + a > 0:
                put(f"home_{t}_duels_percentage", math.floor(h / (h + a) * 100 + 0.5))
                put(f"away_{t}_duels_percentage", math.floor(a / (h + a) * 100 + 0.5))

    out = pd.DataFrame(D, columns=list(dfs[dst].columns) + add_cols).fillna("")

    out, renamed = standardise(out, keys[dst], keep_extra)
    st.session_state["result"] = (out, matched, unmatched, filled, calc, src + 1, dst + 1, add_cols, renamed)

if "result" in st.session_state:
    out, matched, unmatched, filled, calc, s_no, d_no, added, renamed = st.session_state["result"]
    st.success(f"{len(out)} rows (CSV {d_no}) · {matched} matched in CSV {s_no} · "
               f"{unmatched} with no match · {filled} stat cells copied · "
               f"{calc} percentages calculated · {len(added)} essential columns added.")
    if added:
        st.caption("Added columns: " + ", ".join(added))
    if renamed:
        st.caption("Renamed to the standard names: " + ", ".join(f"{a} → {b}" for a, b in renamed.items()))
    blanks = {c: int((out[c] == "").sum()) for c in out.columns if (out[c] == "").any()}
    if blanks:
        st.caption("Columns still containing empty cells: "
                   + ", ".join(f"{c} ({n})" for c, n in blanks.items()))
    st.download_button("⬇️ Download final CSV", out.to_csv(index=False).encode("utf-8"),
                       "final_matches.csv", "text/csv", type="primary")
    st.dataframe(out, use_container_width=True)
