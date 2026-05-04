"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { CodePreview } from "@/components/CodePreview";
import { visualizeDml, type VisualizeResponse } from "@/lib/api";

const EXAMPLE = `#define DELIM ","
record
  -- customer-facing record
  string(DELIM) customer_id;
  string(DELIM) name;
  decimal(10, 2) balance NOT NULL;
  date("YYYY-MM-DD") signup;
  record
    string(DELIM) street;
    string(DELIM) city;
  end address NOT NULL;
  if (type == "purchase") then
    decimal(10,2) amount;
  else
    string(DELIM) reason;
  end;
end;
`;

const STAGES = [
  {
    key: "preprocess",
    label: "Preprocess",
    short: "1",
    blurb: "Strip comments, expand #define, interpolate ${VAR}.",
  },
  {
    key: "tokenize",
    label: "Tokenize",
    short: "2",
    blurb: "Break the cleaned text into typed tokens.",
  },
  {
    key: "parse",
    label: "Parse",
    short: "3",
    blurb: "Recognise records, fields, nested blocks, conditionals.",
  },
  {
    key: "layout",
    label: "Layout",
    short: "4",
    blurb: "Compute byte offsets and lengths for fixed-width records.",
  },
  {
    key: "convert",
    label: "Convert",
    short: "5",
    blurb: "Lower the AST to a PySpark StructType.",
  },
] as const;

const TOKEN_KIND_TINT: Record<string, string> = {
  ident:    "bg-blue-50 text-blue-800 ring-blue-200",
  num:      "bg-violet-50 text-violet-800 ring-violet-200",
  dqstring: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  lparen:   "bg-amber-50 text-amber-800 ring-amber-200",
  rparen:   "bg-amber-50 text-amber-800 ring-amber-200",
  lbracket: "bg-amber-50 text-amber-800 ring-amber-200",
  rbracket: "bg-amber-50 text-amber-800 ring-amber-200",
  comma:    "bg-cream-200 text-ink-600 ring-cream-400",
  semi:     "bg-cream-200 text-ink-600 ring-cream-400",
  eq:       "bg-rose-50 text-rose-800 ring-rose-200",
  eq2:      "bg-rose-50 text-rose-800 ring-rose-200",
  neq:      "bg-rose-50 text-rose-800 ring-rose-200",
  lt:       "bg-rose-50 text-rose-800 ring-rose-200",
  gt:       "bg-rose-50 text-rose-800 ring-rose-200",
  lte:      "bg-rose-50 text-rose-800 ring-rose-200",
  gte:      "bg-rose-50 text-rose-800 ring-rose-200",
};

