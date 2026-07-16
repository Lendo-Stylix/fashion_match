#!/usr/bin/env python3
"""Escape 'W&B' -> 'W\\&B' and 'Fashion KB' ampersands in prose/captions.
Leaves table/tabular rows untouched (those use & as alignment tabs intentionally)."""
import io, os
P = os.path.join(os.path.dirname(__file__), "..", "docs", "reports", "stylist_model_report_dl.tex")
P = os.path.normpath(P)

with io.open(P, "r", encoding="utf-8", newline="\n") as f:
    lines = f.read().split("\n")

in_tabular = False
changed = 0
out = []
for ln in lines:
    stripped = ln.lstrip()
    if stripped.startswith(r"\begin{tabular}"):
        in_tabular = True
    if in_tabular:
        # inside tabular: do NOT escape &. But W&B never appears inside our tables, safe.
        out.append(ln)
    else:
        # prose/caption/section: escape literal "W&B" -> "W\&B"
        if "W&B" in ln:
            ln = ln.replace("W&B", r"W\&B")
            changed += 1
        out.append(ln)
    if stripped.startswith(r"\end{tabular}"):
        in_tabular = False

with io.open(P, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(out))
print(f"OK: escaped {changed} 'W&B' -> 'W\\&B' in prose")
