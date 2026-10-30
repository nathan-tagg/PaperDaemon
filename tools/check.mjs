#!/usr/bin/env node
// Two of the project's rules a machine can check:
//   American spelling in code, prompts, UI text and documentation
//   no secrets in files: tokens and keys live only in the OS credential store
// The Claude Code hooks in .claude/hooks run these on every write. Run them yourself with
//   node tools/check.mjs [path ...]          (no path: the whole repository)
// The word list is explicit: a word is flagged only if it is on it, so "precise" and "advertise"
// (American too) pass. The British forms are stored reversed, so this file holds none itself.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const TEXT_EXT = new Set([".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".csv",
  ".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".ts", ".ps1", ".bat", ".cmd", ".sh"]);
const SKIP_DIRS = new Set([".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", "target",
  ".pytest_cache", ".ruff_cache", ".mypy_cache"]);

// other people's words, kept exactly as they wrote them: their spelling is not ours to change (secrets are still checked)
const VERBATIM = new Set(["paperdaemon/content/handwriting/samples.json",
  "paperdaemon/pipeline/page/dawn/_dawn_cffi.py"]);       // (Dawn's own names, as cffi wrote them from its webgpu.h)

export function isText(file) {
  return TEXT_EXT.has(path.extname(file).toLowerCase());
}

// ---- spelling

const R = (s) => [...s].reverse().join("");

// -our -> -or
const OUR = ["ruoivaheb", "ruovaf", "ruonoh", "ruobal", "ruobhgien", "ruovalf", "ruomuh", "ruomur", "ruobrah",
  "ruopav", "ruomra", "ruolrap", "ruovas", "ruovaedne", "ruodo", "ruogir", "ruogiv", "ruomalc", "ruodnelps",
  "ruoivas", "ruolav", "ruonaemed", "ruodnac", "ruodra", "ruovref", "ruomut", "ruomane"].map(R);
// -ise -> -ize, -isation -> -ization (stems; each forms its own word family)
const ISE = ["summar", "organ", "reorgan", "recogn", "real", "apolog", "priorit", "optim", "normal", "minim",
  "maxim", "initial", "serial", "deserial", "custom", "emphas", "categor", "character", "visual", "util",
  "final", "standard", "synchron", "author", "capital", "memor", "special", "general", "quant", "sanit",
  "stabil", "token", "local", "harmon", "critic", "rational", "random", "digit", "item", "jeopard", "legitim",
  "mechan", "mobil", "modern", "neutral", "penal", "polar", "public", "raster", "vector", "symbol", "sympath",
  "theor", "trivial", "vandal", "verbal", "energ", "equal", "fertil", "formal", "global", "human", "ideal",
  "immun", "internal", "italic", "material", "mesmer", "metabol", "monet", "ostrac", "patron", "personal",
  "pulver", "scrutin", "social", "steril", "subsid", "terror", "union", "parameter", "parametr", "binar",
  "anonym", "amort", R("ruoloc"), "color", "hospital", "dramat", "fantas", "familiar", "glamor", "hypothes",
  "lexical", "marginal", "national", "pressur", "privat", "regular", "revolution", "secular", "sensit",
  "stigmat", "system", "tantal", "textual", "urban", "vocal"];
const ISE_SUFFIX = [["esi", "ize"], ["sesi", "izes"], ["desi", "ized"], ["gnisi", "izing"], ["resi", "izer"],
  ["sresi", "izers"], ["noitasi", "ization"], ["snoitasi", "izations"], ["elbasi", "izable"]]
  .map(([b, a]) => [R(b), a]);
// -yse -> -yze
const YSE = ["anal", "catal", "paral", "breathal"];
const YSE_SUFFIX = [["esy", "yze"], ["desy", "yzed"], ["sesy", "yzes"], ["gnisy", "yzing"], ["resy", "yzer"]]
  .map(([b, a]) => [R(b), a]);
