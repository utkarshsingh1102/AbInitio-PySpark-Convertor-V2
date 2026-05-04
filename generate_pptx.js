// Ab Initio → PySpark Convertor — Dark Tech Executive Deck
// Generates AbInitio-PySpark-Presentation.pptx

const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3" x 7.5"
pres.author = "IBM Network Team";
pres.title = "Ab Initio → PySpark Convertor";

// ---- Theme ----
const C = {
  bg: "0D1117",
  card: "161B22",
  cardBorder: "30363D",
  orange: "F97316",
  blue: "3B82F6",
  green: "22C55E",
  yellow: "EAB308",
  red: "EF4444",
  purple: "A855F7",
  text: "F0F6FC",
  muted: "8B949E",
  dim: "6E7681",
};

const FONT = "Calibri";
const W = 13.3;
const H = 7.5;

// Fresh shadow factories (NEVER reuse option objects)
const cardShadow = () => ({ type: "outer", color: "000000", blur: 12, offset: 3, angle: 90, opacity: 0.35 });

// --- Helper: dark page chrome (background + left orange edge + footer) ---
function chrome(slide, opts = {}) {
  slide.background = { color: C.bg };
  // Left orange accent edge
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: H,
    fill: { color: C.orange }, line: { color: C.orange, width: 0 },
  });
  // Footer divider
  if (!opts.hideFooter) {
    slide.addShape(pres.shapes.LINE, {
      x: 0.5, y: H - 0.45, w: W - 1.0, h: 0,
      line: { color: C.cardBorder, width: 0.75 },
    });
    slide.addText("Ab Initio → PySpark Convertor  ·  IBM Network", {
      x: 0.5, y: H - 0.4, w: 8, h: 0.3,
      fontFace: FONT, fontSize: 10, color: C.dim, margin: 0,
    });
    slide.addText(opts.footerRight || "Internal · May 2026", {
      x: W - 4.5, y: H - 0.4, w: 4, h: 0.3,
      fontFace: FONT, fontSize: 10, color: C.dim, align: "right", margin: 0,
    });
  }
}

function pageTitle(slide, title, subtitle) {
  slide.addText(title, {
    x: 0.5, y: 0.35, w: W - 1, h: 0.7,
    fontFace: FONT, fontSize: 32, bold: true, color: C.text, margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.5, y: 1.05, w: W - 1, h: 0.4,
      fontFace: FONT, fontSize: 15, color: C.muted, margin: 0,
    });
  }
  // Underline accent
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: subtitle ? 1.5 : 1.1, w: 0.6, h: 0.05,
    fill: { color: C.orange }, line: { color: C.orange, width: 0 },
  });
}

function card(slide, x, y, w, h, opts = {}) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: opts.fill || C.card },
    line: { color: opts.border || C.cardBorder, width: opts.borderWidth || 1 },
    shadow: cardShadow(),
  });
}

// =========================================================================
// SLIDE 1 — TITLE
// =========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.bg };

  // Wide left orange edge
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: H,
    fill: { color: C.orange }, line: { color: C.orange, width: 0 },
  });

  // Hero subtle band
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.15, y: 0, w: W - 0.15, h: H,
    fill: { color: C.bg }, line: { color: C.bg, width: 0 },
  });

  // Decorative orange bar above title
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 1.2, y: 2.4, w: 0.6, h: 0.06,
    fill: { color: C.orange }, line: { color: C.orange, width: 0 },
  });

  slide.addText("AB INITIO  →  PYSPARK", {
    x: 1.2, y: 2.55, w: W - 2, h: 0.5,
    fontFace: FONT, fontSize: 18, bold: true, color: C.orange,
    charSpacing: 8, margin: 0,
  });

  slide.addText("Ab Initio → PySpark Convertor", {
    x: 1.2, y: 3.05, w: W - 2, h: 1.2,
    fontFace: FONT, fontSize: 54, bold: true, color: C.text, margin: 0,
  });

  slide.addText("IBM Network  |  Automated Legacy ETL Migration", {
    x: 1.2, y: 4.3, w: W - 2, h: 0.6,
    fontFace: FONT, fontSize: 22, color: C.muted, margin: 0,
  });

  // Bottom-left
  slide.addText("Team Presentation — Internal", {
    x: 1.2, y: H - 0.9, w: 6, h: 0.4,
    fontFace: FONT, fontSize: 12, color: C.dim, margin: 0,
  });
  // Bottom-right
  slide.addText("May 2026", {
    x: W - 3.2, y: H - 0.9, w: 3, h: 0.4,
    fontFace: FONT, fontSize: 12, color: C.dim, align: "right", margin: 0,
  });
}

// =========================================================================
// SLIDE 2 — THE PROBLEM
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "The Problem");

  // 3 stat callouts
  const statY = 1.85;
  const statH = 1.4;
  const stats = [
    { big: "Weeks", label: "Manual Migration Time Per Graph", color: C.orange },
    { big: "High", label: "Error Rate in Manual Re-coding", color: C.red },
    { big: "$$$", label: "Engineering Cost per Migration", color: C.yellow },
  ];
  const gap = 0.25;
  const totalW = W - 1;
  const sw = (totalW - 2 * gap) / 3;
  stats.forEach((s, i) => {
    const x = 0.5 + i * (sw + gap);
    card(slide, x, statY, sw, statH);
    // Top accent
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: statY, w: sw, h: 0.06,
      fill: { color: s.color }, line: { color: s.color, width: 0 },
    });
    slide.addText(s.big, {
      x, y: statY + 0.15, w: sw, h: 0.7,
      fontFace: FONT, fontSize: 38, bold: true, color: s.color,
      align: "center", margin: 0,
    });
    slide.addText(s.label, {
      x: x + 0.15, y: statY + 0.85, w: sw - 0.3, h: 0.5,
      fontFace: FONT, fontSize: 13, color: C.muted,
      align: "center", margin: 0,
    });
  });

  // Two-column comparison
  const colY = 3.55;
  const colH = 3.2;
  const colW = (W - 1 - gap) / 2;

  // LEFT
  card(slide, 0.5, colY, colW, colH);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: colY, w: 0.06, h: colH,
    fill: { color: C.red }, line: { color: C.red, width: 0 },
  });
  slide.addText("Ab Initio Reality", {
    x: 0.75, y: colY + 0.15, w: colW - 0.3, h: 0.4,
    fontFace: FONT, fontSize: 18, bold: true, color: C.text, margin: 0,
  });
  slide.addText([
    { text: "Proprietary .mp graph format — not human-readable", options: { bullet: true, breakLine: true } },
    { text: "DML schemas define complex binary/text layouts", options: { bullet: true, breakLine: true } },
    { text: "Transform expressions in Ab Initio's own language", options: { bullet: true, breakLine: true } },
    { text: "Hundreds of graphs to migrate", options: { bullet: true } },
  ], {
    x: 0.85, y: colY + 0.7, w: colW - 0.45, h: colH - 0.85,
    fontFace: FONT, fontSize: 13, color: C.text, paraSpaceAfter: 6,
  });

  // RIGHT
  const rx = 0.5 + colW + gap;
  card(slide, rx, colY, colW, colH);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: rx, y: colY, w: 0.06, h: colH,
    fill: { color: C.orange }, line: { color: C.orange, width: 0 },
  });
  slide.addText("Current Approach", {
    x: rx + 0.25, y: colY + 0.15, w: colW - 0.3, h: 0.4,
    fontFace: FONT, fontSize: 18, bold: true, color: C.text, margin: 0,
  });
  slide.addText([
    { text: "Engineers manually read each graph", options: { bullet: true, breakLine: true } },
    { text: "Hand-write PySpark equivalents", options: { bullet: true, breakLine: true } },
    { text: "No consistency, high rework rate", options: { bullet: true, breakLine: true } },
    { text: "No validation until runtime", options: { bullet: true } },
  ], {
    x: rx + 0.35, y: colY + 0.7, w: colW - 0.45, h: colH - 0.85,
    fontFace: FONT, fontSize: 13, color: C.text, paraSpaceAfter: 6,
  });
}

