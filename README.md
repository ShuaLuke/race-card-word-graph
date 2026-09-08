# The Race Card Word Graph

An interactive word-co-occurrence graph built from the 13,612 published six-word
stories in **The Race Card Project**, the archive Michele Norris started in 2010.

Words sit near the words they appear beside, links are weighted by how strongly
two words seek each other out, and selecting two or more words shows only the
cards containing all of them.

---

## Source and standing

The data was read once, at a polite rate, from the project's public WordPress API:

```
https://theracecardproject.com/wp-json/wp/v2/posts
```

13,612 published cards, February 2012 – August 2026, retrieved 8 September 2026.

Two things worth stating plainly before this goes anywhere:

- **The site's `robots.txt` disallows AI crawlers** (`ClaudeBot`, `GPTBot`, `CCBot`,
  `Google-Extended`) and sets `Content-Signal: ai-train=no, use=reference`. General
  crawling is allowed, and this was one read for private analysis — but it is a grey
  area, not a clear licence. Ask Norris's team before publishing anything derived
  from it, and certainly before making the page public.
- **The six words belong to the people who wrote them**, and to The Race Card
  Project®. The page embeds the card texts so the pair-lookup works offline. That is
  fine for a small private group; it is republication if the link gets out.

This repo is an independent analysis. It is not affiliated with or endorsed by the
project.

---

## Layout

```
src/index.html      the real page — plaintext, ~1 MB, self-contained
docs/index.html     the encrypted page GitHub Pages serves (built by tools/encrypt.py)
tools/encrypt.py    AES-256-GCM + PBKDF2 encryptor
tools/build_graph.py  rebuilds the embedded graph from the card data
data/…cards.csv     all 13,612 cards: date, six words, word count
```

`src/index.html` and `data/` are **gitignored**. On a public repo they must stay
local — committing them defeats the encryption entirely.

---

## Publish it

### 1. Encrypt

```bash
pip install cryptography
python3 tools/encrypt.py          # prompts twice for the passphrase
```

Writes `docs/index.html`: the page as AES-256-GCM ciphertext, unlocked in the
browser by a key derived with PBKDF2-SHA256 at 600,000 iterations. Pick a long
passphrase — it is the only thing protecting the content — and share it out of
band (not in the repo, not in the same email as the link).

### 2. Push

```bash
git init && git add . && git commit -m "Race Card word graph"
gh repo create race-card-word-graph --public --source=. --push
```

### 3. Turn on Pages

Settings → Pages → Source: **Deploy from a branch** → branch `main`, folder
**`/docs`**. The URL appears in a minute or two.

`crypto.subtle` needs a secure context, so the encrypted page works over the
`https://` Pages URL but not from a `file://` double-click. To check locally:

```bash
python3 -m http.server -d docs 8000   # then open http://localhost:8000
```

---

## What the encryption does and does not do

**Does:** make the repo safe to be public. The ciphertext is opaque to visitors,
scrapers, and GitHub search. No one reads a word without the passphrase.

**Does not:** control who has access. It is one shared secret — anyone holding it
can pass it on, and anyone who unlocks the page has the whole dataset in their
browser. There is no per-person access, no revocation short of re-encrypting with a
new passphrase and redistributing it, and no audit trail.

If you need actual access control — named people, revocable — put it behind
something with real auth (a private Vercel/Netlify deploy with password protection,
Cloudflare Access, or a private repo people are collaborators on) rather than
stretching this further.

## Rebuilding the graph

```bash
pip install networkx
python3 tools/build_graph.py    # expects rcp_raw.tsv (date<TAB>six words) alongside it
```

Writes `graph.json`, which gets inlined into `src/index.html` in place of the
`__DATA__` token. Tunables at the top: `MIN_DF`, `MIN_PAIR`, the nPMI floor, and
`CLUSTER_NAMES`.