// whole words
const WORDS = {
  yerg: "gray", syerg: "grays", deyerg: "grayed", gniyerg: "graying", hsiyerg: "grayish",
  ssenyerg: "grayness", elacsyerg: "grayscale", reyerg: "grayer", tseyerg: "grayest",
  dertnec: "centered", gnirtnec: "centering", ervueonam: "maneuver", servueonam: "maneuvers",
  dervueonam: "maneuvered", gnirvueonam: "maneuvering", dellevart: "traveled",
  gnillevart: "traveling", rellevart: "traveler", srellevart: "travelers", dellecnac: "canceled",
  gnillecnac: "canceling", dellebal: "labeled", gnillebal: "labeling", delledom: "modeled",
  gnilledom: "modeling", relledom: "modeler", dellevel: "leveled", gnillevel: "leveling",
  dellangis: "signaled", gnillangis: "signaling", delleuf: "fueled", gnilleuf: "fueling",
  dellatot: "totaled", gnillatot: "totaling", dellahsram: "marshaled", gnillahsram: "marshaling",
  dellennahc: "channeled", gnillennahc: "channeling", dellennut: "tunneled",
  dellesnuoc: "counseled", rollesnuoc: "counselor", dellaid: "dialed", gnillaid: "dialing",
  dellennuf: "funneled", dellenap: "paneled", dellicnep: "penciled", dellerrauq: "quarreled",
  dellavir: "rivaled", dellevohs: "shoveled", suollevram: "marvelous", nelloow: "woolen",
  yrellewej: "jewelry", tnemlorne: "enrollment", lorne: "enroll", lifluf: "fulfill",
  slifluf: "fulfills", tnemlifluf: "fulfillment", tnemlatsni: "installment", lufliks: "skillful",
  yllufliks: "skillfully", lufliw: "willful", litsni: "instill", litsid: "distill",
  lappa: "appall", ecnefed: "defense", secnefed: "defenses", ecneffo: "offense",
  secneffo: "offenses", ecnecil: "license", secnecil: "licenses", ecneterp: "pretense",
  esitcarp: "practice", desitcarp: "practiced", gnisitcarp: "practicing", sesitcarp: "practices",
  eugolatac: "catalog", seugolatac: "catalogs", deugolatac: "cataloged", gniugolatac: "cataloging",
  eugolana: "analog", seugolana: "analogs", muinimula: "aluminum", tcafetra: "artifact",
  stcafetra: "artifacts", gniega: "aging", tnemegduj: "judgment", stnemegduj: "judgments",
  tnemegdelwonkca: "acknowledgment", stnemegdelwonkca: "acknowledgments", dluom: "mold",
  sdluom: "molds", dedluom: "molded", hguolp: "plow", lacitpecs: "skeptical", citpecs: "skeptic",
  msicitpecs: "skepticism", ysoc: "cozy", ehcatsuom: "mustache", samajyp: "pajamas",
  ruhplus: "sulfur", enalporea: "airplane", senalporea: "airplanes",
  emmargorp: "program", semmargorp: "programs", tnrael: "learned", tleps: "spelled",
  tmaerd: "dreamed", tlips: "spilled", tliops: "spoiled", tslihw: "while", tsgnoma: "among",
  yerots: "story", syerots: "stories", shtam: "math", eriuqne: "inquire", yriuqne: "inquiry",
  seiriuqne: "inquiries", ytilaiceps: "specialty", aideapolcycne: "encyclopedia",
  cirtaideap: "pediatric", aimeana: "anemia", citehtseana: "anesthetic", suteof: "fetus",
  sugahposeo: "esophagus", negortseo: "estrogen", cideapohtro: "orthopedic", brek: "curb",
  thguard: "draft", sthguard: "drafts", loag: "jail", euqehc: "check", seuqehc: "checks",
  esylaid: "dialyze",
};
// parts of words: any word holding one (watercolor, epicenter, kilometer)
const PARTS = [["ertnec", "center"], ["ertem", "meter"], ["ertil", "liter"], ["ertaeht", "theater"],
  ["erbif", "fiber"], ["erbilac", "caliber"], ["erbas", "saber"], ["ertceps", "specter"], ["ertsul", "luster"],
  ["ergaem", "meager"], ["erbmos", "somber"], ["ruoloc", "color"]].map(([b, a]) => [R(b), a]);
const PARTS_FIRST = [["dertnec", "centered"], ["gnirtnec", "centering"], ["dertem", "metered"]]
  .map(([b, a]) => [R(b), a]);
const KEEP = new Set([R("dnuohyerg"), R("sdnuohyerg")]);
const PREFIXES = ["un", "re", "non", "pre", "de", "mis", "over", "under", "sub", "multi", "auto", "self", "co",
  "counter", "dis", "inter", "micro", "mini", "post", "semi", "super", "anti", "hyper", "ultra"];
// endings that are British whatever the stem: no American word ends in them
const ALWAYS = [["noitasi", "ization"], ["snoitasi", "izations"], ["esyl", "lyze"], ["desyl", "lyzed"],
  ["sesyl", "lyzes"], ["gnisyl", "lyzing"]].map(([b, a]) => [R(b), a]);

const TABLE = (() => {
  const t = new Map(Object.entries(WORDS).map(([k, v]) => [R(k), v]));
  const ourSuffixes = ["", "s", "ed", "ing", "ful", "fully", "less", "able", "ably", "ite", "ites", "ings", "er",
    "ers", "hood", "hoods", "ly", "y"];
  for (const w of OUR) for (const suf of ourSuffixes) t.set(w + suf, w.slice(0, -3) + "or" + suf);
  for (const s of new Set(ISE)) {
    const base = s.replace(R("ruoloc"), "color");
    for (const [b, a] of ISE_SUFFIX) t.set(s + b, base + a);
  }
  for (const s of YSE) for (const [b, a] of YSE_SUFFIX) t.set(s + b, s + a);
  return t;
})();

function withCase(src, dst) {
  if (src === src.toUpperCase()) return dst.toUpperCase();
  if (src[0] === src[0].toUpperCase()) return dst[0].toUpperCase() + dst.slice(1);
  return dst;
}