// =========================================================================
// SLIDE 3 — SOLUTION OVERVIEW
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "Our Solution: Automated Conversion Pipeline");

  slide.addText("Input .mp graph  →  Runnable PySpark .py file", {
    x: 0.5, y: 1.55, w: W - 1, h: 0.5,
    fontFace: FONT, fontSize: 20, color: C.text,
    align: "center", italic: true, margin: 0,
  });

  // 4 numbered cards
  const cardsY = 2.55;
  const cardsH = 2.6;
  const gap = 0.3;
  const cw = (W - 1 - 3 * gap) / 4;
  const steps = [
    { n: "1", t: "Parse",    d: "Read Ab Initio graph structure from Neo4j" },
    { n: "2", t: "Schema",   d: "Convert DML record formats to PySpark StructType" },
    { n: "3", t: "Map",      d: "Translate Ab Initio components to PySpark ops" },
    { n: "4", t: "Generate", d: "Synthesize production-ready .py file" },
  ];
  steps.forEach((s, i) => {
    const x = 0.5 + i * (cw + gap);
    card(slide, x, cardsY, cw, cardsH);
    slide.addText(s.n, {
      x, y: cardsY + 0.2, w: cw, h: 1.0,
      fontFace: FONT, fontSize: 64, bold: true, color: C.orange,
      align: "center", margin: 0,
    });
    slide.addText(s.t, {
      x, y: cardsY + 1.25, w: cw, h: 0.5,
      fontFace: FONT, fontSize: 20, bold: true, color: C.text,
      align: "center", margin: 0,
    });
    slide.addText(s.d, {
      x: x + 0.15, y: cardsY + 1.75, w: cw - 0.3, h: 0.8,
      fontFace: FONT, fontSize: 12, color: C.muted,
      align: "center", margin: 0,
    });
  });

  // Banner
  const banY = 5.55;
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: banY, w: W - 1, h: 0.85,
    fill: { color: C.orange }, line: { color: C.orange, width: 0 },
    shadow: cardShadow(),
  });
  slide.addText("90/99 test cases passing  ·  6 components covered  ·  25 DML features supported", {
    x: 0.5, y: banY, w: W - 1, h: 0.85,
    fontFace: FONT, fontSize: 18, bold: true, color: "0D1117",
    align: "center", valign: "middle", margin: 0,
  });
}

// =========================================================================
// SLIDE 4 — ARCHITECTURE
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "Architecture: Two Networks");

  const panelY = 1.85;
  const panelH = 4.95;
  const arrowW = 0.9;
  const panelW = (W - 1 - arrowW) / 2;

  // LEFT panel — Client Network (out of scope)
  card(slide, 0.5, panelY, panelW, panelH, { border: C.dim, borderWidth: 1 });
  slide.addText("OUT OF SCOPE", {
    x: 0.65, y: panelY + 0.2, w: panelW - 0.3, h: 0.3,
    fontFace: FONT, fontSize: 10, bold: true, color: C.dim,
    charSpacing: 4, margin: 0,
  });
  slide.addText("Client Network", {
    x: 0.65, y: panelY + 0.5, w: panelW - 0.3, h: 0.5,
    fontFace: FONT, fontSize: 22, bold: true, color: C.muted, margin: 0,
  });
  slide.addShape(pres.shapes.LINE, {
    x: 0.65, y: panelY + 1.05, w: panelW - 0.3, h: 0,
    line: { color: C.cardBorder, width: 0.75 },
  });
  const lItems = [
    { label: "Ab Initio .mp Graph Files", desc: "Proprietary input format" },
    { label: "Parser (separate workstream)", desc: "Owned by another team" },
    { label: "Outputs to Neo4j Graph DB", desc: "Hand-off boundary" },
  ];
  lItems.forEach((it, i) => {
    const y = panelY + 1.3 + i * 0.85;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.75, y, w: panelW - 0.5, h: 0.7,
      fill: { color: "0D1117" }, line: { color: C.cardBorder, width: 1 },
    });
    slide.addText(it.label, {
      x: 0.85, y: y + 0.06, w: panelW - 0.7, h: 0.32,
      fontFace: FONT, fontSize: 13, bold: true, color: C.text, margin: 0,
    });
    slide.addText(it.desc, {
      x: 0.85, y: y + 0.36, w: panelW - 0.7, h: 0.3,
      fontFace: FONT, fontSize: 10, color: C.muted, margin: 0,
    });
  });
  slide.addText("Runs on client premises", {
    x: 0.75, y: panelY + panelH - 0.55, w: panelW - 0.5, h: 0.3,
    fontFace: FONT, fontSize: 10, italic: true, color: C.dim, margin: 0,
  });

  // CENTER arrow
  const ax = 0.5 + panelW;
  slide.addShape(pres.shapes.RIGHT_TRIANGLE, {
    x: ax + 0.1, y: panelY + panelH / 2 - 0.35, w: 0.7, h: 0.7,
    fill: { color: C.orange }, line: { color: C.orange, width: 0 },
    rotate: 90,
  });
  slide.addText("Neo4j", {
    x: ax - 0.1, y: panelY + panelH / 2 - 0.85, w: arrowW + 0.2, h: 0.3,
    fontFace: FONT, fontSize: 10, bold: true, color: C.orange,
    align: "center", margin: 0,
  });
  slide.addText("Handoff", {
    x: ax - 0.1, y: panelY + panelH / 2 + 0.4, w: arrowW + 0.2, h: 0.3,
    fontFace: FONT, fontSize: 10, color: C.muted,
    align: "center", margin: 0,
  });

  // RIGHT panel — IBM Network (this project)
  const rx = 0.5 + panelW + arrowW;
  card(slide, rx, panelY, panelW, panelH, { border: C.orange, borderWidth: 2 });
  slide.addText("THIS PROJECT", {
    x: rx + 0.15, y: panelY + 0.2, w: panelW - 0.3, h: 0.3,
    fontFace: FONT, fontSize: 10, bold: true, color: C.orange,
    charSpacing: 4, margin: 0,
  });
  slide.addText("IBM Network", {
    x: rx + 0.15, y: panelY + 0.5, w: panelW - 0.3, h: 0.5,
    fontFace: FONT, fontSize: 22, bold: true, color: C.orange, margin: 0,
  });
  slide.addShape(pres.shapes.LINE, {
    x: rx + 0.15, y: panelY + 1.05, w: panelW - 0.3, h: 0,
    line: { color: C.cardBorder, width: 0.75 },
  });
  const rItems = [
    { n: "①", t: "IR Loader",       d: "Neo4j → Pydantic IR" },
    { n: "②", t: "DML Convertor",   d: "DML → StructType" },
    { n: "③", t: "Mapping Engine",  d: "AbInitio ops → PySpark ops" },
    { n: "④", t: "Code Generator",  d: "Jinja2 + LLM → .py" },
  ];
  rItems.forEach((it, i) => {
    const y = panelY + 1.25 + i * 0.7;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: rx + 0.25, y, w: panelW - 0.5, h: 0.58,
      fill: { color: "0D1117" }, line: { color: C.orange, width: 0.75 },
    });
    slide.addText(it.n, {
      x: rx + 0.32, y: y + 0.08, w: 0.4, h: 0.4,
      fontFace: FONT, fontSize: 18, bold: true, color: C.orange, margin: 0,
    });
    slide.addText(it.t, {
      x: rx + 0.75, y: y + 0.05, w: panelW - 1.1, h: 0.3,
      fontFace: FONT, fontSize: 13, bold: true, color: C.text, margin: 0,
    });
    slide.addText(it.d, {
      x: rx + 0.75, y: y + 0.28, w: panelW - 1.1, h: 0.3,
      fontFace: FONT, fontSize: 10, color: C.muted, margin: 0,
    });
  });
  slide.addText("→ Runnable PySpark .py", {
    x: rx + 0.25, y: panelY + panelH - 0.6, w: panelW - 0.5, h: 0.4,
    fontFace: FONT, fontSize: 14, bold: true, color: C.green,
    align: "center", margin: 0,
  });
}

