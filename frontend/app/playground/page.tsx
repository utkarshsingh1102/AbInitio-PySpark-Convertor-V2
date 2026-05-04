"use client";
import { useEffect, useState } from "react";
import { CodePreview } from "@/components/CodePreview";
import { convertDml, type DmlSchemaResult } from "@/lib/api";

const EXAMPLE = `DEFINE customer
BEGIN
    id        decimal(10)   NOT NULL;
    name      string(40)    NULL;
    address   record
                  street    string(50)  NULL;
                  city      string(30)  NULL;
                  zip       string(10)  NOT NULL;
              end           NOT NULL;
    signup    datetime      NULL;
END

DEFINE plain_csv
BEGIN
    a string(20) NULL;
    b string(40) NULL;
END
`;

const FORMAT_TINT: Record<string, { bg: string; fg: string; ring: string }> = {
  parquet:      { bg: "bg-blue-50",   fg: "text-blue-700",   ring: "ring-blue-200" },
  avro:         { bg: "bg-violet-50", fg: "text-violet-700", ring: "ring-violet-200" },
  json:         { bg: "bg-emerald-50",fg: "text-emerald-700",ring: "ring-emerald-200" },
  csv:          { bg: "bg-amber-50",  fg: "text-amber-800",  ring: "ring-amber-200" },
  fixed_width:  { bg: "bg-slate-100", fg: "text-slate-700",  ring: "ring-slate-300" },
  ebcdic_cobol: { bg: "bg-rose-50",   fg: "text-rose-700",   ring: "ring-rose-200" },
};

const FLAG_LABELS: Record<string, string> = {
  has_nested_struct:    "nested struct",
  has_array:            "array",
  has_array_of_struct:  "array of struct",
  has_decimal:          "decimal",
  has_date_or_time:     "date / time",
  has_only_strings:     "all strings",
  deep_nesting:         "deep nesting",
  has_delimited_fields: "delimited",
  has_fixed_layout:     "fixed-width",
  has_ebcdic:           "ebcdic",
  has_packed_decimal:   "packed decimal",
};

