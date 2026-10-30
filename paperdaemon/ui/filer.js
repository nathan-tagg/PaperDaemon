// THE PAGE'S FILE, OFF THE PAGE'S THREAD: the editor's worker (new Worker("filer.js")), and what the editor shares with
// it (window.PDFile). Each stroke's part of the file -- its line in the scene's JSON and its points' records -- is made
// here once, from the file the editor read and from each new stroke's points as a save first needs it; a save is put
// together here in the page's order and sent from here; a look at the file is read and compared here, and the editor
// told only what changed. The editor's thread never makes the file nor reads it whole: a page of tens of thousands of
// strokes cost it tens of milliseconds a save, and a look at a changed file far more.
// A stroke is known here by its number (uid: the editor's itemId[1], new for every stroke the editor makes). A stroke is
// the same stroke as one the file had when its pen, its color and its points to a tenth of a unit are (as the file
// keeps them, in single precision): its HASH, two 32-bit mixes of those numbers -- never a string made of them.
// A MIRROR PAGE (the tablet's own): each stroke read keeps the id the file gave it while it is exactly that stroke on
// that layer, and a stroke the editor wrote takes the id the file gave it once read back (ids, as the editor's knowIds
// did); its group goes with it. Worked out here at every read, the editor told what changed (it keeps them too: the
// write as the page is left is its own, at once)
(function () {
  "use strict";
  const PDS = [0x50, 0x44, 0x53, 0x31], REC = 14;
  const clipTo = (v, hi) => Math.max(0, Math.min(hi, Math.round(v || 0)));
  // A STROKE'S POINTS AS THE FILE KEEPS THEM: six numbers a point (x, y, speed, direction, width, pressure, as the editor
  // keeps them) from `at` -> its 14-byte records (x, y float32; speed, width uint16; direction, pressure uint8, little-endian)
  function recordsOf(a, at, n) {
    const rec = new Uint8Array(n * REC), dv = new DataView(rec.buffer);
    for (let r = 0, o = at; r < n * REC; r += REC, o += 6) {
      dv.setFloat32(r, a[o], true); dv.setFloat32(r + 4, a[o + 1], true);
      dv.setUint16(r + 8, clipTo(a[o + 2], 65535), true); dv.setUint16(r + 10, clipTo(a[o + 4], 65535), true);
      dv.setUint8(r + 12, clipTo(a[o + 3], 255) % 256); dv.setUint8(r + 13, clipTo(a[o + 5], 255));
    }
    return rec;
  }
  const headOf = (ln, n) => JSON.stringify({ pen: ln.pen, penCode: ln.penCode, color: ln.color, colorRgba: ln.colorRgba, thicknessScale: ln.thicknessScale, n });
  // a stroke's line with its id and its group, a Mirror page's (as the editor's sceneBytes writes it)
  const headWith = (head, id, group) => id || group ? head.slice(0, -1) + (id ? ',"id":' + JSON.stringify(id) : "") + (group ? ',"group":' + JSON.stringify(group) : "") + "}" : head;
  // THE MIXES: FNV-1a over 32-bit words, and Murmur3's; as one number of 53 bits (a Map's key)
  function Mix() { this.a = 0x811c9dc5; this.b = 0x9747b28c; }
  Mix.prototype.w = function (v) {
    this.a = Math.imul(this.a ^ v, 0x01000193);
    let k = Math.imul(v, 0xcc9e2d51); k = (k << 15) | (k >>> 17); k = Math.imul(k, 0x1b873593);
    let b = this.b ^ k; b = (b << 13) | (b >>> 19); this.b = (Math.imul(b, 5) + 0xe6546b64) | 0;
  };
  Mix.prototype.out = function () { return (this.a >>> 0) * 2097152 + ((this.b >>> 0) & 0x1fffff); };
  const F64 = new Float64Array(1), U32 = new Uint32Array(F64.buffer);
  Mix.prototype.v = function (x) {                            // any value of a scene's JSON: its kind, then what it holds
    if (x === null || x === undefined) this.w(1);
    else if (x === false || x === true) this.w(x ? 3 : 2);
    else if (typeof x === "number") { this.w(4); F64[0] = x; this.w(U32[0]); this.w(U32[1]); }
    else if (typeof x === "string") { this.w(5); this.w(x.length); for (let i = 0; i < x.length; i++) this.w(x.charCodeAt(i)); }
    else if (Array.isArray(x)) { this.w(6); this.w(x.length); for (const y of x) this.v(y); }
    else { this.w(7); for (const k of Object.keys(x)) { this.v(k); this.v(x[k]); } }
  };
  const code = v => typeof v === "number" ? v | 0 : v === null || v === undefined ? -1 : -2;
  function strokeHash(penCode, color, rec, at, n) {           // a stroke's hash, from its records (at: where they start)
    const m = new Mix(), dv = new DataView(rec.buffer, rec.byteOffset);
    m.w(code(penCode)); m.w(code(color)); m.w(n);
    for (let i = 0, o = at; i < n; i++, o += REC) { m.w(Math.round(dv.getFloat32(o, true) * 10) | 0); m.w(Math.round(dv.getFloat32(o + 4, true) * 10) | 0); }
    return m.out();
  }
  const valueHash = x => { const m = new Mix(); m.v(x); return m.out(); };
  // THE PAGE'S TEXT, ITS PICTURES, ITS OWN FACTS, as hashes: the text by its place and its paragraphs (each its style, its
  // list, each character with whether it is bold and italic), as the editor holds it (chars) or as the file has it (runs)
  function textHash(t) {
    if (!t || !t.paras || !t.paras.length) return 0;
    const m = new Mix();
    m.w(Math.round(t.x) | 0); m.w(Math.round(t.y) | 0); m.w(Math.round(t.width) | 0); m.w(t.paras.length);
    for (const p of t.paras) {
      m.v(p.style); m.v(p.list || null);
      if (p.chars) { m.w(p.chars.length); for (const c of p.chars) { m.v(c.c); m.w((c.b ? 1 : 0) | (c.i ? 2 : 0)); } }
      else {
        const cs = [];
        for (const r of p.runs || []) for (const c of [...String(r.text)]) cs.push(c, (r.bold ? 1 : 0) | (r.italic ? 2 : 0));
        m.w(cs.length / 2); for (let i = 0; i < cs.length; i += 2) { m.v(cs[i]); m.w(cs[i + 1]); }
      }
    }
    return m.out();
  }
  const metaHash = (paperSize, textVisible, templateVisible, template) => valueHash([paperSize || [1620, 2160], textVisible !== false, templateVisible !== false, template || "Blank"]);
  const picturesHash = list => valueHash(list.map(im => [im.name, im.quad.map(p => [Math.round(p[0] * 10), Math.round(p[1] * 10)])]));
  const picturesIn = (sc, mirror) => (sc.images || []).filter(im => im && im.name && (im.quad || []).length === 4)
    .map(im => ({ name: im.name, key: im.key || "", quad: im.quad.map(p => [Number(p[0]), Number(p[1])]), ...(mirror && im.id ? { id: im.id } : {}) }));
  const shared = { recordsOf, headOf, strokeHash, textHash, metaHash, picturesHash, REC };

  if (typeof WorkerGlobalScope === "undefined" || !(self instanceof WorkerGlobalScope)) { window.PDFile = shared; return; }

  // ================================================================ the worker
  // parts: uid -> { n, rec (its records), head (its line in the JSON), h (its hash), f (pen code, color, width scale,
  // colors: what makes it exactly the file's), id and group (a Mirror page's) }. The file as last read or written (known):
  // each layer's strokes, as uids and hashes; the hashes of the text, the pictures, the page's facts; its version
  const parts = new Map();
  let known = null, mirror = false;
  const pend = new Map();                                     // a look's file, until the editor says it took it in (or not)
  function readFile(buf) {                                    // the engine's binary form -> { sc (its JSON), u8, layers: [[{ ln, at, n, h }]] }
    const dv = new DataView(buf), u8 = new Uint8Array(buf);
    if (PDS.some((b, i) => u8[i] !== b)) throw new Error("not a PaperDaemon page");
    const hl = dv.getUint32(4, true), sc = JSON.parse(new TextDecoder().decode(u8.subarray(8, 8 + hl)));
    let at = 8 + hl;
    sc.layers = sc.layers || [];
    const layers = sc.layers.map(L => (L.lines || []).map(ln => {
      const n = ln.n || 0, e = { ln, at, n, h: strokeHash(ln.penCode, ln.color, u8, at, n) };
      at += n * REC;
      return e;
    }));
    return { sc, u8, layers };
  }
  const factsOf = ln => ({ penCode: ln.penCode, color: ln.color, thicknessScale: ln.thicknessScale, colorRgba: ln.colorRgba || null });
  function partFrom(u8, e) {                                  // a stroke of a file read: its part, its records where they are
    const ln = e.ln;
    return { n: e.n, rec: u8.subarray(e.at, e.at + e.n * REC), h: e.h, f: factsOf(ln), id: mirror && ln.id || null, group: mirror && ln.group || null,
             head: headOf({ pen: ln.pen || "FINELINER_2", penCode: ln.penCode, color: ln.color, colorRgba: ln.colorRgba, thicknessScale: ln.thicknessScale }, e.n) };
  }
  function knownFrom(F, uids) {                               // the file read, its strokes these uids -> what is known of it
    const sc = F.sc;
    return { layers: sc.layers.map((L, i) => ({ daemon: !!L.daemon, visible: L.visible !== false, uids: uids[i] || [], hs: F.layers[i].map(e => e.h) })),
             text: sc.text ? textHash(sc.text) : 0, meta: metaHash(sc.paperSize, sc.textVisible, sc.templateVisible, sc.template),
             pics: picturesHash(picturesIn(sc)) };
  }
  // THE PAGE AS READ: each stroke's part, its uid the editor's (uids: each layer's, in the file's order)
  function load(m) {
    mirror = !!m.mirror;
    const F = readFile(m.buf);
    F.layers.forEach((Ls, i) => Ls.forEach((e, j) => parts.set(m.uids[i][j], partFrom(F.u8, e))));
    known = knownFrom(F, m.uids.map(u => Array.from(u))); known.version = m.version || "";
    return { ok: true };
  }
  // A MIRROR PAGE'S IDS, from a file read (the editor's knowIds): its layers' ids (the page's own layers by place among them,
  // the daemon's apart); each stroke known here with an id keeps it while the file has a stroke of that id on that stroke's
  // layer exactly as it is (else it is let go), the first to claim it; each stroke known here without one takes the id of a
  // stroke of the file no stroke here holds that it is exactly (found by its layer and a rough key: its pen code, color,
  // count, first point -- a hash). -> { layerIds, hasText, ids: [[uid, id or null]] and groups: [[uid, group]] that changed,
  // and commit(): them kept here }
  const idKey = id => Array.isArray(id) && id.length === 2 && Number.isInteger(id[0]) && Number.isInteger(id[1]) && id[0] >= 0 && id[0] < 2097152 &&
                      id[1] >= 0 && id[1] < 4294967296 ? id[0] * 4294967296 + id[1] : JSON.stringify(id);
  function sameStroke(p, e, u8) {                             // a part exactly a stroke of a file read (as its file record is)
    const f = p.f, ln = e.ln;
    if (f.penCode !== ln.penCode || f.color !== ln.color || f.thicknessScale !== ln.thicknessScale || p.n !== e.n) return false;
    const ra = f.colorRgba, rb = ln.colorRgba || null;
    if (!ra !== !rb || (ra && (ra.length !== rb.length || ra.some((v, i) => v !== rb[i])))) return false;
    const a = p.rec;
    for (let i = 0, o = e.at; i < a.length; i++, o++) if (a[i] !== u8[o]) return false;
    return true;
  }
  function roughOf(lid, f, n, rec, at) {
    const m = new Mix(), dv = new DataView(rec.buffer, rec.byteOffset);
    m.v(lid); m.w(code(f.penCode)); m.w(code(f.color)); m.w(n);
    if (n) { m.w(dv.getUint32(at, true)); m.w(dv.getUint32(at + 4, true)); }
    return m.out();
  }
  function knowIds(F) {
    const sc = F.sc, fileLs = sc.layers.filter(L => !L.daemon), fileD = sc.layers.find(L => L.daemon);
    const layerIds = { mine: fileLs.map(L => L.id || null), daemon: fileD && fileD.id || null };
    let mi = 0;
    const lid = known.layers.map(L => { const id = L.daemon ? layerIds.daemon : layerIds.mine[mi++] || null; return id ? idKey(id) : ""; });
    const byId = new Map();
    sc.layers.forEach((L, i) => { const l = L.id ? idKey(L.id) : ""; for (const e of F.layers[i]) if (e.ln.id) byId.set(idKey(e.ln.id), { e, lid: l }); });
    const held = new Set(), next = new Map();                 // uid -> [its id now, its group now]
    known.layers.forEach((L, i) => { for (const u of L.uids) {
      const p = parts.get(u);
      if (!p || !p.id) continue;
      const k = idKey(p.id), f = byId.get(k);
      if (f && !held.has(k) && f.lid === lid[i] && sameStroke(p, f.e, F.u8)) { held.add(k); next.set(u, [p.id, f.e.ln.group || null]); }
      else next.set(u, [null, p.group]);
    } });
    const free = new Map();
    for (const [k, f] of byId) {
      if (held.has(k)) continue;
      const h = roughOf(f.lid, factsOf(f.e.ln), f.e.n, F.u8, f.e.at), l = free.get(h);
      if (l) l.push(f.e); else free.set(h, [f.e]);
    }
    if (free.size) known.layers.forEach((L, i) => {
      if (!lid[i]) return;
      for (const u of L.uids) {
        const p = parts.get(u);
        if (!p || !p.n || (next.has(u) ? next.get(u)[0] : p.id)) continue;
        const c = free.get(roughOf(lid[i], p.f, p.n, p.rec, 0));
        if (!c) continue;
        const at = c.findIndex(e => sameStroke(p, e, F.u8));
        if (at < 0) continue;
        const e = c.splice(at, 1)[0];
        next.set(u, [e.ln.id, e.ln.group || null]);
      }
    });
    const ids = [], groups = [];
    for (const [u, [id, group]] of next) {
      const p = parts.get(u);
      if (idKey(id) !== idKey(p.id)) ids.push([u, id]);
      if (JSON.stringify(group) !== JSON.stringify(p.group)) groups.push([u, group]);
    }
    return { layerIds, hasText: !!sc.text, ids, groups, commit() { for (const [u, [id, group]] of next) { const p = parts.get(u); p.id = id; p.group = group; } } };
  }
  // A LOOK: the file read again unless it is as last read or written (its version); if it changed, what changed since it
  // was last read or written -- the daemon's layer, if it changed, as the file has it now; on each of the page's own
  // layers (matched by place among them) the strokes the file has gained (theirs, to be made strokes) and the uids of
  // those it has lost; the text, the pictures and the page's facts as the file has them, with the hashes they had (the
  // editor takes the file's only where its own are still those). Kept until the editor says whether it took it in. A
  // Mirror page's ids come with every file read, kept once the editor takes the read in
  async function look(m) {
    if (!known) return { failed: "nothing known" };
    const r = await fetch(m.url + "?form=bin", { headers: known.version ? { Authorization: "Bearer " + m.token, "If-None-Match": known.version } : { Authorization: "Bearer " + m.token } });
    if (r.status === 304) return { same: true };
    if (!r.ok) return { failed: r.status };
    const version = r.headers.get("ETag") || "", F = readFile(await r.arrayBuffer()), sc = F.sc, was = known;
    const there = knownFrom(F, []), ids = mirror ? knowIds(F) : null;
    const said = ids ? { layerIds: ids.layerIds, hasText: ids.hasText, ids: ids.ids, groups: ids.groups } : {};
    let any = there.text !== was.text || there.meta !== was.meta || there.pics !== was.pics || there.layers.length !== was.layers.length;
    for (let i = 0; !any && i < there.layers.length; i++) {
      const a = there.layers[i], b = was.layers[i];
      any = a.daemon !== b.daemon || a.visible !== b.visible || a.hs.length !== b.hs.length || a.hs.some((h, k) => h !== b.hs[k]);
    }
    if (!any) {                                               // (a write of the same page: nothing new)
      pend.set(m.id, { same: true, ids, version });
      return { same: true, version, ...said };
    }
    const out = { version, ...said, layers: [], daemon: null, text: there.text !== was.text ? { to: sc.text || null, was: was.text } : null,
                  pics: there.pics !== was.pics ? { to: picturesIn(sc, mirror), was: was.pics } : null,
                  meta: there.meta !== was.meta ? { paperSize: sc.paperSize || null, textVisible: sc.textVisible !== false, templateVisible: sc.templateVisible !== false, template: sc.template || "Blank" } : null };
    let total = 0;
    const strokes = [], picks = [], add = e => {              // a stroke to be made: its facts (its points: all in one array, after)
      const ln = e.ln;
      strokes.push({ pen: ln.pen, penCode: ln.penCode, color: ln.color, colorRgba: ln.colorRgba, thicknessScale: ln.thicknessScale, n: e.n,
                     ...(mirror && ln.id ? { id: ln.id, group: ln.group || null } : {}) });
      picks.push(e); total += e.n;
      return strokes.length - 1;
    };
    // (where each stroke the file has now comes from: the uid it keeps, or the stroke to be made -- its place in `strokes`)
    const plan = there.layers.map(() => []);
    const dT = sc.layers.findIndex(L => L.daemon), dW = was.layers.findIndex(L => L.daemon);
    if (dT >= 0) {
      const same = dW >= 0 && there.layers[dT].hs.length === was.layers[dW].hs.length && there.layers[dT].hs.every((h, k) => h === was.layers[dW].hs[k]);
      if (same) plan[dT] = was.layers[dW].uids.map(u => ({ uid: u }));
      else { plan[dT] = F.layers[dT].map(e => ({ make: add(e) })); out.daemon = { label: sc.layers[dT].label, visible: sc.layers[dT].visible !== false, made: plan[dT].map(p => p.make) }; }
    }
    const mineT = [], mineW = [];
    there.layers.forEach((L, i) => { if (!L.daemon) mineT.push(i); });
    was.layers.forEach((L, i) => { if (!L.daemon) mineW.push(i); });
    mineT.forEach((ti, k) => {
      const wi = mineW[k], W = wi === undefined ? null : was.layers[wi], left = new Map();   // the file's strokes before, by hash
      if (W) W.hs.forEach((h, j) => { const l = left.get(h); if (l) l.push(W.uids[j]); else left.set(h, [W.uids[j]]); });
      const P = [], gained = [];
      for (const e of F.layers[ti]) {
        const l = left.get(e.h);
        if (l && l.length) { P.push({ uid: l.shift() }); continue; }
        const s = add(e); P.push({ make: s }); gained.push(s);
      }
      plan[ti] = P;
      const lost = [];
      for (const l of left.values()) for (const u of l) lost.push(u);
      out.layers.push({ label: sc.layers[ti].label, visible: sc.layers[ti].visible !== false, wasVisible: W ? W.visible : null, gained, lost });
    });
    const pts = new Float64Array(6 * total), dv = new DataView(F.u8.buffer, F.u8.byteOffset);
    let o = 0;
    for (const e of picks) for (let k = 0, q = e.at; k < e.n; k++, q += REC, o += 6) {
      pts[o] = dv.getFloat32(q, true); pts[o + 1] = dv.getFloat32(q + 4, true); pts[o + 2] = dv.getUint16(q + 8, true);
      pts[o + 3] = dv.getUint8(q + 12); pts[o + 4] = dv.getUint16(q + 10, true); pts[o + 5] = dv.getUint8(q + 13);
    }
    out.strokes = strokes; out.pts = pts;
    pend.set(m.id, { F, plan, version, ids });
    return out;
  }
  // THE EDITOR TOOK THE LOOK IN: the strokes it made (uids: in the order they were given, `strokes`) -> what is known now
  function took(m) {
    const p = pend.get(m.look); pend.delete(m.look);
    if (!p) return { ok: false };
    if (p.ids) p.ids.commit();                                // (before its new strokes: they come with the file's ids)
    if (p.same) { known.version = p.version; return { ok: true }; }
    const uids = p.plan.map((P, i) => P.map((q, j) => {
      if (q.uid !== undefined) return q.uid;
      const u = m.uids[q.make];
      parts.set(u, partFrom(p.F.u8, p.F.layers[i][j]));
      return u;
    }));
    known = knownFrom(p.F, uids); known.version = p.version;
    return { ok: true };
  }
  // A SAVE: the page's layers (each its JSON up to its strokes, its strokes' uids in order) and the rest of the scene's JSON;
  // the strokes not known here asked for first (need: where each is, its layer and its place; they come as "parts"). Put
  // together as the editor's own sceneBytes would, written, and known as the file now. A Mirror page's strokes with
  // their ids and groups; a write the engine changed the page with (new strokes: ids to read back) is read again at the
  // next look, as is a write refused as stale
  function assemble(m) {
    let total = 0;
    const heads = m.layers.map(L => {
      const hs = new Array(L.uids.length);
      for (let j = 0; j < L.uids.length; j++) { const p = parts.get(L.uids[j]); hs[j] = mirror ? headWith(p.head, p.id, p.group) : p.head; total += p.rec.length; }
      return L.prefix + ',"lines":[' + hs.join(",") + "]}";
    });
    const head = new TextEncoder().encode('{"layers":[' + heads.join(",") + "]," + m.tail);
    const buf = new ArrayBuffer(8 + head.length + total), dv = new DataView(buf), u8 = new Uint8Array(buf);
    u8.set(PDS, 0); dv.setUint32(4, head.length, true); u8.set(head, 8);
    let at = 8 + head.length;
    for (const L of m.layers) for (let j = 0; j < L.uids.length; j++) { const r = parts.get(L.uids[j]).rec; u8.set(r, at); at += r.length; }
    return buf;
  }
  function needs(m) {                                         // the strokes of the save not known here: [layer, place, ...]
    const need = [], seen = new Set();
    m.layers.forEach((L, i) => { for (let j = 0; j < L.uids.length; j++) {
      const u = L.uids[j];
      if (seen.has(u)) throw new Error("a stroke twice in the page: " + u);
      seen.add(u);
      if (!parts.has(u)) need.push(i, j);
    } });
    return need;
  }
  function take(m) {                                          // new strokes: their facts, their points (all in one array)
    let o = 0;
    m.strokes.forEach((s, k) => {
      const rec = recordsOf(m.pts, o, s.n);
      parts.set(m.uids[k], { n: s.n, rec, head: headOf(s, s.n), h: strokeHash(s.penCode, s.color, rec, 0, s.n), f: factsOf(s), id: null, group: s.group || null });
      o += 6 * s.n;
    });
  }
  async function save(m) {
    const buf = assemble(m);
    if (m.check) return { bytes: buf };                       // (the bytes alone: a test compares them with sceneBytes)
    const r = await fetch(m.url, { method: "PUT", body: buf, headers: { Authorization: "Bearer " + m.token, "Content-Type": "application/octet-stream" } });
    let j = null;
    try { j = await r.json(); } catch (e) { j = null; }
    if (r.ok) {
      known = { layers: m.layers.map(L => ({ daemon: L.daemon, visible: L.visible, uids: Array.from(L.uids), hs: Array.from(L.uids, u => parts.get(u).h) })),
                text: m.text, meta: m.meta, pics: m.pics, version: mirror ? (j && j.changed ? "" : known.version) : (j && j.version) || "" };
      // (only the strokes written kept: one the page has no more -- erased, undone -- is asked for again if it comes back)
      const kept = new Set();
      for (const L of m.layers) for (let k = 0; k < L.uids.length; k++) kept.add(L.uids[k]);
      for (const u of parts.keys()) if (!kept.has(u)) parts.delete(u);
    } else if (mirror && j && j.reason === "stale") known.version = "";
    return { ok: r.ok, status: r.status, json: j };
  }
  // one at a time, in the order asked (a save waits for the look before it); a save that needs strokes waits for them
  let chain = Promise.resolve(), pendSave = null;
  self.onmessage = e => {
    const m = e.data;
    chain = chain.then(async () => {
      let out;
      try {
        if (m.op === "load") out = load(m);
        else if (m.op === "look") out = await look(m);
        else if (m.op === "took") out = took(m);
        else if (m.op === "skip") { pend.delete(m.look); out = { ok: true }; }
        else if (m.op === "save") { const need = needs(m); if (need.length) { pendSave = m; out = { need }; } else out = await save(m); }
        else if (m.op === "parts") { const q = pendSave; pendSave = null; if (!q) out = { failed: "no save waits" }; else { take(m); out = await save(q); } }
        else out = { failed: "no such op: " + m.op };
      } catch (err) { out = { failed: String(err && err.message || err) }; }
      const moved = [];
      if (out && out.pts) moved.push(out.pts.buffer);
      if (out && out.bytes) moved.push(out.bytes);
      self.postMessage({ id: m.id, ...out }, moved);
    });
  };
})();