// =========================================================================
// SLIDE 5 — END TO END FLOW
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "How It Works — End to End");

  // 7-step pipeline
  const flowY = 1.7;
  const flowH = 1.6;
  const gap = 0.05;
  const steps = [
    { t: ".mp File",        d: "Ab Initio graph" },
    { t: "Neo4j DB",        d: "Parser output (graph nodes + edges)" },
    { t: "IR Loader",       d: "Pydantic models (Graph, Component, Edge)" },
    { t: "Mapping Engine",  d: "Rule-based + LLM fallback" },
    { t: "DML Convertor",   d: "Lark Earley parser → StructType" },
    { t: "Code Generator",  d: "Jinja2 template + Ollama polish" },
    { t: "output.py",       d: "Runnable PySpark pipeline" },
  ];
  const arrowW = 0.25;
  const totalW = W - 1;
  const stepW = (totalW - 6 * arrowW - 6 * gap * 2) / 7;
  steps.forEach((s, i) => {
    const x = 0.5 + i * (stepW + arrowW + gap * 2);
    card(slide, x, flowY, stepW, flowH);
    // top accent
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: flowY, w: stepW, h: 0.05,
      fill: { color: i === 6 ? C.green : C.orange }, line: { color: C.orange, width: 0 },
    });
    slide.addText(s.t, {
      x, y: flowY + 0.18, w: stepW, h: 0.5,
      fontFace: FONT, fontSize: 12, bold: true, color: C.text,
      align: "center", margin: 0,
    });
    slide.addText(s.d, {
      x: x + 0.05, y: flowY + 0.7, w: stepW - 0.1, h: 0.85,
      fontFace: FONT, fontSize: 9, italic: true, color: C.muted,
      align: "center", margin: 0,
    });
    // arrow
    if (i < 6) {
      slide.addShape(pres.shapes.RIGHT_TRIANGLE, {
        x: x + stepW + gap, y: flowY + flowH / 2 - 0.12, w: arrowW, h: 0.24,
        fill: { color: C.orange }, line: { color: C.orange, width: 0 },
        rotate: 90,
      });
    }
  });

  // Example transform
  const exY = 4.0;
  const exH = 2.6;
  const exGap = 0.4;
  const exW = (W - 1 - exGap) / 2;

  card(slide, 0.5, exY, exW, exH);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: exY, w: 0.06, h: exH,
    fill: { color: C.blue }, line: { color: C.blue, width: 0 },
  });
  slide.addText("Ab Initio REFORMAT — transform body", {
    x: 0.7, y: exY + 0.2, w: exW - 0.3, h: 0.4,
    fontFace: FONT, fontSize: 13, bold: true, color: C.blue, margin: 0,
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: exY + 0.7, w: exW - 0.4, h: exH - 0.95,
    fill: { color: "0D1117" }, line: { color: C.cardBorder, width: 1 },
  });
  slide.addText([
    { text: "out.customer_id :: customer_id;", options: { breakLine: true } },
    { text: "out.name :: string_upcase(name);", options: { breakLine: true } },
    { text: "out.amount :: decimal(amount);", options: {} },
  ], {
    x: 0.85, y: exY + 0.85, w: exW - 0.7, h: exH - 1.2,
    fontFace: "Consolas", fontSize: 13, color: C.text, margin: 0,
  });

  const rx = 0.5 + exW + exGap;
  card(slide, rx, exY, exW, exH);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: rx, y: exY, w: 0.06, h: exH,
    fill: { color: C.green }, line: { color: C.green, width: 0 },
  });
  slide.addText("Generated PySpark", {
    x: rx + 0.2, y: exY + 0.2, w: exW - 0.3, h: 0.4,
    fontFace: FONT, fontSize: 13, bold: true, color: C.green, margin: 0,
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: rx + 0.2, y: exY + 0.7, w: exW - 0.4, h: exH - 0.95,
    fill: { color: "0D1117" }, line: { color: C.cardBorder, width: 1 },
  });
  slide.addText([
    { text: "df.select(", options: { breakLine: true } },
    { text: "    col(\"customer_id\"),", options: { breakLine: true } },
    { text: "    upper(col(\"name\")).alias(\"name\"),", options: { breakLine: true } },
    { text: "    col(\"amount\").cast(\"decimal\"),", options: { breakLine: true } },
    { text: ")", options: {} },
  ], {
    x: rx + 0.35, y: exY + 0.85, w: exW - 0.7, h: exH - 1.2,
    fontFace: "Consolas", fontSize: 12, color: C.text, margin: 0,
  });
}

