// THE RENDERER'S SHADERS: the one copy of how strokes become pixels on the graphics card (GLSL ES 3.00).
//
// Read by the page editor (editor.html, WebGL2: this file is loaded before its script) and by the engine
// (pipeline/page/gpu.py, through moderngl: it reads the text between each name's backquotes and swaps the first line
// for desktop GLSL's #version 330). Change a shader here and both draw with it.
//
// THE FEEDING -- what each stroke is turned into before these run (its points' records, its grain buffer, which
// of a highlighter's points are kept and where its bevels go) -- is written twice, once for each side: partOf() in editor.html and _feed() in
// pipeline/page/gpu.py. A change to one MUST be made to the other (each says so where it is written). render.c is
// the CPU renderer both are measured against, and the fallback when the card cannot be used.
window.PD_SHADERS = {
  // THE STROKES ARE THEIR POINTS, each stored once (16 bytes): x, y and the width (32-bit floats, page units as the
  // file has them), then four bytes read as one (fc: Direct3D 11 takes four bytes at a 4-byte offset as they are; three,
  // or an odd offset, it would have to convert): the flags -- 1 a segment from this point to the next, 2 a dot (a stroke
  // of one point), 4 a bevel at this point (a highlighter's turn), 8 that bevel on the other side -- and the stroke's
  // color (3 bytes, 0..255). One
  // instance a point: it reads its point (a), the next (b) and, for a highlighter's bevel, the one before (p), from the
  // same buffer at three offsets; a point with no segment to the next draws nothing. A grain stroke's density and its
  // length along the stroke at each point come from a buffer of their own (ga, gb: 1 and 0 for every other stroke).
  //
  // PEN STROKES, where: each segment a rectangle laid over it a little wider than the pen (r + 1.5 pixels each way), so
  // every pixel the capsule could touch is visited; r is the mean of its ends' widths over 2 (a dot's: its width over 2).
  VS_SEG: `#version 300 es
  layout(location=0) in vec2 corner;
  layout(location=1) in vec2 pa; layout(location=2) in float wa; layout(location=3) in uvec4 fc;
  layout(location=5) in vec2 pb; layout(location=6) in float wb;
  layout(location=7) in vec2 ga; layout(location=8) in vec2 gb;
  uniform vec2 size; uniform float k; uniform vec2 off;
  flat out vec4 vAB; flat out vec4 vRC; flat out vec4 vG;
  void main() {
    uint fa = fc.x; bool seg = (fa & 1u) != 0u, dot = (fa & 2u) != 0u;
    if (!seg && !dot) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }       // nothing to draw from this point
    vec2 a = pa * k + off, b = (dot ? pa : pb) * k + off;
    float r = (dot ? wa * 0.5 : (wa + wb) * 0.25) * k;
    vec2 d = b - a; float L = length(d);
    vec2 u = L > 0.0 ? d / L : vec2(1.0, 0.0), n = vec2(-u.y, u.x);
    float m = r + 1.5;
    vec2 p = (corner.x < 0.0 ? a - u * m : b + u * m) + n * (corner.y * m);
    gl_Position = vec4(p / size * 2.0 - 1.0, 0.0, 1.0);
    vAB = vec4(a, b); vRC = vec4(r, vec3(fc.yzw) / 255.0); vG = vec4(ga.x, dot ? ga.x : gb.x, ga.y * k, k);
  }`,
  // PEN STROKES, which pixels: a pixel is inked when its CENTER is within r of the segment (a capsule: round ends
  // and joints). With grain on (pencils, light paintbrush and ballpoint) a pixel is inked by chance, from a hash of where
  // it sits along and across the stroke (seed: the stroke's), at the stroke's density there, denser toward the middle
  // (render.c's grain_ink). alpha: 1 for a pen; a shader's wash is its alpha, decided once a pixel a stroke (the stencil
  // holds which stroke did).
  FS_SEG: `#version 300 es
  precision highp float; precision highp int;
  flat in vec4 vAB; flat in vec4 vRC; flat in vec4 vG;
  uniform int grainOn; uniform float alpha; uniform uint seed;
  out vec4 color;
  uint mixh(uint h) { h ^= h >> 16; h *= 0x7feb352du; h ^= h >> 15; h *= 0x846ca68bu; h ^= h >> 16; return h; }
  float hash01(uint s, int a, int b) { return float(mixh(s ^ mixh(uint(a) * 0x9e3779b9u ^ mixh(uint(b) + 0x85ebca6bu)))) / 4294967296.0; }
  void main() {
    vec2 p = gl_FragCoord.xy;                               // the pixel's center; the canvas's rows run down as the texture's do
    vec2 a = vAB.xy, b = vAB.zw, d = b - a; float r = vRC.x;
    float L2 = dot(d, d), tu = L2 > 0.0 ? dot(p - a, d) / L2 : 0.0, t = clamp(tu, 0.0, 1.0);
    vec2 e = p - (a + t * d);
    if (dot(e, e) > r * r) discard;
    float ink = 1.0;
    if (grainOn == 1) {
      float L = sqrt(L2), v = L > 0.0 ? ((p.x - a.x) * d.y - (p.y - a.y) * d.x) / L : length(e), q = r > 0.0 ? v / r : 0.0;
      float den = (vG.x + (vG.y - vG.x) * t) * (1.25 - 0.5 * q * q) / (1.25 - 0.5 / 3.0);
      if (den < 1.0) {
        if (den <= 0.0) ink = 0.0;
        else {
          float unit = vG.w; int cv = int(floor(v / unit));
          float jitter = hash01(seed ^ 0x51ed27u, cv, 0) * 3.0;
          int cu = int(floor(((vG.z + tu * L) / unit + jitter) / 3.0));
          ink = hash01(seed, cu, cv) < den ? 1.0 : 0.0;
        }
      }
    }
    color = vec4(vRC.yzw, ink * alpha);
  }`,
  // HIGHLIGHTERS, where: one instance a point (its stroke's repeats dropped by the feeding, as render.c drops them), nine
  // vertices: the segment to the next point as a rectangle with flat ends, its half width the mean of its ends' widths
  // over 2 and eps past it (two triangles: a+n b+n b-n, a+n b-n a-n), then the bevel across the turn's outer corner at a
  // when its flags say so (a, a + s * the previous segment's normal, a + s * this one's; the side s decided by the
  // feeding, as render.c decides it), a point when not.
  VS_HL: `#version 300 es
  layout(location=1) in vec2 pa; layout(location=2) in float wa; layout(location=3) in uvec4 fc;
  layout(location=5) in vec2 pb; layout(location=6) in float wb;
  layout(location=9) in vec2 pp; layout(location=10) in float wp;
  uniform vec2 size; uniform float k; uniform vec2 off; uniform float eps;
  flat out vec3 vCol;
  void main() {
    uint fa = fc.x;
    if ((fa & 1u) == 0u) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }   // the stroke's last point
    vec2 a = pa, b = pb, d = b - a; float L = length(d), hw = (wa + wb) * 0.25 + eps;
    vec2 u = L > 0.0 ? d / L : vec2(1.0, 0.0), n = vec2(-u.y, u.x) * hw, p;
    int v = gl_VertexID;
    bool bevel = (fa & 4u) != 0u;
    float s = (fa & 8u) != 0u ? -1.0 : 1.0;
    if (v == 0 || v == 3) p = a + n;
    else if (v == 1) p = b + n;
    else if (v == 2 || v == 4) p = b - n;
    else if (v == 5) p = a - n;
    else if (v == 6 || !bevel) p = a;
    else if (v == 7) {
      vec2 q = a - pp; float Lq = length(q); vec2 w = Lq > 0.0 ? q / Lq : vec2(1.0, 0.0);
      p = a + s * vec2(-w.y, w.x) * ((wp + wa) * 0.25 + eps);
    }
    else p = a + s * n;
    gl_Position = vec4((p * k + off) / size * 2.0 - 1.0, 0.0, 1.0);
    vCol = vec3(fc.yzw) / 255.0;
  }`,
  // HIGHLIGHTERS, the color: drawn with a per-channel MINIMUM (darken) blend, so a wash over itself never darkens twice.
  FS_TRI: `#version 300 es
  precision highp float; flat in vec3 vCol; out vec4 color; void main() { color = vec4(vCol, 1.0); }`,
  // ONE TRIANGLE COVERING THE WHOLE TARGET, for the two passes below.
  VS_FULL: `#version 300 es
  void main() { vec2 p = vec2(gl_VertexID == 1 ? 3.0 : -1.0, gl_VertexID == 2 ? 3.0 : -1.0); gl_Position = vec4(p, 0.0, 1.0); }`,
  // WHAT IS UNDER THE INK (paper, template, a book's page, pictures, typed text) copied onto the working canvas first.
  FS_COPY: `#version 300 es
  precision highp float; uniform sampler2D tex; out vec4 color;
  void main() { color = vec4(texelFetch(tex, ivec2(gl_FragCoord.xy), 0).rgb, 1.0); }`,
  // THE WORKING CANVAS AVERAGED DOWN: each ss x ss block to one pixel of the picture, rounded as render.c rounds.
  FS_DOWN: `#version 300 es
  precision highp float; uniform sampler2D tex; uniform int ss; uniform int h; out vec4 color;
  void main() {                                             // the screen's row from the top; each block as the CPU averages it
    ivec2 o = ivec2(int(gl_FragCoord.x), h - 1 - int(gl_FragCoord.y)) * ss;
    vec3 sum = vec3(0.0);
    for (int j = 0; j < ss; j++) for (int i = 0; i < ss; i++) sum += texelFetch(tex, o + ivec2(i, j), 0).rgb;
    float n = float(ss * ss);
    vec3 s = floor(sum * 255.0 + 0.5);                        // the block's sum in whole levels, then render.c's (sum + n/2) / n
    color = vec4(floor((s + floor(n * 0.5)) / n) / 255.0, 1.0);
  }`,
  // THE PAGE EDITOR'S WORKING CANVAS SHRUNK TO THE SCREEN, by any ratio (W working pixels across to cw screen pixels: the
  // editor draws at the tablet's resolution or the screen's, whichever is finer, so W >= cw). Each screen pixel is the
  // average of the working pixels under it, each weighted by how much of it lies under that screen pixel. In WHOLE
  // NUMBERS: along each side a screen pixel spans W units and a working pixel cw, so every overlap is a whole number,
  // the weights sum to W * W, and the sum stays under 2^32 while W <= 4000 (the editor keeps it so). editor.html's
  // shrink() does the same sum on the CPU, so a patch it puts on the screen matches the card's to the last bit.
  FS_AREA: `#version 300 es
  precision highp float; precision highp int; uniform sampler2D tex; uniform int W; uniform int cw; uniform int h; out vec4 color;
  void main() {                                             // the screen's row from the top; the canvas's rows run down
    int x = int(gl_FragCoord.x), y = h - 1 - int(gl_FragCoord.y);
    int i0 = (x * W) / cw, i1 = ((x + 1) * W - 1) / cw, j0 = (y * W) / cw, j1 = ((y + 1) * W - 1) / cw;
    uvec3 sum = uvec3(0u);
    for (int j = j0; j <= j1; j++) {
      uint wy = uint(min((y + 1) * W, (j + 1) * cw) - max(y * W, j * cw));
      uvec3 row = uvec3(0u);
      for (int i = i0; i <= i1; i++) {
        uint wx = uint(min((x + 1) * W, (i + 1) * cw) - max(x * W, i * cw));
        row += uvec3(texelFetch(tex, ivec2(i, j), 0).rgb * 255.0 + 0.5) * wx;
      }
      sum += row * wy;
    }
    uint n = uint(W) * uint(W);
    color = vec4(vec3((sum + n / 2u) / n) / 255.0, 1.0);
  }`,
};