export default function PlaygroundPage() {
  const [dml, setDml] = useState<string>(EXAMPLE);
  const [results, setResults] = useState<DmlSchemaResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // The Schema → DML page can hand off DML via sessionStorage (set when the
  // user clicks "open in DML Playground"). We read it once on mount and
  // clear so re-visits don't keep replacing manually-pasted text.
  useEffect(() => {
    try {
      const prefill = sessionStorage.getItem("playground_prefill");
      if (prefill) {
        setDml(prefill);
        sessionStorage.removeItem("playground_prefill");
      }
    } catch {}
  }, []);

  async function onConvert() {
    setBusy(true);
    setErr(null);
    setResults(null);
    try {
      const r = await convertDml(dml);
      setResults(r.schemas);
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function loadExample() {
    setDml(EXAMPLE);
    setResults(null);
    setErr(null);
  }

  return (
    <main className="min-h-[calc(100vh-3.5rem)]">
      <div className="max-w-6xl mx-auto px-6 py-10">
        {/* Header */}
        <div className="mb-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-coral-50 border border-coral-200 text-coral-700 text-xs font-medium mb-4">
            <span className="w-1.5 h-1.5 rounded-full bg-coral-500" />
            DML Playground
          </div>
          <h1 className="text-3xl font-serif tracking-tight text-ink-800 leading-tight">
            Translate Ab Initio DML schemas to <span className="text-coral-600">PySpark I/O</span>.
          </h1>
          <p className="text-ink-400 mt-3 text-sm leading-relaxed max-w-2xl">
            Paste one or more <code className="text-ink-600 bg-cream-300 px-1.5 py-0.5 rounded text-xs">DEFINE … BEGIN … END</code> blocks.
            We classify each schema, pick the best file format, and emit a
            complete read-and-write PySpark snippet against assumed paths.
          </p>
        </div>

        {/* Editor + button */}
        <div className="rounded-2xl border border-cream-400 bg-white shadow-card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-cream-300 bg-cream-50">
            <span className="text-xs font-mono uppercase tracking-wider text-ink-400">
              schema.dml
            </span>
            <button
              onClick={loadExample}
              className="text-xs text-ink-400 hover:text-coral-600 transition"
            >
              load example
            </button>
          </div>
          <textarea
            value={dml}
            onChange={(e) => setDml(e.target.value)}
            spellCheck={false}
            className="block w-full h-[280px] p-4 font-mono text-[13px] leading-[1.6] text-ink-700 bg-white outline-none resize-y"
            placeholder="DEFINE my_record BEGIN ... END"
          />
        </div>

        <div className="mt-5 flex items-center gap-4">
          <button
            disabled={busy || !dml.trim()}
            onClick={onConvert}
            className="px-6 py-3 rounded-xl bg-coral-500 hover:bg-coral-600 disabled:bg-cream-400 disabled:text-ink-300 disabled:cursor-not-allowed text-white font-medium shadow-soft transition active:scale-[0.98]"
          >
            {busy ? "Converting…" : "Convert"}
          </button>
          {results && (
            <span className="text-sm text-ink-400">
              {results.length} schema{results.length === 1 ? "" : "s"} parsed
            </span>
          )}
        </div>

        {err && (
          <div className="mt-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm whitespace-pre-wrap">
            {err}
          </div>
        )}

        {/* Results */}
        {results && results.length > 0 && (
          <div className="mt-10 space-y-10">
            {results.map((s) => (
              <SchemaCard key={s.name} schema={s} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

function SchemaCard({ schema }: { schema: DmlSchemaResult }) {
  const tint = FORMAT_TINT[schema.recommended_format.name] || FORMAT_TINT.parquet;
  const activeFlags = Object.entries(schema.feature_flags)
    .filter(([, v]) => v)
    .map(([k]) => FLAG_LABELS[k] ?? k);

  return (
    <section className="rounded-2xl border border-cream-400 bg-white shadow-card overflow-hidden">
      {/* Header strip */}
      <div className="px-5 py-4 border-b border-cream-300 bg-cream-50 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.08em] font-medium text-ink-400 mb-1">
            DEFINE
          </div>
          <h2 className="text-xl font-serif text-ink-800">{schema.name}</h2>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {activeFlags.length > 0 ? (
              activeFlags.map((f) => (
                <span
                  key={f}
                  className="text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded bg-cream-200 text-ink-500"
                >
                  {f}
                </span>
              ))
            ) : (
              <span className="text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded bg-cream-200 text-ink-400">
                flat
              </span>
            )}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-[0.08em] font-medium text-ink-400 mb-1">
            recommended
          </div>
          <span
            className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-mono ring-1 ${tint.bg} ${tint.fg} ${tint.ring}`}
          >
            {schema.recommended_format.name}
          </span>
          <p className="mt-2 text-xs text-ink-500 max-w-xs leading-relaxed">
            {schema.recommended_format.reason}
          </p>
        </div>
      </div>

      {/* Body */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-0">
        {/* Field list */}
        <div className="lg:col-span-1 p-5 border-b lg:border-b-0 lg:border-r border-cream-300">
          <div className="text-[10px] uppercase tracking-[0.08em] font-medium text-ink-400 mb-3">
            fields
          </div>
          <FieldTree fields={schema.fields} />
          {schema.alternatives.length > 0 && (
            <div className="mt-6">
              <div className="text-[10px] uppercase tracking-[0.08em] font-medium text-ink-400 mb-2">
                alternatives
              </div>
              <div className="flex flex-wrap gap-1.5">
                {schema.alternatives.map((a) => (
                  <span
                    key={a.name}
                    title={a.reason}
                    className="text-xs font-mono px-2 py-0.5 rounded bg-cream-200 text-ink-500 cursor-help"
                  >
                    {a.name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* PySpark code */}
        <div className="lg:col-span-2 p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[10px] uppercase tracking-[0.08em] font-medium text-ink-400">
              pyspark.py
            </div>
            <button
              onClick={() => navigator.clipboard.writeText(schema.pyspark_code)}
              className="text-xs text-ink-400 hover:text-coral-600 transition"
            >
              copy
            </button>
          </div>
          <CodePreview code={schema.pyspark_code} language="python" />
        </div>
      </div>
    </section>
  );
}

function FieldTree({ fields, depth = 0 }: { fields: any[]; depth?: number }) {
  return (
    <ul className={depth === 0 ? "space-y-1.5" : "space-y-1.5 mt-1.5 ml-4 border-l border-cream-300 pl-3"}>
      {fields.map((f, i) => (
        <li key={`${f.name}-${i}`} className="text-[13px] leading-snug">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="font-mono text-ink-800">{f.name}</span>
            <span className="font-mono text-[11px] text-coral-700">
              {f.type === "struct"
                ? f.array ? "struct[]" : "struct"
                : f.array ? `${f.type}[]` : f.type}
              {f.args && f.args.length > 0 ? `(${f.args.join(",")})` : ""}
            </span>
            {!f.nullable && (
              <span className="text-[9px] uppercase tracking-wider text-ink-400 font-medium">
                not null
              </span>
            )}
          </div>
          {f.type === "struct" && f.fields && (
            <FieldTree fields={f.fields} depth={depth + 1} />
          )}
        </li>
      ))}
    </ul>
  );
}