// =========================================================================
// SLIDE 6 — DML CONVERTOR DEEP DIVE
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "DML Convertor: Feature Coverage", "Lark Earley parser handles the full Ab Initio DML grammar");

  const features = [
    ["Scalar types (decimal, integer, real, string, date, datetime, void)", "✅ Supported", C.green],
    ["Delimited fields + per-field null sentinels", "✅ Supported", C.green],
    ["Fixed-width (no-delimiter) records", "✅ Supported", C.green],
    ["Nested sub-records (record...end name)", "✅ Supported", C.green],
    ["Fixed-length vectors  field[N]", "✅ Supported", C.green],
    ["Variable-length vectors  record[disc]...end", "✅ Supported", C.green],
    ["Union fields", "✅ MANUAL_REVIEW flagged", C.green],
    ["Conditional fields (if / else if / else chains)", "✅ Supported", C.green],
    ["Packed / zoned decimal", "✅ MANUAL_REVIEW flagged", C.green],
    ["Mixed-delimiter records", "✅ Supported", C.green],
    ["Comments and whitespace", "✅ Supported", C.green],
    ["Include resolver  (%include)", "🔄 In Progress", C.yellow],
    ["Type aliases  (typedef)", "🔄 In Progress", C.yellow],
    ["EBCDIC charset", "🔄 In Progress", C.yellow],
  ];

  const tableY = 1.95;
  const tableX = 0.5;
  const tableW = W - 1;
  const rowH = 0.34;
  const featW = tableW * 0.72;
  const statW = tableW * 0.28;

  // Header
  slide.addShape(pres.shapes.RECTANGLE, {
    x: tableX, y: tableY, w: tableW, h: 0.4,
    fill: { color: "1F2937" }, line: { color: C.cardBorder, width: 0 },
  });
  slide.addText("Feature", {
    x: tableX + 0.15, y: tableY, w: featW - 0.15, h: 0.4,
    fontFace: FONT, fontSize: 11, bold: true, color: C.muted,
    valign: "middle", charSpacing: 2, margin: 0,
  });
  slide.addText("Status", {
    x: tableX + featW, y: tableY, w: statW - 0.15, h: 0.4,
    fontFace: FONT, fontSize: 11, bold: true, color: C.muted,
    valign: "middle", charSpacing: 2, margin: 0,
  });

  features.forEach(([feat, stat, color], i) => {
    const y = tableY + 0.4 + i * rowH;
    if (i % 2 === 0) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: tableX, y, w: tableW, h: rowH,
        fill: { color: "12181F" }, line: { color: C.bg, width: 0 },
      });
    }
    slide.addText(feat, {
      x: tableX + 0.15, y, w: featW - 0.15, h: rowH,
      fontFace: FONT, fontSize: 11, color: C.text,
      valign: "middle", margin: 0,
    });
    slide.addText(stat, {
      x: tableX + featW, y, w: statW - 0.15, h: rowH,
      fontFace: FONT, fontSize: 11, bold: true, color,
      valign: "middle", margin: 0,
    });
  });
}

// =========================================================================
// SLIDE 7 — MAPPING ENGINE
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "Mapping Engine: 6 Components Covered", "Rule-based deterministic mapping. LLM fallback only for unknowns.");

  const comps = [
    { name: "REFORMAT",              op: "df.select(*cols)",                 code: 'df.select(col("id"), upper(col("name")))' },
    { name: "FILTER_BY_EXPRESSION",  op: "df.filter(...)",                   code: 'df.filter(F.expr("amount > 100"))' },
    { name: "JOIN",                  op: "left.join(right, on=keys)",        code: 'left.join(right, on=["id"], how="inner")' },
    { name: "SORT",                  op: "df.orderBy(*keys)",                code: 'df.orderBy("date", "id")' },
    { name: "ROLLUP",                op: "df.groupBy().agg()",               code: 'df.groupBy("region").agg(sum("sales"))' },
    { name: "DEDUP_SORTED",          op: "df.dropDuplicates()",              code: 'df.dropDuplicates(["customer_id"])' },
  ];

  const gridY = 1.95;
  const gridGap = 0.2;
  const cw = (W - 1 - 2 * gridGap) / 3;
  const ch = 1.85;

  comps.forEach((c, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.5 + col * (cw + gridGap);
    const y = gridY + row * (ch + gridGap);

    card(slide, x, y, cw, ch);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: cw, h: 0.05,
      fill: { color: C.orange }, line: { color: C.orange, width: 0 },
    });

    slide.addText(c.name, {
      x: x + 0.15, y: y + 0.15, w: cw - 0.3, h: 0.35,
      fontFace: FONT, fontSize: 14, bold: true, color: C.orange, margin: 0,
    });
    slide.addText("→  " + c.op, {
      x: x + 0.15, y: y + 0.55, w: cw - 0.3, h: 0.35,
      fontFace: "Consolas", fontSize: 12, color: C.blue, margin: 0,
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x + 0.15, y: y + 0.95, w: cw - 0.3, h: 0.75,
      fill: { color: "0D1117" }, line: { color: C.cardBorder, width: 1 },
    });
    slide.addText(c.code, {
      x: x + 0.25, y: y + 1.0, w: cw - 0.5, h: 0.65,
      fontFace: "Consolas", fontSize: 9, color: C.text,
      valign: "middle", margin: 0,
    });
  });

  // Bottom strategy banner
  const banY = gridY + 2 * (ch + gridGap) + 0.05;
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: banY, w: W - 1, h: 0.7,
    fill: { color: C.card }, line: { color: C.orange, width: 1 },
  });
  slide.addText([
    { text: "Strategy:  ", options: { bold: true, color: C.orange } },
    { text: "Deterministic rules handle ~90% of cases. Local LLM (Ollama) invoked only for unknown components or unparseable transform expressions.", options: { color: C.text } },
  ], {
    x: 0.7, y: banY, w: W - 1.4, h: 0.7,
    fontFace: FONT, fontSize: 12, valign: "middle", margin: 0,
  });
}

