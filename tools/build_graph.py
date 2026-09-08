import re, math, json, csv, unicodedata
from collections import Counter, defaultdict
import networkx as nx

SRC = "rcp_raw.tsv"

rows = []
for line in open(SRC, encoding="utf-8"):
    line = line.rstrip("\n")
    if not line:
        continue
    date, _, text = line.partition("\t")
    text = unicodedata.normalize("NFKC", text).replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    # a handful of source posts carry junk years like "0202"; treat anything outside 20xx as undated
    rows.append((date if re.match(r"^20\d{2}-\d{2}$", date) else "", text.strip()))

# ---------- tokenize ----------
STOP = set("""a an the and or of to in on at as by for from with is are was were be been being am
it its this that these those there here so if then than but not no nor do does did doing done have has had
i i'm you you're we we're they they're he she me my mine your yours our ours their theirs him her his them us
what who whom which when where why how all any both each few more most other some such only own same s t can
will just don't should now""".split())
# pronouns / negations carry real meaning in this corpus -> keep a curated subset
KEEP = set("""i my me you your we our they them their he she his her not no never
am is are don't can't won't didn't doesn't isn't aren't wasn't ain't""".split())
STOP -= KEEP
# copulas / auxiliaries add edges that mean nothing ("i"—"am"); drop them
STOP |= set("is are am was were be been being do does did doing done have has had "
            "will would could should about very much really got michele norris".split())

TOKEN = re.compile(r"[a-z][a-z''\-]*")

def tokens(text):
    t = text.lower().replace("'", "'")
    out = []
    for w in TOKEN.findall(t):
        w = w.strip("-'")
        if len(w) < 2 and w not in ("i",):
            continue
        out.append(w)
    return out

def content(text):
    return [w for w in tokens(text) if w not in STOP]

docs = [content(t) for _, t in rows]
N = len(docs)

df = Counter()
for d in docs:
    df.update(set(d))

pair_df = Counter()
for d in docs:
    u = sorted(set(d))
    for i in range(len(u)):
        for j in range(i + 1, len(u)):
            pair_df[(u[i], u[j])] += 1

MIN_DF = 12            # word must appear in >= 12 cards
MIN_PAIR = 4           # pair must co-occur in >= 4 cards
vocab = {w for w, c in df.items() if c >= MIN_DF}

edges = []
for (a, b), c in pair_df.items():
    if c < MIN_PAIR or a not in vocab or b not in vocab:
        continue
    pxy = c / N
    px = df[a] / N
    py = df[b] / N
    pmi = math.log(pxy / (px * py))
    npmi = pmi / (-math.log(pxy))
    if npmi <= 0.08:
        continue
    edges.append((a, b, c, npmi))

G = nx.Graph()
for a, b, c, npmi in edges:
    G.add_edge(a, b, weight=npmi, count=c)

# keep the giant component, then trim to top nodes by df
if G.number_of_nodes():
    giant = max(nx.connected_components(G), key=len)
    G = G.subgraph(giant).copy()

TOP_N = 520
keep = sorted(G.nodes(), key=lambda w: df[w], reverse=True)[:TOP_N]
G = G.subgraph(keep).copy()
G.remove_nodes_from(list(nx.isolates(G)))

# prune weakest edges per node but keep graph connected-ish (keep top 10 by npmi per node)
KEEP_PER_NODE = 10
keep_edges = set()
for n in G.nodes():
    nb = sorted(G[n].items(), key=lambda kv: kv[1]["weight"], reverse=True)[:KEEP_PER_NODE]
    for m, _ in nb:
        keep_edges.add(tuple(sorted((n, m))))
G = nx.Graph((a, b, G[a][b]) for a, b in sorted(keep_edges))
G.remove_nodes_from(list(nx.isolates(G)))
if G.number_of_nodes():
    G = G.subgraph(max(nx.connected_components(G), key=len)).copy()

comms = nx.algorithms.community.louvain_communities(nx.Graph(sorted(G.edges(data=True))), weight="weight", seed=7, resolution=0.72)
comm_of = {}
for ci, cs in enumerate(sorted(comms, key=len, reverse=True)):
    for w in cs:
        comm_of[w] = ci


