# Notes for Claude Code

This repo publishes one static page to GitHub Pages, passphrase-encrypted.

## The one rule
`src/index.html` (the plaintext page) and `data/` (the full corpus) must never be
committed. They are in `.gitignore`. Only `docs/index.html` — the ciphertext — is
published. If you are asked to "just commit everything", say why that is wrong first.

## Task the user is likely to hand you
1. `pip install cryptography`
2. `python3 tools/encrypt.py` — prompts for the passphrase. Never pass `--passphrase`
   on the command line unless the user explicitly asks; it lands in shell history.
   Never invent a passphrase, and never write one into a file in this repo.
3. `git init`, commit, create the repo, push. Ask before creating anything public.
4. Settings → Pages → deploy from branch `main`, folder `/docs`.
5. Verify: fetch the Pages URL and confirm it returns the unlock form, and that
   `git ls-files` does not list `src/index.html` or anything under `data/`.

## Re-encrypting with a new passphrase
Re-run `tools/encrypt.py` and commit the new `docs/index.html`. The old passphrase
stops working for the new file, but anyone who already opened the old one kept what
they saw — rotation limits future access, not past.

## Editing the page
Edit `src/index.html` (a single self-contained file: styles, markup, a JSON blob,
and one IIFE). Then re-run the encryptor. Do not hand-edit `docs/index.html`.

## Provenance — keep this accurate
Data is from `theracecardproject.com/wp-json/wp/v2/posts`, retrieved 8 Sep 2026,
13,612 published cards. That site's robots.txt disallows AI crawlers and sets
`ai-train=no`. Do not re-crawl it, do not expand the dataset, and do not remove the
SOURCE block or the "What this is not" section from the page. See README.md.