function convertWord(w) {
  const low = w.toLowerCase();
  if (KEEP.has(low)) return w;
  if (TABLE.has(low)) return withCase(w, TABLE.get(low));
  for (const p of PREFIXES) {                        // unquantized, relabeled, misbehavior
    if (low.startsWith(p) && TABLE.has(low.slice(p.length))) return withCase(w, p + TABLE.get(low.slice(p.length)));
  }
  for (const [b, a] of ALWAYS) {
    if (low.endsWith(b) && low.length > b.length + 2) return withCase(w, low.slice(0, -b.length) + a);
  }
  for (const [b, a] of PARTS) {
    if (low.includes(b)) {
      let out = low;
      for (const [fb, fa] of PARTS_FIRST) out = out.replaceAll(fb, fa);
      return withCase(w, out.replaceAll(b, a));
    }
  }
  return w;
}

// every run of letters -- so snake_case and camelCase names are found -- split into its camelCase parts
const convertRun = (run) => run.replace(/[A-Z]?[a-z]+|[A-Z]+(?![a-z])/g, convertWord);

const TOKEN_CH = /[A-Za-z0-9+/=]/;

/** Inside embedded base64 or a long hash: the unbroken token around the letters is long. */
function inBlob(text, i, j) {
  let a = i;
  while (a > 0 && TOKEN_CH.test(text[a - 1])) if (i - --a > 40) return true;
  let b = j;
  while (b < text.length && TOKEN_CH.test(text[b])) if (++b - j > 40) return true;
  return b - a > 40;
}

function lineOf(text) {
  const starts = [0];
  for (let i = 0; i < text.length; i++) if (text[i] === "\n") starts.push(i + 1);
  return (index) => {
    let lo = 0, hi = starts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (starts[mid] <= index) lo = mid; else hi = mid - 1;
    }
    return lo + 1;
  };
}

/** Every British spelling in the text: [{line, word, fix}]. */
export function spelling(text) {
  const line = lineOf(text);
  const hits = [];
  for (const m of text.matchAll(/[A-Za-z]+/g)) {
    const fix = convertRun(m[0]);
    if (fix !== m[0] && !inBlob(text, m.index, m.index + m[0].length)) hits.push({ line: line(m.index), word: m[0], fix });
  }
  return hits;
}

// ---- secrets

const SECRETS = [
  ["a JSON web token (reMarkable device and user tokens look like this)",
    /eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g],
  ["an Anthropic API key", /sk-ant-[A-Za-z0-9_-]{20,}/g],
  ["an OpenAI-style API key", /\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}/g],
  ["a GitHub token", /\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})/g],
  ["a Google API key", /\bAIza[0-9A-Za-z_-]{35}/g],
  ["a Hugging Face token", /\bhf_[A-Za-z0-9]{30,}/g],
  ["a private key", /-----BEGIN [A-Z ]*PRIVATE KEY-----/g],
];

/** Every secret-shaped string in the text: [{line, what}]. Never returns the secret itself. */
export function secrets(text) {
  const line = lineOf(text);
  const hits = new Map();
  for (const [what, re] of SECRETS) {
    for (const m of text.matchAll(re)) {
      const n = line(m.index);
      if (!hits.has(n)) hits.set(n, { line: n, what });
    }
  }
  return [...hits.values()].sort((a, b) => a.line - b.line);
}

// ---- the command line

function* walk(p) {
  const st = fs.statSync(p, { throwIfNoEntry: false });
  if (!st) return;
  if (st.isFile()) { if (isText(p)) yield p; return; }
  for (const e of fs.readdirSync(p, { withFileTypes: true })) {
    if (e.isDirectory()) { if (!SKIP_DIRS.has(e.name)) yield* walk(path.join(p, e.name)); }
    else if (isText(e.name)) yield path.join(p, e.name);
  }
}

function main(args) {
  let found = 0, files = 0;
  for (const f of (args.length ? args : [ROOT]).flatMap((p) => [...walk(path.resolve(p))])) {
    let text;
    try { text = fs.readFileSync(f, "utf8"); } catch { continue; }
    const rel = path.relative(ROOT, f) || f;
    const out = [
      ...(VERBATIM.has(rel.split(path.sep).join("/")) ? [] : spelling(text)).map((h) => `${rel}:${h.line}  ${h.word} -> ${h.fix}`),
      ...secrets(text).map((h) => `${rel}:${h.line}  ${h.what}`),
    ];
    if (out.length) { files++; found += out.length; console.log(out.join("\n")); }
  }
  console.log(`${found} finding(s) in ${files} file(s)`);
  return found ? 1 : 0;
}

const same = (a, b) => (process.platform === "win32" ? a.toLowerCase() === b.toLowerCase() : a === b);
if (process.argv[1] && same(path.resolve(process.argv[1]), fileURLToPath(import.meta.url))) {
  process.exitCode = main(process.argv.slice(2));
}