export default function VisualizerPage() {
  const [dml, setDml] = useState<string>(EXAMPLE);
  const [data, setData] = useState<VisualizeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [activeStage, setActiveStage] = useState<number>(0);
  const [autoplay, setAutoplay] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function onRun() {
    setBusy(true);
    setErr(null);
    setData(null);
    setActiveStage(0);
    try {
      const r = await visualizeDml(dml);
      setData(r);
      setActiveStage(0);
      setAutoplay(true);
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  // Autoplay timer — advance one stage every 2.5 s while autoplay is on.
  useEffect(() => {
    if (!autoplay || !data) return;
    if (activeStage >= STAGES.length - 1) {
      setAutoplay(false);
      return;
    }
    timerRef.current = setTimeout(() => setActiveStage((s) => s + 1), 2500);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [autoplay, activeStage, data]);

  function step(delta: number) {
    setAutoplay(false);
    setActiveStage((s) => Math.max(0, Math.min(STAGES.length - 1, s + delta)));
  }

  return (
    <main className="min-h-[calc(100vh-3.5rem)]">
      <div className="max-w-6xl mx-auto px-6 py-10">
        {/* Header */}
        <div className="mb-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-coral-50 border border-coral-200 text-coral-700 text-xs font-medium mb-4">
            <span className="w-1.5 h-1.5 rounded-full bg-coral-500" />
            Pipeline Visualizer
          </div>
          <h1 className="text-3xl font-serif tracking-tight text-ink-800 leading-tight">
            Watch DML <span className="text-coral-600">become PySpark</span>, stage by stage.
          </h1>
          <p className="text-ink-400 mt-3 text-sm leading-relaxed max-w-2xl">
            Paste a DML record, hit <em>Run</em>, and step through every parser stage —
            preprocessing, tokenization, parsing, layout analysis, and PySpark conversion —
            with the actual intermediate output of each.
          </p>
        </div>

        {/* Source editor */}
        <div className="rounded-2xl border border-cream-400 bg-white shadow-card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-cream-300 bg-cream-50">
            <span className="text-xs font-mono uppercase tracking-wider text-ink-400">
              schema.dml
            </span>
            <button
              onClick={() => { setDml(EXAMPLE); setData(null); setErr(null); }}
              className="text-xs text-ink-400 hover:text-coral-600 transition"
            >
              load example
            </button>
          </div>
          <textarea
            value={dml}
            onChange={(e) => setDml(e.target.value)}
            spellCheck={false}
            className="block w-full h-[200px] p-4 font-mono text-[12.5px] leading-[1.6] text-ink-700 bg-white outline-none resize-y"
          />
        </div>

        <div className="mt-5 flex items-center gap-4">
          <button
            disabled={busy || !dml.trim()}
            onClick={onRun}
            className="px-6 py-3 rounded-xl bg-coral-500 hover:bg-coral-600 disabled:bg-cream-400 disabled:text-ink-300 disabled:cursor-not-allowed text-white font-medium shadow-soft transition active:scale-[0.98]"
          >
            {busy ? "Parsing…" : "Run pipeline"}
          </button>

          {data && (
            <div className="flex items-center gap-2">
              <button onClick={() => step(-1)} disabled={activeStage === 0}
                className="px-3 py-2 rounded-lg border border-cream-400 text-ink-500 hover:text-coral-600 disabled:opacity-40 transition">
                ← prev
              </button>
              <button
                onClick={() => setAutoplay((p) => !p)}
                className="px-3 py-2 rounded-lg border border-cream-400 text-ink-500 hover:text-coral-600 transition"
              >
                {autoplay ? "❚❚ pause" : "▶ play"}
              </button>
              <button onClick={() => step(+1)} disabled={activeStage >= STAGES.length - 1}
                className="px-3 py-2 rounded-lg border border-cream-400 text-ink-500 hover:text-coral-600 disabled:opacity-40 transition">
                next →
              </button>
            </div>
          )}
        </div>

        {err && (
          <div className="mt-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm whitespace-pre-wrap">
            {err}
          </div>
        )}

        {/* Stepper */}
        {data && (
          <div className="mt-10">
            <div className="flex items-center gap-0">
              {STAGES.map((s, i) => {
                const active = i === activeStage;
                const done = i < activeStage;
                return (
                  <div key={s.key} className="flex items-center flex-1 last:flex-none">
                    <button
                      onClick={() => { setAutoplay(false); setActiveStage(i); }}
                      className="flex items-center gap-3 group"
                    >
                      <span
                        className={[
                          "w-9 h-9 rounded-full flex items-center justify-center text-sm font-mono transition border",
                          active
                            ? "bg-coral-500 text-white border-coral-500 shadow-soft scale-110"
                            : done
                            ? "bg-coral-50 text-coral-700 border-coral-300"
                            : "bg-cream-100 text-ink-400 border-cream-400",
                        ].join(" ")}
                      >
                        {s.short}
                      </span>
                      <span
                        className={[
                          "text-sm font-medium hidden sm:inline transition",
                          active ? "text-ink-800" : done ? "text-ink-500" : "text-ink-300",
                        ].join(" ")}
                      >
                        {s.label}
                      </span>
                    </button>
                    {i < STAGES.length - 1 && (
                      <span
                        className={[
                          "h-px flex-1 mx-3 transition",
                          done ? "bg-coral-300" : "bg-cream-400",
                        ].join(" ")}
                      />
                    )}
                  </div>
                );
              })}
            </div>

            {/* Stage caption */}
            <p className="mt-4 text-sm text-ink-500 leading-relaxed">
              <span className="font-medium text-ink-700">Stage {STAGES[activeStage].short}: {STAGES[activeStage].label}.</span>{" "}
              {STAGES[activeStage].blurb}
            </p>

            {/* Stage panel */}
            <div className="mt-6 rounded-2xl border border-cream-400 bg-white shadow-card p-6 min-h-[420px]">
              <StagePanel stageKey={STAGES[activeStage].key} data={data} />
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

function StagePanel({ stageKey, data }: { stageKey: string; data: VisualizeResponse }) {
  switch (stageKey) {
    case "preprocess": return <PreprocessPanel data={data} />;
    case "tokenize":   return <TokenizePanel data={data} />;
    case "parse":      return <ParsePanel data={data} />;
    case "layout":     return <LayoutPanel data={data} />;
    case "convert":    return <ConvertPanel data={data} />;
    default:           return null;
  }
}

// ── Stage 1 ────────────────────────────────────────────────────────────────

function PreprocessPanel({ data }: { data: VisualizeResponse }) {
  const stripped = data.source_raw !== data.after_comments;
  const expanded = data.after_comments !== data.after_macros;
  const interp   = data.after_macros !== data.after_interpolate;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 fade-in">
      <PreprocessColumn
        title="Original"
        body={data.source_raw}
        tone="muted"
      />
      <div className="space-y-3">
        <PreprocessColumn
          title="After preprocessing"
          body={data.after_interpolate || data.after_macros || data.after_comments}
          tone="clean"
        />
        <ul className="text-xs space-y-1.5">
          <PreprocessNote done={stripped} label="Comments stripped" />
          <PreprocessNote done={expanded} label="C macros (#define) expanded" />
          <PreprocessNote done={interp}   label="${VAR} interpolation" />
        </ul>
      </div>
    </div>
  );
}

function PreprocessColumn({ title, body, tone }: { title: string; body: string; tone: "muted" | "clean" }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.08em] font-medium text-ink-400 mb-2">{title}</div>
      <pre
        className={[
          "rounded-xl border p-4 font-mono text-[12px] leading-[1.6] whitespace-pre-wrap break-all overflow-auto max-h-[360px]",
          tone === "muted"
            ? "border-cream-300 bg-cream-50 text-ink-400"
            : "border-coral-200 bg-coral-50/40 text-ink-800",
        ].join(" ")}
      >
        {body || "(empty)"}
      </pre>
    </div>
  );
}

function PreprocessNote({ done, label }: { done: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2">
      <span className={`w-2 h-2 rounded-full ${done ? "bg-coral-500" : "bg-cream-400"}`} />
      <span className={done ? "text-ink-700" : "text-ink-400"}>
        {label}{done ? "" : " — no-op for this input"}
      </span>
    </li>
  );
}

// ── Stage 2 ────────────────────────────────────────────────────────────────

function TokenizePanel({ data }: { data: VisualizeResponse }) {
  return (
    <div className="fade-in">
      <div className="text-xs text-ink-500 mb-4">
        {data.tokens.length} token{data.tokens.length === 1 ? "" : "s"} produced.
        Hover any token to see its kind. Multi-character operators (<code className="font-mono text-ink-700">==</code>,{" "}
        <code className="font-mono text-ink-700">&lt;=</code>) are recognised before single ones.
      </div>
      <div className="flex flex-wrap gap-1.5 max-h-[420px] overflow-auto p-1 staggered-children">
        {data.tokens.map((t, i) => (
          <span
            key={i}
            title={t.kind}
            style={{ animationDelay: `${Math.min(i * 18, 1200)}ms` }}
            className={[
              "token-chip inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-mono ring-1",
              TOKEN_KIND_TINT[t.kind] || "bg-cream-100 text-ink-500 ring-cream-300",
            ].join(" ")}
          >
            {prettyTokenValue(t.kind, t.value)}
          </span>
        ))}
      </div>
    </div>
  );
}

function prettyTokenValue(kind: string, value: string): string {
  if (kind === "dqstring") return value;
  if (kind === "ident" || kind === "num") return value;
  return value;
}

// ── Stage 3 ────────────────────────────────────────────────────────────────

function ParsePanel({ data }: { data: VisualizeResponse }) {
  if (data.schemas.length === 0) {
    return <div className="text-ink-500 text-sm">No DEFINE/record blocks parsed.</div>;
  }
  return (
    <div className="fade-in space-y-6">
      {data.schemas.map((s) => (
        <div key={s.name}>
          <div className="text-[10px] uppercase tracking-[0.08em] font-medium text-ink-400 mb-2">
            {s.name}
          </div>
          <FieldTree fields={s.fields} />
        </div>
      ))}
    </div>
  );
}

function FieldTree({ fields, depth = 0 }: { fields: any[]; depth?: number }) {
  return (
    <ul className={depth === 0 ? "space-y-1.5 staggered-children" : "space-y-1.5 mt-1.5 ml-4 border-l border-cream-300 pl-3"}>
      {fields.map((f, i) => {
        const dims = f.array_dims ?? (f.array ? [f.array_length ?? null] : []);
        const arrSuffix = dims.map((d: any) => `[${d ?? ""}]`).join("");
        const argsTxt = f.args && f.args.length ? `(${f.args.join(",")})` : "";
        const typeStr = f.type === "struct" ? `struct${arrSuffix}` : `${f.type}${argsTxt}${arrSuffix}`;
        return (
          <li
            key={`${f.name}-${i}`}
            className="text-[13px] leading-snug node-fade"
            style={{ animationDelay: `${Math.min(i * 60, 1200)}ms` }}
          >
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="font-mono text-ink-800">{f.name}</span>
              <span className="font-mono text-[11px] text-coral-700">{typeStr}</span>
              {!f.nullable && (
                <span className="text-[9px] uppercase tracking-wider text-ink-400 font-medium">not null</span>
              )}
              {f.delimiter !== undefined && f.delimiter !== null && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700">
                  delim {JSON.stringify(f.delimiter)}
                </span>
              )}
              {f.format && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">
                  fmt {f.format}
                </span>
              )}
              {f.encoding && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-50 text-rose-700">
                  enc {f.encoding}
                </span>
              )}
              {f.condition && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-violet-50 text-violet-700">
                  if {f.condition.col} {f.condition.op} {JSON.stringify(f.condition.value)} ({f.condition.branch})
                </span>
              )}
            </div>
            {f.type === "struct" && f.fields && (
              <FieldTree fields={f.fields} depth={depth + 1} />
            )}
          </li>
        );
      })}
    </ul>
  );
}

