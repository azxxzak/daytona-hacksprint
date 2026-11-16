"""HTML player: video (or banner) with a live AI-viewer heatmap and persona gaze dots synced to playback.

The heatmap is built from where the AI viewers (Claude personas) look at each moment, weighted by
how interested they are; it can be blended with the image-saliency map and filtered by segment.
"""
import base64
import json
from html import escape

from core.i18n import STRINGS, t

TEMPLATE = r"""
<style>
  body{margin:0;font-family:"Zen Kaku Gothic New","Hiragino Sans",sans-serif;color:#1D2321;background:#F3F4F1}
  #wrap{display:flex;gap:12px;align-items:flex-start}
  #stage{position:relative;flex:0 0 66%;max-width:66%;background:#15181A;border-radius:6px;padding:10px}
  #stage video,#stage img{width:100%;display:block}
  #ov{position:absolute;left:10px;top:10px;width:calc(100% - 20px);height:calc(100% - 20px);pointer-events:none}
  #side{flex:1;max-height:__H__px;overflow:auto;font-size:12px}
  .row{display:flex;gap:8px;padding:7px 4px;border-bottom:1px solid #D6DAD5}
  .dot{width:10px;height:10px;border-radius:50%;flex:0 0 10px;margin-top:3px}
  .meta{color:#5E6763} .bar{height:3px;background:#D6DAD5;margin-top:4px}
  .bar>div{height:3px;background:#2448D8}
  #ctl{margin:8px 0;font-size:13px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center} #t{font-weight:700}
  #ctl select{font:inherit;padding:3px 6px;border:1px solid #D6DAD5;border-radius:6px;background:#fff;color:#1D2321}
</style>
<div id="ctl">
  <label>__L_p_heat__
    <select id="mode">
      <option value="ai">__L_p_ai__</option>
      <option value="mix">__L_p_mix__</option>
      <option value="img">__L_p_img__</option>
      <option value="off">__L_p_off__</option>
    </select></label>
  <label>__L_p_who__
    <select id="seg">
      <option value="all">__L_p_all__</option>
      <option value="a1">__L_p_u25__</option><option value="a2">25-34</option>
      <option value="a3">35-44</option><option value="a4">__L_p_45__</option>
      <option value="F">__L_p_women__</option><option value="M">__L_p_men__</option>
    </select></label>
  <label><input type="checkbox" id="cDots" checked> __L_p_faces__</label>
  <span>t=<span id="t">0.0</span>s, <span id="avg"></span></span>
</div>
<div id="wrap">
  <div id="stage">__MEDIA__<canvas id="ov"></canvas></div>
  <div id="side"></div>
</div>
<script>
const D = __DATA__;
const media = document.getElementById('media'), ov = document.getElementById('ov'), ctx = ov.getContext('2d');
const [GW, GH] = D.grid;
const off = document.createElement('canvas'); off.width = GW; off.height = GH;
const octx = off.getContext('2d'), img = octx.createImageData(GW, GH);
const byId = {}; D.personas.forEach(p => { byId[p.id] = p; if (p.img) { p.im = new Image(); p.im.src = p.img; } });
const tracks = {};  // persona id -> sorted gaze points
D.gaze.forEach(g => (tracks[g.id] = tracks[g.id] || []).push(g));
Object.values(tracks).forEach(a => a.sort((x, y) => x.t - y.t));

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function jet(v){ // v 0..1 -> rgb
  const r = Math.min(1, Math.max(0, 1.5 - Math.abs(4*v - 3)));
  const g = Math.min(1, Math.max(0, 1.5 - Math.abs(4*v - 2)));
  const b = Math.min(1, Math.max(0, 1.5 - Math.abs(4*v - 1)));
  return [r*255, g*255, b*255];
}
function frameAt(t){ let lo = 0; for (let i = 0; i < D.frames.length; i++) { if (D.frames[i].t <= t) lo = i; else break; } return D.frames[lo]; }
function gazeAt(track, t){
  if (t <= track[0].t) return {...track[0], cur: track[0]};
  for (let i = 0; i < track.length - 1; i++) {
    const a = track[i], b = track[i+1];
    if (t <= b.t) { const k = (t - a.t) / Math.max(1e-6, b.t - a.t);
      return {x: a.x + (b.x - a.x)*k, y: a.y + (b.y - a.y)*k, cur: a}; }
  }
  const last = track[track.length - 1]; return {...last, cur: last};
}
const SIG = 2.6;  // gaussian spread of one viewer's gaze, in grid cells
const pheat = new Float32Array(GW * GH);
function inSeg(p){
  const v = document.getElementById('seg').value, a = +p.age, g = String(p.gender || '').toLowerCase();
  if (v === 'all') return true;
  if (v === 'a1') return a < 25; if (v === 'a2') return a >= 25 && a < 35;
  if (v === 'a3') return a >= 35 && a < 45; if (v === 'a4') return a >= 45;
  return v === 'F' ? g.startsWith('f') : g.startsWith('m');
}
function aiHeat(points){  // points: [{x, y, w}] -> normalised grid
  pheat.fill(0); let mx = 0;
  for (const q of points) {
    const gx = q.x * GW, gy = q.y * GH, r = Math.ceil(SIG * 3);
    for (let y = Math.max(0, Math.floor(gy - r)); y < Math.min(GH, gy + r); y++)
      for (let x = Math.max(0, Math.floor(gx - r)); x < Math.min(GW, gx + r); x++) {
        const d2 = (x + .5 - gx) ** 2 + (y + .5 - gy) ** 2, i = y * GW + x;
        pheat[i] += q.w * Math.exp(-d2 / (2 * SIG * SIG)); if (pheat[i] > mx) mx = pheat[i];
      }
  }
  if (mx > 0) for (let i = 0; i < pheat.length; i++) pheat[i] /= mx;
  return pheat;
}
function draw(){
  const t = media.currentTime || 0;
  const w = media.clientWidth, h = media.clientHeight;
  if (ov.width !== w || ov.height !== h) { ov.width = w; ov.height = h; }
  ctx.clearRect(0, 0, w, h);
  document.getElementById('t').textContent = t.toFixed(1);
  const mode = document.getElementById('mode').value;
  const pts = [];
  for (const id in tracks) { const p = byId[id]; if (!p || !inSeg(p)) continue;
    const g = gazeAt(tracks[id], t); pts.push({x: g.x, y: g.y, w: 0.4 + g.cur.interest / 5}); }
  if (mode !== 'off') {
    const f = frameAt(t), ai = aiHeat(pts);
    for (let i = 0; i < GW*GH; i++) {
      const s = f.heat[i] / 255;
      const v = mode === 'img' ? s : mode === 'ai' ? ai[i] : 0.7 * ai[i] + 0.3 * s;
      const [r, g, b] = jet(v);
      img.data[i*4] = r; img.data[i*4+1] = g; img.data[i*4+2] = b; img.data[i*4+3] = v > 0.35 ? v*170 : 0; }
    octx.putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(off, 0, 0, w, h);
  }
  const rows = []; let sum = 0, n = 0;
  for (const id in tracks) {
    const p = byId[id]; if (!p || !inSeg(p)) continue;
    const g = gazeAt(tracks[id], t); sum += g.cur.interest; n++;
    if (document.getElementById('cDots').checked) {
      const R = p.im ? 15 : 7, cx = g.x*w, cy = g.y*h;
      if (p.im && p.im.complete) {
        ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, R, 0, 7); ctx.clip();
        ctx.drawImage(p.im, cx - R, cy - R, 2*R, 2*R); ctx.restore();
      } else { ctx.beginPath(); ctx.arc(cx, cy, R, 0, 7); ctx.fillStyle = p.color; ctx.fill(); }
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, 7); ctx.lineWidth = 3; ctx.strokeStyle = p.color; ctx.stroke();
      ctx.font = '11px sans-serif'; ctx.fillStyle = '#fff'; ctx.fillText(p.name, cx + R + 3, cy + 4);
    }
    rows.push({p, g: g.cur});
  }
  const seg = (D.transcript || []).find(s => t >= s.start && t <= s.end);
  if (seg) {
    ctx.font = `bold ${Math.max(11, Math.min(18, w / 38))}px sans-serif`; ctx.textAlign = 'center';
    const tw = ctx.measureText(seg.text).width;
    ctx.fillStyle = 'rgba(0,0,0,.7)'; ctx.fillRect(w/2 - tw/2 - 8, h - 46, tw + 16, 26);
    ctx.fillStyle = '#fff'; ctx.fillText(seg.text, w/2, h - 27); ctx.textAlign = 'start';
  }
  rows.sort((a, b) => b.g.interest - a.g.interest);
  document.getElementById('avg').textContent = n ? D.L.p_avg.replace('{n}', n).replace('{a}', (sum/n).toFixed(1)) : D.L.p_none;
  document.getElementById('side').innerHTML = rows.map(({p, g}) => `
    <div class="row">${p.img ? `<img src="${p.img}" style="width:34px;height:34px;border-radius:50%;border:2px solid ${p.color};flex:0 0 34px">` : `<div class="dot" style="background:${p.color}"></div>`}<div>
      <b>${esc(p.name)}</b> <span class="meta">${esc(p.age)}, ${esc(p.occupation)}</span><br>
      <span class="meta">${D.L.p_looking}: ${esc(g.looking_at)}</span><br>${esc(D.lang === "en" && g.thought_en ? g.thought_en : g.thought)}
      <div class="bar"><div style="width:${g.interest*20}%"></div></div></div></div>`).join('');
  requestAnimationFrame(draw);
}
(media.tagName === 'VIDEO' ? media.addEventListener('loadedmetadata', draw) : (media.complete ? draw() : media.addEventListener('load', draw)));
</script>
"""


def render_player(media: bytes, mime: str, analysis: dict, personas: list[dict], gaze: list[dict], height=560,
                  avatars: dict | None = None, lang: str = "en") -> str:
    avatars = avatars or {}
    src = f"data:{mime};base64,{base64.b64encode(media).decode()}"
    if mime.startswith("video"):
        tag = f'<video id="media" src="{src}" controls muted playsinline></video>'
    else:
        tag = f'<img id="media" src="{src}">'
    data = {"grid": analysis["grid"],
            "frames": [{"t": f["t"], "heat": f["heat"]} for f in analysis["frames"]],
            "personas": [{**{k: p.get(k) for k in ("id", "name", "age", "gender", "occupation", "color")},
                          "img": avatars.get(p["id"])} for p in personas],
            "gaze": gaze,
            "transcript": analysis.get("transcript", []),
            "lang": lang, "L": {k: t(k, lang) for k in STRINGS if k.startswith("p_")}}
    html = TEMPLATE
    for k in data["L"]:
        html = html.replace(f"__L_{k}__", escape(data["L"][k]))
    return (html.replace("__MEDIA__", tag)
            .replace("__DATA__", json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/"))
            .replace("__H__", str(height - 60)))
