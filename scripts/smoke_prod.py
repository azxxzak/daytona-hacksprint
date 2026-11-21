"""End-to-end smoke test against a deployed AdLens (default: the Vercel frontend origin, so the rewrite is covered).

    python -m scripts.smoke_prod [https://adlens-tau.vercel.app] [samples/speech_ad.mp4]

Signs in with ADLENS_ADMIN_EMAIL / ADLENS_ADMIN_PASSWORD from .env (never printed), uploads the file straight to
storage, runs a 6-viewer test on the Daytona worker, checks the report, then asks one question over SSE.
"""
import json
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://adlens-tau.vercel.app"
FILE = Path(sys.argv[2] if len(sys.argv) > 2 else "samples/speech_ad.mp4")
LANG = sys.argv[3] if len(sys.argv) > 3 else "ja"
v = dotenv_values(".env")
c = httpx.Client(base_url=BASE, timeout=300, follow_redirects=False, headers={"X-Lang": LANG})
T0 = time.time()


def step(label, r, ok=(200, 201, 204)):
    print(f"[{time.time() - T0:6.1f}s] {label}: {r.status_code}" + ("" if r.status_code in ok else f"  {r.text[:300]}"))
    if r.status_code not in ok:
        sys.exit(1)
    return r


step("login", c.post("/api/auth/login", json={"email": v["ADLENS_ADMIN_EMAIL"], "password": v["ADLENS_ADMIN_PASSWORD"]}))
ctype = "video/mp4" if FILE.suffix == ".mp4" else "image/png"
up = step("upload slot", c.post("/api/uploads", json={"filename": FILE.name, "size": FILE.stat().st_size,
                                                      "content_type": ctype})).json()
put = httpx.request(up.get("method", "PUT"), up["upload_url"], content=FILE.read_bytes(),
                    headers={"content-type": ctype, **(up.get("headers") or {})}, timeout=300)
step("PUT to storage", put)
t = step("create test", c.post("/api/tests", json={
    "upload_id": up["upload_id"], "name": "smoke " + time.strftime("%H:%M"), "context": "新しいスキンケア商品の15秒動画広告",
    "lang": LANG, "panel": {"source": "bank", "age_min": 20, "age_max": 49, "genders": ["F", "M"], "count": 6}})).json()
tid = t["id"]
last = None
while True:
    r = c.get(f"/api/tests/{tid}")
    s = r.json()
    cur = (s.get("status"), s.get("step"), s.get("percent"))
    if cur != last:
        print(f"[{time.time() - T0:6.1f}s]   {cur[0]} {cur[1]} {cur[2]}% {s.get('message', '')}")
        last = cur
    if s.get("status") in ("done", "failed"):
        break
    if time.time() - T0 > 900:
        sys.exit("timed out")
    time.sleep(3)
if s["status"] != "done":
    sys.exit(f"FAILED: {s.get('error')}")
res = s.get("result") or s
gaze = res.get("gaze") or []
print("  test lang:", s.get("lang"), "| first viewer:", (res.get("personas") or [{}])[0].get("name"), "/", (res.get("personas") or [{}])[0].get("occupation"))
for th in (res.get("themes") or [])[:2]:
    print("  theme:", th.get("title"), "—", (th.get("examples") or [{}])[0].get("text", "")[:100])
print(f"  viewers {len(res.get('personas') or [])} | reactions {len(gaze)} | themes "
      f"{len((res.get('themes') or {}).get('themes', []) if isinstance(res.get('themes'), dict) else res.get('themes') or [])}"
      f" | engaged {s.get('engaged')} | avg interest {s.get('avg_interest')}")
if gaze:
    g = gaze[0]
    print("  sample thought:", json.dumps({k: g.get(k) for k in ('persona', 'persona_id', 'time', 'thought', 'thought_en', 'interest') if k in g}, ensure_ascii=False)[:300])
m = c.get(f"/api/tests/{tid}/media")
print(f"[{time.time() - T0:6.1f}s] media: {m.status_code} -> {'signed storage URL' if 'supabase' in m.headers.get('location', '') else m.headers.get('location', '')[:60]}")
personas = res.get("personas") or []
pid = personas[0]["id"]
a = c.get(personas[0].get("avatar_url") or f"/api/avatars/p/{pid}.jpg")
print(f"[{time.time() - T0:6.1f}s] portrait: {a.status_code}")
talk = step("new talk", c.post(f"/api/tests/{tid}/talks", json={"persona_ids": [pid], "mode": "qa"})).json()
first = None
events = []
with c.stream("POST", f"/api/tests/{tid}/talks/{talk['id']}/ask", json={"message": "この広告で一番印象に残ったのはどこですか？" if LANG == "ja" else "What stuck with you most in this ad?"}) as r:
    print(f"[{time.time() - T0:6.1f}s] ask (SSE): {r.status_code} {r.headers.get('content-type')}")
    t1 = time.time()
    for line in r.iter_lines():
        if line.startswith("event:"):
            events.append(line[6:].strip())
            if first is None:
                first = time.time() - t1
        if line.startswith("data:") and events and events[-1] in ("message", "answer", "done"):
            data = line[5:].strip()
            if '"text"' in data:
                print("  answer:", data[:260])
print(f"  first SSE event after {first:.1f}s | events: {sorted(set(events))}")
print(f"DONE in {time.time() - T0:.0f}s — test id {tid}")
