"""HTML player: video (or banner) with a live saliency heatmap and persona gaze dots synced to playback."""
import base64
import json

TEMPLATE = r"""
<style>
  body{margin:0;font-family:-apple-system,"Hiragino Sans",sans-serif;color:#eee;background:#0e1117}
  #wrap{display:flex;gap:12px;align-items:flex-start}
  #stage{position:relative;flex:0 0 66%;max-width:66%}
  #stage video,#stage img{width:100%;display:block;border-radius:8px}
  #ov{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none}
  #side{flex:1;max-height:__H__px;overflow:auto;font-size:12px}
  .row{display:flex;gap:6px;padding:5px 4px;border-bottom:1px solid #222}
  .dot{width:10px;height:10px;border-radius:50%;flex:0 0 10px;margin-top:3px}
  .meta{color:#999} .bar{height:4px;background:#333;border-radius:2px;margin-top:3px}
  .bar>div{height:4px;border-radius:2px;background:#f5a623}
  #ctl{margin:8px 0;font-size:13px} #ctl label{margin-right:14px} #t{color:#f5a623}
</style>
<div id="ctl">
  <label><input type="checkbox" id="cHeat" checked> Heatmap / ヒートマップ</label>
  <label><input type="checkbox" id="cDots" checked> Persona gaze / 視線</label>
  <span>t=<span id="t">0.0</span>s</span> · <span id="avg"></span>
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
function draw(){
  const t = media.currentTime || 0;
  const w = media.clientWidth, h = media.clientHeight;
  if (ov.width !== w || ov.height !== h) { ov.width = w; ov.height = h; }
  ctx.clearRect(0, 0, w, h);
  document.getElementById('t').textContent = t.toFixed(1);
  if (document.getElementById('cHeat').checked) {
    const f = frameAt(t);
    for (let i = 0; i < GW*GH; i++) { const v = f.heat[i] / 255, [r, g, b] = jet(v);
      img.data[i*4] = r; img.data[i*4+1] = g; img.data[i*4+2] = b; img.data[i*4+3] = v > 0.35 ? v*170 : 0; }
    octx.putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(off, 0, 0, w, h);
  }
  const rows = []; let sum = 0, n = 0;
  for (const id in tracks) {
    const p = byId[id]; if (!p) continue;
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
  document.getElementById('avg').textContent = n ? `avg interest ${(sum/n).toFixed(2)} / 5` : '';
  document.getElementById('side').innerHTML = rows.map(({p, g}) => `
    <div class="row">${p.img ? `<img src="${p.img}" style="width:34px;height:34px;border-radius:50%;border:2px solid ${p.color};flex:0 0 34px">` : `<div class="dot" style="background:${p.color}"></div>`}<div>
      <b>${esc(p.name)}</b> <span class="meta">${esc(p.age)} · ${esc(p.gender)} · ${esc(p.occupation)}</span><br>
      👁 ${esc(g.looking_at)}<br>💭 ${esc(g.thought)}
      <div class="bar"><div style="width:${g.interest*20}%"></div></div></div></div>`).join('');
  requestAnimationFrame(draw);
}
(media.tagName === 'VIDEO' ? media.addEventListener('loadedmetadata', draw) : (media.complete ? draw() : media.addEventListener('load', draw)));
</script>
"""


def render_player(media: bytes, mime: str, analysis: dict, personas: list[dict], gaze: list[dict], height=560,
                  avatars: dict | None = None) -> str:
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
            "transcript": analysis.get("transcript", [])}
    return (TEMPLATE.replace("__MEDIA__", tag)
            .replace("__DATA__", json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/"))
            .replace("__H__", str(height - 60)))
