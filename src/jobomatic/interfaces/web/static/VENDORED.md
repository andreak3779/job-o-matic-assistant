# Vendored files

## htmx.min.js

- **What:** htmx 2.0.11, the minified build (`package/dist/htmx.min.js`), used for partial updates
  (ADR 0025). Every page also works as an ordinary form post.
- **Licence:** 0BSD (Zero-Clause BSD), in `htmx.LICENSE`.
- **Where it came from:** the npm registry tarball `https://registry.npmjs.org/htmx.org/-/htmx.org-2.0.11.tgz`,
  downloaded into an empty folder. The tarball's SHA-512 matched the registry's `integrity` value
  (`sha512-Thx/WtpeOQqSrqBCw/A1cwGJGg4UrVa3+...`), and its SHA-1 matched the registry's `shasum`.
- **SHA-256 of the file in this folder:**
  `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717`.
  `tests/test_web_vendored.py` fails if the file changes without this note changing.
- **The private-value scan** reads a short word in this minified file as an employer name, a
  coincidence in someone else's code. `scripts/pii-allowlist.txt` therefore lists this one path, which is
  safe only because the file's hash is pinned; `tests/test_web_vendored.py` fails if the list holds
  anything else.
- **Settings** (in `templates/base.html`): `selfRequestsOnly` on, `allowEval` off, `allowScriptTags`
  off, history snapshots off (its default keeps page snapshots, here a profile and postings, in the
  browser's `localStorage`) and `includeIndicatorStyles` off (it would inject an inline `<style>`,
  which the Content-Security-Policy forbids).
- **To upgrade:** repeat the steps above with the new version, then change the version and the
  SHA-256 here and in the test.