// =========================================================================
// SLIDE 8 — CODE GENERATOR
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "Code Generator: From IR to Production Python", "Deterministic synthesis with optional LLM polish — all on-premise");

  const colY = 1.95;
  const colH = 4.7;
  const colGap = 0.4;
  const colW = (W - 1 - colGap) / 2;

  // LEFT — How it works
  card(slide, 0.5, colY, colW, colH);
  slide.addText("How it works", {
    x: 0.7, y: colY + 0.2, w: colW - 0.3, h: 0.45,
    fontFace: FONT, fontSize: 18, bold: true, color: C.text, margin: 0,
  });
  slide.addShape(pres.shapes.LINE, {
    x: 0.7, y: colY + 0.7, w: 1.0, h: 0,
    line: { color: C.orange, width: 2 },
  });

  const steps = [
    "Walk IR graph in topological order",
    "Pull mapped op for each component",
    "Render via Jinja2 pipeline template",
    "LLM polish pass (optional, local only)",
    "Output clean, importable .py file",
  ];
  steps.forEach((s, i) => {
    const y = colY + 1.0 + i * 0.65;
    slide.addShape(pres.shapes.OVAL, {
      x: 0.75, y: y, w: 0.4, h: 0.4,
      fill: { color: C.orange }, line: { color: C.orange, width: 0 },
    });
    slide.addText(String(i + 1), {
      x: 0.75, y: y, w: 0.4, h: 0.4,
      fontFace: FONT, fontSize: 14, bold: true, color: "0D1117",
      align: "center", valign: "middle", margin: 0,
    });
    slide.addText(s, {
      x: 1.3, y: y + 0.04, w: colW - 0.85, h: 0.4,
      fontFace: FONT, fontSize: 13, color: C.text,
      valign: "middle", margin: 0,
    });
  });

  // RIGHT — Why local LLM
  const rx = 0.5 + colW + colGap;
  card(slide, rx, colY, colW, colH);
  slide.addText("Why Local LLM?", {
    x: rx + 0.2, y: colY + 0.2, w: colW - 0.3, h: 0.45,
    fontFace: FONT, fontSize: 18, bold: true, color: C.text, margin: 0,
  });
  slide.addShape(pres.shapes.LINE, {
    x: rx + 0.2, y: colY + 0.7, w: 1.0, h: 0,
    line: { color: C.orange, width: 2 },
  });
  // Orange callout
  slide.addShape(pres.shapes.RECTANGLE, {
    x: rx + 0.2, y: colY + 1.0, w: colW - 0.4, h: 1.4,
    fill: { color: C.orange }, line: { color: C.orange, width: 0 },
  });
  slide.addText('"Client DML schemas and transform expressions contain proprietary business logic. Data CANNOT leave the client network."', {
    x: rx + 0.4, y: colY + 1.05, w: colW - 0.8, h: 1.3,
    fontFace: FONT, fontSize: 13, bold: true, italic: true, color: "0D1117",
    valign: "middle", margin: 0,
  });

  const bullets = [
    "Model: qwen2.5-coder:14b via Ollama",
    "Alternative: vLLM on IBM-side infra",
    "LLM is optional — pipeline works without it",
    "Used only for fallback + final polish",
  ];
  slide.addText(bullets.map((b, i) => ({
    text: b, options: { bullet: true, breakLine: i < bullets.length - 1 },
  })), {
    x: rx + 0.4, y: colY + 2.6, w: colW - 0.6, h: colH - 2.8,
    fontFace: FONT, fontSize: 12, color: C.text, paraSpaceAfter: 6,
  });
}

// =========================================================================
// SLIDE 9 — WEB UI
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "Bonus: Local Web UI for Schema Exploration", "FastAPI + static HTML/JS — runs at localhost:8000");

  const cards = [
    { title: "DML Schema Tab",      color: C.blue,   desc: "Paste DML record → Get PySpark StructType + full spark.read chain" },
    { title: "Transform Body Tab",  color: C.orange, desc: "Paste Ab Initio out.x :: expr block → Get df.select() arguments" },
    { title: "Single Expression Tab", color: C.green, desc: "One Ab Initio expression → PySpark Column expression" },
    { title: "Full Pipeline Tab",   color: C.purple, desc: "POST graph JSON → Complete runnable .py file" },
  ];

  const gridY = 1.95;
  const gridGap = 0.3;
  const cw = (W - 1 - gridGap) / 2;
  const ch = 1.85;

  cards.forEach((c, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.5 + col * (cw + gridGap);
    const y = gridY + row * (ch + gridGap);
    card(slide, x, y, cw, ch);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.08, h: ch,
      fill: { color: c.color }, line: { color: c.color, width: 0 },
    });
    slide.addShape(pres.shapes.OVAL, {
      x: x + 0.3, y: y + 0.3, w: 0.7, h: 0.7,
      fill: { color: c.color, transparency: 75 },
      line: { color: c.color, width: 1.5 },
    });
    slide.addText(String(i + 1), {
      x: x + 0.3, y: y + 0.3, w: 0.7, h: 0.7,
      fontFace: FONT, fontSize: 22, bold: true, color: c.color,
      align: "center", valign: "middle", margin: 0,
    });
    slide.addText(c.title, {
      x: x + 1.15, y: y + 0.35, w: cw - 1.3, h: 0.5,
      fontFace: FONT, fontSize: 17, bold: true, color: C.text, margin: 0,
    });
    slide.addText(c.desc, {
      x: x + 1.15, y: y + 0.85, w: cw - 1.3, h: ch - 1.0,
      fontFace: FONT, fontSize: 12, color: C.muted, margin: 0,
    });
  });

  // Bottom command bar
  const cmdY = gridY + 2 * (ch + gridGap) + 0.05;
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: cmdY, w: W - 1, h: 0.55,
    fill: { color: "0D1117" }, line: { color: C.orange, width: 1 },
  });
  slide.addText('$  pip install -e ".[web]"  &&  uvicorn ibm_network.web.server:app --reload --port 8000', {
    x: 0.7, y: cmdY, w: W - 1.4, h: 0.55,
    fontFace: "Consolas", fontSize: 12, color: C.green,
    valign: "middle", margin: 0,
  });
}

