#!/usr/bin/env python3
"""
Encrypt src/index.html into a passphrase-gated docs/index.html for GitHub Pages.

    python3 tools/encrypt.py                 # prompts for the passphrase (twice)
    python3 tools/encrypt.py --in src/index.html --out docs/index.html

The output is a single self-contained page. It holds the real page as an
AES-256-GCM ciphertext; the browser derives the key from the passphrase with
PBKDF2-SHA256 (600,000 iterations) and only then writes the page into the
document. Without the passphrase the file is opaque — to a visitor, a scraper,
or GitHub's own search.

WHAT THIS IS AND IS NOT
  It is: real encryption. The repo can be public and the content stays unreadable.
  It is not: access control. Everyone shares one passphrase, anyone who has it can
  pass it on, and once a person has decrypted the page they have the whole dataset.
  Treat it as "not casually readable", not as "only these five people, ever".

Requires: Python 3.8+, and the `cryptography` package
    pip install cryptography
"""

import argparse
import base64
import getpass
import json
import os
import pathlib
import sys

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    sys.exit("Missing dependency. Run:  pip install cryptography")

ITERATIONS = 600_000

SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>__TITLE__</title>
<style>
  :root{color-scheme:light dark;--bg:#e7e6e0;--fg:#191815;--mut:#6f6d65;--line:#cdcbc2;--panel:#f7f6f3}
  @media (prefers-color-scheme:dark){:root{--bg:#131316;--fg:#eeede8;--mut:#95938c;--line:#33353a;--panel:#1b1c20}}
  html,body{height:100%}
  body{margin:0;background:var(--bg);color:var(--fg);
    font:15px/1.55 ui-sans-serif,system-ui,"Helvetica Neue",Arial,sans-serif;
    display:grid;place-items:center;padding:24px}
  .box{width:100%;max-width:392px;background:var(--panel);border:1px solid var(--line);
    border-radius:4px;padding:26px 24px}
  h1{font:600 19px/1.25 ui-serif,Georgia,serif;margin:0 0 6px;letter-spacing:-.01em}
  p{margin:0 0 18px;color:var(--mut);font-size:13.5px}
  label{display:block;font:500 10px/1 ui-monospace,Menlo,monospace;letter-spacing:.11em;
    text-transform:uppercase;color:var(--mut);margin-bottom:7px}
  input{width:100%;padding:9px 10px;font-size:15px;color:var(--fg);background:var(--bg);
    border:1px solid var(--line);border-radius:2px}
  button{width:100%;margin-top:12px;padding:9px 10px;background:var(--fg);color:var(--panel);
    border:0;border-radius:2px;font:500 12px/1 ui-monospace,Menlo,monospace;
    letter-spacing:.08em;text-transform:uppercase;cursor:pointer}
  button[disabled]{opacity:.55;cursor:default}
  .err{margin:12px 0 0;color:#c0392b;font-size:13px;min-height:1.2em}
  @media (prefers-color-scheme:dark){.err{color:#ea8a80}}
  .fine{margin:18px 0 0;font-size:11.5px;color:var(--mut);line-height:1.65}
</style>
</head>
<body>
<main class="box">
  <h1>__TITLE__</h1>
  <p>This page is encrypted. Enter the passphrase you were given.</p>
  <form id="f">
    <label for="p">Passphrase</label>
    <input id="p" type="password" autocomplete="current-password" autofocus>
    <button id="go" type="submit">Unlock</button>
  </form>
  <p class="err" id="e" role="status" aria-live="polite"></p>
  <p class="fine">Shared analysis of published Race Card Project submissions. Please don't
    forward the passphrase or the decrypted contents.</p>
</main>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
(function(){
  "use strict";
  var D = JSON.parse(document.getElementById("payload").textContent);
  var f = document.getElementById("f"), pw = document.getElementById("p"),
      go = document.getElementById("go"), err = document.getElementById("e");

  if (!(window.crypto && window.crypto.subtle)){
    err.textContent = "This browser can't decrypt here — open the page over https.";
    go.disabled = true;
    return;
  }
  var b64 = function(s){
    var raw = atob(s), out = new Uint8Array(raw.length);
    for (var i=0;i<raw.length;i++) out[i] = raw.charCodeAt(i);
    return out;
  };

  f.addEventListener("submit", function(ev){
    ev.preventDefault();
    err.textContent = ""; go.disabled = true; go.textContent = "Unlocking\\u2026";
    setTimeout(function(){
      crypto.subtle.importKey("raw", new TextEncoder().encode(pw.value), "PBKDF2", false, ["deriveKey"])
        .then(function(base){
          return crypto.subtle.deriveKey(
            {name:"PBKDF2", salt:b64(D.salt), iterations:D.iterations, hash:"SHA-256"},
            base, {name:"AES-GCM", length:256}, false, ["decrypt"]);
        })
        .then(function(key){
          return crypto.subtle.decrypt({name:"AES-GCM", iv:b64(D.iv)}, key, b64(D.ct));
        })
        .then(function(plain){
          var html = new TextDecoder().decode(plain);
          document.open(); document.write(html); document.close();
        })
        .catch(function(){
          err.textContent = "That passphrase didn't work.";
          go.disabled = false; go.textContent = "Unlock";
          pw.select();
        });
    }, 16);
  });
})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="Passphrase-encrypt a static HTML page.")
    ap.add_argument("--in", dest="src", default="src/index.html")
    ap.add_argument("--out", dest="dst", default="docs/index.html")
    ap.add_argument("--title", default="The Race Card Word Graph")
    ap.add_argument("--passphrase", help="Skip the prompt. Avoid on a shared machine — it lands in shell history.")
    args = ap.parse_args()

    src = pathlib.Path(args.src)
    if not src.exists():
        sys.exit(f"No such file: {src}")

    if args.passphrase:
        secret = args.passphrase
    else:
        secret = getpass.getpass("Passphrase: ")
        if secret != getpass.getpass("Again: "):
            sys.exit("Passphrases don't match.")
    if len(secret) < 10:
        sys.exit("Use at least 10 characters — this is the only thing protecting the page.")

    plaintext = src.read_bytes()
    salt, iv = os.urandom(16), os.urandom(12)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    key = kdf.derive(secret.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, plaintext, None)

    payload = json.dumps({
        "salt": base64.b64encode(salt).decode(),
        "iv": base64.b64encode(iv).decode(),
        "ct": base64.b64encode(ct).decode(),
        "iterations": ITERATIONS,
    }, separators=(",", ":"))

    out = pathlib.Path(args.dst)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(SHELL.replace("__TITLE__", args.title).replace("__PAYLOAD__", payload))

    print(f"{src} ({len(plaintext)//1024} KB)  ->  {out} ({out.stat().st_size//1024} KB)")
    print("Commit docs/index.html. Do NOT commit src/index.html to a public repo — it is the plaintext.")


if __name__ == "__main__":
    main()
