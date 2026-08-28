"""
VISHFUL FIRST-PARTY WEBSITE VISIBILITY CHECK (network; run by hand; OUTSIDE run_all --verify).

Renders Vishful's own public pages with Playwright (headless Chromium) and records, per nearby
information category, whether the site ALREADY visibly shows equivalent customer-facing information.
Purpose: never recommend adding information the property page already shows.

Same evidence discipline as phase3_playwright_market.py — assert only what actually rendered, record
HTTP status and rendered-text length per page, store absence as False and a render failure as
Unknown. Never asserts a negative it did not observe.

Detection is DETERMINISTIC keyword matching over the rendered text (no model). The matched snippet is
stored verbatim so the owner can check the call.

Public pages only. No login, no CAPTCHA, no anti-bot bypass.
Freezes to outputs/phase3_vishful_site_location_facts.csv. Writes ONLY that file + _summary.csv.
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
RETRIEVAL_DATE = "2026-08-27"          # explicit constant — never now()
BASE = "https://vishful.co.in"
PAGES = [f"{BASE}/", f"{BASE}/about", f"{BASE}/contact", f"{BASE}/locations", f"{BASE}/amenities"]
TIMEOUT_MS = 30000

# Category -> keywords that indicate the site talks about this kind of nearby information at all.
# Detection is two-tier, because "mentioned" and "usefully shown" are different things:
#   SPECIFIC — a category keyword within PROXIMITY_CHARS of an explicit distance figure. The visitor
#              is told WHICH place and HOW FAR. Equivalent information already provided -> no
#              recommendation.
#   GENERIC  — the category keyword appears, but with no distance anywhere near it (e.g. "located
#              near colleges, offices and metro stations"). The visitor learns the category exists
#              but not which place or how far. That named-place-and-distance gap is the materially
#              different missing piece, so a recommendation IS produced, with an upgrade ask.
#   ABSENT   — no keyword at all -> recommend adding the section.
CATEGORY_KEYWORDS = {
    "TRANSPORT":  [r"metro station", r"railway station", r"train station", r"mrts",
                   r"bus (?:stop|stand|terminus|station)", r"transport(?:ation)?\b"],
    "HEALTHCARE": [r"hospital", r"pharmac(?:y|ies)", r"clinic", r"healthcare", r"medical (?:store|shop|centre|center)"],
    "ESSENTIALS": [r"supermarket", r"grocery", r"greengrocer", r"provision store", r"marketplace",
                   r"essential (?:services|stores|shops)"],
    "EDUCATION":  [r"college", r"school", r"university", r"educational institut"],
    "FINANCIAL":  [r"\bbank\b", r"\batm\b"],
}
DISTANCE_RX = r"\d+(?:\.\d+)?\s*(?:km|kms|kilomet(?:er|re)s?|m\b)"
PROXIMITY_CHARS = 120
CATEGORY_ORDER = ["TRANSPORT", "HEALTHCARE", "ESSENTIALS", "EDUCATION", "FINANCIAL"]


def render_pages():
    """Returns (page_rows, {url: rendered_text}). Empty text where the page did not render."""
    from playwright.sync_api import sync_playwright
    rows = []; texts = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36 VishfulMarketAI/1.0 (contact: wecare@vishful.co.in)"))
        page = ctx.new_page()
        for url in PAGES:
            status = None; txt = ""; err = None
            try:
                resp = page.goto(url, timeout=TIMEOUT_MS, wait_until="domcontentloaded")
                status = resp.status if resp else None
                page.wait_for_timeout(1500)          # let client-side content settle
                txt = page.inner_text("body") or ""
            except Exception as e:
                err = type(e).__name__
            # Only a real 200 page counts as rendered content. A 404 body ("page not found")
            # must never be searched for evidence, and must never count toward coverage.
            usable = (status == 200 and len(txt) > 200)
            texts[url] = txt if usable else ""
            rows.append(dict(url=url, http_status=status, rendered_text_len=len(txt),
                             usable_content=usable, error=err, retrieval_date=RETRIEVAL_DATE,
                             provenance="playwright_headless_chromium"))
            print(f"  {status}  len={len(txt):>6}  {url}" + (f"  [{err}]" if err else ""))
        browser.close()
    return rows, texts


def main():
    print("VISHFUL SITE LOCATION-INFORMATION VISIBILITY CHECK")
    page_rows, texts = render_pages()
    any_rendered = any(r["usable_content"] for r in page_rows)

    rows = []
    for cat in CATEGORY_ORDER:
        best = None       # (specificity_rank, url, pattern, snippet) — 2=specific, 1=generic
        for url in PAGES:
            body = texts.get(url, "") or ""
            if not body: continue
            low = body.lower()
            for pat in CATEGORY_KEYWORDS[cat]:
                for m in re.finditer(pat, low):
                    s = max(0, m.start() - PROXIMITY_CHARS); e = min(len(low), m.end() + PROXIMITY_CHARS)
                    window = low[s:e]
                    rank = 2 if re.search(DISTANCE_RX, window) else 1
                    if best is None or rank > best[0]:
                        snip = re.sub(r"\s+", " ", body[max(0, m.start() - 60):min(len(body), m.end() + 60)]).strip()
                        best = (rank, url, pat, snip)
                    if best[0] == 2: break
                if best and best[0] == 2: break
            if best and best[0] == 2: break

        if best is None:
            spec = ("absent" if any_rendered else "unknown")
            visible = ("False" if any_rendered else "Unknown")
            url = pat = snip = None
        else:
            rank, url, pat, snip = best
            spec = "specific" if rank == 2 else "generic"
            visible = "True"

        rows.append(dict(
            category=cat,
            already_visible=visible,
            visibility_specificity=spec,
            names_a_place_and_distance=("True" if spec == "specific" else "False"),
            matched_pattern=pat,
            evidence_url=url,
            evidence_text=snip,
            pages_checked=len(PAGES),
            pages_rendered=sum(1 for r in page_rows if r["usable_content"]),
            retrieval_date=RETRIEVAL_DATE,
            source_type="first_party",
            detection_method=("deterministic keyword match over rendered text (no model); "
                              f"'specific' requires a distance figure within {PROXIMITY_CHARS} chars of the keyword"),
        ))

    V = pd.DataFrame(rows)
    V.to_csv(os.path.join(OUT, "phase3_vishful_site_location_facts.csv"), index=False)
    P = pd.DataFrame(page_rows)
    P.to_csv(os.path.join(OUT, "phase3_vishful_site_pages.csv"), index=False)

    summary = [("base_url", BASE), ("pages_attempted", len(PAGES)),
               ("pages_rendered_with_content", int(P["usable_content"].sum())),
               ("pages_errored", int(P["error"].notna().sum())),
               ("http_statuses", str(P["http_status"].tolist())),
               ("retrieval_date", RETRIEVAL_DATE),
               ("categories_checked", ",".join(CATEGORY_ORDER)),
               ("already_visible", str(dict(zip(V["category"], V["already_visible"])))),
               ("visibility_specificity", str(dict(zip(V["category"], V["visibility_specificity"])))),
               ("detection", "deterministic regex over rendered body text; matched snippet stored verbatim"),
               ("bypass_used", "none — public pages only, no login/CAPTCHA/anti-bot bypass"),
               ("note", "absence recorded as False only when at least one page rendered; otherwise Unknown")]
    pd.DataFrame(summary, columns=["metric", "value"]).to_csv(
        os.path.join(OUT, "phase3_vishful_site_location_facts_summary.csv"), index=False)
    print()
    for k, v in summary: print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
