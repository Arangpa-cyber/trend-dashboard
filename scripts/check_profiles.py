#!/usr/bin/env python3
"""profiles.json 이 index.html 의 UNIVERSE 와 같은 종목을 담고 있는지 확인한다."""
import json, re, sys, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
html = (root / "index.html").read_text(encoding="utf8")
blk = html.split("const UNIVERSE")[1].split("const MARKET")[0]
uni = set(re.findall(r'\["([A-Z.]+)","[^"]+"\]', blk))
prof = json.loads((root / "profiles.json").read_text(encoding="utf8"))["items"]
missing, extra = sorted(uni - set(prof)), sorted(set(prof) - uni)
need = ("g", "theme", "sub", "do", "why", "types", "edge")
bad = [t for t, v in prof.items() if any(not v.get(k) for k in need)]
print(f"UNIVERSE {len(uni)}종목, profiles {len(prof)}종목")
if missing: print("프로필 없음:", ", ".join(missing))
if extra: print("UNIVERSE에 없음:", ", ".join(extra))
if bad: print("빈 칸 있음:", ", ".join(bad))
sys.exit(1 if (missing or extra or bad) else 0)
