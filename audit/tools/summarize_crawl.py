"""Summarise the before/after UI crawls into tables for audit/09-ui-functional-audit.md (prints markdown)."""
import collections
import json
import re
from pathlib import Path

E = Path("audit/evidence")
before = json.loads((E / "ui-crawl-before.json").read_text())
after = json.loads((E / "ui-crawl.json").read_text())


def outcomes(d):
    return collections.Counter(r["effect"] for r in d["results"])


def runtime_names(d):
    return {c["name"] for inv in d["inventories"].values() for c in inv}


def axe(d):
    c = collections.Counter()
    for vs in d["axe"].values():
        for v in vs:
            if v["id"] != "horizontal-overflow" and v["impact"] in ("critical", "serious", "moderate"):
                c[v["impact"]] += 1
    return c


def overflow(d):
    return sum(1 for vs in d["axe"].values() for v in vs if v["id"] == "horizontal-overflow" and v["impact"] != "none")


src = json.loads((E / "source-aria-labels.json").read_text())
labels = sorted({l for ls in src.values() for l in ls if "${" not in l})
rt = runtime_names(after)
unreached = [l for l in labels if not any(l == n or n.startswith(l) for n in rt)]

print("| | Before | After |\n|---|---|---|")
print(f"| States × viewports crawled | {len(before['inventories'])} | {len(after['inventories'])} |")
print(f"| Visible controls inventoried (sum over states) | {sum(len(v) for v in before['inventories'].values())} | {sum(len(v) for v in after['inventories'].values())} |")
print(f"| Unique control interactions exercised | {len(before['results'])} | {len(after['results'])} |")
for k in sorted(set(outcomes(before)) | set(outcomes(after))):
    print(f"| outcome `{k}` | {outcomes(before).get(k, 0)} | {outcomes(after).get(k, 0)} |")
pe = lambda d: sum(1 for r in d["results"] if r.get("console"))
nf = lambda d: sum(1 for r in d["results"] if r.get("failed"))
print(f"| interactions with console/page errors | {pe(before)} | {pe(after)} |")
print(f"| interactions with failed network requests | {nf(before)} | {nf(after)} |")
for imp in ("critical", "serious", "moderate"):
    print(f"| axe {imp} (rule × state, Monaco excluded) | {axe(before).get(imp, 0)} | {axe(after).get(imp, 0)} |")
print(f"| states with horizontal overflow | {overflow(before)} | {overflow(after)} |")
cov = collections.Counter(r.get("coveredBy") for r in after["results"] if r.get("coveredBy"))
print("\nCovered controls in the final crawl (element at the control's centre):", dict(cov) or "none")
print("\nSource aria-labels never seen at runtime:", unreached or "none")
print("\nFinal-crawl rows that are not CHANGED:")
for r in after["results"]:
    if r["effect"] != "CHANGED":
        print(f"- {r['viewport']} / {r['state']} / {r.get('role')} \"{r.get('name', '')[:50]}\" → {r['effect']}"
              f"{' (' + r['error'][:90] + ')' if r.get('error') else ''}{' covered by ' + r['coveredBy'] if r.get('coveredBy') else ''}")
