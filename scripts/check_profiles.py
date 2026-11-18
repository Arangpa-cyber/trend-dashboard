#!/usr/bin/env python3
"""profiles.json 이 index.html 의 UNIVERSE 와 5층 큰손(whales) 종목을 모두 담고 있는지 확인한다."""
import json, re, sys, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
html = (root / "index.html").read_text(encoding="utf8")
blk = html.split("const UNIVERSE")[1].split("const MARKET")[0]
uni = set(re.findall(r'\["([A-Z.]+)","[^"]+"\]', blk))
for inv in json.loads((root / "whales" / "index.json").read_text(encoding="utf8"))["investors"]:
    if inv.get("latest"):
        uni |= {x["t"] for x in json.loads((root / "whales" / inv["latest"]).read_text(encoding="utf8"))["top"]}
prof = json.loads((root / "profiles.json").read_text(encoding="utf8"))["items"]
missing, extra = sorted(uni - set(prof)), sorted(set(prof) - uni)
need = ("g", "theme", "sub", "do", "why", "types", "edge", "moat")
bad = [t for t, v in prof.items() if any(not v.get(k) for k in need)]
print(f"UNIVERSE+큰손 {len(uni)}종목, profiles {len(prof)}종목")
if missing: print("프로필 없음:", ", ".join(missing))
if extra: print("UNIVERSE·큰손에 없음:", ", ".join(extra))
if bad: print("빈 칸 있음:", ", ".join(bad))
sys.exit(1 if (missing or extra or bad) else 0)