# ---------- era skew: early (2012-16) vs recent (2020-26) ----------
EARLY = {str(y) for y in range(2012, 2017)}
RECENT = {str(y) for y in range(2020, 2027)}
n_early = sum(1 for (d, _) in rows if d[:4] in EARLY)
n_recent = sum(1 for (d, _) in rows if d[:4] in RECENT)
cnt_early, cnt_recent = Counter(), Counter()
for (d, _), doc in zip(rows, docs):
    y = d[:4]
    if y in EARLY:
        cnt_early.update(set(doc))
    elif y in RECENT:
        cnt_recent.update(set(doc))

def skew(w):
    pe = (cnt_early[w] + 2.0) / n_early
    pr = (cnt_recent[w] + 2.0) / n_recent
    v = math.log2(pr / pe)
    return max(-1.6, min(1.6, v))

CLUSTER_NAMES = {
    0: "Family, heritage, mixed",
    1: "How it feels to be assumed",
    2: "Skin, shade, and what it means",
    3: "Where are you really from?",
    4: "We, together, someday",
    5: "Race as a category",
    6: "Privilege, ancestors, responsibility",
    7: "Please don't touch my hair",
    8: "Racism, still",
    9: "Diversity, and changing",
    10: "Something my mother said",
    11: "Learned it growing up",
}
OTHER = -1

# community-aware layout: place the neighborhoods first, then lay out each one inside its own patch
CG = nx.Graph()
for ci in set(comm_of.values()):
    CG.add_node(ci)
for a, b in G.edges():
    ca, cb = comm_of[a], comm_of[b]
    if ca != cb:
        CG.add_edge(ca, cb, weight=CG.get_edge_data(ca, cb, {}).get("weight", 0) + G[a][b]["weight"])
centers = nx.spring_layout(CG, weight="weight", k=2.6, iterations=900, seed=5, scale=1.0)

members = defaultdict(list)
for w, ci in comm_of.items():
    if w in G:
        members[ci].append(w)

# radius each neighborhood needs, then push circles apart until none overlap
radius = {ci: 0.055 + 0.0165 * math.sqrt(len(ws)) for ci, ws in members.items()}
C = {ci: [centers[ci][0], centers[ci][1]] for ci in members}
GAP = 0.035
for _ in range(900):
    moved = 0.0
    keys = sorted(C)
    for a in range(len(keys)):
        for b in range(a + 1, len(keys)):
            i, j = keys[a], keys[b]
            dx = C[j][0] - C[i][0]; dy = C[j][1] - C[i][1]
            d = math.hypot(dx, dy) or 1e-6
            need = radius[i] + radius[j] + GAP
            if d < need:
                push = (need - d) / 2
                ux, uy = dx / d, dy / d
                C[i][0] -= ux * push; C[i][1] -= uy * push
                C[j][0] += ux * push; C[j][1] += uy * push
                moved += push
    # mild pull toward the origin so the map stays compact
    for i in C:
        C[i][0] *= 0.9995; C[i][1] *= 0.9995
    if moved < 1e-5:
        break

pos = {}
for ci, ws in members.items():
    sub = G.subgraph(ws)
    local = nx.spring_layout(sub, weight="weight",
                             k=2.4 / math.sqrt(max(len(ws), 1)), iterations=500, seed=ci + 3)
    lx = [p[0] for p in local.values()]; ly = [p[1] for p in local.values()]
    span = max(max(lx) - min(lx), max(ly) - min(ly), 1e-6)
    cx, cy = C[ci]
    for w, (x, y) in local.items():
        pos[w] = (cx + (x / span) * 2 * radius[ci] * 0.92,
                  cy + (y / span) * 2 * radius[ci] * 0.92)

xs = [p[0] for p in pos.values()]
ys = [p[1] for p in pos.values()]
minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
def nx_(v, lo, hi): return (v - lo) / (hi - lo) if hi > lo else .5

# example cards per node (prefer exactly-6-word cards, shortest first, dedup)
by_word = defaultdict(list)
for (date, text), d in zip(rows, docs):
    s = set(d)
    for w in s:
        if w in G:
            by_word[w].append((date, text))