// =========================================================================
// SLIDE 10 — TEST PROGRESS
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "Test Progress: 90 / 99 Passing", "DML Suite — TC-001 through TC-025 + CLI + E2E tests");

  // Big stat
  slide.addText("90", {
    x: 0.5, y: 1.6, w: 4.5, h: 1.6,
    fontFace: FONT, fontSize: 110, bold: true, color: C.orange,
    align: "center", valign: "middle", margin: 0,
  });
  slide.addText("/", {
    x: 4.7, y: 1.6, w: 1.0, h: 1.6,
    fontFace: FONT, fontSize: 70, color: C.muted,
    align: "center", valign: "middle", margin: 0,
  });
  slide.addText("99", {
    x: 5.2, y: 1.6, w: 2.5, h: 1.6,
    fontFace: FONT, fontSize: 80, color: C.muted,
    align: "center", valign: "middle", margin: 0,
  });
  slide.addText("tests passing", {
    x: 0.5, y: 3.15, w: 7.2, h: 0.45,
    fontFace: FONT, fontSize: 17, color: C.text,
    align: "center", margin: 0,
  });

  // Side legend
  card(slide, 8.2, 1.7, 4.6, 2.1);
  slide.addText("Legend", {
    x: 8.4, y: 1.78, w: 4.2, h: 0.35,
    fontFace: FONT, fontSize: 13, bold: true, color: C.muted,
    charSpacing: 3, margin: 0,
  });
  const legend = [
    { c: C.green,  l: "PASS" },
    { c: C.yellow, l: "PARTIAL / Manual Review" },
    { c: C.red,    l: "FAIL" },
  ];
  legend.forEach((it, i) => {
    const y = 2.2 + i * 0.45;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 8.45, y, w: 0.35, h: 0.32,
      fill: { color: it.c }, line: { color: it.c, width: 0 },
    });
    slide.addText(it.l, {
      x: 8.95, y, w: 3.6, h: 0.32,
      fontFace: FONT, fontSize: 12, color: C.text,
      valign: "middle", margin: 0,
    });
  });

  // Test grid
  const grid = [
    // PASS = green, PARTIAL = yellow, FAIL = red
    { id: "TC-001", s: "P" }, { id: "TC-002", s: "P" }, { id: "TC-003", s: "P" }, { id: "TC-004", s: "P" }, { id: "TC-005", s: "P" },
    { id: "TC-006", s: "P" }, { id: "TC-007", s: "P" }, { id: "TC-008", s: "P" }, { id: "TC-009", s: "P" }, { id: "TC-010", s: "P" },
    { id: "TC-011", s: "P" }, { id: "TC-012", s: "P" }, { id: "TC-013", s: "P" }, { id: "TC-014", s: "P" }, { id: "TC-015", s: "P" },
    { id: "TC-016", s: "P" }, { id: "TC-017", s: "P" }, { id: "TC-018", s: "P" }, { id: "TC-019", s: "P" }, { id: "TC-020", s: "Y" },
    { id: "TC-021", s: "F" }, { id: "TC-022", s: "F" }, { id: "TC-023", s: "P" }, { id: "TC-024", s: "F" }, { id: "TC-025", s: "F" },
  ];
  const gx0 = 0.5;
  const gy0 = 4.0;
  const gW = W - 1;
  const gGap = 0.12;
  const cellW = (gW - 4 * gGap) / 5;
  const cellH = 0.55;

  grid.forEach((cell, i) => {
    const col = i % 5;
    const row = Math.floor(i / 5);
    const x = gx0 + col * (cellW + gGap);
    const y = gy0 + row * (cellH + gGap);
    let bg, txt;
    if (cell.s === "P") { bg = C.green;  txt = "0D1117"; }
    else if (cell.s === "Y") { bg = C.yellow; txt = "0D1117"; }
    else { bg = C.red; txt = "FFFFFF"; }
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: cellW, h: cellH,
      fill: { color: bg }, line: { color: bg, width: 0 },
    });
    slide.addText(cell.id, {
      x, y, w: cellW, h: cellH,
      fontFace: FONT, fontSize: 13, bold: true, color: txt,
      align: "center", valign: "middle", margin: 0,
    });
  });

  // Footer note
  slide.addText("9 failing tests across 5 scenarios. All failures are tracked with clear remediation paths.", {
    x: 0.5, y: H - 0.85, w: W - 1, h: 0.35,
    fontFace: FONT, fontSize: 11, italic: true, color: C.muted,
    align: "center", margin: 0,
  });
}

// =========================================================================
// SLIDE 11 — SCOPE
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "Scope: V1 Coverage");

  const panelY = 1.85;
  const panelH = 4.95;
  const panelGap = 0.4;
  const panelW = (W - 1 - panelGap) / 2;

  // LEFT — In Scope
  card(slide, 0.5, panelY, panelW, panelH);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: panelY, w: 0.1, h: panelH,
    fill: { color: C.green }, line: { color: C.green, width: 0 },
  });
  slide.addText([
    { text: "✓ ", options: { color: C.green, bold: true } },
    { text: "In Scope — V1", options: { color: C.text, bold: true } },
  ], {
    x: 0.75, y: panelY + 0.2, w: panelW - 0.3, h: 0.5,
    fontFace: FONT, fontSize: 22, margin: 0,
  });
  const inScope = [
    { h: "Ab Initio Components", b: "REFORMAT, FILTER_BY_EXPRESSION, JOIN, SORT, ROLLUP, DEDUP_SORTED" },
    { h: "DML Features", b: "All scalar types, null sentinels, date/time, vectors, nested records, conditionals, unions, packed decimal (stub)" },
    { h: "Infrastructure", b: "Neo4j → IR pipeline, CLI tool, Web UI, E2E tests, Docker Compose dev setup" },
  ];
  inScope.forEach((sec, i) => {
    const y = panelY + 0.95 + i * 1.3;
    slide.addText(sec.h, {
      x: 0.85, y, w: panelW - 0.45, h: 0.35,
      fontFace: FONT, fontSize: 13, bold: true, color: C.green,
      charSpacing: 1, margin: 0,
    });
    slide.addText(sec.b, {
      x: 0.85, y: y + 0.35, w: panelW - 0.45, h: 0.95,
      fontFace: FONT, fontSize: 12, color: C.text, margin: 0,
    });
  });

  // RIGHT — Out of Scope
  const rx = 0.5 + panelW + panelGap;
  card(slide, rx, panelY, panelW, panelH);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: rx, y: panelY, w: 0.1, h: panelH,
    fill: { color: C.red }, line: { color: C.red, width: 0 },
  });
  slide.addText([
    { text: "✕ ", options: { color: C.red, bold: true } },
    { text: "Out of Scope — V1", options: { color: C.text, bold: true } },
  ], {
    x: rx + 0.25, y: panelY + 0.2, w: panelW - 0.3, h: 0.5,
    fontFace: FONT, fontSize: 22, margin: 0,
  });
  const outScope = [
    { h: "Ab Initio Components", b: "SCAN, NORMALIZE, DENORMALIZE, LOOKUP, MULTI_REFORMAT, PARTITION_BY_KEY, GATHER, MERGE" },
    { h: "DML Features", b: "Include resolver (%include), Type aliases (typedef), EBCDIC charset full support" },
    { h: "Infrastructure", b: "The Parser (Client Network — separate workstream), Cloud deployment, CI/CD pipeline, Production hardening" },
  ];
  outScope.forEach((sec, i) => {
    const y = panelY + 0.95 + i * 1.3;
    slide.addText(sec.h, {
      x: rx + 0.35, y, w: panelW - 0.45, h: 0.35,
      fontFace: FONT, fontSize: 13, bold: true, color: C.red,
      charSpacing: 1, margin: 0,
    });
    slide.addText(sec.b, {
      x: rx + 0.35, y: y + 0.35, w: panelW - 0.45, h: 0.95,
      fontFace: FONT, fontSize: 12, color: C.text, margin: 0,
    });
  });
}

