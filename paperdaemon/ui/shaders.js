// THE RENDERER'S SHADERS: the one copy of how strokes become pixels on the graphics card (WGSL, for WebGPU).
//
// Read by the page editor (editor.html: this file is loaded before its script, and runs in WebView2's WebGPU) and by
// the engine (pipeline/page/gpu.py, through Dawn: it reads the text between each name's backquotes). Change a shader
// here and both draw with it.
//
// THE FEEDING -- what each stroke is turned into before these run (its points' records, its grain buffer, which
// of a highlighter's points are kept and where its bevels go) -- is written twice, once for each side: partOf() in
// editor.html and _feed() in pipeline/page/gpu.py. A change to one MUST be made to the other (each says so where it is
// written). render.c is the CPU renderer both are measured against, and the fallback when the card cannot be used.
//
// THE STROKES ARE THEIR POINTS, each stored once (16 bytes): x, y and the width (32-bit floats, page units as the file
// has them), then four bytes read as one: the flags -- 1 a segment from this point to the next, 2 a dot (a stroke of
// one point), 4 a bevel at this point (a highlighter's turn), 8 that bevel on the other side -- and the stroke's color
// (3 bytes, 0..255). A grain stroke's density and its length along the stroke at each point come from a buffer of their
// own. PEN STROKES: each segment a rectangle laid over it a hair wider than the pen (r + EDGE pixels each way: the
// card's rounding of its corners, a 512th of a pixel, and the arithmetic's), so every pixel the capsule could touch is visited, r the mean of its ends' widths over 2 (a dot's: its width over 2); a
// pixel is inked when its CENTER is within r of the segment (a capsule: round ends and joints). With grain on (pencils,
// light paintbrush and ballpoint) a pixel is inked by chance, from a hash of the page's cell it lies in, at the
// stroke's density there (render.c's grain_ink). A shader's wash is its alpha, decided once a pixel a stroke.
window.PD_SHADERS = {};
// How a vertex finds its point: the records are a storage buffer read by the instance (a chunk's records lie in draw
// order), a highlighter's shapes from the four corners of one quad, and a stroke drawn on its
// own (a shader's wash, a grain stroke) finds its row in the frame's table by its vertex number (16 a row: the row is
// vertex_index / 16, the corner vertex_index % 16). Rows: grain (1 or 0), where its grain starts, its first record, its
// alpha, its depth; row 0 is the pens'. Measured: 0 pixels different from the WebGL2 shaders they replaced (0.1.85),
// on both cards, Direct3D 12 and 11, in the editor; the engine's pictures 0 different from its ANGLE ones.
// A value passed flat is "flat, either": WebGPU's compatibility mode (Direct3D 11) refuses plain "flat" (which means the
// first corner's), and each such value is the same at every corner of its shape.
window.PD_SHADERS.WGSL = {
  STROKES: `
struct View { size: vec2<f32>, off: vec2<f32>, k: f32, eps: f32, evAt: u32, stAt: u32, io: vec2<f32> };
struct Own { grain: u32, gfirst: u32, first: u32, alpha: f32, depth: f32 };
@group(0) @binding(0) var<uniform> V: View;
@group(0) @binding(1) var<storage, read> owns: array<Own>;
@group(1) @binding(0) var<storage, read> rec: array<vec4<u32>>;
@group(1) @binding(1) var<storage, read> grb: array<vec2<u32>>;
fn xyOf(r: vec4<u32>) -> vec2<f32> { return vec2<f32>(bitcast<f32>(r.x), bitcast<f32>(r.y)); }
// THE EDITOR'S RECORDS CARRY THEIR STROKE'S NUMBER, not its color (V.stAt: where the editor's table of strokes is in
// the grain records, + 1; 0: the records carry their color -- the engine's, an area's copies): a record's top three bytes
// its stroke's number, the table eight words a number -- its first record, how many, its kind, layer and whether drawn,
// its half width, its color, where its grain starts, its erase slot's entry (NONE: none), its length (stw, colorOf).
// A STROKE THE CARD IS CUTTING (ERASE below) is drawn in its own place by the page's own draws: once it is cut its
// records carry the flag CUT (16), and its number's slot entry is in the table of strokes being cut, in the grain records
// at V.evAt -- eight words an entry: its first record, how many, where its map is, where its pieces are, where their
// grain is. Its map, a word a point: which of its pieces' records came from that point's segment (where the first is,
// << 3, and how many). cutAt(i) -> where record i's pieces' records are (<< 3) and how many, or NONE. A
// pen's segment that is cut is drawn once, over all of it: a pixel is inked when one of the parts the segment keeps (its
// pieces' segments, four at the most, all of one color) inks it, as the pieces will (cutSeg, fsSeg). A highlighter's
// record draws each part as its own shape (hlPart), a grain or wash stroke's each part at its piece's own depth (vsOwn):
// nothing of which strokes are cut is known to the processor. Each part is drawn AS THE SEGMENT IT LIES ON DRAWS: that
// segment's width, its grain's density along it, a highlighter's bevel at its point by the point before it -- a cut changes
// no pixel farther from the eraser than its reach; the pieces' own widths (a new end takes the width of the point beyond
// it) are drawn once they are made strokes
const NONE: u32 = 0xffffffffu;
const EDGE: f32 = 0.015625;                                  // (a 64th of a pixel: a shape's room past its ink)
fn ew(w: u32) -> u32 { let g = grb[V.evAt + (w >> 1u)]; return select(g.x, g.y, (w & 1u) == 1u); }
fn stw(sid: u32, w: u32) -> u32 { let g = grb[V.stAt - 1u + sid * 4u + (w >> 1u)]; return select(g.x, g.y, (w & 1u) == 1u); }
fn colorOf(w: u32) -> u32 { if (V.stAt == 0u) { return w >> 8u; } return stw(w >> 8u, 4u); }
fn cutEntry(i: u32) -> u32 {                                 // the entry (its first word) of the cut stroke i is of, or NONE
  let r = rec[i].w;
  if ((r & 16u) == 0u) { return NONE; }
  let e0 = stw(r >> 8u, 6u);
  if (e0 == NONE) { return NONE; }
  let e = 8u * e0; let b = ew(e);
  if (i < b || i >= b + ew(e + 1u)) { return NONE; }
  return e;
}
fn cutOf(i: u32, e: u32) -> u32 {                             // record i's pieces' records (<< 3) and how many, by its entry
  let k = i - ew(e);
  let w = rec[ew(e + 2u) + (k >> 2u)][k & 3u];
  return ((ew(e + 3u) + (w >> 3u)) << 3u) | (w & 7u);
}
fn cutAt(i: u32) -> u32 {
  let e = cutEntry(i);
  if (e == NONE) { return NONE; }
  return cutOf(i, e);
}
fn partRec(c: u32, part: u32) -> u32 {                        // of those records, the part-th that starts a segment (or NONE)
  var k = 0u;
  for (var q = 0u; q < (c & 7u); q++) {
    let r = (c >> 3u) + q;
    if ((rec[r].w & 1u) == 0u) { continue; }
    if (k == part) { return r; }
    k += 1u;
  }
  return NONE;
}
// A STROKE THE CARD IS CUTTING, DRAWN BY RANGE (its entry's word 7: how many stretches it keeps, the top bit clear): its
// pieces are not written while the swipe goes. Each stretch is two records at its entry's word 3 (ERASE's spans: where
// it starts, where it ends -- the record j, the place t along the segment, the point; bit 31 of the start's j the record
// beside its new start dropped, bit 30 its new end dropped). Each part of a cut segment is drawn from the
// stroke's own records and those ends as ERASE's pieces will write the piece once the swipe is let go: the same records,
// flags and turns, bit for bit (vraw, vrec), the same of them for each point as the pieces' map has them (candQ: a new start
// for the segment it lies on, the point for itself, a new end for the segment it lies on), seven at the most. Once the
// pieces are written (the top bit set) they are drawn where they lie
fn byRange(e: u32) -> bool { return (ew(e + 7u) >> 31u) == 0u; }
fn vt(e: u32, m: u32, w: u32) -> vec4<u32> { return rec[ew(e + 3u) + 2u * m + w]; }
struct Pc { b: u32, j0: u32, j1: u32, h: bool, t: bool, i0: u32, total: u32, n: u32, hd: bool, td: bool, s0: vec4<u32>, s1: vec4<u32> };
fn pcOf(e: u32, m: u32) -> Pc {                              // stretch m's piece
  let s0 = vt(e, m, 0u); let s1 = vt(e, m, 1u); let j0 = s0.x & 0x3fffffffu;
  let h = bitcast<f32>(s0.y) > 0.0; let t = bitcast<f32>(s1.y) > 0.0; let i0 = select(j0, j0 + 1u, h);
  let hd = (s0.x >> 31u) == 1u; let td = ((s0.x >> 30u) & 1u) == 1u;
  let total = select(0u, 1u, h) + (s1.x + 1u - i0) + select(0u, 1u, t);
  return Pc(ew(e), j0, s1.x, h, t, i0, total, total - select(0u, 1u, hd) - select(0u, 1u, td), hd, td, s0, s1);
}
fn vsrc(c: Pc, q: u32) -> u32 {                              // its record q's source (a new start: the point beyond it; a new end too)
  let qr = q + select(0u, 1u, c.hd && q >= 1u);
  if (c.h && qr == 0u) { return c.i0; }
  if (c.t && qr == c.total - 1u) { return c.j1 + 1u; }
  return c.i0 + qr - select(0u, 1u, c.h);
}
fn vraw(c: Pc, q: u32) -> vec4<u32> {                        // its record q as pieces writes it, before a highlighter's turns
  let qr = q + select(0u, 1u, c.hd && q >= 1u);
  var r = rec[c.b + vsrc(c, q)];
  if (c.h && qr == 0u) { r.x = c.s0.z; r.y = c.s0.w; }
  else if (c.t && qr == c.total - 1u) { r.x = c.s1.z; r.y = c.s1.w; }
  r.w = r.w & 0xffffffefu;
  if (q == c.n - 1u) { r.w = r.w & 0xffffff00u; } else if (q == 0u) { r.w = (r.w & 0xffffff00u) | 1u; }
  return r;
}
fn turnOf(p0: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> u32 {   // a highlighter's flags at a (ERASE's turnAt)
  var e = a - p0; var Ln = sqrt(dot(e, e));
  let pdx = e.x / Ln; let pdy = e.y / Ln;
  e = b - a; Ln = sqrt(dot(e, e));
  let cross = pdx * (e.y / Ln) - pdy * (e.x / Ln);
  if (abs(cross) >= 1e-6) { return select(5u, 13u, cross > 0.0); }
  return 1u;
}
fn vrec(c: Pc, q: u32, hl: bool) -> vec4<u32> {              // its record q, a highlighter's turns beside its new ends worked out
  var r = vraw(c, q);
  if (hl && c.n > 2u && ((c.h && q == 1u) || (c.t && !c.td && q == c.n - 2u))) {
    r.w = (r.w & 0xffffff00u) | turnOf(xyOf(vraw(c, q - 1u)), xyOf(r), xyOf(vraw(c, q + 1u)));
  }
  return r;
}
fn candQ(c: Pc, k: u32, x: u32) -> u32 {                     // its record for point k: x 0 its new start, 1 the point, 2 its new end
  if (x == 0u) { return select(NONE, 0u, c.h && c.j0 == k); }
  if (x == 1u) {
    if (k < c.i0 || k > c.j1) { return NONE; }
    let qr = k - c.i0 + select(0u, 1u, c.h);
    if (c.hd && qr == 1u) { return NONE; }
    return qr - select(0u, 1u, c.hd && qr > 1u);
  }
  return select(NONE, c.n - 1u, c.t && !c.td && c.j1 == k);
}
fn spanFirst(e: u32, k: u32) -> u32 {                         // the first stretch whose last record is point k or after
  var lo = 0u; var hi = ew(e + 7u) & 0xffffffu;
  while (lo < hi) { let md = (lo + hi) >> 1u; if (vt(e, md, 1u).x < k) { lo = md + 1u; } else { hi = md; } }
  return lo;
}
fn cutSegR(i: u32, e: u32, v: u32, O: Own) -> VS {            // cutSeg, by range
  var P = array<vec4<f32>, 4>(vec4<f32>(0.0), vec4<f32>(0.0), vec4<f32>(0.0), vec4<f32>(0.0));
  var R = array<f32, 4>(0.0, 0.0, 0.0, 0.0);
  var np = 0u; var col = 0u; var w = 0.0;
  let k = i - ew(e); let nA = ew(e + 7u) & 0xffffffu;
  var seen = 0u;
  for (var m = spanFirst(e, k); m < nA && seen < 7u; m++) {
    let c = pcOf(e, m);
    if (c.j0 > k) { break; }
    for (var x = 0u; x < 3u && seen < 7u; x++) {
      let q = candQ(c, k, x);
      if (q == NONE) { continue; }
      seen += 1u;
      let A = vraw(c, q);
      if ((A.w & 1u) == 0u || np >= 4u) { continue; }
      col = A.w;
      let B = vraw(c, q + 1u);
      P[np] = vec4<f32>(xyOf(A) * V.k + V.off, xyOf(B) * V.k + V.off);
      R[np] = (bitcast<f32>(A.z) + bitcast<f32>(B.z)) * 0.25 * V.k; w = max(w, R[np]); np += 1u;
    }
  }
  return cutShape(i, P, R, np, col, w, v, O);
}
fn partR(e: u32, k: u32, part: u32, hl: bool) -> vec2<u32> {   // by range: the part-th record of point k that starts a segment -> (stretch, q), or NONE
  var seen = 0u; var found = 0u;
  for (var m = spanFirst(e, k); m < (ew(e + 7u) & 0xffffffu) && seen < 7u; m++) {
    let c = pcOf(e, m);
    if (c.j0 > k) { break; }
    for (var x = 0u; x < 3u && seen < 7u; x++) {
      let q = candQ(c, k, x);
      if (q == NONE) { continue; }
      seen += 1u;
      if ((vraw(c, q).w & 1u) == 0u) { continue; }               // (a turn changes no segment's start)
      if (found == part) { return vec2<u32>(m, q); }
      found += 1u;
    }
  }
  return vec2<u32>(NONE, NONE);
}
fn hlPartR(i: u32, e: u32, part: u32, v: u32, z: f32) -> VH {   // hlPart, by range
  let mq = partR(e, i - ew(e), part, true);
  if (mq.x == NONE) { var o: VH; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  let c = pcOf(e, mq.x); let A = vrec(c, mq.y, true);
  var Pp = A; if ((A.w & 4u) != 0u) { Pp = vraw(c, mq.y - 1u); }
  return hlCore(A, vraw(c, mq.y + 1u), Pp, v, z);
}
fn ownPartR(i: u32, e: u32, part: u32, v: u32, O: Own, key: u32) -> VS {   // a grain or wash stroke's part, by range (pieceAt)
  let mq = partR(e, i - ew(e), part, false);
  if (mq.x == NONE) { var o: VS; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  let c = pcOf(e, mq.x); let q = mq.y;
  let grainOf = (stw(rec[i].w >> 8u, 2u) & 0xffu) == 2u;     // (a grain stroke's density at the point it came from; a wash's 1)
  var da = 1.0; var db = 1.0;
  if (grainOf) { da = bitcast<f32>(grb[O.gfirst + vsrc(c, q)].x); db = bitcast<f32>(grb[O.gfirst + vsrc(c, q + 1u)].x); }
  var ga = vec2<f32>(1.0, 0.0); var gb = vec2<f32>(1.0, 0.0);
  if ((O.grain & 1u) != 0u) { ga.x = da; gb.x = db; }
  let z = select(O.depth - f32(mq.x) / 65535.0, keyZ(key + mq.x), key != NONE);
  return segQuad(vraw(c, q), vraw(c, q + 1u), v, O, ga, gb, z, -1.0);
}
// THE VIEW'S OFFSET IN TWO: whole pixels (V.io) and the rest (V.off). Strokes are placed by the rest alone and each pixel
// decided from its place less the whole pixels, so a view moved by whole pixels decides every pixel as it did (a scroll
// moves what is drawn and draws only what it brings in: the editor's scroll); clip puts the whole pixels back
fn clip(p: vec2<f32>, z: f32) -> vec4<f32> { let q = p + V.io; return vec4<f32>(q.x / V.size.x * 2.0 - 1.0, 1.0 - q.y / V.size.y * 2.0, z, 1.0); }
struct VS { @builtin(position) pos: vec4<f32>, @location(0) @interpolate(flat, either) ab: vec4<f32>, @location(1) @interpolate(flat, either) rc: vec4<f32>,
            @location(2) @interpolate(flat, either) g: vec4<f32>, @location(3) @interpolate(flat, either) grainOn: u32, @location(4) @interpolate(flat, either) alpha: f32,
            @location(5) @interpolate(flat, either) x1: vec4<f32>, @location(6) @interpolate(flat, either) x2: vec4<f32>,
            @location(7) @interpolate(flat, either) x3: vec4<f32>, @location(8) @interpolate(flat, either) xr: vec4<f32>,
            @location(9) @interpolate(flat, either) np: u32 };
// PEN STROKES, where: each segment a rectangle laid over it a hair wider than the pen (r + EDGE pixels each way); record
// i's segment, corner v, drawn by row O of the frame's table
@vertex fn vsSeg(@builtin(vertex_index) vi: u32, @builtin(instance_index) j: u32) -> VS {
  return segOrCut(j, vi % 16u, owns[vi / 16u]);
}
fn segOrCut(i: u32, v: u32, O: Own) -> VS {
  let e = cutEntry(i);
  if (e == NONE) { return segAt(i, v, O); }
  if (byRange(e)) { return cutSegR(i, e, v, O); }
  return cutSeg(i, cutOf(i, e), v, O);
}
// a pen's segment the card has cut: the parts it keeps (each a piece's segment, as wide as the piece's own points make it,
// as the piece will draw), the shape laid over all of the segment
fn cutSeg(i: u32, c: u32, v: u32, O: Own) -> VS {
  var o: VS;
  var P = array<vec4<f32>, 4>(vec4<f32>(0.0), vec4<f32>(0.0), vec4<f32>(0.0), vec4<f32>(0.0));
  var R = array<f32, 4>(0.0, 0.0, 0.0, 0.0);
  var np = 0u; var col = 0u; var w = 0.0;
  let s = c >> 3u;
  for (var q = 0u; q < (c & 7u); q++) {
    let A = rec[s + q];
    if ((A.w & 1u) == 0u || np >= 4u) { continue; }
    col = A.w;
    let B = rec[s + q + 1u];
    P[np] = vec4<f32>(xyOf(A) * V.k + V.off, xyOf(B) * V.k + V.off);
    R[np] = (bitcast<f32>(A.z) + bitcast<f32>(B.z)) * 0.25 * V.k; w = max(w, R[np]); np += 1u;
  }
  return cutShape(i, P, R, np, col, w, v, O);
}
fn cutShape(i: u32, P: array<vec4<f32>, 4>, R: array<f32, 4>, np: u32, col: u32, w: f32, v: u32, O: Own) -> VS {   // over all of segment i
  var o: VS;
  if (np == 0u) { o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  let A = rec[i]; let B = rec[i + 1u];
  let a = xyOf(A) * V.k + V.off; let b = xyOf(B) * V.k + V.off;
  let d = b - a; let L = length(d);
  let u = select(vec2<f32>(1.0, 0.0), d / L, L > 0.0); let n = vec2<f32>(-u.y, u.x);
  let m = w + EDGE;
  let cx = select(-1.0, 1.0, (v & 1u) == 1u); let cy = select(-1.0, 1.0, v >= 2u);
  o.pos = clip(select(b + u * m, a - u * m, cx < 0.0) + n * (cy * m), O.depth);
  o.ab = P[0]; o.x1 = P[1]; o.x2 = P[2]; o.x3 = P[3]; o.xr = vec4<f32>(R[1], R[2], R[3], 0.0); o.np = np;
  let cc = colorOf(col);
  o.rc = vec4<f32>(R[0], f32(cc & 0xffu) / 255.0, f32((cc >> 8u) & 0xffu) / 255.0, f32((cc >> 16u) & 0xffu) / 255.0);
  o.g = vec4<f32>(1.0, 1.0, 0.0, V.k); o.grainOn = 0u; o.alpha = O.alpha;
  return o;
}
fn segAt(i: u32, v: u32, O: Own) -> VS {
  // grain bit 0: grain on; bit 1 (a stroke's pieces in one draw): each piece at its own depth, its number along in its
  // grain record's second number (the editor's only; the engine never sets it)
  var ga = vec2<f32>(1.0, 0.0); var gb = vec2<f32>(1.0, 0.0); var z = O.depth;
  if ((O.grain & 3u) != 0u) { let gi = O.gfirst + (i - O.first); ga = bitcast<vec2<f32>>(grb[gi]); gb = bitcast<vec2<f32>>(grb[gi + 1u]); }
  if ((O.grain & 2u) != 0u) { z = O.depth - ga.y / 65535.0; }
  return segCore(i, v, O, ga, gb, z, -1.0);
}
// a cut stroke's part (its piece's record r, on segment j) draws as the piece will: its own points' widths, its grain's
// densities as the piece's own grain records have them (at gi: a new end the point's beyond it), the piece's depth (its
// number along, its grain record's second number; key: a listed draw's, the stroke's place in the page's order, the
// piece n places after it -- NONE: the frame's table's depth) -- what is shown while the swipe goes is what it leaves
fn pieceAt(r: u32, j: u32, v: u32, O: Own, gi: u32, key: u32) -> VS {
  let g0 = bitcast<vec2<f32>>(grb[gi]);
  var ga = vec2<f32>(1.0, 0.0); var gb = vec2<f32>(1.0, 0.0);
  if ((O.grain & 1u) != 0u) { ga.x = g0.x; gb.x = bitcast<vec2<f32>>(grb[gi + 1u]).x; }
  let z = select(O.depth - g0.y / 65535.0, keyZ(key + u32(g0.y)), key != NONE);
  return segCore(r, v, O, ga, gb, z, -1.0);
}
fn segCore(i: u32, v: u32, O: Own, ga: vec2<f32>, gb: vec2<f32>, z: f32, rw: f32) -> VS {   // (rw >= 0: its half width)
  let A = rec[i];
  let fa = A.w & 0xffu;
  if ((fa & 3u) == 0u) { var o: VS; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  return segQuad(A, rec[i + 1u], v, O, ga, gb, z, rw);
}
fn segQuad(A: vec4<u32>, B: vec4<u32>, v: u32, O: Own, ga: vec2<f32>, gb: vec2<f32>, z: f32, rw: f32) -> VS {   // (A a segment's start, or a dot)
  var o: VS;
  let fa = A.w & 0xffu; let dt = (fa & 2u) != 0u;
  if ((fa & 3u) == 0u) { o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  let pa = xyOf(A); let wa = bitcast<f32>(A.z); let pb = xyOf(B); let wb = bitcast<f32>(B.z);
  let a = pa * V.k + V.off; let b = select(pb, pa, dt) * V.k + V.off;
  let r = select(select((wa + wb) * 0.25, wa * 0.5, dt), rw, rw >= 0.0) * V.k;
  let d = b - a; let L = length(d);
  let u = select(vec2<f32>(1.0, 0.0), d / L, L > 0.0); let n = vec2<f32>(-u.y, u.x);
  let m = r + EDGE;
  let cx = select(-1.0, 1.0, (v & 1u) == 1u); let cy = select(-1.0, 1.0, v >= 2u);
  let p = select(b + u * m, a - u * m, cx < 0.0) + n * (cy * m);
  o.pos = clip(p, z);
  o.ab = vec4<f32>(a, b);
  let c = colorOf(A.w);
  o.rc = vec4<f32>(r, f32(c & 0xffu) / 255.0, f32((c >> 8u) & 0xffu) / 255.0, f32((c >> 16u) & 0xffu) / 255.0);
  o.g = vec4<f32>(ga.x, select(gb.x, ga.x, dt), ga.y * V.k, V.k);
  o.grainOn = O.grain & 1u; o.alpha = O.alpha; o.np = 1u;
  return o;
}
// GRAIN AND WASH STROKES, each a draw of its own at its own depth: six corners a part (the two triangles of segAt's
// four), four parts a record, 32 vertex numbers a row of the frame's table. A record not cut draws part 0 as segAt; one
// the card has cut, each part its segment keeps as its piece draws it (pieceAt)
@vertex fn vsOwn(@builtin(vertex_index) vi: u32, @builtin(instance_index) j: u32) -> VS {
  let O = owns[vi / 32u];
  let w = vi % 32u; let part = w / 6u; let k = w % 6u;
  let v = select(select(k, 2u, k == 3u), select(1u, 3u, k == 5u), k >= 4u);   // (0 1 2, 2 1 3)
  let e = cutEntry(j);
  if (e == NONE) {
    if (part != 0u) { var o: VS; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
    return segAt(j, v, O);
  }
  if (byRange(e)) { return ownPartR(j, e, part, v, O, NONE); }
  let r = partRec(cutOf(j, e), part);
  if (r == NONE) { var o: VS; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  return pieceAt(r, j, v, O, ew(e + 4u) + (r - ew(e + 3u)), NONE);
}
fn mixh(h0: u32) -> u32 { var h = h0; h ^= h >> 16u; h *= 0x7feb352du; h ^= h >> 15u; h *= 0x846ca68bu; h ^= h >> 16u; return h; }
fn hash01(s: u32, a: i32, b: i32) -> f32 { return f32(mixh(s ^ mixh((u32(a) * 0x9e3779b9u) ^ mixh(u32(b) + 0x85ebca6bu)))) / 4294967296.0; }
// PEN STROKES, which pixels: a pixel is inked when its CENTER is within r of the segment; grain by the page's cell
fn within(p: vec2<f32>, ab: vec4<f32>, r: f32) -> f32 {     // where along a segment a pixel within r of it is (else -1)
  let a = ab.xy; let b = ab.zw; let d = b - a;
  let L2 = dot(d, d); let tu = select(0.0, dot(p - a, d) / L2, L2 > 0.0); let t = clamp(tu, 0.0, 1.0);
  let e = p - (a + t * d);
  return select(t, -1.0, dot(e, e) > r * r);
}
@fragment fn fsSeg(i: VS) -> @location(0) vec4<f32> {
  let p = i.pos.xy - V.io;
  var t = within(p, i.ab, i.rc.x);
  if (t < 0.0 && i.np > 1u) {                                  // a cut segment: any of the parts it keeps
    if (within(p, i.x1, i.xr.x) >= 0.0 || (i.np > 2u && within(p, i.x2, i.xr.y) >= 0.0) || (i.np > 3u && within(p, i.x3, i.xr.z) >= 0.0)) { t = 0.0; }
  }
  if (t < 0.0) { discard; }
  var ink = 1.0;
  if (i.grainOn == 1u) {
    let den = (i.g.x + (i.g.y - i.g.x) * t);
    if (den < 1.0) {
      if (den <= 0.0) { ink = 0.0; }
      else { let cell = vec2<i32>(floor((p - V.off) / V.k)); ink = select(0.0, 1.0, hash01(0x2545f491u, cell.x, cell.y) < den); }
    }
  }
  return vec4<f32>(i.rc.yzw, ink * i.alpha);
}
struct VH { @builtin(position) pos: vec4<f32>, @location(0) @interpolate(flat, either) cs: u32,
            @location(1) @interpolate(flat, either) q01: vec4<f32>, @location(2) @interpolate(flat, either) q2: vec2<f32>,
            @location(3) @interpolate(flat, either) t1: vec2<f32> };
// HIGHLIGHTERS, where: each record one quad round its rectangle and its bevel (hlAt), indexed as two triangles (0 1 2,
// 0 2 3), and the editor's index list has it four times over, 16 vertex numbers apart: a record's parts (hlPart), each
// the shape of a piece's record (64 a run of a culled draw)
@vertex fn vsHl(@builtin(vertex_index) vi: u32, @builtin(instance_index) j: u32) -> VH {
  return hlPart(j, vi % 64u, 0.0);
}
fn hlPart(i: u32, w: u32, z: f32) -> VH {                    // record i's part w / 16, its corner w % 16, at depth z
  let part = w / 16u;
  let e = cutEntry(i);
  if (e == NONE) {
    if (part != 0u) { var o: VH; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
    return hlAt(i, w % 16u, z);
  }
  if (byRange(e)) { return hlPartR(i, e, part, w % 16u, z); }
  let r = partRec(cutOf(i, e), part);
  if (r == NONE) { var o: VH; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  return hlAt(r, w % 16u, z);                                // (as its piece will draw it: its own widths, its own turns)
}
// record i's shape, corner v (0..3), at depth z (hlCore: the record, the next and the one before in hand). In the target's
// pixels, as render.c makes them: its rectangle sa+n, sb+n,
// sb-n, sa-n (its ends and n to fsHl: they always wind the one way) and, where its flags say it turns, its bevel, the
// triangle sa, t1, sa + s n against the rectangle's start (t1 to fsHl, with s and the sign of its area) -- one quad laid
// round both, along and across the segment, a hair out
fn hlAt(i: u32, v: u32, z: f32) -> VH {
  let A = rec[i]; let fa = A.w & 0xffu;
  if ((fa & 1u) == 0u || v >= 4u) { var o: VH; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  var Pp = A; if ((fa & 4u) != 0u) { Pp = rec[i - 1u]; }
  return hlCore(A, rec[i + 1u], Pp, v, z);
}
fn hlCore(A: vec4<u32>, B: vec4<u32>, Pp: vec4<u32>, v: u32, z: f32) -> VH {
  var o: VH;
  let fa = A.w & 0xffu;
  if ((fa & 1u) == 0u || v >= 4u) { o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  let a = xyOf(A); let wa = bitcast<f32>(A.z); let b = xyOf(B);
  let hw = (wa + bitcast<f32>(B.z)) * 0.25 + V.eps;
  let d = b - a; let L = length(d);
  let u = select(vec2<f32>(1.0, 0.0), d / L, L > 0.0); let nu = vec2<f32>(-u.y, u.x);
  let K = V.k; let sa = a * K + V.off; let sb = b * K + V.off; let n = nu * hw * K;
  var back = 0.0; var lo = -hw * K; var hi = hw * K;            // (the quad: back from sa along -u, across from lo to hi)
  o.cs = 0u; o.t1 = sa;
  if ((fa & 4u) != 0u) {
    let s = select(1.0, -1.0, (fa & 8u) != 0u);
    let pp = xyOf(Pp); let wp = bitcast<f32>(Pp.z);
    let qq = a - pp; let Lq = length(qq); let wq = select(vec2<f32>(1.0, 0.0), qq / Lq, Lq > 0.0);
    let t1 = sa + s * vec2<f32>(-wq.y, wq.x) * ((wp + wa) * 0.25 + V.eps) * K; let t2 = sa + s * n;
    let area = (sa.x * t1.y - t1.x * sa.y) + (t1.x * t2.y - t2.x * t1.y) + (t2.x * sa.y - sa.x * t2.y);
    if (abs(area) >= 1e-12) {
      o.t1 = t1; o.cs = (select(0u, 2u, s < 0.0) | select(0u, 4u, area > 0.0) | 1u) << 24u;
      let r = t1 - sa; back = max(0.0, -dot(r, u)); lo = min(lo, dot(r, nu)); hi = max(hi, dot(r, nu));
    }
  }
  let along = select(-back - EDGE, L * K + EDGE, v == 1u || v == 2u); let across = select(lo - EDGE, hi + EDGE, v < 2u);
  o.pos = clip(sa + u * along + nu * across, z);
  o.q01 = vec4<f32>(sa, sb); o.q2 = n;
  o.cs |= colorOf(A.w) & 0xffffffu;                           // (its color; above it 1 a bevel, 2 its s -1, 4 its area > 0)
  return o;
}
// is p on the inner side of the edge q -> r (its sign sg), or exactly on it and it faces up or left -- render.c's
// convex(), an edge at a time?
fn edgeIn(p: vec2<f32>, q: vec2<f32>, r: vec2<f32>, sg: f32) -> bool {
  let ex = (r.x - q.x) * sg; let ey = (r.y - q.y) * sg;
  let e = ex * (p.y - q.y) - ey * (p.x - q.x);
  return e > 0.0 || (e == 0.0 && (ey > 0.0 || (ey == 0.0 && ex < 0.0)));
}
// HIGHLIGHTERS, which pixels: a pixel is inked when its CENTER is inside the rectangle or the bevel, each edge taken as
// render.c's convex() takes it; drawn with a per-channel MINIMUM (darken) blend
@fragment fn fsHl(i: VH) -> @location(0) vec4<f32> {
  let p = i.pos.xy - V.io; let k = i.cs >> 24u;
  let n = i.q2; let q0 = i.q01.xy + n; let q1 = i.q01.zw + n; let q2 = i.q01.zw - n; let q3 = i.q01.xy - n;
  var ink = edgeIn(p, q0, q1, -1.0) && edgeIn(p, q1, q2, -1.0) && edgeIn(p, q2, q3, -1.0) && edgeIn(p, q3, q0, -1.0);
  if (!ink && (k & 1u) != 0u) {
    let sa = i.q01.xy; let t2 = sa + select(1.0, -1.0, (k & 2u) != 0u) * n; let sg = select(-1.0, 1.0, (k & 4u) != 0u);
    ink = edgeIn(p, sa, i.t1, sg) && edgeIn(p, i.t1, t2, sg) && edgeIn(p, t2, sa, sg);
  }
  if (!ink) { discard; }
  let c = i.cs;
  return vec4<f32>(f32(c & 0xffu), f32((c >> 8u) & 0xffu), f32((c >> 16u) & 0xffu), 255.0) / 255.0;
}
// A CULLED DRAW (CULL below): run k (its vertex number over 16, a highlighters' over 64: the draw's first vertex, or its
// base vertex) draws the blocks of its records that reach the area, as CULL packed them -- instance j the record j % 16
// of block clist[s0 + j / 16] (s0: where the run's blocks start in the list); a record of the block outside the run
// draws nothing
@group(2) @binding(0) var<storage, read> clist: array<u32>;
@group(2) @binding(1) var<storage, read> runs: array<vec4<u32>>;
fn culledIn(T: vec4<u32>, j: u32) -> u32 {
  let i = clist[T.z + j / 16u] * 16u + j % 16u;
  return select(NONE, i, i >= T.x && i < T.y);
}
fn culled(vi: u32, j: u32) -> u32 { return culledIn(runs[vi / 16u], j); }
@vertex fn vsSegC(@builtin(vertex_index) vi: u32, @builtin(instance_index) j: u32) -> VS {
  let i = culled(vi, j);
  if (i == NONE) { var o: VS; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  return segOrCut(i, vi % 16u, owns[0]);
}
@vertex fn vsHlC(@builtin(vertex_index) vi: u32, @builtin(instance_index) j: u32) -> VH {
  let i = culledIn(runs[vi / 64u], j);
  if (i == NONE) { var o: VH; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  return hlPart(i, vi % 64u, 0.0);
}
// LISTED DRAWS (the editor's, where the card culls: LISTS in CULL below): a few draws for the whole page, however many
// strokes it has -- its pens in one, then for each level its highlighters in one and its grain and wash strokes in one
// (the level a run of highlighters and the grain or wash strokes after it, in the page's order). Each a list of blocks
// of the page's records, the card's own, in the page's order -- an entry a block and the span of the page it is listed
// for (a record of the block outside the span draws nothing); the draw's first vertex (a highlighter's base vertex) is
// where its list starts, times 16 (32, 64). Every stroke is drawn at the depth of its place in the page's order (its
// KEY, worked out on the card: SK in the grain records, LVU.skAt), so a pen drawn after a later one, in any order, is
// still under it, and what lies over what is as the page's order has it: the pens first, each over what is earlier
// (depth test), then a highlighter only where nothing later lies (darken, depth tested, not written), then grain and
// wash strokes in the page's order, each over what is earlier and deciding each pixel once (depth tested and written).
// A stroke's own facts from the table of strokes: its grain's place, its first record, its wash's alpha (the color
// word's top byte, LVU's table of the 256 alphas, as the processor works them out)
@group(2) @binding(2) var<storage, read> lst: array<vec2<u32>>;
@group(2) @binding(3) var<storage, read> spn: array<vec4<u32>>;
struct LV { skAt: u32, p1: u32, p2: u32, p3: u32, alpha: array<vec4<f32>, 64> };
@group(2) @binding(4) var<uniform> LVU: LV;
fn keyZ(key: u32) -> f32 { return bitcast<f32>(0x3f7fffffu - key); }   // a key's depth: each key its own, a later one nearer
fn listed(vi: u32, per: u32, j: u32) -> u32 {                // the record instance j of a listed draw draws (or NONE)
  let e = lst[vi / per + j / 16u];
  let i = e.x * 16u + j % 16u;
  let S = spn[e.y];
  return select(NONE, i, i >= S.x && i < S.y);
}
fn keyOf(i: u32) -> u32 { return grb[LVU.skAt + (rec[i].w >> 8u)].x; }
@vertex fn vsPenL(@builtin(vertex_index) vi: u32, @builtin(instance_index) j: u32) -> VS {
  let i = listed(vi, 16u, j);
  if (i == NONE) { var o: VS; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  return segOrCut(i, vi % 16u, Own(0u, 0u, 0u, 1.0, keyZ(keyOf(i))));
}
@vertex fn vsHlL(@builtin(vertex_index) vi: u32, @builtin(instance_index) j: u32) -> VH {
  let i = listed(vi, 64u, j);
  if (i == NONE) { var o: VH; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  return hlPart(i, vi % 64u, keyZ(keyOf(i)));
}
@vertex fn vsOwnL(@builtin(vertex_index) vi: u32, @builtin(instance_index) j: u32) -> VS {
  let i = listed(vi, 32u, j);
  if (i == NONE) { var o: VS; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  let sid = rec[i].w >> 8u; let key = grb[LVU.skAt + sid].x;
  let gs = stw(sid, 5u); let a = stw(sid, 4u) >> 24u;
  let O = Own(select(1u, 0u, gs == NONE), gs, stw(sid, 0u), LVU.alpha[a / 4u][a % 4u], keyZ(key));
  let w = vi % 32u; let part = w / 6u; let k = w % 6u;
  let v = select(select(k, 2u, k == 3u), select(1u, 3u, k == 5u), k >= 4u);   // (0 1 2, 2 1 3)
  let e = cutEntry(i);
  if (e == NONE) {
    if (part != 0u) { var o: VS; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
    return segAt(i, v, O);
  }
  if (byRange(e)) { return ownPartR(i, e, part, v, O, key); }
  let r = partRec(cutOf(i, e), part);
  if (r == NONE) { var o: VS; o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  return pieceAt(r, i, v, O, ew(e + 4u) + (r - ew(e + 3u)), key);
}
// THE MASK'S DRAW (ERASE's mk): each record it lists marks every pixel its ink can have touched -- within half its widest
// width there (a highlighter's turn by the segment before's), its wash's reach and EDGE pixels, of its segment (a band with
// round ends: fsMask; its box is within the mask's box, so every stroke that can ink a pixel it marks is drawn) -- at the
// farthest depth (1), where the depth was cleared to the nearest (0): only there do the page's draws after it pass
@group(2) @binding(5) var<storage, read> mkr: array<u32>;
fn unord(u: u32) -> f32 { return bitcast<f32>(select(~u, u ^ 0x80000000u, (u >> 31u) == 1u)); }
@vertex fn vsMask(@builtin(vertex_index) v: u32, @builtin(instance_index) j: u32) -> VS {
  var o: VS;
  if (mkr[5] != 0u) {                                         // more records than the mask has room for (CULL's listArgs):
    let lo = vec2<f32>(unord(mkr[1]), unord(mkr[2])) * V.k + V.off - vec2<f32>(2.0);   // its box marked, all of it -- every
    let hi = vec2<f32>(unord(mkr[3]), unord(mkr[4])) * V.k + V.off + vec2<f32>(2.0);   // record's ink is in it (maskBox)
    let c = select(lo, hi, vec2<bool>((v & 1u) == 1u, v >= 2u));
    o.pos = clip(c, 1.0); o.ab = vec4<f32>(c, c); o.rc = vec4<f32>(1e18, 0.0, 0.0, 0.0);
    return o;
  }
  let i = mkr[16u + j];
  let A = rec[i]; let f = A.w & 0xffu;
  if ((f & 3u) == 0u) { o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }
  let a = xyOf(A); var b = a; var w = bitcast<f32>(A.z);
  if ((f & 1u) != 0u) { let B = rec[i + 1u]; b = xyOf(B); w = max(w, bitcast<f32>(B.z)); }
  if ((f & 4u) != 0u) { w = max(w, bitcast<f32>(rec[i - 1u].z)); }
  let pa = a * V.k + V.off; let pb = b * V.k + V.off;
  let m = (w * 0.5 + 0.35) * V.k + EDGE;
  let d = pb - pa; let L = length(d);
  let u = select(vec2<f32>(1.0, 0.0), d / L, L > 0.0); let n = vec2<f32>(-u.y, u.x);
  let cx = select(-1.0, 1.0, (v & 1u) == 1u); let cy = select(-1.0, 1.0, v >= 2u);
  o.pos = clip(select(pb + u * m, pa - u * m, cx < 0.0) + n * (cy * m), 1.0);
  o.ab = vec4<f32>(pa, pb); o.rc = vec4<f32>(m, 0.0, 0.0, 0.0);
  return o;
}
@fragment fn fsMask(i: VS) -> @location(0) vec4<f32> {
  if (within(i.pos.xy - V.io, i.ab, i.rc.x) < 0.0) { discard; }
  return vec4<f32>(0.0);
}
`,
  // WHAT IS UNDER THE INK copied onto the working canvas first; the working canvas averaged down to the screen (AREA)
  COPY: `
@group(0) @binding(0) var under: texture_2d<f32>;
struct VF { @builtin(position) pos: vec4<f32> };
@vertex fn vsFull(@builtin(vertex_index) v: u32) -> VF {
  var o: VF; o.pos = vec4<f32>(select(-1.0, 3.0, v == 1u), select(-1.0, 3.0, v == 2u), 0.0, 1.0); return o;
}
@fragment fn fsCopy(i: VF) -> @location(0) vec4<f32> { return vec4<f32>(textureLoad(under, vec2<i32>(i.pos.xy), 0).rgb, 1.0); }
`,
  AREA: `
struct A { W: i32, cw: i32, h: i32, g: i32 };               // (g: W's and cw's greatest common divisor, all the weights'
                                                             // too -- divided out, the sums stay within 32 bits)
@group(0) @binding(0) var tex: texture_2d<f32>;
@group(0) @binding(1) var<uniform> U: A;
struct VF { @builtin(position) pos: vec4<f32> };
@vertex fn vsFull(@builtin(vertex_index) v: u32) -> VF {
  var o: VF; o.pos = vec4<f32>(select(-1.0, 3.0, v == 1u), select(-1.0, 3.0, v == 2u), 0.0, 1.0); return o;
}
@fragment fn fsArea(i: VF) -> @location(0) vec4<f32> {
  let x = i32(i.pos.x); let y = i32(i.pos.y); let W = U.W; let cw = U.cw;
  let i0 = (x * W) / cw; let i1 = ((x + 1) * W - 1) / cw; let j0 = (y * W) / cw; let j1 = ((y + 1) * W - 1) / cw;
  var sum = vec3<u32>(0u);
  let g = max(U.g, 1);
  for (var j = j0; j <= j1; j++) {
    let wy = u32((min((y + 1) * W, (j + 1) * cw) - max(y * W, j * cw)) / g);
    var row = vec3<u32>(0u);
    for (var ii = i0; ii <= i1; ii++) {
      let wx = u32((min((x + 1) * W, (ii + 1) * cw) - max(x * W, ii * cw)) / g);
      row += vec3<u32>(textureLoad(tex, vec2<i32>(ii, j), 0).rgb * 255.0 + 0.5) * wx;
    }
    sum += row * wy;
  }
  let n = u32(W / g) * u32(W / g);
  return vec4<f32>(vec3<f32>((sum + n / 2u) / n) / 255.0, 1.0);
}
// fsArea from tables (the editor's): column x's first texel, how many, then their weights, at tb[x * sc]; row y's at
// tb[rowAt + y * sr]; n = (W / g)^2 -- the same sums, the same order, no division but the last
struct AT { sc: u32, sr: u32, rowAt: u32, n: u32 };
@group(0) @binding(4) var<uniform> UT: AT;
@group(0) @binding(5) var<storage, read> tb: array<u32>;
@fragment fn fsAreaT(i: VF) -> @location(0) vec4<f32> {
  let c = u32(i.pos.x) * UT.sc; let r = UT.rowAt + u32(i.pos.y) * UT.sr;
  let i0 = i32(tb[c]); let nx = tb[c + 1u]; let j0 = i32(tb[r]); let ny = tb[r + 1u];
  var sum = vec3<u32>(0u);
  for (var j = 0u; j < ny; j++) {
    var row = vec3<u32>(0u);
    for (var q = 0u; q < nx; q++) {
      row += vec3<u32>(textureLoad(tex, vec2<i32>(i0 + i32(q), j0 + i32(j)), 0).rgb * 255.0 + 0.5) * tb[c + 2u + q];
    }
    sum += row * tb[r + 2u + j];
  }
  let n = UT.n;
  return vec4<f32>(vec3<f32>((sum + n / 2u) / n) / 255.0, 1.0);
}
// THE SCREEN'S PIXELS OVER THE MASK'S BOX (ERASE's mk): the box, page units to the working canvas's pixels (BX: k, the
// offset) to the screen's (a working pixel i lies under screen pixel i * cw / W), out by two -- fsArea makes each anew
@group(0) @binding(2) var<storage, read> mkb: array<u32>;
struct BU { k: f32, ox: f32, oy: f32, pad: f32 };
@group(0) @binding(3) var<uniform> BX: BU;
fn unord(u: u32) -> f32 { return bitcast<f32>(select(~u, u ^ 0x80000000u, (u >> 31u) == 1u)); }
@vertex fn vsBox(@builtin(vertex_index) v: u32) -> VF {
  var o: VF;
  if (mkb[1] == 0xffffffffu) { o.pos = vec4<f32>(2.0, 2.0, 2.0, 1.0); return o; }   // (no box: nothing marked)
  let lo = vec2<f32>(unord(mkb[1]), unord(mkb[2])); let hi = vec2<f32>(unord(mkb[3]), unord(mkb[4]));
  let s = f32(U.cw) / f32(U.W); let off = vec2<f32>(BX.ox, BX.oy);
  let p0 = (lo * BX.k + off) * s - vec2<f32>(2.0); let p1 = (hi * BX.k + off) * s + vec2<f32>(2.0);
  let q = vec2<f32>(select(p0.x, p1.x, (v & 1u) == 1u), select(p0.y, p1.y, v >= 2u));
  o.pos = vec4<f32>(q.x / f32(U.cw) * 2.0 - 1.0, 1.0 - q.y / f32(U.h) * 2.0, 0.0, 1.0);
  return o;
}
`,
  // THE CULLING: which blocks of the page's records (16 records a block, in the one buffer all chunks' records lie in)
  // can reach the area being drawn, packed in the buffer's order (a prefix sum: each run's blocks stay in order, so what
  // lies over what stays exact), and each run's draw written for an indirect draw. boxOf: a block's box, worked out as
  // its records go up (the points its segments draw, out by half the widest width there -- a highlighter's turn by the
  // segment before's too -- and a highlighter's 0.35 and a unit more); reach: each block against the area (page
  // units); scanBlocks, scanTop, place: the prefix sum and the packed list; drawArgs: each run's count and place. No
  // entry point reads or writes more than four storage buffers (compatibility mode's own limit)
  CULL: `
struct C { lo: vec2<f32>, hi: vec2<f32>, n: u32, nb: u32, first: u32, count: u32 };
@group(0) @binding(0) var<uniform> A: C;
@group(0) @binding(1) var<storage, read> rec: array<vec4<u32>>;
@group(0) @binding(2) var<storage, read_write> boxes: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read_write> flags: array<u32>;
@group(0) @binding(4) var<storage, read_write> scan: array<u32>;
@group(0) @binding(5) var<storage, read_write> sums: array<u32>;
@group(0) @binding(6) var<storage, read_write> clist: array<u32>;
@group(0) @binding(7) var<storage, read_write> runs: array<vec4<u32>>;
@group(0) @binding(8) var<storage, read_write> args: array<u32>;
@group(0) @binding(9) var<storage, read> spans: array<vec2<u32>>;
fn xyOf(r: vec4<u32>) -> vec2<f32> { return vec2<f32>(bitcast<f32>(r.x), bitcast<f32>(r.y)); }
var<workgroup> ws: array<u32, 128>;
// spans: the ranges of blocks whose records went up, each [its first block, where its boxes start in this dispatch],
// A.count of them; A.first the blocks in all
@compute @workgroup_size(64) fn boxOf(@builtin(global_invocation_id) id: vec3<u32>) {
  if (id.x >= A.first) { return; }
  var j = 0u;
  for (var q = 1u; q < A.count; q++) { if (spans[q].y <= id.x) { j = q; } }
  let b = spans[j].x + (id.x - spans[j].y);
  var lo = vec2<f32>(3.0e38); var hi = vec2<f32>(-3.0e38); var w = 0.0;
  for (var k = 0u; k < 16u; k++) {
    let i = b * 16u + k;
    let R = rec[i]; let f = R.w & 0xffu;
    if ((f & 3u) == 0u) { continue; }
    let p = xyOf(R); lo = min(lo, p); hi = max(hi, p); w = max(w, bitcast<f32>(R.z));
    if ((f & 1u) != 0u) { let Q = rec[i + 1u]; let q2 = xyOf(Q); lo = min(lo, q2); hi = max(hi, q2); w = max(w, bitcast<f32>(Q.z)); }
    if ((f & 4u) != 0u) { w = max(w, bitcast<f32>(rec[i - 1u].z)); }
  }
  let m = w * 0.5 + 0.35 + 1.0;
  boxes[b] = select(vec4<f32>(3.0e38, 3.0e38, -3.0e38, -3.0e38), vec4<f32>(lo - vec2<f32>(m), hi + vec2<f32>(m)), hi.x >= lo.x);
}
@compute @workgroup_size(128) fn reach(@builtin(global_invocation_id) id: vec3<u32>) {
  let b = id.x;
  if (b >= A.n) { return; }
  let B = boxes[b];
  flags[b] = select(0u, 1u, B.z >= A.lo.x && B.x <= A.hi.x && B.w >= A.lo.y && B.y <= A.hi.y);
}
@compute @workgroup_size(128) fn scanBlocks(@builtin(workgroup_id) wid: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  let i = wid.x * 128u + li;
  var f = 0u;
  if (i < A.n) { f = flags[i]; }
  ws[li] = f;
  workgroupBarrier();
  for (var off = 1u; off < 128u; off *= 2u) {
    var v = 0u;
    if (li >= off) { v = ws[li - off]; }
    workgroupBarrier();
    ws[li] += v;
    workgroupBarrier();
  }
  if (i < A.n) { scan[i] = ws[li] - f; }
  if (li == 127u) { sums[wid.x] = ws[127]; }
}
@compute @workgroup_size(128) fn scanTop(@builtin(local_invocation_index) li: u32) {
  let ng = (A.n + 127u) / 128u; let per = (ng + 127u) / 128u; let g0 = li * per;
  var s = 0u;
  for (var j = 0u; j < per; j++) { let g = g0 + j; if (g < ng) { s += sums[g]; } }
  ws[li] = s;
  workgroupBarrier();
  for (var off = 1u; off < 128u; off *= 2u) {
    var v = 0u;
    if (li >= off) { v = ws[li - off]; }
    workgroupBarrier();
    ws[li] += v;
    workgroupBarrier();
  }
  var acc = ws[li] - s;
  for (var j = 0u; j < per; j++) { let g = g0 + j; if (g < ng) { let t = sums[g]; sums[g] = acc; acc += t; } }
  if (li == 127u) { scan[A.n] = ws[127]; }
}
@compute @workgroup_size(128) fn place(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x;
  if (i >= A.n) { return; }
  let at = scan[i] + sums[i / 128u];
  scan[i] = at;
  if (flags[i] == 1u) { clist[at] = i; }
}
@compute @workgroup_size(64) fn drawArgs(@builtin(global_invocation_id) id: vec3<u32>) {
  let k = id.x;
  if (k >= A.nb) { return; }
  let T = runs[k];
  let b0 = T.x / 16u; let b1 = (T.y + 15u) / 16u;
  let s0 = scan[b0]; let n = scan[b1] - s0;
  runs[k].z = s0;
  let o = k * 8u;
  if ((T.w & 1u) == 1u) { args[o] = 24u; args[o + 1u] = n * 16u; args[o + 2u] = 0u; args[o + 3u] = k * 64u; args[o + 4u] = 0u; }
  else { args[o] = 4u; args[o + 1u] = n * 16u; args[o + 2u] = k * 16u; args[o + 3u] = 0u; }
}
// LISTS (STROKES' listed draws): the page is its SPANS, made from its order on the card (ORDER, below) -- each a run of
// records lying one after another in the page's records, of one class: the pens, or a level's highlighters, or a level's
// grain and wash strokes (sp: its first record, past its last, its class). The table lists them class by class, each
// class's in the page's order (ctab: a class's first span, past its last, its kind: 0 pens, 1 highlighters, 2 grain and
// wash); how many spans and classes there are, the card's own (lh). Each draw, after reach and the prefix sum over the
// blocks: each span's blocks that reach the area counted (spanCount), the counts summed (spanScan: where each span's start
// in the list, and the expansion's size), each class's draw written (classArgs: its list's place, as its first or base
// vertex; the classes past the page's, as many as the processor draws, nothing), and the list made (expand: an entry a
// block and its span). The expansion's size first in largs, then each class's draw
struct LQ { ncCap: u32, n: u32, skAt: u32, stAt: u32, wide: u32, p1: u32, p2: u32, p3: u32 };   // (p1 the mask's room, p2 a record's parts drawn)
@group(0) @binding(10) var<uniform> Q: LQ;
@group(0) @binding(11) var<storage, read> sp: array<vec4<u32>>;
@group(0) @binding(12) var<storage, read_write> soff: array<u32>;
@group(0) @binding(13) var<storage, read_write> lst: array<vec2<u32>>;
@group(0) @binding(14) var<storage, read> ctab: array<vec4<u32>>;
@group(0) @binding(15) var<storage, read_write> largs: array<u32>;
@group(0) @binding(16) var<storage, read_write> grbw: array<vec2<u32>>;
@group(0) @binding(27) var<storage, read_write> lh: array<u32>;   // (the order's header: 0 spans, 1 classes, 2 pens, 3 others, 4 strokes)
var<workgroup> wsS: array<u32, 128>;
@compute @workgroup_size(64) fn spanCount(@builtin(global_invocation_id) id: vec3<u32>) {
  let k = id.x;
  if (k >= lh[0]) { return; }
  let S = sp[k];
  soff[k] = scan[(S.y + 15u) / 16u] - scan[S.x / 16u];
}
@compute @workgroup_size(128) fn spanScan(@builtin(local_invocation_index) li: u32) {
  let n = lh[0]; let per = (n + 127u) / 128u; let k0 = li * per;
  var s = 0u;
  for (var q = 0u; q < per; q++) { let k = k0 + q; if (k < n) { s += soff[k]; } }
  wsS[li] = s;
  workgroupBarrier();
  for (var off = 1u; off < 128u; off *= 2u) {
    var v = 0u;
    if (li >= off) { v = wsS[li - off]; }
    workgroupBarrier();
    wsS[li] += v;
    workgroupBarrier();
  }
  var acc = wsS[li] - s;
  for (var q = 0u; q < per; q++) { let k = k0 + q; if (k < n) { let t = soff[k]; soff[k] = acc; acc += t; } }
  if (li == 127u) {
    let all = wsS[127]; soff[n] = all;
    let g = (all + 63u) / 64u;
    largs[0] = min(g, 65535u); largs[1] = (g + 65534u) / 65535u; largs[2] = 1u;
  }
}
@compute @workgroup_size(64) fn classArgs(@builtin(global_invocation_id) id: vec3<u32>) {
  let c = id.x;
  if (c >= Q.ncCap) { return; }
  let o = (c + 1u) * 8u;
  if (c >= lh[1]) { largs[o] = 0u; largs[o + 1u] = 0u; largs[o + 2u] = 0u; largs[o + 3u] = 0u; largs[o + 4u] = 0u; return; }
  let T = ctab[c]; let s0 = soff[T.x]; let n = soff[T.y] - s0;
  let parts = max(Q.p2, 1u);                                 // (a record's parts: four while the card cuts strokes, else its one)
  if (T.z == 1u) { largs[o] = 6u * parts; largs[o + 1u] = n * 16u; largs[o + 2u] = 0u; largs[o + 3u] = s0 * 64u; largs[o + 4u] = 0u; }
  else if (T.z == 2u) { largs[o] = 6u * parts; largs[o + 1u] = n * 16u; largs[o + 2u] = s0 * 32u; largs[o + 3u] = 0u; }
  else { largs[o] = 4u; largs[o + 1u] = n * 16u; largs[o + 2u] = s0 * 16u; largs[o + 3u] = 0u; }
}
@compute @workgroup_size(64) fn expand(@builtin(global_invocation_id) id: vec3<u32>) {
  let e = id.x + id.y * 65535u * 64u; let n = lh[0];
  if (e >= soff[n]) { return; }
  var lo = 0u; var hi = n;                                   // the span whose list holds entry e: soff[lo] <= e < soff[lo + 1]
  while (hi - lo > 1u) { let m = (lo + hi) / 2u; if (soff[m] <= e) { lo = m; } else { hi = m; } }
  let S = sp[lo];
  lst[e] = vec2<u32>(clist[scan[S.x / 16u] + (e - soff[lo])], lo);
}
// A MASK THE PROCESSOR LISTS (the stroke being drawn: its new segments; a fold's pieces made fresh; a selection moved):
// its records in the mask (ERASE's msk: its header, then the records), its box worked out here (listBoxes, a thread a
// record: each workgroup's box made first, then one word of each side the mask's -- not every record at the same four
// words), and the mask's draw written (listArgs; an erase's frame writes it here too) -- Q.p1: how many records the
// mask has room for
@group(0) @binding(19) var<storage, read_write> mkw: array<atomic<u32>>;
fn ordW(f: f32) -> u32 { let b = bitcast<u32>(f); return select(b ^ 0x80000000u, ~b, (b >> 31u) == 1u); }
var<workgroup> wbx: array<vec4<u32>, 64>;
@compute @workgroup_size(64) fn listBoxes(@builtin(global_invocation_id) id: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  var B = vec4<u32>(0xffffffffu, 0xffffffffu, 0u, 0u);       // (ordered words: no box)
  if (id.x < min(atomicLoad(&mkw[0]), Q.p1)) {
    let i = atomicLoad(&mkw[16u + id.x]);
    let R0 = rec[i]; let f = R0.w & 0xffu;
    if ((f & 3u) != 0u) {
      let a = xyOf(R0); var b = a; var w = bitcast<f32>(R0.z);
      if ((f & 1u) != 0u) { let R1 = rec[i + 1u]; b = xyOf(R1); w = max(w, bitcast<f32>(R1.z)); }
      if ((f & 4u) != 0u) { w = max(w, bitcast<f32>(rec[i - 1u].z)); }
      let r = w * 0.5 + 0.35 + 1.0;
      B = vec4<u32>(ordW(min(a.x, b.x) - r), ordW(min(a.y, b.y) - r), ordW(max(a.x, b.x) + r), ordW(max(a.y, b.y) + r));
    }
  }
  wbx[li] = B;
  workgroupBarrier();
  for (var s = 32u; s > 0u; s >>= 1u) {
    if (li < s) { let o = wbx[li + s]; let m = wbx[li]; wbx[li] = vec4<u32>(min(m.xy, o.xy), max(m.zw, o.zw)); }
    workgroupBarrier();
  }
  if (li == 0u && wbx[0].x != 0xffffffffu) {
    let m = wbx[0];
    atomicMin(&mkw[1], m.x); atomicMin(&mkw[2], m.y); atomicMax(&mkw[3], m.z); atomicMax(&mkw[4], m.w);
  }
}
@compute @workgroup_size(1) fn listArgs() {
  let c = atomicLoad(&mkw[0]); let over = c > Q.p1;          // (more than it has room for: its box drawn instead, word 5 --
  atomicStore(&mkw[5], select(0u, 1u, over));                 // STROKES' vsMask)
  atomicStore(&mkw[8], 4u); atomicStore(&mkw[9], select(c, 1u, over)); atomicStore(&mkw[10], 0u); atomicStore(&mkw[11], 0u);
}
// reachBox: reach, the area the mask's box (ERASE's mk, its words 1 to 4 in order: unord), out by A.lo.x (page units);
// a mask with nothing in it reaches nothing (its box's words as they began: no box). Its box, not its count: an undo's
// second mark may list nothing and still have the first's box (swap)
@group(0) @binding(18) var<storage, read> mkb: array<u32>;
fn unord(u: u32) -> f32 { return bitcast<f32>(select(~u, u ^ 0x80000000u, (u >> 31u) == 1u)); }
@compute @workgroup_size(128) fn reachBox(@builtin(global_invocation_id) id: vec3<u32>) {
  let b = id.x;
  if (b >= A.n) { return; }
  let B = boxes[b]; let m = A.lo.x;
  let lo = vec2<f32>(unord(mkb[1]), unord(mkb[2])) - vec2<f32>(m); let hi = vec2<f32>(unord(mkb[3]), unord(mkb[4])) + vec2<f32>(m);
  flags[b] = select(0u, 1u, mkb[1] != 0xffffffffu && B.z >= lo.x && B.x <= hi.x && B.w >= lo.y && B.y <= hi.y);
}
// ORDER: THE PAGE'S ORDER ON THE CARD -- the numbers of the page's strokes as the page draws them (each shown layer's in
// order, the bottom layer first), in ordr. The processor changes it by EDITS (eb: the anchors, each a stroke of the order,
// three words -- its number, where its list starts in eb, how many and whether the stroke stays (bit 31) -- then the
// strokes put before all, then the lists): each anchor replaced by its list (kept before it if it stays). Made here in a
// few passes -- the anchors marked in the table of edits (ed), each place's count, the prefix sum, each place's strokes
// put where they now go (ordw), the marks cleared -- so a change costs the processor what changed, never the page. Then
// all the listed draws need, made from it here: each stroke's KEY, its place (SK, its depth); the classes' order, the pens
// first then the others in the page's order (ok: number | kind << 30, 1 a highlighter, 2 a grain or wash stroke) -- the
// others' classes rise along the page's order, so the classes' order is theirs with the pens taken out; each one's LEVEL
// (a highlighter after a grain or wash stroke begins the next: the count of those before it) and so its class (ocl: 0
// pens, 2 level + 1 a level's highlighters, 2 level + 2 its grain and wash); the SPANS, a run of places of one class whose
// records lie one after another; and the classes' table (ctab), its classes past the page's (up to O.ncCap, the
// processor's) empty. lh: 0 spans, 1 classes, 2 pens, 3 others, 4 strokes (the order's length: what every pass goes by), 5
// levels, 6 classes past ncCap (1), 7 and 8 a prefix sum's length and total, 9 the edit's anchors, 10 its strokes put
// before all
struct OQ { n: u32, headN: u32, ncCap: u32, stAt: u32, skAt: u32, nA: u32, m: u32, p7: u32 };   // (ncCap, stAt, skAt: the rest are lh's)
@group(0) @binding(20) var<uniform> O: OQ;
@group(0) @binding(21) var<storage, read> ordr: array<u32>;
@group(0) @binding(22) var<storage, read_write> ordw: array<u32>;
@group(0) @binding(23) var<storage, read_write> ed: array<vec2<u32>>;
@group(0) @binding(24) var<storage, read> eb: array<u32>;
@group(0) @binding(25) var<storage, read_write> osc: array<u32>;
@group(0) @binding(26) var<storage, read_write> osb: array<u32>;
@group(0) @binding(28) var<storage, read_write> ok: array<u32>;
@group(0) @binding(29) var<storage, read_write> spw: array<u32>;
@group(0) @binding(30) var<storage, read_write> ctw: array<u32>;
@group(0) @binding(31) var<storage, read_write> ocl: array<u32>;
var<workgroup> wsO: array<u32, 128>;
fn kindOfSid(sid: u32) -> u32 {                               // 0 a pen, 1 a highlighter, 2 a grain or wash stroke
  let k = grbw[O.stAt + sid * 4u + 1u].x & 0xffu;
  return select(select(2u, 1u, k == 1u), 0u, k == 0u);
}
// A PREFIX SUM of osc[0..lh[7]): each the sum of those before it, osc[lh[7]] and lh[8] the total (three passes: each 128's
// own, their sums', each 128's start added)
@compute @workgroup_size(128) fn oScanLocal(@builtin(workgroup_id) wid: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  let n = lh[7]; let i = wid.x * 128u + li;
  var f = 0u;
  if (i < n) { f = osc[i]; }
  wsO[li] = f;
  workgroupBarrier();
  for (var off = 1u; off < 128u; off *= 2u) {
    var v = 0u;
    if (li >= off) { v = wsO[li - off]; }
    workgroupBarrier();
    wsO[li] += v;
    workgroupBarrier();
  }
  if (i < n) { osc[i] = wsO[li] - f; }
  if (li == 127u) { osb[wid.x] = wsO[127]; }
}
@compute @workgroup_size(128) fn oScanTop(@builtin(local_invocation_index) li: u32) {
  let n = lh[7]; let ng = (n + 127u) / 128u; let per = (ng + 127u) / 128u; let g0 = li * per;
  var s = 0u;
  for (var j = 0u; j < per; j++) { let g = g0 + j; if (g < ng) { s += osb[g]; } }
  wsO[li] = s;
  workgroupBarrier();
  for (var off = 1u; off < 128u; off *= 2u) {
    var v = 0u;
    if (li >= off) { v = wsO[li - off]; }
    workgroupBarrier();
    wsO[li] += v;
    workgroupBarrier();
  }
  var acc = wsO[li] - s;
  for (var j = 0u; j < per; j++) { let g = g0 + j; if (g < ng) { let t = osb[g]; osb[g] = acc; acc += t; } }
  if (li == 127u) { lh[8] = wsO[127]; osc[n] = wsO[127]; }
}
@compute @workgroup_size(128) fn oScanAdd(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x;
  if (i >= lh[7]) { return; }
  osc[i] += osb[i / 128u];
}
// THE EDITS: the anchors marked; each place's count (an anchor: its list, and itself if it stays; any other: itself);
// each place's strokes put where they now go, the strokes before all first; the marks cleared
@compute @workgroup_size(128) fn ordMark(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x;
  if (i >= lh[9]) { return; }
  ed[eb[3u * i]] = vec2<u32>(eb[3u * i + 1u], eb[3u * i + 2u] | 0x40000000u);
}
@compute @workgroup_size(128) fn ordCount(@builtin(global_invocation_id) id: vec3<u32>) {
  let k = id.x; let n = lh[4];
  if (k == 0u) { lh[7] = n; }
  if (k >= n) { return; }
  let e = ed[ordr[k]];
  var c = 1u;
  if (((e.y >> 30u) & 1u) == 1u) { c = (e.y & 0x3fffffffu) + (e.y >> 31u); }
  osc[k] = c;
}
@compute @workgroup_size(128) fn ordPut(@builtin(global_invocation_id) id: vec3<u32>) {
  let k = id.x; let hn = lh[10]; let n = lh[7];
  if (k == 0u) {
    for (var j = 0u; j < hn; j++) { ordw[j] = eb[3u * lh[9] + j]; }
    lh[4] = hn + lh[8];
  }
  if (k >= n) { return; }
  let s0 = ordr[k]; let e = ed[s0];
  var o = hn + osc[k];
  if (((e.y >> 30u) & 1u) == 0u) { ordw[o] = s0; return; }
  if ((e.y >> 31u) == 1u) { ordw[o] = s0; o += 1u; }
  let c = e.y & 0x3fffffffu;
  for (var j = 0u; j < c; j++) { ordw[o + j] = eb[e.x + j]; }
}
@compute @workgroup_size(128) fn ordClear(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x;
  if (i >= lh[9]) { return; }
  ed[eb[3u * i]] = vec2<u32>(0u, 0u);
}
// WHAT THE DRAWS NEED, from the order (lh[4] its strokes): the keys, and which are not pens (counted)
@compute @workgroup_size(128) fn ordKey(@builtin(global_invocation_id) id: vec3<u32>) {
  let k = id.x; let m = lh[4];
  if (k == 0u) { lh[7] = m; }
  if (k >= m) { return; }
  let sid = ordr[k];
  grbw[O.skAt + sid].x = k;
  osc[k] = select(1u, 0u, kindOfSid(sid) == 0u);
}
@compute @workgroup_size(128) fn ordSplit(@builtin(global_invocation_id) id: vec3<u32>) {   // the classes' order
  let k = id.x; let nn = lh[8]; let np = lh[4] - nn;
  if (k == 0u) { lh[2] = np; lh[3] = nn; }
  if (k >= lh[4]) { return; }
  let sid = ordr[k]; let kd = kindOfSid(sid); let rn = osc[k];
  if (kd == 0u) { ok[k - rn] = sid; } else { ok[np + rn] = sid | (kd << 30u); }
}
@compute @workgroup_size(128) fn ordTrans(@builtin(global_invocation_id) id: vec3<u32>) {   // where a level begins
  let r = id.x; let nn = lh[3]; let np = lh[2];
  if (r == 0u) { lh[7] = nn; }
  if (r >= nn) { return; }
  var t = 0u;
  if ((ok[np + r] >> 30u) == 1u && r > 0u && (ok[np + r - 1u] >> 30u) == 2u) { t = 1u; }
  osc[r] = t;
}
@compute @workgroup_size(128) fn ordClass(@builtin(global_invocation_id) id: vec3<u32>) {
  let q = id.x; let np = lh[2]; let nn = lh[3];
  if (q == 0u) {
    let lv = select(0u, lh[8] + 1u, nn > 0u);
    lh[5] = lv; lh[1] = 1u + 2u * lv; lh[6] = select(0u, 1u, 1u + 2u * lv > O.ncCap);
  }
  if (q >= lh[4]) { return; }
  if (q < np) { ocl[q] = 0u; return; }
  let r = q - np; let kd = ok[q] >> 30u;
  var t = 0u;
  if (kd == 1u && r > 0u && (ok[q - 1u] >> 30u) == 2u) { t = 1u; }
  ocl[q] = 2u * (osc[r] + t) + kd;
}
fn rowAt(q: u32) -> vec2<u32> { return grbw[O.stAt + (ok[q] & 0x3fffffffu) * 4u]; }   // a place's stroke's first record, how many
@compute @workgroup_size(128) fn ordStart(@builtin(global_invocation_id) id: vec3<u32>) {
  let q = id.x;
  if (q == 0u) { lh[7] = lh[4]; }
  if (q >= lh[4]) { return; }
  var b = 1u;
  if (q > 0u) { let a = rowAt(q - 1u); let c = rowAt(q); if (ocl[q] == ocl[q - 1u] && a.x + a.y == c.x) { b = 0u; } }
  osc[q] = b;
}
@compute @workgroup_size(128) fn ordSpan(@builtin(global_invocation_id) id: vec3<u32>) {
  let q = id.x;
  if (q == 0u) { lh[0] = lh[8]; }
  if (q >= lh[4]) { return; }
  let s0 = osc[q]; let start = osc[q + 1u] != s0;
  let at = select(s0 - 1u, s0, start);
  let c = rowAt(q);
  if (start) { spw[4u * at] = c.x; spw[4u * at + 2u] = ocl[q]; spw[4u * at + 3u] = 0u; }
  if (q + 1u >= lh[4] || osc[q + 2u] != osc[q + 1u]) { spw[4u * at + 1u] = c.x + c.y; }
}
@compute @workgroup_size(64) fn ordCtabClear(@builtin(global_invocation_id) id: vec3<u32>) {
  let c = id.x;
  if (c >= O.ncCap) { return; }
  ctw[4u * c] = 0u; ctw[4u * c + 1u] = 0u; ctw[4u * c + 2u] = select(select(2u, 1u, (c & 1u) == 1u), 0u, c == 0u); ctw[4u * c + 3u] = 0u;
}
@compute @workgroup_size(128) fn ordCtab(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x; let ns = lh[0];
  if (i >= ns) { return; }
  let c = spw[4u * i + 2u];
  if (c >= O.ncCap) { return; }
  if (i == 0u || spw[4u * (i - 1u) + 2u] != c) { ctw[4u * c] = i; }
  if (i + 1u == ns || spw[4u * (i + 1u) + 2u] != c) { ctw[4u * c + 1u] = i + 1u; }
}
// THE CARD'S OWN EDIT (an erase's pieces put where their stroke was: ERASE's flip): the order written back where it is
// read, so its buffers stay the processor's whether the card made one or not
@group(0) @binding(17) var<storage, read_write> ordx: array<u32>;
@compute @workgroup_size(128) fn ordBack(@builtin(global_invocation_id) id: vec3<u32>) {
  let k = id.x;
  if (k >= lh[4]) { return; }
  ordx[k] = ordw[k];
}
`,
  // ERASING ON THE CARD (the editor's eraser, a swipe): the processor sends the swipe's path, a step a frame, and the card
  // does the rest. FIND: each block of the page's records whose box the step can reach (CULL's passes pack them, in
  // order). REACH: a thread a record of those blocks -- a segment (or a dot) of a stroke drawn now, on the layer in hand,
  // against the step's capsules at the eraser's radius and the stroke's half width: the stretches of it inside (passing),
  // or whether it is touched at all (the whole-stroke eraser), kept as its entry (3 words: how many stretches, the first
  // and last place of one; 255: more, worked out again when stitched); the stroke listed once as touched. ALLOC:
  // a slot for each stroke touched that has none, its room taken from the swipe's pools. STITCH: a thread a touched stroke,
  // its entries in order -- cut where the eraser reaches it, or each stretch it touches taken whole, as the editor's
  // cutAlong and touchedOut do it on the processor: a graze of less than a thousandth of a unit is no cut, a piece shorter
  // than half the eraser is wide goes, the cut let out a ten-thousandth of a unit. MARK and PIECES: sixty-four threads a
  // stroke. CELLS: the areas its cuts changed beyond the reach of a cut segment from the path (pieces made anew, the
  // stretches the whole-stroke eraser took), listed for the processor to draw again.
  // A SLOT (es) holds what is left of a stroke and where its pieces' records go. Its header, 20 words: 0 its first record,
  // 1 its records, 2 its kind (0 pen, 1 highlighter, 2 grain, 3 wash), 3 its half width, 4 the most stretches it can have,
  // 5 where its stretches start, 6 which of the two is in use, 7 how many, 8 its pieces' place, 9 that place's records,
  // 10 their grain's place, 11 how far the last pieces went, 12 the step it last changed in, 13 its own grain's place, 14
  // how often it was cut, 15 the step it was last cut in, 16 and 17 the records that step's cuts changed how it lays its
  // ink across (first, past the last; none: 16 > 17) -- a grain's pieces that start at a new place, a wash's pieces where
  // it was cut in two or more (each lays its wash once a pixel), the stretches the whole-stroke eraser took, a crumb a cut
  // left shorter than half the eraser (gone, wherever it lies: on segments the step did not reach too) -- 18 its
  // stroke's number, 19 where its room in the page's records starts, 20 the most stretches it can have (a kept stretch is
  // half the eraser long at least; its room is for four at first, made larger only when a cut needs it: grow), 21 its
  // entry in the table of strokes being cut, 22 its pieces' records as last written (pos), 23 not used. Its places in the
  // pools are packed, one after another. A stretch, 10 words: where it starts (a record j, a
  // place t along the segment from it, 0 <= t < 1, kept apart so no precision is lost; and the point there, as the card
  // worked it out), where it ends (the same), where its piece's records are and how many. PIECES writes a stroke's pieces'
  // records one after another (the records kept, copied; a new one at each cut, a copy of the record of the point beyond
  // it moved to the cut; the first of each piece a segment's start, the last its end, a highlighter's turns beside a new
  // end worked out again, and its new end dropped when it lies on the record beside it, as a fresh part drops it), each
  // piece's number along in its grain records' second number (STROKES draws each piece at its own depth by it), the rest
  // of the place cleared.
  // THE CONTROL WORDS (ctl): 0 strokes touched this step, 1 cells listed this frame, 2 what ran out (1 the blocks found, 2
  // the touched list, 4 the slots' room, 8 the records' pool, 16 the grain's pool, 32 the table of strokes being cut, 64
  // the cells, 128 the list of slots), 3 the step, 4 and 5 the slots' room (next, end), 6 and 7 the records' pool's, 8 and
  // 9 the grain pool's, 10 and 11 the table's entries, 12 the slots made, 13 their pieces' size (words), 14 the
  // blocks found (as many as are entered), 15 found in all; 16 the numbers taken, 17 how many the processor gave, 18 the
// first of them, 19 the slots flipped this frame, 20 the log's words, 21 the order's anchors, 22 their lists' words, 23
// the log's room, 24 the anchors' room, 25 the lists', 26 the order's room, 27 the classes drawn, 28 the slots done (made
// strokes, or let go as they were); then the strokes touched, the cells listed (a cell's key as the editor's dkey), the cells' map (a bit
  // a cell), the slots made (where each is in es), and each stroke number's last step touched
  ERASE: `
struct Step { lo: vec2<f32>, hi: vec2<f32>, R: f32, least: f32, reach: f32, nS: u32, frame: u32, mode: u32, layer: u32, nb: u32,
              tCap: u32, cCap: u32, slCap: u32, stCap: u32, offT: u32, offC: u32, offB: u32, offSL: u32, offST: u32, evAt: u32, stAt: u32, hitCap: u32,
              mCap: u32, p1: u32, p2: u32, p3: u32 };
@group(0) @binding(0) var<storage, read_write> es: array<u32>;
@group(0) @binding(1) var<storage, read> fin: array<u32>;
@group(0) @binding(2) var<storage, read_write> rec: array<vec4<u32>>;
@group(0) @binding(3) var<storage, read_write> grb: array<vec2<u32>>;
@group(0) @binding(4) var<uniform> F: Step;
@group(0) @binding(5) var<storage, read> boxes: array<vec4<f32>>;
@group(0) @binding(6) var<storage, read_write> flags: array<u32>;
@group(0) @binding(7) var<storage, read> clist: array<u32>;
@group(0) @binding(8) var<storage, read> scan: array<u32>;
@group(0) @binding(9) var<storage, read_write> ctl: array<atomic<u32>>;
@group(0) @binding(10) var<storage, read_write> ent: array<u32>;
@group(0) @binding(11) var<storage, read_write> eargs: array<u32>;
@group(0) @binding(12) var<storage, read_write> pack: array<u32>;   // (the flips' log, read back)
@group(0) @binding(14) var<storage, read_write> oeb: array<u32>;    // (the order's edits: flip)
@group(0) @binding(15) var<storage, read_write> boxw: array<vec4<f32>>;   // (the blocks' boxes: flipBox)
@group(0) @binding(16) var<storage, read_write> olh: array<u32>;    // (the order's header: flipEnd)
@group(0) @binding(17) var<storage, read_write> oargs: array<u32>;  // (the order's passes' dispatches for the card's own edit: flipEnd)
const NONE: u32 = 0xffffffffu;
const HDR: u32 = 24u;
struct Pl { j: u32, t: f32, p: vec2<f32> };
var<private> base: u32; var<private> nR: u32;
var<private> oAt: u32; var<private> nO: u32; var<private> capO: u32; var<private> full: bool;
var<private> IN: array<f32, 80>; var<private> nIN: u32;
var<private> fm: u32; var<private> fat: Pl; var<private> ft: bool;
var<private> mAt: u32; var<private> mk: u32; var<private> ms: u32; var<private> mc: u32;
var<private> wk: u32; var<private> st0: Pl; var<private> sk0: u32; var<private> sk1: u32;   // (what a cut made anew)
var<private> kn: u32; var<private> klo: u32; var<private> khi: u32; var<private> nlo: u32; var<private> nhi: u32;
fn P(j: u32) -> vec2<f32> { let r = rec[base + j]; return vec2<f32>(bitcast<f32>(r.x), bitcast<f32>(r.y)); }
fn seg(i: u32) -> vec4<f32> {                                // the step's path, a segment at a time (a point: one of no length)
  let o = 4u * i;
  return vec4<f32>(bitcast<f32>(fin[o]), bitcast<f32>(fin[o + 1u]), bitcast<f32>(fin[o + 2u]), bitcast<f32>(fin[o + 3u]));
}
fn lt(a: Pl, b: Pl) -> bool { return a.j < b.j || (a.j == b.j && a.t < b.t); }
fn placeAt(j: u32, t: f32) -> Pl {
  if (t <= 0.0) { return Pl(j, 0.0, P(j)); }
  if (t >= 1.0) { return Pl(j + 1u, 0.0, P(j + 1u)); }
  let a = P(j); let b = P(j + 1u);
  return Pl(j, t, a + (b - a) * t);
}
fn aStart(A: u32, m: u32) -> Pl { let o = A + m * 10u; return Pl(es[o], bitcast<f32>(es[o + 1u]), vec2<f32>(bitcast<f32>(es[o + 2u]), bitcast<f32>(es[o + 3u]))); }
fn aEnd(A: u32, m: u32) -> Pl { let o = A + m * 10u + 4u; return Pl(es[o], bitcast<f32>(es[o + 1u]), vec2<f32>(bitcast<f32>(es[o + 2u]), bitcast<f32>(es[o + 3u]))); }
fn put(c: Pl, d: Pl) {
  if (nO >= capO) { full = true; return; }
  let o = oAt + nO * 10u;
  es[o] = c.j; es[o + 1u] = bitcast<u32>(c.t); es[o + 2u] = bitcast<u32>(c.p.x); es[o + 3u] = bitcast<u32>(c.p.y);
  es[o + 4u] = d.j; es[o + 5u] = bitcast<u32>(d.t); es[o + 6u] = bitcast<u32>(d.p.x); es[o + 7u] = bitcast<u32>(d.p.y);
  es[o + 8u] = 0u; es[o + 9u] = 0u;
  nO += 1u;
}
fn lengthOver(c: Pl, d: Pl) -> bool {                       // the stroke from c to d at least half the eraser long?
  var len = 0.0;
  for (var j = c.j; j <= d.j && j + 1u < nR; j++) {
    let f0 = select(0.0, c.t, j == c.j); let f1 = select(1.0, d.t, j == d.j);
    len += length(P(j + 1u) - P(j)) * (f1 - f0);
    if (len >= F.least) { return true; }
  }
  return false;
}
fn keep(c: Pl, d: Pl) {
  if (!lt(c, d)) { return; }
  if (!lengthOver(c, d)) {                                   // a crumb shorter than half the eraser: gone, wherever it lies
    sk0 = min(sk0, c.j); sk1 = max(sk1, d.j + select(0u, 1u, d.t > 0.0)); return;
  }
  put(c, d);
  let e = d.j + select(0u, 1u, d.t > 0.0);
  kn += 1u; klo = min(klo, c.j); khi = max(khi, e);
  if (lt(st0, c)) { nlo = min(nlo, c.j); nhi = max(nhi, e); }   // a piece starting at a new place
}
fn keepNote(c: Pl, d: Pl, enough: bool) {                    // keep, its piece laid down already (whether long enough known)
  if (!enough) { sk0 = min(sk0, c.j); sk1 = max(sk1, d.j + select(0u, 1u, d.t > 0.0)); return; }
  let e = d.j + select(0u, 1u, d.t > 0.0);
  kn += 1u; klo = min(klo, c.j); khi = max(khi, e);
  if (lt(st0, c)) { nlo = min(nlo, c.j); nhi = max(nhi, e); }
}
fn anew() {                                                  // the stretch just done was cut: what of it was made anew
  if (wk == 3u && kn >= 2u) { sk0 = min(sk0, klo); sk1 = max(sk1, khi); }
  if (wk == 2u && nlo <= nhi) { sk0 = min(sk0, nlo); sk1 = max(sk1, nhi); }
}
fn stretchBegun() { kn = 0u; klo = 0xffffffffu; khi = 0u; nlo = 0xffffffffu; nhi = 0u; }
fn segPointD2(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
  let d = b - a; let L2 = dot(d, d);
  var t = 0.0;
  if (L2 > 0.0) { t = clamp(dot(p - a, d) / L2, 0.0, 1.0); }
  let e = a + t * d - p;
  return dot(e, e);
}
fn pathD2(p: vec2<f32>) -> f32 {
  var m = 3.0e38;
  for (var i = 0u; i < F.nS; i++) { let s = seg(i); m = min(m, segPointD2(p, s.xy, s.zw)); }
  return m;
}
fn segSeg(a: vec2<f32>, b: vec2<f32>, c: vec2<f32>, d: vec2<f32>) -> f32 {
  let d1 = b - a; let d2 = d - c; let r = a - c;
  let A = dot(d1, d1); let E = dot(d2, d2); let f = dot(d2, r);
  var s = 0.0; var t = 0.0;
  if (A <= 1e-12) { if (E > 1e-12) { t = clamp(f / E, 0.0, 1.0); } }
  else {
    let cc = dot(d1, r);
    if (E <= 1e-12) { s = clamp(-cc / A, 0.0, 1.0); }
    else {
      let bb = dot(d1, d2); let den = A * E - bb * bb;
      if (den > 1e-12) { s = clamp((bb * f - cc * E) / den, 0.0, 1.0); }
      t = (bb * s + f) / E;
      if (t < 0.0) { t = 0.0; s = clamp(-cc / A, 0.0, 1.0); }
      else if (t > 1.0) { t = 1.0; s = clamp((bb - cc) / A, 0.0, 1.0); }
    }
  }
  let q = a + d1 * s - c - d2 * t;
  return dot(q, q);
}
fn nearPath(a: vec2<f32>, b: vec2<f32>, r2: f32) -> bool {   // segment a-b within reach of the step anywhere?
  for (var i = 0u; i < F.nS; i++) { let s = seg(i); if (segSeg(a, b, s.xy, s.zw) <= r2) { return true; } }
  return false;
}
fn addIN(t0: f32, t1: f32) {                                 // [t0, t1] into IN, one with those it meets, IN kept in order
  var a = t0; var b = t1; var w = 0u;
  for (var k = 0u; k < nIN; k += 2u) {
    if (IN[k] <= b && IN[k + 1u] >= a) { a = min(a, IN[k]); b = max(b, IN[k + 1u]); }
    else { IN[w] = IN[k]; IN[w + 1u] = IN[k + 1u]; w += 2u; }
  }
  if (w >= 80u) { nIN = w; return; }
  var j = w;
  while (j > 0u && IN[j - 2u] > a) { IN[j] = IN[j - 2u]; IN[j + 1u] = IN[j - 1u]; j -= 2u; }
  IN[j] = a; IN[j + 1u] = b; nIN = w + 2u;
}
// segment a-b against the step's capsules at reach r: the parts of it inside, as places along it, in IN, in order, merged
fn inSweep(a: vec2<f32>, b: vec2<f32>, r2: f32, r: f32) -> bool {
  nIN = 0u;
  let e = b - a; let ee = dot(e, e);
  let bx0 = min(a.x, b.x) - r; let bx1 = max(a.x, b.x) + r; let by0 = min(a.y, b.y) - r; let by1 = max(a.y, b.y) + r;
  var nudge = 0.0;
  if (ee > 1e-12) { nudge = 1e-4 / sqrt(ee); }
  for (var i = 0u; i < F.nS; i++) {
    let s = seg(i); let c = s.xy; let d = s.zw;
    if (max(c.x, d.x) < bx0 || min(c.x, d.x) > bx1 || max(c.y, d.y) < by0 || min(c.y, d.y) > by1) { continue; }
    var lo = 3.0e38; var hi = -3.0e38;
    for (var k = 0u; k < 2u; k++) {                         // the circles at the capsule's ends
      let f = a - select(c, d, k == 1u); let bq = dot(e, f); let cq = dot(f, f) - r2;
      if (ee <= 1e-12) { if (cq <= 0.0) { lo = -3.0e38; hi = 3.0e38; } continue; }
      let disc = bq * bq - ee * cq;
      if (disc < 0.0) { continue; }
      let sq = sqrt(disc); let t0 = (-bq - sq) / ee; let t1 = (-bq + sq) / ee;
      if (t0 < lo) { lo = t0; } if (t1 > hi) { hi = t1; }
    }
    let u = d - c; let uu = dot(u, u);
    if (uu > 1e-12) {                                       // the band between them
      let s0 = dot(a - c, u); let sd = dot(e, u);
      let v0 = u.x * (a.y - c.y) - u.y * (a.x - c.x); let vd = u.x * e.y - u.y * e.x; let rv = r * sqrt(uu);
      var blo = -3.0e38; var bhi = 3.0e38;
      if (abs(sd) < 1e-12) { if (s0 < 0.0 || s0 > uu) { bhi = -3.0e38; } }
      else { let p = -s0 / sd; let q = (uu - s0) / sd; blo = max(blo, min(p, q)); bhi = min(bhi, max(p, q)); }
      if (abs(vd) < 1e-12) { if (abs(v0) > rv) { bhi = -3.0e38; } }
      else { let p = (-rv - v0) / vd; let q = (rv - v0) / vd; blo = max(blo, min(p, q)); bhi = min(bhi, max(p, q)); }
      if (blo <= bhi) { if (blo < lo) { lo = blo; } if (bhi > hi) { hi = bhi; } }
    }
    if (lo > hi || hi < 0.0 || lo > 1.0) { continue; }
    var t0 = 0.0; var t1 = 1.0;
    if (lo > 0.0) { t0 = max(0.0, lo - nudge); }
    if (hi < 1.0) { t1 = min(1.0, hi + nudge); }
    addIN(t0, t1);
  }
  return nIN > 0u;
}
// THE STEP'S ENTRIES FOR A STROKE, in order: its records in the blocks found (h * 16 + q, h the block's place in the list,
// which keeps the blocks in order), from the first block at or after its own first
fn hitsNow() -> u32 { return min(atomicLoad(&ctl[14]), F.hitCap); }
fn firstHit(b0: u32, hits: u32) -> u32 {
  var lo = 0u; var hi = hits;
  while (lo < hi) { let m = (lo + hi) >> 1u; if (clist[m] < b0) { lo = m + 1u; } else { hi = m; } }
  return lo * 16u;
}
fn entNext(g0: u32, hits: u32) -> u32 {                      // the stroke's next entry from g0 on, or NONE
  var g = g0;
  loop {
    if ((g >> 4u) >= hits) { return NONE; }
    let i = clist[g >> 4u] * 16u + (g & 15u);
    if (i >= base + nR) { return NONE; }
    if (i >= base && ent[g * 3u] != 0u) { return g; }
    g += 1u;
  }
}
fn entJ(g: u32) -> u32 { return clist[g >> 4u] * 16u + (g & 15u) - base; }
// a stretch done (fm): as it was, untouched, or what is left of it after its cuts
fn finish(A: u32, nA: u32) {
  let e = aEnd(A, fm);
  if (!ft) { put(aStart(A, fm), e); } else { if (lt(fat, e)) { keep(fat, e); } anew(); }
  fm += 1u; ft = false; stretchBegun();
  if (fm < nA) { fat = aStart(A, fm); st0 = fat; }
}
fn gone(A: u32, nA: u32, g0: Pl, g1: Pl) {                   // g0..g1 went (within one stretch, after those before)
  while (fm < nA && !lt(g0, aEnd(A, fm))) { finish(A, nA); }
  ft = true;
  if (lt(fat, g0)) { keep(fat, g0); }
  if (lt(fat, g1)) { fat = g1; }
}
fn cutAlong(A: u32, nA: u32, r: f32, r2: f32) -> bool {
  fm = 0u; fat = aStart(A, 0u); st0 = fat; ft = false; stretchBegun();
  var k = 0u; var any = false; var g0 = fat; var g1 = fat;
  let hits = hitsNow();
  for (var g = entNext(firstHit(base / 16u, hits), hits); g != NONE; g = entNext(g + 1u, hits)) {   // (its segments the step reaches)
    let j = entJ(g);
    if (j + 1u >= nR) { continue; }
    let a = P(j); let b = P(j + 1u);
    let pj = Pl(j, 0.0, a); let pj1 = Pl(j + 1u, 0.0, b);
    while (k < nA && !lt(pj, aEnd(A, k))) { k++; }           // what is left of it along this segment, if anything
    if (k >= nA || !lt(aStart(A, k), pj1)) { continue; }
    let c = ent[g * 3u];
    if (c == 0xffu) { if (!inSweep(a, b, r2, r)) { continue; } }   // (more than its entry holds: worked out again)
    else { nIN = 2u; IN[0] = bitcast<f32>(ent[g * 3u + 1u]); IN[1] = bitcast<f32>(ent[g * 3u + 2u]); }
    let sl = length(b - a);
    for (var q = 0u; q < nIN; q += 2u) {
      let ga = placeAt(j, IN[q]); let gb = placeAt(j, IN[q + 1u]);
      for (var m = k; m < nA; m++) {
        let s0 = aStart(A, m);
        if (!lt(s0, gb)) { break; }
        let s1 = aEnd(A, m);
        var u0 = ga; if (lt(ga, s0)) { u0 = s0; }
        var u1 = gb; if (lt(s1, gb)) { u1 = s1; }
        let f0 = select(1.0, u0.t, u0.j == j); let f1 = select(1.0, u1.t, u1.j == j);
        if ((f1 - f0) * sl < 1e-3) { continue; }            // a graze of an edge already cut: no cut
        if (any && !lt(g1, u0)) { if (lt(g1, u1)) { g1 = u1; } }
        else { if (any) { gone(A, nA, g0, g1); } g0 = u0; g1 = u1; any = true; }
      }
    }
  }
  if (!any) { return false; }
  gone(A, nA, g0, g1);
  while (fm < nA) { finish(A, nA); }
  return true;
}
fn touchedOut(A: u32, nA: u32, r2: f32) -> bool {
  var any = false;
  let hits = hitsNow();
  var g = entNext(firstHit(base / 16u, hits), hits);         // (its segments the step reaches, in order, beside its stretches)
  for (var m = 0u; m < nA; m++) {
    let s0 = aStart(A, m); let s1 = aEnd(A, m);
    var hit = false;
    var jb = s1.j;
    if (s1.t <= 0.0) { if (jb == 0u) { put(s0, s1); continue; } jb -= 1u; }
    while (g != NONE && entJ(g) < s0.j) { g = entNext(g + 1u, hits); }
    for (var h = g; h != NONE && !hit; h = entNext(h + 1u, hits)) {
      let j = entJ(h);
      if (j > jb || j + 1u >= nR) { break; }
      var a = P(j); var b = P(j + 1u);
      if (j == s0.j && s0.t > 0.0) { a = s0.p; }
      if (j == s1.j) { b = s1.p; }
      hit = nearPath(a, b, r2);
    }
    if (hit) { any = true; sk0 = min(sk0, s0.j); sk1 = max(sk1, s1.j + select(0u, 1u, s1.t > 0.0)); } else { put(s0, s1); }
  }
  return any;
}
// the stretches just made (oAt, nO) would put more than seven of the pieces' records in one segment (its point, a new end
// at each cut in it): the draws give a record eight instances, so such a cut is not made (it stays exact)
fn tooMany() -> bool {
  var k = 0xffffffffu; var c = 0u;
  for (var m = 0u; m < nO; m++) {
    let o = oAt + m * 10u;
    if (bitcast<f32>(es[o + 1u]) > 0.0) { if (es[o] != k) { k = es[o]; c = 0u; } c += 1u; if (c > 6u) { return true; } }
    if (bitcast<f32>(es[o + 5u]) > 0.0) { if (es[o + 4u] != k) { k = es[o + 4u]; c = 0u; } c += 1u; if (c > 6u) { return true; } }
  }
  return false;
}
fn nTouched() -> u32 { return min(atomicLoad(&ctl[0]), F.tCap); }
fn touched(t: u32) -> u32 { return atomicLoad(&ctl[F.offT + t]); }
fn slotOf(sid: u32) -> u32 {                                 // a stroke's slot (its header in es), or NONE
  let e = grb[F.stAt + sid * 4u + 3u].x;
  if (e == NONE) { return NONE; }
  return grb[F.evAt + e * 4u + 2u].y;
}
fn segBox(a: vec2<f32>, b: vec2<f32>, lo: vec2<f32>, hi: vec2<f32>) -> bool {   // segment a-b meets the box?
  if (max(a.x, b.x) < lo.x || min(a.x, b.x) > hi.x || max(a.y, b.y) < lo.y || min(a.y, b.y) > hi.y) { return false; }
  let d = b - a; let c = (lo + hi) * 0.5; let e = (hi - lo) * 0.5;
  return abs(d.x * (c.y - a.y) - d.y * (c.x - a.x)) <= abs(d.y) * e.x + abs(d.x) * e.y + 1e-3;
}
// find: each block whose box, out by the eraser's radius and the widest half width, the step's path crosses
@compute @workgroup_size(128) fn find(@builtin(global_invocation_id) id: vec3<u32>) {
  let b = id.x;
  if (b >= F.nb) { return; }
  let B = boxes[b];
  var hit = false;
  if (B.x < B.z) {                                          // (a box worked out is never one point: all zero, none)
    let lo = B.xy - vec2<f32>(F.reach); let hi = B.zw + vec2<f32>(F.reach);
    if (hi.x >= F.lo.x && lo.x <= F.hi.x && hi.y >= F.lo.y && lo.y <= F.hi.y) {
      for (var i = 0u; i < F.nS && !hit; i++) { let s = seg(i); hit = segBox(s.xy, s.zw, lo, hi); }
    }
  }
  flags[b] = select(0u, 1u, hit);
}
@compute @workgroup_size(1) fn hitArgs() {                   // the blocks found (scan's last): reach's threads, sixteen a block
  let all = scan[F.nb];
  var n = all;
  if (n > F.hitCap) { atomicOr(&ctl[2], 1u); n = F.hitCap; }
  atomicStore(&ctl[14], n); atomicStore(&ctl[15], all); atomicStore(&ctl[3], F.frame);
  let w = (n + 3u) / 4u;
  eargs[0] = min(w, 65535u); eargs[1] = (w + 65534u) / 65535u; eargs[2] = 1u;
}
// reach: a record of a block found -- a stroke's segment (or its dot), its stroke drawn now, on the layer in hand -- and
// what of it the step reaches (its entry: how many stretches, then the one; 255: more, worked out again)
@compute @workgroup_size(64) fn reach(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  let g = (wg.x + wg.y * 65535u) * 64u + li;
  if ((g >> 4u) >= hitsNow()) { return; }
  let i = clist[g >> 4u] * 16u + (g & 15u);
  let o = g * 3u;
  ent[o] = 0u;
  let R0 = rec[i]; let f = R0.w & 0xffu;
  if ((f & 3u) == 0u) { return; }
  let sid = R0.w >> 8u;
  if (sid >= F.stCap) { return; }
  let t0 = grb[F.stAt + sid * 4u]; let t1 = grb[F.stAt + sid * 4u + 1u];
  let kw = t1.x;
  if ((kw >> 31u) == 0u || ((kw >> 8u) & 0x7fffffu) != F.layer || i < t0.x || i >= t0.x + t0.y) { return; }
  let hw = bitcast<f32>(t1.y); let r = F.R + hw; let r2 = r * r;
  let a = vec2<f32>(bitcast<f32>(R0.x), bitcast<f32>(R0.y));
  var c = 0u;
  if ((f & 2u) != 0u) { if (pathD2(a) <= r2) { c = 1u; } }   // a dot
  else if (i + 1u < t0.x + t0.y) {
    let R1 = rec[i + 1u]; let b = vec2<f32>(bitcast<f32>(R1.x), bitcast<f32>(R1.y));
    if (F.mode == 1u) { if (nearPath(a, b, r2 * 1.0001 + 1e-6)) { c = 1u; } }   // (touched at all: its stretches tested in stitch)
    else if (inSweep(a, b, r2, r)) {
      c = nIN / 2u;
      if (c > 1u) { c = 0xffu; } else { ent[o + 1u] = bitcast<u32>(IN[0]); ent[o + 2u] = bitcast<u32>(IN[1]); }
    }
  }
  if (c == 0u) { return; }
  ent[o] = c;
  if (atomicMax(&ctl[F.offST + sid], F.frame) != F.frame) {  // (its stroke listed once)
    let t = atomicAdd(&ctl[0], 1u);
    if (t < F.tCap) { atomicStore(&ctl[F.offT + t], sid); } else { atomicOr(&ctl[2], 2u); }
  }
}
@compute @workgroup_size(1) fn touchArgs() {                 // the strokes touched: a thread each, a workgroup each
  let t = nTouched();
  eargs[3] = (t + 63u) / 64u; eargs[4] = 1u; eargs[5] = 1u;
  eargs[6] = min(t, 65535u); eargs[7] = (t + 65534u) / 65535u; eargs[8] = 1u;
}
// alloc: a slot for a stroke touched that has none -- its header, one stretch (all of it), its entry in the table of
// strokes being cut, its number's slot -- its room from the swipe's pools (none left: not made, the step sent again)
@compute @workgroup_size(64) fn alloc(@builtin(global_invocation_id) id: vec3<u32>) {
  if (id.x >= nTouched()) { return; }
  let sid = touched(id.x);
  let at = F.stAt + sid * 4u;
  let t0 = grb[at]; let t1 = grb[at + 1u]; let t2 = grb[at + 2u]; let t3 = grb[at + 3u];
  if (t3.x != NONE) { return; }
  let b = t0.x; let n = t0.y; let kind = t1.x & 0xffu; let gs = t2.y;
  let most = u32(ceil(bitcast<f32>(t3.y) / (F.R / 2.0))) + 3u;   // (a kept stretch is half the eraser long at least)
  let cap = min(most, 4u);
  let mapN = (n + 3u) / 4u; let nB = n + 2u * cap + 2u;   // (its pieces; drawn by range, its stretches' table: spans)
  let esN = HDR + 20u * cap;
  let S = atomicAdd(&ctl[4], esN);
  if (S + esN > atomicLoad(&ctl[5])) { atomicOr(&ctl[2], 4u); return; }
  let allocAt = atomicAdd(&ctl[6], mapN + nB);
  if (allocAt + mapN + nB > atomicLoad(&ctl[7])) { atomicOr(&ctl[2], 8u); return; }
  var gAt = 0u;
  if (kind >= 2u) { gAt = atomicAdd(&ctl[8], nB); if (gAt + nB > atomicLoad(&ctl[9])) { atomicOr(&ctl[2], 16u); return; } }
  let e = atomicAdd(&ctl[10], 1u);
  if (e >= atomicLoad(&ctl[11])) { atomicOr(&ctl[2], 32u); return; }
  let k = atomicAdd(&ctl[12], 1u);
  if (k >= F.slCap) { atomicOr(&ctl[2], 128u); return; }
  let areaAt = allocAt + mapN; let mapAt = allocAt;         // (its map, a word a point, just before its pieces)
  let p0 = rec[b]; let p1 = rec[b + n - 1u];
  es[S] = b; es[S + 1u] = n; es[S + 2u] = kind; es[S + 3u] = t1.y; es[S + 4u] = cap; es[S + 5u] = S + HDR; es[S + 6u] = 0u; es[S + 7u] = 1u;
  es[S + 8u] = areaAt; es[S + 9u] = nB; es[S + 10u] = gAt; es[S + 11u] = nB; es[S + 12u] = F.frame; es[S + 13u] = select(gs, 0u, gs == NONE);
  es[S + 14u] = 0u; es[S + 15u] = 0u; es[S + 16u] = 1u; es[S + 17u] = 0u; es[S + 18u] = sid; es[S + 19u] = allocAt;
  es[S + 20u] = most; es[S + 21u] = e; es[S + 22u] = 0u; es[S + 23u] = 0u;
  let A = S + HDR;                                            // (its pieces written this step: one, all of it)
  es[A] = 0u; es[A + 1u] = 0u; es[A + 2u] = p0.x; es[A + 3u] = p0.y;
  es[A + 4u] = n - 1u; es[A + 5u] = 0u; es[A + 6u] = p1.x; es[A + 7u] = p1.y; es[A + 8u] = 0u; es[A + 9u] = 0u;
  let v = F.evAt + e * 4u;
  grb[v] = vec2<u32>(b, n); grb[v + 1u] = vec2<u32>(mapAt, areaAt); grb[v + 2u] = vec2<u32>(gAt, S); grb[v + 3u] = vec2<u32>(sid, 0u);
  grb[at + 3u] = vec2<u32>(e, t3.y);
  atomicStore(&ctl[F.offSL + k], S);
  atomicAdd(&ctl[13], HDR + 10u);                            // (its pack: its header, its one stretch)
}
// a slot's room made larger, its stretches kept (a cut needs more of them than it has room for): four times as many, no
// more than it can have; its pieces' place (and their grain's) larger too, its entry pointed at them -> made?
fn grow(S: u32, A: u32, nA: u32) -> bool {
  let cap = es[S + 4u]; let most = es[S + 20u];
  if (cap >= most) { return false; }                         // (at its most already: not cut, as it was)
  let nc = min(most, cap * 4u); let n = es[S + 1u];
  let mapN = (n + 3u) / 4u; let nB = n + 2u * nc + 2u;
  let A2 = atomicAdd(&ctl[4], 20u * nc);
  if (A2 + 20u * nc > atomicLoad(&ctl[5])) { atomicOr(&ctl[2], 4u); return false; }
  let at = atomicAdd(&ctl[6], mapN + nB);
  if (at + mapN + nB > atomicLoad(&ctl[7])) { atomicOr(&ctl[2], 8u); return false; }
  var g = 0u;
  if (es[S + 2u] >= 2u) { g = atomicAdd(&ctl[8], nB); if (g + nB > atomicLoad(&ctl[9])) { atomicOr(&ctl[2], 16u); return false; } }
  for (var k = 0u; k < nA * 10u; k++) { es[A2 + k] = es[A + k]; }
  es[S + 4u] = nc; es[S + 5u] = A2; es[S + 6u] = 0u;
  es[S + 8u] = at + mapN; es[S + 9u] = nB; es[S + 10u] = g; es[S + 11u] = nB; es[S + 12u] = F.frame; es[S + 19u] = at;
  let v = F.evAt + grb[F.stAt + es[S + 18u] * 4u + 3u].x * 4u;
  grb[v + 1u] = vec2<u32>(at, at + mapN); grb[v + 2u] = vec2<u32>(g, S);
  return true;
}
// STITCH, DATA-PARALLEL (a workgroup a stroke touched): cutAlong and touchedOut made by its sixty-four threads at once,
// the same arithmetic in the same order (the same stretches). Its stretches into the workgroup's memory (xS: [2m] where
// stretch m starts, [2m + 1] where it ends). Its entries sixty-four at a time, a thread each: the runs of what the step took
// along the entry's segment, each within one stretch, as cutAlong joins them (a run goes on while the next part taken
// begins at or before its end), the first joined to the last run of the entry before it that has one; the runs numbered
// in order by a scan (rG0 where each begins, rG1 where it ends, rM its stretch). Then a thread a run: the piece before it
// (from its stretch's start, or the run before it in the stretch) and, the last of its stretch, the piece after it --
// each, if it has length, long enough or a crumb (rF: 1 a piece before, 2 long enough; 4 a piece after, 8 long enough).
// Then a thread a stretch: as it was, or its pieces long enough; their places in order (a scan), the room for them (grow),
// laid down; then too many new ends in one segment (tooMany), a thread an output; what was made anew (sk) and the slot's
// header by one. touchedOut: each entry tests the stretches its segment lies in; a stretch reached goes whole. A dot, or
// more stretches or runs than the lists hold: one thread, where they lie (cutAlong, touchedOut)
const XS: u32 = 64u;
const XR: u32 = 64u;
var<workgroup> xS: array<vec4<u32>, 128>;
var<workgroup> rG0: array<vec4<u32>, 64>;
var<workgroup> rG1: array<vec4<u32>, 64>;
var<workgroup> rM: array<u32, 64>;
var<workgroup> rF: array<u32, 64>;
var<workgroup> xL: array<vec4<u32>, 64>;                     // (an entry's last run's end, these sixty-four)
var<workgroup> xA: array<u32, 64>;                           // (the scans)
var<workgroup> xOwn: array<atomic<u32>, 64>;                 // (who ends a run, of these sixty-four)
var<workgroup> xHit: array<atomic<u32>, 64>;                 // (touchedOut: a stretch reached)
var<workgroup> xFlag: atomic<u32>;                           // 1 more than the lists hold, 2 too many new ends in a segment
var<workgroup> cRuns: u32;
var<workgroup> cHas: u32;
var<workgroup> cLast: vec4<u32>;                             // (carried from sixty-four to the next: runs, the last run's end)
var<private> lU0: array<Pl, 4>; var<private> lU1: array<Pl, 4>; var<private> lM: array<u32, 4>;
var<private> nL: u32; var<private> lOver: bool;
fn xPl(v: vec4<u32>) -> Pl { return Pl(v.x, bitcast<f32>(v.y), vec2<f32>(bitcast<f32>(v.z), bitcast<f32>(v.w))); }
fn plX(q: Pl) -> vec4<u32> { return vec4<u32>(q.j, bitcast<u32>(q.t), bitcast<u32>(q.p.x), bitcast<u32>(q.p.y)); }
fn xStart(m: u32) -> Pl { return xPl(xS[2u * m]); }
fn xEnd(m: u32) -> Pl { return xPl(xS[2u * m + 1u]); }
fn placeAB(j: u32, t: f32, a: vec2<f32>, b: vec2<f32>) -> Pl {   // placeAt, the segment's ends in hand
  if (t <= 0.0) { return Pl(j, 0.0, a); }
  if (t >= 1.0) { return Pl(j + 1u, 0.0, b); }
  return Pl(j, t, a + (b - a) * t);
}
fn wscan(li: u32, v: u32, most: bool) -> vec3<u32> {         // over the sixty-four (sums, or the most): to here, before here, all
  xA[li] = v;
  workgroupBarrier();
  for (var d = 1u; d < 64u; d <<= 1u) {
    var t = xA[li];
    if (li >= d) { let u = xA[li - d]; t = select(t + u, max(t, u), most); }
    workgroupBarrier();
    xA[li] = t;
    workgroupBarrier();
  }
  var ex = 0u; if (li > 0u) { ex = xA[li - 1u]; }
  let out = vec3<u32>(xA[li], ex, xA[63]);
  workgroupBarrier();
  return out;
}
fn entryRuns(j: u32, c: u32, it: vec2<f32>, a: vec2<f32>, b: vec2<f32>, nA: u32, r: f32, r2: f32) {   // (lU0, lU1, lM, nL)
  nL = 0u; lOver = false;
  if (j + 1u >= nR) { return; }
  let pj = Pl(j, 0.0, a); let pj1 = Pl(j + 1u, 0.0, b);
  var lo = 0u; var hi = nA;                                  // (the first stretch ending after the segment's start)
  while (lo < hi) { let md = (lo + hi) >> 1u; if (!lt(pj, xEnd(md))) { lo = md + 1u; } else { hi = md; } }
  let k = lo;
  if (k >= nA || !lt(xStart(k), pj1)) { return; }
  if (c == 0xffu) { if (!inSweep(a, b, r2, r)) { return; } }   // (more than its entry holds: worked out again)
  else { nIN = 2u; IN[0] = it.x; IN[1] = it.y; }
  let sl = length(b - a);
  for (var q = 0u; q < nIN; q += 2u) {
    let ga = placeAB(j, IN[q], a, b); let gb = placeAB(j, IN[q + 1u], a, b);
    for (var m = k; m < nA; m++) {
      let s0 = xStart(m);
      if (!lt(s0, gb)) { break; }
      let s1 = xEnd(m);
      var u0 = ga; if (lt(ga, s0)) { u0 = s0; }
      var u1 = gb; if (lt(s1, gb)) { u1 = s1; }
      let f0 = select(1.0, u0.t, u0.j == j); let f1 = select(1.0, u1.t, u1.j == j);
      if ((f1 - f0) * sl < 1e-3) { continue; }              // a graze of an edge already cut: no cut
      if (nL > 0u && !lt(lU1[nL - 1u], u0)) { if (lt(lU1[nL - 1u], u1)) { lU1[nL - 1u] = u1; } }
      else { if (nL >= 4u) { lOver = true; return; } lU0[nL] = u0; lU1[nL] = u1; lM[nL] = m; nL += 1u; }
    }
  }
}
fn entryHits(j: u32, a: vec2<f32>, b: vec2<f32>, nA: u32, r2: f32) {   // touchedOut's test of segment j, in each stretch it lies in
  if (j + 1u >= nR) { return; }
  var lo = 0u; var hi = nA;                                  // (the first stretch whose last segment is j or after)
  while (lo < hi) {
    let md = (lo + hi) >> 1u; let e = xEnd(md);
    if (e.j - select(0u, 1u, e.t <= 0.0) < j) { lo = md + 1u; } else { hi = md; }
  }
  for (var m = lo; m < nA; m++) {
    let s0 = xStart(m); let s1 = xEnd(m);
    if (s0.j > j) { break; }
    if (s1.t <= 0.0 && s1.j == 0u) { continue; }
    var a2 = a; var b2 = b;
    if (j == s0.j && s0.t > 0.0) { a2 = s0.p; }
    if (j == s1.j) { b2 = s1.p; }
    if (nearPath(a2, b2, r2)) { atomicOr(&xHit[m], 1u); }
  }
}
fn xOut(o: u32, c: vec4<u32>, d: vec4<u32>) {               // put, at its place
  es[o] = c.x; es[o + 1u] = c.y; es[o + 2u] = c.z; es[o + 3u] = c.w;
  es[o + 4u] = d.x; es[o + 5u] = d.y; es[o + 6u] = d.z; es[o + 7u] = d.w; es[o + 8u] = 0u; es[o + 9u] = 0u;
}
// stitch: a stroke touched, cut (or its stretches taken) by its entries, in order -- a workgroup a stroke (above)
var<workgroup> sGo: u32;
var<workgroup> sS: u32;
var<workgroup> sG0: u32;
var<workgroup> sN: u32;
var<workgroup> sNA: u32;
var<workgroup> sA: u32;
var<workgroup> sBad: u32;
var<workgroup> sRuns: u32;
var<workgroup> sOk: u32;
var<workgroup> sOAt: u32;
@compute @workgroup_size(64) fn stitch(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  let w = wg.x + wg.y * 65535u;
  if (li == 0u) {
    var go = 0u; var S0 = NONE; var g0 = 0u; var n = 0u; var A0 = 0u; var nA0 = 0u;
    if (w < nTouched()) {
      S0 = slotOf(touched(w));                               // (none: no room for one -- the step is sent again)
      if (S0 != NONE && es[S0 + 7u] != 0u) {                 // (no stretch left: all of it gone already)
        let b = es[S0]; let nr = es[S0 + 1u]; let hits = hitsNow();
        g0 = firstHit(b / 16u, hits); n = firstHit((b + nr - 1u) / 16u + 1u, hits) - g0;
        nA0 = es[S0 + 7u]; A0 = es[S0 + 5u] + es[S0 + 6u] * es[S0 + 4u] * 10u;
        go = select(2u, 1u, nr > 1u && nA0 <= XS);           // (a dot, or more stretches than the list holds: one thread)
      }
    }
    sGo = go; sS = S0; sG0 = g0; sN = n; sNA = nA0; sA = A0;
    cRuns = 0u; cHas = 0u; atomicStore(&xFlag, 0u);
  }
  atomicStore(&xHit[li], 0u);
  let go = workgroupUniformLoad(&sGo);
  if (go == 0u) { return; }
  let S = workgroupUniformLoad(&sS);
  base = es[S]; nR = es[S + 1u]; wk = es[S + 2u];
  let r = F.R + bitcast<f32>(es[S + 3u]); let r2 = r * r;
  if (go == 1u) {
    let g0 = workgroupUniformLoad(&sG0); let n = workgroupUniformLoad(&sN);
    let nA = workgroupUniformLoad(&sNA); let A = workgroupUniformLoad(&sA);
    for (var m = li; m < nA; m += 64u) {
      let o = A + m * 10u;
      xS[2u * m] = vec4<u32>(es[o], es[o + 1u], es[o + 2u], es[o + 3u]);
      xS[2u * m + 1u] = vec4<u32>(es[o + 4u], es[o + 5u], es[o + 6u], es[o + 7u]);
    }
    workgroupBarrier();
    for (var c0 = 0u; c0 < n; c0 += 64u) {                  // (the entries, sixty-four at once)
      let k = c0 + li; var c = 0u; var g = 0u; var i = 0u;
      if (k < n) { g = g0 + k; i = clist[g >> 4u] * 16u + (g & 15u); if (i >= base && i < base + nR) { c = ent[g * 3u]; } }
      nL = 0u; lOver = false;
      if (c != 0u) {
        let j = i - base; let a = P(j); var e = a;
        if (j + 1u < nR) { e = P(j + 1u); }
        if (F.mode == 1u) { entryHits(j, a, e, nA, r2); }
        else { entryRuns(j, c, vec2<f32>(bitcast<f32>(ent[g * 3u + 1u]), bitcast<f32>(ent[g * 3u + 2u])), a, e, nA, r, r2); }
      }
      if (lOver) { atomicOr(&xFlag, 1u); }
      if (F.mode != 1u) {
        let has = nL > 0u;
        if (has) { xL[li] = plX(lU1[nL - 1u]); }
        atomicStore(&xOwn[li], 0u);
        let pv = wscan(li, select(0u, li + 1u, has), true);   // (the entry before it here with a run: pv.y - 1; the last: pv.z - 1)
        var join = false;
        if (has) {
          if (pv.y > 0u) { join = !lt(xPl(xL[pv.y - 1u]), lU0[0]); }
          else if (cHas != 0u) { join = !lt(xPl(cLast), lU0[0]); }
        }
        let jn = select(0u, 1u, join);
        let st = wscan(li, select(0u, nL - jn, has), false);  // (runs begun, in order)
        let before = cRuns + st.y;
        for (var l = 0u; l < nL; l++) {
          let rr = before + l - jn;
          if (rr >= XR) { atomicOr(&xFlag, 1u); break; }
          if (l > 0u || !join) { rG0[rr] = plX(lU0[l]); rM[rr] = lM[l]; }
          atomicMax(&xOwn[rr], li * 4u + l + 1u);
        }
        workgroupBarrier();
        for (var l = 0u; l < nL; l++) {
          let rr = before + l - jn;
          if (rr < XR && atomicLoad(&xOwn[rr]) == li * 4u + l + 1u) { rG1[rr] = plX(lU1[l]); }   // (where its run ends, so far)
        }
        if (li == 0u) { cRuns = cRuns + st.z; if (pv.z > 0u) { cLast = xL[pv.z - 1u]; cHas = 1u; } }
        workgroupBarrier();
      }
    }
    if (li == 0u) { sBad = atomicLoad(&xFlag); sRuns = cRuns; }
    let bad = workgroupUniformLoad(&sBad); let nRuns = workgroupUniformLoad(&sRuns);
    if (bad == 0u) {
      if (F.mode != 1u && nRuns == 0u) { return; }           // (nothing the step took: as it was)
      if (F.mode != 1u && li < nRuns) {                      // (a run's pieces)
        let m = rM[li];
        let first = li == 0u || rM[li - 1u] != m;
        let last = li + 1u >= nRuns || rM[li + 1u] != m;
        var c = xStart(m); if (!first) { c = xPl(rG1[li - 1u]); }
        let d = xPl(rG0[li]);
        var f = 0u;
        if (lt(c, d)) { f = 1u; if (lengthOver(c, d)) { f = 3u; } }
        if (last) { let c2 = xPl(rG1[li]); let d2 = xEnd(m); if (lt(c2, d2)) { f |= 4u; if (lengthOver(c2, d2)) { f |= 8u; } } }
        rF[li] = f;
      }
      workgroupBarrier();
      var cnt = 0u; var rf = 0u; var rl = 0u; var cut = false;   // (a stretch: what it lays down)
      if (li < nA) {
        if (F.mode == 1u) { cnt = select(1u, 0u, atomicLoad(&xHit[li]) != 0u); }
        else {
          var lo = 0u; var hi = nRuns;
          while (lo < hi) { let md = (lo + hi) >> 1u; if (rM[md] < li) { lo = md + 1u; } else { hi = md; } }
          if (lo < nRuns && rM[lo] == li) {
            cut = true; rf = lo; rl = lo;
            while (rl + 1u < nRuns && rM[rl + 1u] == li) { rl += 1u; }
            for (var q = rf; q <= rl; q++) { let f = rF[q]; cnt += select(0u, 1u, (f & 3u) == 3u) + select(0u, 1u, (f & 12u) == 12u); }
          } else { cnt = 1u; }
        }
      }
      let oc = wscan(li, cnt, false);
      if (li == 0u) {                                        // (the room for them: grown as cutAlong grows it)
        var ok = 0u; var at = 0u;
        if (F.mode != 1u || oc.z != nA) {
          for (var tries = 0u; tries < 6u; tries++) {
            let cap = es[S + 4u]; let cur = es[S + 6u];
            if (oc.z <= cap) { ok = 1u; at = es[S + 5u] + (1u - cur) * cap * 10u; break; }
            if (!grow(S, es[S + 5u] + cur * cap * 10u, nA)) { break; }
          }
        }
        sOk = ok; sOAt = at;
      }
      let ok = workgroupUniformLoad(&sOk);
      if (ok == 0u) { return; }
      let at = workgroupUniformLoad(&sOAt);
      if (li < nA) {                                         // (laid down)
        var o = at + oc.y * 10u;
        if (cut) {
          for (var q = rf; q <= rl; q++) {
            let f = rF[q];
            if ((f & 3u) == 3u) { var c = xS[2u * li]; if (q > rf) { c = rG1[q - 1u]; } xOut(o, c, rG0[q]); o += 10u; }
            if ((f & 12u) == 12u) { xOut(o, rG1[q], xS[2u * li + 1u]); o += 10u; }
          }
        } else if (cnt == 1u) { xOut(o, xS[2u * li], xS[2u * li + 1u]); }
      }
      storageBarrier();
      for (var o = li; o < oc.z; o += 64u) {                 // (tooMany: seven new ends in one segment)
        for (var h = 0u; h < 2u; h++) {
          let q = at + o * 10u + h * 4u;
          if (bitcast<f32>(es[q + 1u]) > 0.0) {
            let p6 = 2u * o + h + 6u;
            if (p6 < 2u * oc.z) {
              let q6 = at + (p6 >> 1u) * 10u + (p6 & 1u) * 4u;
              if (bitcast<f32>(es[q6 + 1u]) > 0.0 && es[q6] == es[q]) { atomicOr(&xFlag, 2u); }
            }
          }
        }
      }
      workgroupBarrier();
      if (li != 0u) { return; }
      if ((atomicLoad(&xFlag) & 2u) != 0u) { return; }
      sk0 = 0xffffffffu; sk1 = 0u;                           // (what was made anew, as cutAlong and touchedOut work it out)
      if (F.mode == 1u) {
        for (var m = 0u; m < nA; m++) {
          if (atomicLoad(&xHit[m]) != 0u) { let s0 = xStart(m); let s1 = xEnd(m); sk0 = min(sk0, s0.j); sk1 = max(sk1, s1.j + select(0u, 1u, s1.t > 0.0)); }
        }
      } else {
        var q = 0u;
        while (q < nRuns) {
          let m = rM[q]; st0 = xStart(m); stretchBegun();
          loop {
            let f = rF[q];
            if ((f & 1u) != 0u) { var c = st0; if (q > 0u && rM[q - 1u] == m) { c = xPl(rG1[q - 1u]); } keepNote(c, xPl(rG0[q]), (f & 2u) != 0u); }
            if ((f & 4u) != 0u) { keepNote(xPl(rG1[q]), xEnd(m), (f & 8u) != 0u); }
            q += 1u;
            if (q >= nRuns || rM[q] != m) { break; }
          }
          anew();
        }
      }
      let cur = es[S + 6u]; let nO2 = oc.z;
      let again = es[S + 15u] == F.frame;
      es[S + 16u] = select(sk0, min(es[S + 16u], sk0), again); es[S + 17u] = select(sk1, max(es[S + 17u], sk1), again);
      atomicAdd(&ctl[13], (nO2 - nA) * 10u);                // (its pack: its stretches now)
      es[S + 6u] = 1u - cur; es[S + 7u] = nO2; es[S + 12u] = F.frame; es[S + 14u] = es[S + 14u] + 1u; es[S + 15u] = F.frame;
      return;
    }
  }
  if (li != 0u) { return; }
  for (var tries = 0u; tries < 6u; tries++) {               // ONE THREAD, WHERE THEY LIE (more stretches than its room: room for more, and the cut again)
    let cap = es[S + 4u]; let cur = es[S + 6u]; let nA = es[S + 7u];
    if (nA == 0u) { return; }                                // all of it gone already
    let A = es[S + 5u] + cur * cap * 10u;
    oAt = es[S + 5u] + (1u - cur) * cap * 10u; nO = 0u; capO = cap; full = false;
    sk0 = 0xffffffffu; sk1 = 0u;
    var took = false;
    if (nR == 1u) { took = true; sk0 = 0u; sk1 = 1u; }     // a dot the step reached: gone
    else if (F.mode == 1u) { took = touchedOut(A, nA, r2); }
    else { took = cutAlong(A, nA, r, r2); }
    if (!took) { return; }
    if (full) { if (grow(S, A, nA)) { continue; } return; }
    if (tooMany()) { return; }
    let again = es[S + 15u] == F.frame;
    es[S + 16u] = select(sk0, min(es[S + 16u], sk0), again); es[S + 17u] = select(sk1, max(es[S + 17u], sk1), again);
    atomicAdd(&ctl[13], (nO - nA) * 10u);                   // (its pack: its stretches now)
    es[S + 6u] = 1u - cur; es[S + 7u] = nO; es[S + 12u] = F.frame; es[S + 14u] = es[S + 14u] + 1u; es[S + 15u] = F.frame;
    return;
  }
}
// mark: a grain or wash stroke cut for the first time -- its records say so (CUT), sixty-four threads a stroke (its
// pieces are drawn each at its own depth). A pen's or a highlighter's records say so only about a cut (cutNear, below):
// the rest of it draws as it always did, as its pieces will
var<workgroup> wNeed: u32;
var<workgroup> wS: u32;
@compute @workgroup_size(64) fn mark(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  let w = wg.x + wg.y * 65535u;
  if (li == 0u) {
    var need = 0u; var S = NONE;
    if (w < nTouched()) { S = slotOf(touched(w)); if (S != NONE && es[S + 14u] > 0u && es[S + 2u] >= 2u && (rec[es[S]].w & 16u) == 0u) { need = 1u; } }
    wNeed = need; wS = S;
  }
  workgroupBarrier();
  if (wNeed == 0u) { return; }
  let S = wS; let b = es[S]; let n = es[S + 1u];
  for (var k = li; k < n; k += 64u) { rec[b + k].w = rec[b + k].w | 16u; }
}
fn xy(i: u32) -> vec2<f32> { let r = rec[i]; return vec2<f32>(bitcast<f32>(r.x), bitcast<f32>(r.y)); }
fn mapDone() { if (mk != 0xffffffffu && mc > 0u) { rec[mAt + (mk >> 2u)][mk & 3u] = (ms << 3u) | min(mc, 7u); } }
fn mapNote(k: u32, pos: u32) {                               // a piece's record at pos came from point k's segment
  if (k != mk) { mapDone(); mk = k; ms = pos; mc = 0u; }
  mc += 1u;
}
fn turnAt(p0: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> u32 {  // a highlighter's flags at a, as a fresh part works them out
  var e = a - p0; var Ln = sqrt(dot(e, e));
  let pdx = e.x / Ln; let pdy = e.y / Ln;
  e = b - a; Ln = sqrt(dot(e, e));
  let cross = pdx * (e.y / Ln) - pdy * (e.x / Ln);
  if (abs(cross) >= 1e-6) { return select(5u, 13u, cross > 0.0); }
  return 1u;
}
fn grain(i: u32) -> f32 { return bitcast<f32>(grb[i].x); }
fn grainPut(i: u32, d: f32, m: u32) { grb[i] = vec2<u32>(bitcast<u32>(d), bitcast<u32>(f32(m))); }
fn piecesOne(S: u32) {                                      // (a stroke's pieces, one thread)
  base = es[S]; nR = es[S + 1u];
  let kind = es[S + 2u]; let cap = es[S + 4u]; let A = es[S + 5u] + es[S + 6u] * cap * 10u; let nA = es[S + 7u];
  let area = es[S + 8u]; let g = es[S + 10u]; let hi = es[S + 11u]; let gs = es[S + 13u];
  let hl = kind == 1u; let gr = kind >= 2u;
  mAt = area - (nR + 3u) / 4u; mk = 0xffffffffu; ms = 0u; mc = 0u;   // its map, just before its pieces
  for (var z = 0u; z < (nR + 3u) / 4u; z++) { rec[mAt + z] = vec4<u32>(0u); }
  var pos = 0u;
  for (var m = 0u; m < nA; m++) {
    let o = A + m * 10u;
    let j0 = es[o]; let t0 = bitcast<f32>(es[o + 1u]); let j1 = es[o + 4u]; let t1 = bitcast<f32>(es[o + 5u]);
    let start = pos;
    if (nR == 1u) {                                          // a dot, as it is
      var d0 = rec[base]; d0.w = d0.w & 0xffffffefu; rec[area + pos] = d0; mapNote(0u, pos);
      if (gr) { var d = 1.0; if (kind == 2u) { d = grain(gs); } grainPut(g + pos, d, m); }
      pos += 1u; es[o + 8u] = start; es[o + 9u] = 1u; continue;
    }
    let h = t0 > 0.0; let t = t1 > 0.0;
    let i0 = select(j0, j0 + 1u, h);
    let total = select(0u, 1u, h) + (j1 + 1u - i0) + select(0u, 1u, t);
    var tailGone = false;
    for (var q = 0u; q < total; q++) {
      var src = i0 + q - select(0u, 1u, h);
      var r: vec4<u32>;
      let isT = t && q == total - 1u;
      if (h && q == 0u) { src = i0; r = rec[base + src]; r.x = es[o + 2u]; r.y = es[o + 3u]; }
      else if (isT) { src = j1 + 1u; r = rec[base + src]; r.x = es[o + 6u]; r.y = es[o + 7u]; }
      else { r = rec[base + src]; }
      r.w = r.w & 0xffffffefu;                                 // (a piece's records: the stroke's number, not the cut's flag)
      if (hl && pos > start && ((h && q == 1u) || isT)) {       // on the record beside a new end: dropped
        let lp = rec[area + pos - 1u];
        if (abs(bitcast<f32>(r.x) - bitcast<f32>(lp.x)) <= 1e-6 && abs(bitcast<f32>(r.y) - bitcast<f32>(lp.y)) <= 1e-6) { if (isT) { tailGone = true; } continue; }
      }
      rec[area + pos] = r; mapNote(select(select(src, j1, isT), j0, h && q == 0u), pos);
      if (gr) { var d = 1.0; if (kind == 2u) { d = grain(gs + src); } grainPut(g + pos, d, m); }
      pos += 1u;
    }
    let n = pos - start;
    if (n > 0u) {
      rec[area + start].w = (rec[area + start].w & 0xffffff00u) | 1u;
      rec[area + pos - 1u].w = rec[area + pos - 1u].w & 0xffffff00u;
      if (hl && n > 2u) {
        if (h) { let i = area + start + 1u; rec[i].w = (rec[i].w & 0xffffff00u) | turnAt(xy(i - 1u), xy(i), xy(i + 1u)); }
        if (t && !tailGone) { let i = area + pos - 2u; rec[i].w = (rec[i].w & 0xffffff00u) | turnAt(xy(i - 1u), xy(i), xy(i + 1u)); }
      }
    }
    es[o + 8u] = start; es[o + 9u] = n;
  }
  mapDone();
  for (var z = pos; z < hi; z++) { rec[area + z] = vec4<u32>(0u); if (gr) { grb[g + z] = vec2<u32>(0u); } }
  es[S + 11u] = pos;
  if (hl) { atomicAdd(&ctl[13], (pos - es[S + 22u]) * 4u); es[S + 22u] = pos; }   // (a highlighter's pack: its pieces' records)
}
// THE PIECES, WRITTEN AS A SLOT IS FLIPPED (while it is cut it is drawn by range: spans), SIXTY-FOUR THREADS A STROKE (a
// workgroup a slot of the frame's flips): each stretch's records counted (pCnt: how many, bit 31
// the record beside its head dropped, bit 30 its tail dropped -- a highlighter's, where it lies on the record before), their
// places summed (pOff), then each record written by a thread of its own, its point's map word by the first of that
// point's records, and last each piece's turns and place: the same records, bit for bit, as piecesOne writes them
var<workgroup> pCnt: array<u32, 1024>;
var<workgroup> pOff: array<u32, 1024>;
var<workgroup> pGo: u32;
var<workgroup> pS: u32;
var<workgroup> pTot: u32;
fn near6(a: vec2<f32>, b: vec2<f32>) -> bool { return abs(a.x - b.x) <= 1e-6 && abs(a.y - b.y) <= 1e-6; }
fn stretchCount(A: u32, m: u32, hl: bool) -> u32 {          // its records, and which beside a new end it drops
  if (nR == 1u) { return 1u; }
  let o = A + m * 10u;
  let j0 = es[o]; let j1 = es[o + 4u]; let h = bitcast<f32>(es[o + 1u]) > 0.0; let t = bitcast<f32>(es[o + 5u]) > 0.0;
  let i0 = select(j0, j0 + 1u, h);
  let total = select(0u, 1u, h) + (j1 + 1u - i0) + select(0u, 1u, t);
  var hd = false; var td = false;
  if (hl) {
    let hp = vec2<f32>(bitcast<f32>(es[o + 2u]), bitcast<f32>(es[o + 3u]));
    if (h && !(t && total == 2u)) { hd = near6(xy(base + i0), hp); }
    if (t) {
      let qp = total - 2u;                                   // (the record before the tail, as written)
      var lp = hp;
      if (!(h && (qp == 0u || (qp == 1u && hd)))) { lp = xy(base + i0 + qp - select(0u, 1u, h)); }
      td = near6(vec2<f32>(bitcast<f32>(es[o + 6u]), bitcast<f32>(es[o + 7u])), lp);
    }
  }
  return (total - select(0u, 1u, hd) - select(0u, 1u, td)) | select(0u, 1u << 31u, hd) | select(0u, 1u << 30u, td);
}
fn stretchHolding(p: u32, nA: u32) -> u32 {                 // the stretch whose records hold place p
  var lo = 0u; var hi = nA;
  while (lo + 1u < hi) { let m = (lo + hi) >> 1u; if (pOff[m] <= p) { lo = m; } else { hi = m; } }
  return lo;
}
fn pieceAt(A: u32, p: u32, nA: u32) -> vec4<u32> {          // place p -> its stretch, the q it is, its source record, its point
  let m = stretchHolding(p, nA);
  if (nR == 1u) { return vec4<u32>(m, 0u, 0u, 0u); }
  let o = A + m * 10u;
  let j0 = es[o]; let j1 = es[o + 4u]; let h = bitcast<f32>(es[o + 1u]) > 0.0; let t = bitcast<f32>(es[o + 5u]) > 0.0;
  let i0 = select(j0, j0 + 1u, h);
  let total = select(0u, 1u, h) + (j1 + 1u - i0) + select(0u, 1u, t);
  let qq = p - pOff[m];
  let q = qq + select(0u, 1u, (pCnt[m] >> 31u) == 1u && qq >= 1u);
  if (h && q == 0u) { return vec4<u32>(m, q, i0, j0); }
  if (t && q == total - 1u) { return vec4<u32>(m, q, j1 + 1u, j1); }
  let src = i0 + q - select(0u, 1u, h);
  return vec4<u32>(m, q, src, src);
}
@compute @workgroup_size(64) fn piecesF(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  let w = wg.x + wg.y * 65535u;
  if (li == 0u) {
    var go = 0u; var S0 = NONE;
    if (w < min(atomicLoad(&ctl[19]), F.slCap)) { S0 = ent[5u * w]; go = select(1u, 2u, es[S0 + 7u] > 1024u); }
    pGo = go; pS = S0;
  }
  let go = workgroupUniformLoad(&pGo);
  if (go == 0u) { return; }
  let S = workgroupUniformLoad(&pS);
  if (go == 2u) { if (li == 0u) { piecesOne(S); written(S); } return; }   // (more stretches than the workgroup keeps)
  piecesOf(S, li);
}
fn piecesOf(S: u32, li: u32) {
  base = es[S]; nR = es[S + 1u];
  let kind = es[S + 2u]; let cap = es[S + 4u]; let A = es[S + 5u] + es[S + 6u] * cap * 10u; let nA = es[S + 7u];
  let area = es[S + 8u]; let g = es[S + 10u]; let hi = es[S + 11u]; let gs = es[S + 13u];
  let hl = kind == 1u; let gr = kind >= 2u; let mapAt = area - (nR + 3u) / 4u;
  for (var z = li; z < (nR + 3u) / 4u; z += 64u) { rec[mapAt + z] = vec4<u32>(0u); }
  for (var m = li; m < nA; m += 64u) { pCnt[m] = stretchCount(A, m, hl); }
  workgroupBarrier();
  if (li == 0u) { var at = 0u; for (var m = 0u; m < nA; m++) { pOff[m] = at; at += pCnt[m] & 0x3fffffffu; } pTot = at; }
  let pos = workgroupUniformLoad(&pTot);
  storageBarrier();
  for (var p = li; p < pos; p += 64u) {                      // each record, as piecesOne writes it
    let c = pieceAt(A, p, nA);
    let m = c.x; let o = A + m * 10u;
    var r = rec[base + c.z];
    if (nR > 1u) {
      let h = bitcast<f32>(es[o + 1u]) > 0.0; let t = bitcast<f32>(es[o + 5u]) > 0.0;
      let j0 = es[o]; let j1 = es[o + 4u]; let i0 = select(j0, j0 + 1u, h);
      let total = select(0u, 1u, h) + (j1 + 1u - i0) + select(0u, 1u, t);
      if (h && c.y == 0u) { r.x = es[o + 2u]; r.y = es[o + 3u]; }
      else if (t && c.y == total - 1u) { r.x = es[o + 6u]; r.y = es[o + 7u]; }
    }
    r.w = r.w & 0xffffffefu;
    if (nR > 1u) {
      let n = pCnt[m] & 0x3fffffffu; let qq = p - pOff[m];
      if (qq == n - 1u) { r.w = r.w & 0xffffff00u; } else if (qq == 0u) { r.w = (r.w & 0xffffff00u) | 1u; }
    }
    rec[area + p] = r;
    if (gr) { var d = 1.0; if (kind == 2u) { d = grain(gs + c.z); } grainPut(g + p, d, m); }
    let k = c.w;                                             // its point's map word, by the first of its records
    if (p == 0u || pieceAt(A, p - 1u, nA).w != k) {
      var n = 1u;
      while (p + n < pos && n < 8u && pieceAt(A, p + n, nA).w == k) { n += 1u; }
      rec[mapAt + (k >> 2u)][k & 3u] = (p << 3u) | min(n, 7u);
    }
  }
  storageBarrier();
  for (var m = li; m < nA; m += 64u) {                       // each piece's turns beside its new ends, its place
    let o = A + m * 10u; let n = pCnt[m] & 0x3fffffffu; let start = pOff[m];
    if (hl && nR > 1u && n > 2u) {
      let h = bitcast<f32>(es[o + 1u]) > 0.0; let t = bitcast<f32>(es[o + 5u]) > 0.0; let td = ((pCnt[m] >> 30u) & 1u) == 1u;
      if (h) { let i = area + start + 1u; rec[i].w = (rec[i].w & 0xffffff00u) | turnAt(xy(i - 1u), xy(i), xy(i + 1u)); }
      if (t && !td) { let i = area + start + n - 2u; rec[i].w = (rec[i].w & 0xffffff00u) | turnAt(xy(i - 1u), xy(i), xy(i + 1u)); }
    }
    es[o + 8u] = start; es[o + 9u] = n;
  }
  for (var z = pos + li; z < hi; z += 64u) { rec[area + z] = vec4<u32>(0u); if (gr) { grb[g + z] = vec2<u32>(0u); } }
  if (li == 0u) { es[S + 11u] = pos; if (hl) { atomicAdd(&ctl[13], (pos - es[S + 22u]) * 4u); es[S + 22u] = pos; } written(S); }
}
fn written(S: u32) {                                         // its pieces written: drawn where they lie (its entry's word 7, top bit)
  let v = F.evAt + es[S + 21u] * 4u + 3u;
  grb[v] = vec2<u32>(grb[v].x, es[S + 7u] | 0x80000000u);
}
// SPANS, EACH FRAME OF A SWIPE, a stroke cut this frame (a workgroup each): its stretches where STROKES reads them -- two
// records a stretch at its pieces' place: where it starts (its record j, bit 31 the record beside its new start dropped,
// bit 30 its new end dropped: stretchCount), where it ends -- and how many in its entry's word 7, the top bit clear (drawn
// by range); a highlighter's pack counted as its pieces will be written
var<workgroup> sTot: atomic<u32>;
@compute @workgroup_size(64) fn spans(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  let w = wg.x + wg.y * 65535u;
  if (li == 0u) {
    var go = 0u; var S0 = NONE;
    if (w < nTouched()) { S0 = slotOf(touched(w)); if (S0 != NONE && es[S0 + 12u] == F.frame && es[S0 + 14u] > 0u) { go = 1u; } }
    pGo = go; pS = S0; atomicStore(&sTot, 0u);
  }
  let go = workgroupUniformLoad(&pGo);
  if (go == 0u) { return; }
  let S = workgroupUniformLoad(&pS);
  base = es[S]; nR = es[S + 1u];
  let hl = es[S + 2u] == 1u; let A = es[S + 5u] + es[S + 6u] * es[S + 4u] * 10u; let nA = es[S + 7u]; let area = es[S + 8u];
  for (var m = li; m < nA; m += 64u) {
    let o = A + m * 10u; let cnt = stretchCount(A, m, hl);
    rec[area + 2u * m] = vec4<u32>(es[o] | (cnt & 0xc0000000u), es[o + 1u], es[o + 2u], es[o + 3u]);
    rec[area + 2u * m + 1u] = vec4<u32>(es[o + 4u], es[o + 5u], es[o + 6u], es[o + 7u]);
    atomicAdd(&sTot, cnt & 0x3fffffffu);
  }
  workgroupBarrier();
  if (li == 0u) {
    let v = F.evAt + es[S + 21u] * 4u + 3u;
    grb[v] = vec2<u32>(grb[v].x, nA);
    let pos = atomicLoad(&sTot);
    if (hl) { atomicAdd(&ctl[13], (pos - es[S + 22u]) * 4u); es[S + 22u] = pos; }
  }
}
// FLIP, AS THE SWIPE GOES: a slot not changed for COLD steps (every slot, once the swipe is let go: F.p1) made its pieces --
// each a stroke of its own, numbered from the room the processor gave (ctl 17, 18), its row written as the processor would
// write it (a grain stroke's piece with no grain left a pen's), its records given its number, in the order where its stroke
// was (the order's edit: its stroke an anchor, its pieces the list) -- and its stroke taken out (not drawn, not cut, its
// map cleared); what was done written in the log for the processor (pack: the slot's stroke, how many pieces, its kind, the
// first number, its places, a highlighter's records' count; each stretch, 10 words; each piece's row, 8; a highlighter's
// pieces' records). A slot never cut is let go as it was. The log's entries lie one after another from its start: none
// is given room once one was refused (the numbers first: one refused there leaves no hole)
const COLD: u32 = 8u;
@compute @workgroup_size(64) fn flipPick(@builtin(global_invocation_id) id: vec3<u32>) {
  let k = id.x + id.y * 65535u * 64u;
  if (k >= min(atomicLoad(&ctl[12]), F.slCap)) { return; }
  let S = atomicLoad(&ctl[F.offSL + k]);
  if (es[S + 23u] != 0u) { return; }                          // (made strokes already)
  if (F.p1 == 0u && es[S + 12u] + COLD > F.frame) { return; } // (changed in the last steps: it may be cut again)
  if (es[S + 14u] == 0u) {                                    // never cut: let go as it was
    es[S + 23u] = 1u; grb[F.stAt + es[S + 18u] * 4u + 3u].x = NONE; atomicAdd(&ctl[28], 1u); return;
  }
  let nA = es[S + 7u];
  let size = 8u + nA * 18u + select(0u, es[S + 22u] * 4u, es[S + 2u] == 1u);
  let s0 = atomicAdd(&ctl[16], nA);
  if (s0 + nA > atomicLoad(&ctl[17])) { atomicOr(&ctl[2], 256u); return; }
  let lg = atomicAdd(&ctl[20], size);
  if (lg + size > atomicLoad(&ctl[23])) { atomicOr(&ctl[2], 512u); return; }
  let a = atomicAdd(&ctl[21], 1u); let la = atomicAdd(&ctl[22], nA);   // (room for every slot's anchor and every number's place: the processor's)
  let j = atomicAdd(&ctl[19], 1u);
  es[S + 23u] = 2u;
  ent[5u * j] = S; ent[5u * j + 1u] = atomicLoad(&ctl[18]) + s0; ent[5u * j + 2u] = lg; ent[5u * j + 3u] = a; ent[5u * j + 4u] = la;
}
@compute @workgroup_size(1) fn flipArgs() {                  // the slots flipped: a workgroup each
  let n = min(atomicLoad(&ctl[19]), F.slCap);
  eargs[9] = min(n, 65535u); eargs[10] = (n + 65534u) / 65535u; eargs[11] = 1u;
}
var<workgroup> fN: u32;
@compute @workgroup_size(64) fn flip(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  let w = wg.x + wg.y * 65535u;
  if (li == 0u) { fN = min(atomicLoad(&ctl[19]), F.slCap); }
  if (w >= workgroupUniformLoad(&fN)) { return; }
  let S = ent[5u * w]; let s0 = ent[5u * w + 1u]; let lg = ent[5u * w + 2u]; let a = ent[5u * w + 3u]; let la = ent[5u * w + 4u];
  let sid = es[S + 18u]; let nA = es[S + 7u]; let kind = es[S + 2u]; let nr = es[S + 1u];
  let at = F.stAt + sid * 4u; let t1 = grb[at + 1u]; let t2 = grb[at + 2u];
  let A = es[S + 5u] + es[S + 6u] * es[S + 4u] * 10u; let area = es[S + 8u]; let g = es[S + 10u];
  let hl = kind == 1u; let m = select(0u, es[S + 22u], hl); let lb = atomicLoad(&ctl[24]) * 3u + la;
  if (li == 0u) {
    pack[lg] = sid; pack[lg + 1u] = nA; pack[lg + 2u] = kind; pack[lg + 3u] = s0; pack[lg + 4u] = area; pack[lg + 5u] = g; pack[lg + 6u] = m; pack[lg + 7u] = 0u;
    oeb[3u * a] = sid; oeb[3u * a + 1u] = lb; oeb[3u * a + 2u] = nA;
    grb[at + 1u] = vec2<u32>(t1.x & 0x7fffffffu, t1.y);       // its stroke out: not drawn, not cut
    grb[at + 3u] = vec2<u32>(NONE, grb[at + 3u].y);
    es[S + 23u] = 1u; atomicAdd(&ctl[28], 1u);
  }
  for (var q = li; q < nA; q += 64u) {                         // each piece (a thread each): its row, its place in the list, the log
    let o = A + q * 10u; let st = es[o + 8u]; let cnt = es[o + 9u]; let b = area + st;
    var kd = kind; var gs = NONE;
    if (kind == 2u) {
      var any = false;
      for (var k = 0u; k < cnt && !any; k++) { any = grain(g + st + k) < 1.0; }
      if (any) { gs = g + st; } else { kd = 0u; }
    }
    var len = 0.0;
    for (var k = 1u; k < cnt; k++) { len += length(xy(b + k) - xy(b + k - 1u)); }
    let ns = s0 + q; let r = F.stAt + ns * 4u;
    let w0 = vec2<u32>(b, cnt); let w1 = vec2<u32>((t1.x & 0xffffff00u) | kd, t1.y); let w2 = vec2<u32>(t2.x, gs); let w3 = vec2<u32>(NONE, bitcast<u32>(len));
    grb[r] = w0; grb[r + 1u] = w1; grb[r + 2u] = w2; grb[r + 3u] = w3;
    oeb[lb + q] = ns;
    let E = lg + 8u + q * 10u;
    for (var z = 0u; z < 10u; z++) { pack[E + z] = es[o + z]; }
    let R = lg + 8u + nA * 10u + q * 8u;
    pack[R] = w0.x; pack[R + 1u] = w0.y; pack[R + 2u] = w1.x; pack[R + 3u] = w1.y; pack[R + 4u] = w2.x; pack[R + 5u] = w2.y; pack[R + 6u] = w3.x; pack[R + 7u] = w3.y;
  }
  if (hl) { let H = lg + 8u + nA * 18u; for (var i = li; i < m * 4u; i += 64u) { pack[H + i] = rec[area + i / 4u][i % 4u]; } }
  storageBarrier();
  for (var q = 0u; q < nA; q++) {                               // each piece's records given its number (sixty-four threads a piece)
    let o = A + q * 10u; let b = area + es[o + 8u]; let cnt = es[o + 9u]; let ns = s0 + q;
    for (var k = li; k < cnt; k += 64u) { rec[b + k].w = (rec[b + k].w & 0xffu) | (ns << 8u); }
  }
  let mapAt = area - (nr + 3u) / 4u;                            // its map: no longer read (its stroke is not drawn by range)
  for (var z = li; z < (nr + 3u) / 4u; z += 64u) { rec[mapAt + z] = vec4<u32>(0u); }
}
// the blocks its pieces lie in boxed anew (CULL's boxOf, here): the eraser finds them as it finds any stroke
@compute @workgroup_size(64) fn flipBox(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  let w = wg.x + wg.y * 65535u;
  if (w >= min(atomicLoad(&ctl[19]), F.slCap)) { return; }
  let S = ent[5u * w]; let area = es[S + 8u]; let pos = es[S + 11u];
  if (pos == 0u) { return; }
  for (var b = area / 16u + li; b <= (area + pos - 1u) / 16u; b += 64u) {
    var lo = vec2<f32>(3.0e38); var hi = vec2<f32>(-3.0e38); var wd = 0.0;
    for (var k = 0u; k < 16u; k++) {
      let i = b * 16u + k;
      let R = rec[i]; let f = R.w & 0xffu;
      if ((f & 3u) == 0u) { continue; }
      let q = xy(i); lo = min(lo, q); hi = max(hi, q); wd = max(wd, bitcast<f32>(R.z));
      if ((f & 1u) != 0u) { let q2 = xy(i + 1u); lo = min(lo, q2); hi = max(hi, q2); wd = max(wd, bitcast<f32>(rec[i + 1u].z)); }
      if ((f & 4u) != 0u) { wd = max(wd, bitcast<f32>(rec[i - 1u].z)); }
    }
    let mg = wd * 0.5 + 0.35 + 1.0;
    boxw[b] = select(vec4<f32>(3.0e38, 3.0e38, -3.0e38, -3.0e38), vec4<f32>(lo - vec2<f32>(mg), hi + vec2<f32>(mg)), hi.x >= lo.x);
  }
}
// the order's edit as the card made it: how many anchors, and its passes' dispatches (oargs: over the order, over its
// anchors, the classes' table cleared, one workgroup -- none when nothing was flipped)
@compute @workgroup_size(1) fn flipEnd() {
  let nA = atomicLoad(&ctl[21]); let go = nA > 0u;
  olh[9] = nA; olh[10] = 0u;
  oargs[0] = select(0u, (olh[4] + atomicLoad(&ctl[22]) + 127u) / 128u, go); oargs[1] = 1u; oargs[2] = 1u;   // (as long as it is, and as it will be)
  oargs[3] = select(0u, (nA + 127u) / 128u, go); oargs[4] = 1u; oargs[5] = 1u;
  oargs[6] = select(0u, (atomicLoad(&ctl[27]) + 63u) / 64u, go); oargs[7] = 1u; oargs[8] = 1u;
  oargs[9] = select(0u, 1u, go); oargs[10] = 1u; oargs[11] = 1u;
}
// unslot (the swipe let go, its slots made strokes or not): no stroke of the swipe's is drawn as one the card is cutting --
// each slot's stroke's entry cleared at once on the card (the processor's own copy is written later, and a slot never read
// back is never let go there), a thread a slot
@compute @workgroup_size(64) fn unslot(@builtin(global_invocation_id) id: vec3<u32>) {
  let k = id.x + id.y * 65535u * 64u;
  if (k >= min(atomicLoad(&ctl[12]), F.slCap)) { return; }
  let a = F.stAt + es[atomicLoad(&ctl[F.offSL + k]) + 18u] * 4u + 3u;
  grb[a] = vec2<u32>(NONE, grb[a].y);
}
// THE MASK (msk): what the frame's steps changed on the page, for the card to draw again there and nowhere else (STROKES'
// vsMask marks those pixels; the page's own draws then make them anew). Its header: 0 how many records, 1 to 4 their box
// (page units, each as an ordered word: ordU), 8 to 11 the mask's draw; its records from word 16. maskHits: every record
// the step reached (a cut can change ink only on the segment it cuts: each part kept is drawn as its segment draws it);
// maskAnew: a stroke cut this step whose cuts changed its ink away from the path -- a grain's or wash's pieces made anew,
// the stretches the whole-stroke eraser took -- those records. A record's box: its points, out by half its widest width
// there (a highlighter's turn by the segment before's too), its wash's reach and a unit more
@group(0) @binding(13) var<storage, read_write> msk: array<atomic<u32>>;
fn ordU(f: f32) -> u32 { let b = bitcast<u32>(f); return select(b ^ 0x80000000u, ~b, (b >> 31u) == 1u); }   // (in order as the floats)
fn maskBox(i: u32) {                                         // record i's box into the mask's (it has ink)
  let R0 = rec[i]; let f = R0.w & 0xffu;
  let a = vec2<f32>(bitcast<f32>(R0.x), bitcast<f32>(R0.y));
  var b = a; var w = bitcast<f32>(R0.z);
  if ((f & 1u) != 0u) { let R1 = rec[i + 1u]; b = vec2<f32>(bitcast<f32>(R1.x), bitcast<f32>(R1.y)); w = max(w, bitcast<f32>(R1.z)); }
  if ((f & 4u) != 0u) { w = max(w, bitcast<f32>(rec[i - 1u].z)); }
  let r = w * 0.5 + 0.35 + 1.0;
  atomicMin(&msk[1], ordU(min(a.x, b.x) - r)); atomicMin(&msk[2], ordU(min(a.y, b.y) - r));
  atomicMax(&msk[3], ordU(max(a.x, b.x) + r)); atomicMax(&msk[4], ordU(max(a.y, b.y) + r));
}
fn maskAdd(i: u32) {                                         // record i into the mask, if it has ink
  if ((rec[i].w & 3u) == 0u) { return; }
  let k = atomicAdd(&msk[0], 1u);
  if (k < F.mCap) { atomicStore(&msk[16u + k], i); } else { atomicOr(&ctl[2], 64u); }
  maskBox(i);
}
@compute @workgroup_size(64) fn maskHits(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  let g = (wg.x + wg.y * 65535u) * 64u + li;
  if ((g >> 4u) >= hitsNow()) { return; }
  if (ent[g * 3u] == 0u) { return; }
  let i = clist[g >> 4u] * 16u + (g & 15u);
  maskAdd(i);
  cutNear(i);
}
// a pen's or a highlighter's records about record i, of a stroke cut (two each side: a new start's record beside it, a
// highlighter's turn beside a new end) say CUT -- drawn as its pieces will be (STROKES, by range or where they lie)
fn cutNear(i: u32) {
  let sid = rec[i].w >> 8u;
  if (sid >= F.stCap) { return; }
  let S = slotOf(sid);
  if (S == NONE || es[S + 14u] == 0u || es[S + 2u] >= 2u) { return; }
  let b = es[S]; let n = es[S + 1u];
  let hi = min(i + 2u, b + n - 1u);
  for (var k = max(i, b + 2u) - 2u; k <= hi; k++) { rec[k].w = rec[k].w | 16u; }
}
var<workgroup> aGo: u32;
var<workgroup> aS: u32;
@compute @workgroup_size(64) fn maskAnew(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_index) li: u32) {
  let w = wg.x + wg.y * 65535u;
  if (li == 0u) {
    var go = 0u; var S0 = NONE;
    if (w < nTouched()) {
      S0 = slotOf(touched(w));
      if (S0 != NONE && es[S0 + 15u] == F.frame && es[S0 + 16u] <= es[S0 + 17u]) { go = 1u; }
    }
    aGo = go; aS = S0;
  }
  let go = workgroupUniformLoad(&aGo);
  if (go == 0u) { return; }
  let S = workgroupUniformLoad(&aS);
  let b = es[S]; let n = es[S + 1u]; let k1 = min(es[S + 17u], n - 1u);
  for (var k = es[S + 16u] + li; k <= k1; k += 64u) { maskAdd(b + k); }
  if (es[S + 2u] < 2u) {                                     // (a pen's or a highlighter's: those records and two each side CUT)
    let f1 = min(k1 + 2u, n - 1u);
    for (var k = max(es[S + 16u], 2u) - 2u + li; k <= f1; k += 64u) { rec[b + k].w = rec[b + k].w | 16u; }
  }
}
`,
  // A SELECTION MOVED WHERE IT LIES (the editor's; the engine uses none of it): its strokes' records stay in their own
  // places in the page's records, so what lies over and under them is as the page's order has it. Taken up, they are
  // copied aside as they were (grab: the records the mask lists, ERASE's mk, in its order); each frame of the drag puts
  // each one where the frame's matrix takes it, with its width for the frame's size as the processor works it out (wid:
  // what a stroke of the moved points draws), its flags as they were (carry); let go, grab reads the moved ones back, and
  // a drag given up puts them back as they were (back). The page is drawn again only where they were and where they
  // are, from the mask (STROKES' vsMask), as an erase's frame is
  MOVE: `
struct MU { a: vec4<f32>, t: vec2<f32>, n: u32, wide: u32, w: u32, p0: u32, p1: u32, p2: u32 };
@group(0) @binding(0) var<uniform> U: MU;
@group(0) @binding(1) var<storage, read_write> rec: array<vec4<u32>>;
@group(0) @binding(2) var<storage, read_write> org: array<vec4<u32>>;
@group(0) @binding(3) var<storage, read> mkr: array<u32>;
@group(0) @binding(4) var<storage, read> wid: array<f32>;
@compute @workgroup_size(64) fn grab(@builtin(global_invocation_id) id: vec3<u32>) {
  let j = id.x + id.y * U.wide;
  if (j >= U.n) { return; }
  org[j] = rec[mkr[16u + j]];
}
@compute @workgroup_size(64) fn carry(@builtin(global_invocation_id) id: vec3<u32>) {
  let j = id.x + id.y * U.wide;
  if (j >= U.n) { return; }
  let R = org[j]; let x = bitcast<f32>(R.x); let y = bitcast<f32>(R.y);
  let p = vec2<f32>(U.a.x * x + U.a.y * y + U.t.x, U.a.z * x + U.a.w * y + U.t.y);
  rec[mkr[16u + j]] = vec4<u32>(bitcast<u32>(p.x), bitcast<u32>(p.y), select(R.z, bitcast<u32>(wid[j]), U.w != 0u), R.w);
}
@compute @workgroup_size(64) fn back(@builtin(global_invocation_id) id: vec3<u32>) {
  let j = id.x + id.y * U.wide;
  if (j >= U.n) { return; }
  rec[mkr[16u + j]] = org[j];
}
`,
  // THE ENGINE'S CANVAS ONTO THE CARD AND ITS PICTURE BACK, as bytes (pipeline/page/gpu.py; the editor uses none of it):
  // the canvas it is given, three bytes a pixel, row after row, put up as they are -- a byte a texel, TW across --
  // and laid on the working canvas, each pixel ss x ss (fsUnpack: what render.c copies under the ink); the picture
  // made read into three bytes a pixel again, four bytes a word (pack). The processor only copies bytes
  PIXELS: `
const TW: u32 = 4096u;
struct PU { W: u32, H: u32, ss: u32, pad: u32 };
@group(0) @binding(0) var<uniform> PX: PU;
@group(0) @binding(1) var bytes: texture_2d<u32>;
fn byteAt(i: u32) -> u32 { return textureLoad(bytes, vec2<i32>(i32(i % TW), i32(i / TW)), 0).x; }
struct VF { @builtin(position) pos: vec4<f32> };
@vertex fn vsFull(@builtin(vertex_index) v: u32) -> VF {
  var o: VF; o.pos = vec4<f32>(select(-1.0, 3.0, v == 1u), select(-1.0, 3.0, v == 2u), 0.0, 1.0); return o;
}
@fragment fn fsUnpack(i: VF) -> @location(0) vec4<f32> {
  let at = ((u32(i.pos.y) / PX.ss) * PX.W + u32(i.pos.x) / PX.ss) * 3u;
  return vec4<f32>(f32(byteAt(at)), f32(byteAt(at + 1u)), f32(byteAt(at + 2u)), 255.0) / 255.0;
}
@group(0) @binding(2) var pic: texture_2d<f32>;
@group(0) @binding(3) var<storage, read_write> packed: array<u32>;
@compute @workgroup_size(64) fn pack(@builtin(global_invocation_id) id: vec3<u32>) {
  let w = id.x + id.y * 65535u * 64u; let n = PX.W * PX.H * 3u;
  if (w * 4u >= n) { return; }
  var word = 0u;
  for (var k = 0u; k < 4u; k++) {                             // (bytes 4w to 4w + 3: each its pixel's channel)
    let b = w * 4u + k;
    if (b < n) {
      let p = b / 3u;
      let t = textureLoad(pic, vec2<i32>(i32(p % PX.W), i32(p / PX.W)), 0);
      word = word | (u32(round(t[b % 3u] * 255.0)) << (k * 8u));
    }
  }
  packed[w] = word;
}
`,
  // A FILL ON THE CARD (the editor's fill tool): the area of one color under the click, found in the page as shown -- the
  // screen's texture, or a sweep's copy of it as its drag began -- every pixel at once. seed: the click's pixel and the
  // nine by nine round it (a thin line: fewer than a third of them its color and the paper far from it -- then a pixel
  // is the line's when nearer its color than the paper's and no farther than the paper is; else within 24 a channel), and
  // a sweep's own checks (a pixel it filled already, a color not its own: no fill). label: each pixel that is the
  // click's color its own label (the click's pixel always). link: labels side by side joined (and corner to corner on a
  // thin line) -- union-find, the smaller root kept. flat: each its root. box: the click's area's box. bits: its pixels in
  // the box, a bit each, rows one after another (numpy.packbits' order: the first pixel the byte's top bit), and a
  // sweep's pixels marked filled -- what the processor's flood fill makes, for the engine's ring planner
  FILL: `
struct FU { W: u32, H: u32, px: u32, py: u32, sweep: u32, p1: u32, p2: u32, p3: u32 };
@group(0) @binding(0) var src: texture_2d<f32>;
@group(0) @binding(1) var<uniform> U: FU;
@group(0) @binding(2) var<storage, read_write> lab: array<atomic<u32>>;
@group(0) @binding(3) var<storage, read_write> fp: array<atomic<u32>>;
@group(0) @binding(4) var<storage, read_write> done: array<u32>;
// fp: 0 thin, 1..3 the paper's color, 4 how far the paper is, 5..8 the box (x0 y0 x1 y1), 9 the area's root, 10 no fill,
// 11 a sweep's color (its first fill's; NONE: none yet), 16.. the bits
const NONE: u32 = 0xffffffffu;
fn rgb(x: u32, y: u32) -> vec3<i32> { return vec3<i32>(textureLoad(src, vec2<i32>(i32(x), i32(y)), 0).rgb * 255.0 + 0.5); }
fn sum3(d: vec3<i32>) -> i32 { return abs(d.x) + abs(d.y) + abs(d.z); }
@compute @workgroup_size(1) fn fseed() {
  let px = U.px; let py = U.py; let c0 = rgb(px, py); let at = py * U.W + px;
  var no = 0u;
  if (U.sweep == 1u) {
    if (done[at] != 0u) { no = 1u; }
    let sc = atomicLoad(&fp[11]);
    if (no == 0u) {
      if (sc == NONE) { atomicStore(&fp[11], u32(c0.x) | (u32(c0.y) << 8u) | (u32(c0.z) << 16u)); }
      else {
        let k = vec3<i32>(i32(sc & 0xffu), i32((sc >> 8u) & 0xffu), i32((sc >> 16u) & 0xffu));
        if (abs(c0.x - k.x) > 24 || abs(c0.y - k.y) > 24 || abs(c0.z - k.z) > 24) { no = 1u; }
      }
    }
  }
  var near = 0u; var all = 0u; var far = -1; var bg = c0;
  for (var j = max(i32(py) - 4, 0); j <= min(i32(U.H) - 1, i32(py) + 4); j++) {
    for (var i = max(i32(px) - 4, 0); i <= min(i32(U.W) - 1, i32(px) + 4); i++) {
      let c = rgb(u32(i), u32(j)); let f = sum3(c - c0); all += 1u;
      if (f <= 72) { near += 1u; }
      if (f > far) { far = f; bg = c; }
    }
  }
  atomicStore(&fp[0], select(0u, 1u, near * 3u < all && far > 72));
  atomicStore(&fp[1], u32(bg.x)); atomicStore(&fp[2], u32(bg.y)); atomicStore(&fp[3], u32(bg.z)); atomicStore(&fp[4], u32(far));
  atomicStore(&fp[5], NONE); atomicStore(&fp[6], NONE); atomicStore(&fp[7], 0u); atomicStore(&fp[8], 0u); atomicStore(&fp[10], no);
}
fn same(x: u32, y: u32) -> bool {                            // the processor's same()
  let c = rgb(x, y); let f = sum3(c - rgb(U.px, U.py));
  if (atomicLoad(&fp[0]) == 1u) {
    let bg = vec3<i32>(i32(atomicLoad(&fp[1])), i32(atomicLoad(&fp[2])), i32(atomicLoad(&fp[3])));
    return f < sum3(c - bg) && f <= i32(atomicLoad(&fp[4]));
  }
  let d = abs(c - rgb(U.px, U.py)); return d.x <= 24 && d.y <= 24 && d.z <= 24;
}
@compute @workgroup_size(8, 8) fn flabel(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= U.W || g.y >= U.H || atomicLoad(&fp[10]) != 0u) { return; }
  let i = g.y * U.W + g.x;
  var on = g.x == U.px && g.y == U.py;
  if (!on) { on = same(g.x, g.y) && (U.sweep == 0u || done[i] == 0u); }
  atomicStore(&lab[i], select(NONE, i, on));
}
fn findr(i0: u32) -> u32 { var i = i0; loop { let q = atomicLoad(&lab[i]); if (q == i) { return i; } i = q; } }
fn merge(a0: u32, b0: u32) {                                 // (two labels' roots made one: the smaller kept)
  var a = a0; var b = b0;
  loop {
    a = findr(a); b = findr(b);
    if (a == b) { return; }
    if (a < b) { let old = atomicMin(&lab[b], a); if (old == b) { return; } b = old; }
    else { let old = atomicMin(&lab[a], b); if (old == a) { return; } a = old; }
  }
}
@compute @workgroup_size(8, 8) fn flink(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= U.W || g.y >= U.H || atomicLoad(&fp[10]) != 0u) { return; }
  let i = g.y * U.W + g.x;
  if (atomicLoad(&lab[i]) == NONE) { return; }
  if (g.x + 1u < U.W && atomicLoad(&lab[i + 1u]) != NONE) { merge(i, i + 1u); }
  if (g.y + 1u < U.H) {
    let d = i + U.W;
    if (atomicLoad(&lab[d]) != NONE) { merge(i, d); }
    if (atomicLoad(&fp[0]) == 1u) {                          // (a thin line: corner to corner too)
      if (g.x + 1u < U.W && atomicLoad(&lab[d + 1u]) != NONE) { merge(i, d + 1u); }
      if (g.x > 0u && atomicLoad(&lab[d - 1u]) != NONE) { merge(i, d - 1u); }
    }
  }
}
@compute @workgroup_size(8, 8) fn fflat(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= U.W || g.y >= U.H || atomicLoad(&fp[10]) != 0u) { return; }
  let i = g.y * U.W + g.x;
  if (atomicLoad(&lab[i]) != NONE) { atomicStore(&lab[i], findr(i)); }
}
@compute @workgroup_size(1) fn froot() { if (atomicLoad(&fp[10]) == 0u) { atomicStore(&fp[9], findr(U.py * U.W + U.px)); } }
@compute @workgroup_size(8, 8) fn fbox(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= U.W || g.y >= U.H || atomicLoad(&fp[10]) != 0u) { return; }
  let i = g.y * U.W + g.x;
  if (atomicLoad(&lab[i]) != atomicLoad(&fp[9])) { return; }
  atomicMin(&fp[5], g.x); atomicMin(&fp[6], g.y); atomicMax(&fp[7], g.x); atomicMax(&fp[8], g.y);
}
@compute @workgroup_size(8, 8) fn fbits(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= U.W || g.y >= U.H || atomicLoad(&fp[10]) != 0u) { return; }
  let i = g.y * U.W + g.x;
  if (atomicLoad(&lab[i]) != atomicLoad(&fp[9])) { return; }
  let x0 = atomicLoad(&fp[5]); let y0 = atomicLoad(&fp[6]); let gw = atomicLoad(&fp[7]) - x0 + 1u;
  let k = (g.y - y0) * gw + (g.x - x0); let b = k >> 3u;
  atomicOr(&fp[16u + (b >> 2u)], 1u << ((b & 3u) * 8u + 7u - (k & 7u)));
  if (U.sweep == 1u) { done[i] = 1u; }
}
`,
};