examples = {}
for w, lst in by_word.items():
    seen, out = set(), []
    lst.sort(key=lambda dt: (abs(len(dt[1].split()) - 6), len(dt[1])))
    for date, text in lst:
        k = text.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(text)
        if len(out) == 5:
            break
    examples[w] = out

# first/last appearance year distribution for a small trend sparkline
years = defaultdict(Counter)
for (date, _), d in zip(rows, docs):
    if not date:
        continue
    y = date[:4]
    for w in set(d):
        if w in G:
            years[w][y] += 1

nodes = []
for w in G.nodes():
    yr = years.get(w, Counter())
    nodes.append({
        "id": w,
        "df": df[w],
        "c": comm_of.get(w, 0) if comm_of.get(w, 0) in CLUSTER_NAMES else OTHER,
        "e": round(skew(w), 3),
        "ce": cnt_early[w], "cr": cnt_recent[w],
        "x": round(nx_(pos[w][0], minx, maxx), 4),
        "y": round(nx_(pos[w][1], miny, maxy), 4),
        "deg": G.degree(w),
        "ex": examples.get(w, [])[:4],
        "yr": {y: n for y, n in sorted(yr.items()) if y >= "2010"},
    })

edges_out = [{"s": a, "t": b, "w": round(G[a][b]["weight"], 3), "n": G[a][b]["count"]}
             for a, b in G.edges()]

# cluster labels: highest-df words in each community
labels = {}
for ci in sorted({n["c"] for n in nodes}):
    ws = sorted([n for n in nodes if n["c"] == ci], key=lambda n: -n["df"])
    members = [w["id"] for w in ws]
    xs_ = [w["x"] for w in ws]; ys_ = [w["y"] for w in ws]
    labels[ci] = {
        "name": CLUSTER_NAMES.get(ci, "Smaller threads"),
        "size": len(ws),
        "top": members[:8],
        "cx": round(sum(xs_) / len(xs_), 4),
        "cy": round(sum(ys_) / len(ys_), 4),
        "r": round(max(math.hypot(w["x"] - sum(xs_)/len(xs_), w["y"] - sum(ys_)/len(ys_)) for w in ws), 4),
        "cards": sum(1 for d in docs if any(m in d for m in members[:40])),
    }

meta = {
    "cards": N,
    "vocabAll": len(df),
    "vocabKept": len(vocab),
    "nodes": len(nodes),
    "edges": len(edges_out),
    "communities": len(labels),
    "minDf": MIN_DF, "minPair": MIN_PAIR,
    "nEarly": n_early, "nRecent": n_recent,
    "years": {y: c for y, c in sorted(Counter(d[:4] for d, _ in rows if d).items()) if "2010" <= y <= "2026"},
}

# ---------- full card index, so the page can answer "these words TOGETHER" ----------
idx = {n["id"]: i for i, n in enumerate(nodes)}
cards_out = []
for (date, text), doc in zip(rows, docs):
    ids = sorted({idx[w] for w in set(doc) if w in idx})
    cards_out.append([text, date[:4], ids])

json.dump({"meta": meta, "nodes": nodes, "edges": edges_out, "labels": labels, "cards": cards_out},
          open("graph.json", "w"), ensure_ascii=False, separators=(",", ":"))

with open("race_card_project_cards.csv", "w", newline="", encoding="utf-8") as f:
    wcsv = csv.writer(f)
    wcsv.writerow(["date", "six_words", "word_count"])
    for date, text in rows:
        wcsv.writerow([date, text, len(text.split())])

print(json.dumps(meta, indent=2))
print("\ncluster labels:")
for ci, L in labels.items():
    print(f"  {ci} (n={L['size']}): {L['name']} :: {', '.join(L['top'])}")
print("\ntop words:", ", ".join(f"{w}({df[w]})" for w, _ in df.most_common(25)))
print("\nrising words:", ", ".join(f"{n['id']}(+{n['e']})" for n in sorted(nodes, key=lambda n: -n["e"])[:18]))
print("\nfading words:", ", ".join(f"{n['id']}({n['e']})" for n in sorted(nodes, key=lambda n: n["e"])[:18]))
print("\ntop edges by npmi:")
for e in sorted(edges_out, key=lambda e: -e["w"])[:20]:
    print(f"  {e['s']} — {e['t']}  npmi={e['w']} n={e['n']}")