// =========================================================================
// SLIDE 12 — REMAINING WORK
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "Remaining Work: 5 Items");

  const items = [
    { id: "TC-021", title: "Include Resolver",         what: "grammar.lark + parser pre-processing for %include \"other.dml\"", effort: "~1 day" },
    { id: "TC-022", title: "Type Aliases",             what: "grammar extension + symbol table for typedef declarations",       effort: "~1 day" },
    { id: "TC-024", title: "EBCDIC Charset",           what: "grammar fix + MANUAL_REVIEW warning generation",                  effort: "~0.5 day" },
    { id: "TC-025", title: "Boss Fight Integration",   what: "Full integration test — depends on TC-021 / 022 / 024",           effort: "~0.5 day after blockers" },
    { id: "TC-020", title: "Packed / Zoned Binary",    what: "UDF stub + byte-level decode logic (intentionally hard)",         effort: "~2 days" },
  ];

  const startY = 1.85;
  const rowH = 0.85;
  const rowGap = 0.1;

  items.forEach((it, i) => {
    const y = startY + i * (rowH + rowGap);
    card(slide, 0.5, y, W - 1, rowH);
    // Orange ID badge
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y, w: 1.2, h: rowH,
      fill: { color: C.orange }, line: { color: C.orange, width: 0 },
    });
    slide.addText(it.id, {
      x: 0.5, y, w: 1.2, h: rowH,
      fontFace: FONT, fontSize: 14, bold: true, color: "0D1117",
      align: "center", valign: "middle", margin: 0,
    });
    // Title
    slide.addText(it.title, {
      x: 1.85, y: y + 0.08, w: 4.2, h: 0.4,
      fontFace: FONT, fontSize: 15, bold: true, color: C.text, margin: 0,
    });
    slide.addText(it.what, {
      x: 1.85, y: y + 0.45, w: 7.5, h: 0.4,
      fontFace: FONT, fontSize: 11, color: C.muted, margin: 0,
    });
    // Effort badge
    slide.addShape(pres.shapes.RECTANGLE, {
      x: W - 2.5, y: y + 0.18, w: 1.9, h: 0.5,
      fill: { color: "0D1117" }, line: { color: C.orange, width: 1 },
    });
    slide.addText(it.effort, {
      x: W - 2.5, y: y + 0.18, w: 1.9, h: 0.5,
      fontFace: FONT, fontSize: 12, bold: true, color: C.orange,
      align: "center", valign: "middle", margin: 0,
    });
  });

  // Bottom note
  const noteY = startY + 5 * (rowH + rowGap) + 0.05;
  slide.addText([
    { text: "Plus:  ", options: { bold: true, color: C.orange } },
    { text: "fix CLI read_strategy routing for no-delimiter decimal fields (test_cli.py)", options: { color: C.text } },
  ], {
    x: 0.5, y: noteY, w: W - 1, h: 0.4,
    fontFace: FONT, fontSize: 12, italic: true, margin: 0,
  });
}

// =========================================================================
// SLIDE 13 — BLOCKERS
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "Blockers — Action Required");

  const blockers = [
    {
      n: "1", sev: C.red,
      title: "Neo4j Schema Contract",
      body: "Parser team has not confirmed node labels, relationship types, or property names. IR loader is built on assumed schema — could break when real Parser output arrives.",
      action: "Parser team to share Cypher schema definition",
    },
    {
      n: "2", sev: C.red,
      title: "No Real Client Graphs",
      body: "All testing uses hand-crafted synthetic fixtures. No sanitized real Ab Initio graphs from client yet. Coverage gaps may be hidden.",
      action: "Client Network team to provide 5–10 sanitized graph examples",
    },
    {
      n: "3", sev: C.yellow,
      title: "LLM Model Uncertainty",
      body: "Which model is available on IBM-side infra not confirmed (qwen2.5-coder vs codellama vs deepseek-coder). Prompts and fallback logic may need tuning per model.",
      action: "IBM infra team to confirm available model + endpoint",
    },
    {
      n: "4", sev: C.yellow,
      title: "V1 Coverage Target Not Signed Off",
      body: "Proposed target: ≥90% deterministic, <10% LLM fallback. Not formally agreed with stakeholders. Without this, \"done\" has no definition.",
      action: "Stakeholder sign-off needed",
    },
  ];

  const gridY = 1.85;
  const gridGap = 0.2;
  const cw = (W - 1 - gridGap) / 2;
  const ch = 2.4;

  blockers.forEach((b, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.5 + col * (cw + gridGap);
    const y = gridY + row * (ch + gridGap);

    card(slide, x, y, cw, ch);
    // Severity bar
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: cw, h: 0.06,
      fill: { color: b.sev }, line: { color: b.sev, width: 0 },
    });
    // Number badge
    slide.addShape(pres.shapes.OVAL, {
      x: x + 0.25, y: y + 0.25, w: 0.6, h: 0.6,
      fill: { color: b.sev }, line: { color: b.sev, width: 0 },
    });
    slide.addText(b.n, {
      x: x + 0.25, y: y + 0.25, w: 0.6, h: 0.6,
      fontFace: FONT, fontSize: 20, bold: true, color: "0D1117",
      align: "center", valign: "middle", margin: 0,
    });
    slide.addText(b.title, {
      x: x + 1.0, y: y + 0.3, w: cw - 1.15, h: 0.5,
      fontFace: FONT, fontSize: 16, bold: true, color: C.text, margin: 0,
    });
    slide.addText(b.body, {
      x: x + 0.25, y: y + 0.95, w: cw - 0.4, h: 1.0,
      fontFace: FONT, fontSize: 11, color: C.muted, margin: 0,
    });
    // Action footer
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: y + ch - 0.45, w: cw, h: 0.45,
      fill: { color: "0D1117" }, line: { color: C.cardBorder, width: 0 },
    });
    slide.addText([
      { text: "Action:  ", options: { bold: true, color: b.sev } },
      { text: b.action, options: { color: C.text } },
    ], {
      x: x + 0.25, y: y + ch - 0.45, w: cw - 0.4, h: 0.45,
      fontFace: FONT, fontSize: 11, valign: "middle", margin: 0,
    });
  });
}