// ── Stage 4 ────────────────────────────────────────────────────────────────

function LayoutPanel({ data }: { data: VisualizeResponse }) {
  return (
    <div className="fade-in space-y-6">
      {data.schemas.map((s) => (
        <div key={s.name}>
          <div className="flex items-baseline gap-3 mb-3">
            <div className="text-[10px] uppercase tracking-[0.08em] font-medium text-ink-400">
              {s.name}
            </div>
            <span
              className={[
                "text-[11px] font-mono px-2 py-0.5 rounded ring-1",
                s.layout === "fixed"
                  ? "bg-blue-50 text-blue-700 ring-blue-200"
                  : s.layout === "delimited"
                  ? "bg-amber-50 text-amber-800 ring-amber-200"
                  : "bg-cream-200 text-ink-500 ring-cream-400",
              ].join(" ")}
            >
              layout: {s.layout || "—"}
            </span>
            {s.record_length != null && (
              <span className="text-xs text-ink-500">
                record_length = <span className="font-mono text-ink-800">{s.record_length}</span> bytes
              </span>
            )}
          </div>

          <table className="w-full text-[12px] font-mono">
            <thead>
              <tr className="text-ink-400 text-left text-[10px] uppercase tracking-wider border-b border-cream-300">
                <th className="py-1.5 pr-3">Field</th>
                <th className="py-1.5 pr-3">Type</th>
                <th className="py-1.5 pr-3 text-right">Offset</th>
                <th className="py-1.5 pr-3 text-right">Length</th>
                <th className="py-1.5 pr-3">Notes</th>
              </tr>
            </thead>
            <tbody className="staggered-children">
              {s.fields.map((f: any, i: number) => (
                <tr
                  key={`${f.name}-${i}`}
                  className="border-b border-cream-200 last:border-0 node-fade"
                  style={{ animationDelay: `${Math.min(i * 70, 1200)}ms` }}
                >
                  <td className="py-1.5 pr-3 text-ink-800">{f.name}</td>
                  <td className="py-1.5 pr-3 text-coral-700">{f.type}</td>
                  <td className="py-1.5 pr-3 text-right text-ink-700">
                    {f.offset !== undefined ? f.offset : "—"}
                  </td>
                  <td className="py-1.5 pr-3 text-right text-ink-700">
                    {f.length !== undefined ? f.length : "—"}
                  </td>
                  <td className="py-1.5 pr-3 text-ink-400">
                    {f.delimiter ? "variable-length (delimited)" : f.type === "struct" ? "nested" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

// ── Stage 5 ────────────────────────────────────────────────────────────────

function ConvertPanel({ data }: { data: VisualizeResponse }) {
  return (
    <div className="fade-in space-y-6">
      {data.schemas.map((s) => (
        <div key={s.name}>
          <div className="flex items-baseline justify-between mb-3">
            <div className="text-[10px] uppercase tracking-[0.08em] font-medium text-ink-400">
              {s.name}
            </div>
            <button
              onClick={() => navigator.clipboard.writeText(s.struct_code)}
              className="text-xs text-ink-400 hover:text-coral-600 transition"
            >
              copy
            </button>
          </div>
          <CodePreview code={s.struct_code} language="python" />
        </div>
      ))}
    </div>
  );
}