// =========================================================================
// SLIDE 14 — PHASE STATUS
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "Development Phases: Where We Are");

  const phases = [
    { p: "Phase 0", st: "DONE",        c: C.green,  t: "Scaffolding",         d: "pyproject.toml, docker-compose, Makefile, README" },
    { p: "Phase 1", st: "DONE",        c: C.green,  t: "IR + Neo4j Loader",   d: "Pydantic IR models, Cypher queries, fixture seeding" },
    { p: "Phase 2", st: "DONE",        c: C.green,  t: "DML Convertor",       d: "Lark grammar, Earley parser, AST, StructType emitter" },
    { p: "Phase 3", st: "DONE",        c: C.green,  t: "Mapping Engine",      d: "6 component rules, transform expression parser (Lark)" },
    { p: "Phase 4", st: "DONE",        c: C.green,  t: "Code Generator",      d: "Jinja2 templates, Ollama LLM client, synthesizer" },
    { p: "Phase 5", st: "DONE",        c: C.green,  t: "CLI + E2E Glue",      d: "ibm-net convert command, E2E test, spark-submit verify" },
    { p: "Phase 6", st: "IN PROGRESS", c: C.yellow, t: "Validation & Iteration", d: "DML fixture corpus, coverage matrix — 5 items remaining" },
    { p: "Phase 7", st: "NOT STARTED", c: C.muted,  t: "Documentation & Handoff", d: "Per-component mapping reference, runbook, troubleshooting" },
  ];

  const startY = 1.85;
  const rowH = 0.5;
  const rowGap = 0.05;

  phases.forEach((ph, i) => {
    const y = startY + i * (rowH + rowGap);
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y, w: W - 1, h: rowH,
      fill: { color: i % 2 === 0 ? C.card : "12181F" }, line: { color: C.cardBorder, width: 0 },
    });
    // Status pill
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y: y + 0.1, w: 0.08, h: rowH - 0.2,
      fill: { color: ph.c }, line: { color: ph.c, width: 0 },
    });
    slide.addText(ph.p, {
      x: 0.85, y, w: 1.1, h: rowH,
      fontFace: FONT, fontSize: 13, bold: true, color: C.text,
      valign: "middle", margin: 0,
    });
    slide.addText(ph.st, {
      x: 2.0, y, w: 1.5, h: rowH,
      fontFace: FONT, fontSize: 11, bold: true, color: ph.c,
      valign: "middle", charSpacing: 2, margin: 0,
    });
    slide.addText(ph.t, {
      x: 3.55, y, w: 3.2, h: rowH,
      fontFace: FONT, fontSize: 13, color: C.text,
      valign: "middle", margin: 0,
    });
    slide.addText(ph.d, {
      x: 6.8, y, w: W - 7.3, h: rowH,
      fontFace: FONT, fontSize: 11, color: C.muted,
      valign: "middle", margin: 0,
    });
  });

  // Progress bar
  const pbY = startY + 8 * (rowH + rowGap) + 0.1;
  slide.addText("Overall progress", {
    x: 0.5, y: pbY, w: 4, h: 0.3,
    fontFace: FONT, fontSize: 11, color: C.muted, charSpacing: 2, margin: 0,
  });
  slide.addText("75%", {
    x: W - 1.5, y: pbY, w: 1, h: 0.3,
    fontFace: FONT, fontSize: 11, bold: true, color: C.orange,
    align: "right", margin: 0,
  });
  // Track
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: pbY + 0.32, w: W - 1, h: 0.18,
    fill: { color: "1F2937" }, line: { color: "1F2937", width: 0 },
  });
  // Fill (75%)
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: pbY + 0.32, w: (W - 1) * 0.75, h: 0.18,
    fill: { color: C.orange }, line: { color: C.orange, width: 0 },
  });
}

// =========================================================================
// SLIDE 15 — NEXT STEPS
// =========================================================================
{
  const slide = pres.addSlide();
  chrome(slide);
  pageTitle(slide, "Next Steps", "To reach 99/99 and hand off to production");

  const cols = [
    {
      title: "This Sprint",
      color: C.orange,
      items: [
        "Implement include resolver (TC-021)",
        "Implement type aliases (TC-022)",
        "Fix EBCDIC grammar (TC-024)",
        "Run boss fight integration (TC-025)",
      ],
    },
    {
      title: "Needs External Input",
      color: C.yellow,
      items: [
        "Parser team: Neo4j schema contract",
        "Client team: real sanitized graph samples",
        "IBM infra: confirm LLM model + endpoint",
        "Stakeholders: sign off V1 coverage target",
      ],
    },
    {
      title: "After Blockers Resolved",
      color: C.green,
      items: [
        "Validate against real client graphs",
        "Tune LLM prompts for confirmed model",
        "Write Phase 7 documentation",
        "Plan V2 component scope (SCAN, NORMALIZE, etc.)",
      ],
    },
  ];

  const colY = 1.95;
  const colH = 3.6;
  const colGap = 0.25;
  const cw = (W - 1 - 2 * colGap) / 3;

  cols.forEach((c, i) => {
    const x = 0.5 + i * (cw + colGap);
    card(slide, x, colY, cw, colH);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: colY, w: cw, h: 0.08,
      fill: { color: c.color }, line: { color: c.color, width: 0 },
    });
    slide.addText(c.title, {
      x: x + 0.2, y: colY + 0.25, w: cw - 0.4, h: 0.5,
      fontFace: FONT, fontSize: 17, bold: true, color: c.color, margin: 0,
    });
    slide.addShape(pres.shapes.LINE, {
      x: x + 0.2, y: colY + 0.78, w: 0.8, h: 0,
      line: { color: C.cardBorder, width: 1 },
    });
    slide.addText(c.items.map((it, j) => ({
      text: it, options: { bullet: true, breakLine: j < c.items.length - 1 },
    })), {
      x: x + 0.3, y: colY + 0.95, w: cw - 0.45, h: colH - 1.1,
      fontFace: FONT, fontSize: 12, color: C.text, paraSpaceAfter: 8,
    });
  });

  // Bottom CTA
  const ctaY = colY + colH + 0.25;
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: ctaY, w: W - 1, h: 0.85,
    fill: { color: C.orange }, line: { color: C.orange, width: 0 },
    shadow: cardShadow(),
  });
  slide.addText("The core pipeline is production-capable. Unblocking the 4 open items will take us to 99/99 and Phase 7 handoff.", {
    x: 0.5, y: ctaY, w: W - 1, h: 0.85,
    fontFace: FONT, fontSize: 16, bold: true, color: "0D1117",
    align: "center", valign: "middle", margin: 0,
  });
}

// ---- Save ----
pres.writeFile({ fileName: "/Users/utkarshsingh/Desktop/AbInitio-PySpark-Presentation.pptx" })
  .then((fn) => console.log("Saved:", fn))
  .catch((e) => { console.error(e); process.exit(1); });
