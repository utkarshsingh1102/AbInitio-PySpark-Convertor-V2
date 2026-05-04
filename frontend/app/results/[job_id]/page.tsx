"use client";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useParams } from "next/navigation";
import { DAGViewer } from "@/components/DAGViewer";
import { CodePreview } from "@/components/CodePreview";
import { DAG, OptimizationReport, downloadUrl, executeStream, generateCode, getGraph, getOrder, seedTestData } from "@/lib/api";

export default function ResultsPage() {
  const { job_id } = useParams<{ job_id: string }>();
  const [dag, setDag] = useState<DAG | null>(null);
  const [order, setOrder] = useState<any[] | null>(null);
  const [pyCode, setPyCode] = useState("");
  const [kshCode, setKshCode] = useState("");
  const [report, setReport] = useState<OptimizationReport | null>(null);
  const [tab, setTab] = useState<"py" | "ksh">("py");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!job_id) return;
    (async () => {
      try {
        const [g, o, gen] = await Promise.all([
          getGraph(job_id),
          getOrder(job_id),
          generateCode(job_id),
        ]);
        setDag(g);
        setOrder(o.order);
        setPyCode(gen.pyspark);
        setKshCode(gen.ksh);
        if (gen.report) setReport(gen.report);
      } catch (e: any) {
        setError(e.message || String(e));
      }
    })();
  }, [job_id]);

  function runPipeline() {
    if (!job_id || running) return;
    setRunning(true);
    cancelRef.current = executeStream(
      job_id,
      () => {},
      () => setRunning(false),
    );
  }

  async function seedAndRun() {
    if (!job_id || running) return;
    setRunning(true);
    try {
      await seedTestData(job_id);
    } catch (e: any) {
      setError(`Seed failed: ${e.message ?? e}`);
      setRunning(false);
      return;
    }
    cancelRef.current = executeStream(
      job_id,
      () => {},
      () => setRunning(false)
    );
  }

  return (
    <main className="min-h-screen">
      <div className="max-w-7xl mx-auto px-6 py-10 space-y-8">
        <header className="flex flex-wrap items-end justify-between gap-4 pb-6 border-b border-cream-400">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-coral-50 border border-coral-200 text-coral-700 text-xs font-medium mb-3">
              <span className="w-1.5 h-1.5 rounded-full bg-coral-500" />
              {dag?.pipeline_name || "Pipeline"}
            </div>
            <h1 className="text-3xl font-serif tracking-tight text-ink-800">
              {job_id}
            </h1>
            <p className="text-ink-400 text-sm mt-1">
              DAG sourced from Neo4j · Generated PySpark + KSH
            </p>
          </div>
          <div className="flex items-center gap-2">
            <a
              href={job_id ? downloadUrl(job_id) : "#"}
              className="px-4 py-2 rounded-lg bg-white hover:bg-cream-200 border border-cream-400 text-ink-700 text-sm font-medium transition shadow-card"
            >
              Download zip
            </a>
            <button
              onClick={seedAndRun}
              disabled={running}
              className="px-4 py-2 rounded-lg bg-white hover:bg-cream-200 border border-cream-400 text-ink-700 text-sm font-medium disabled:opacity-50 transition shadow-card"
              title="Create dummy CSVs at the input paths the pipeline expects, then run"
            >
              {running ? "Running…" : "Seed + Run"}
            </button>
            <button
              onClick={runPipeline}
              disabled={running}
              className="px-4 py-2 rounded-lg bg-coral-500 hover:bg-coral-600 disabled:bg-cream-400 disabled:text-ink-300 text-white text-sm font-medium shadow-soft transition active:scale-[0.98]"
            >
              {running ? "Running…" : "Run pipeline"}
            </button>
          </div>
        </header>

        {error && (
          <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm">
            {error}
          </div>
        )}

        <section className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
          <div>
            <h2 className="text-sm uppercase tracking-wider text-ink-400 font-medium mb-3">Graph</h2>
            {dag ? <DAGViewer dag={dag} /> : <Skeleton h={500} />}
          </div>
          <div className="h-[500px] flex flex-col gap-5">
            <div className="flex-1 min-h-0 flex flex-col">
              <h2 className="text-sm uppercase tracking-wider text-ink-400 font-medium mb-3 shrink-0">Execution order</h2>
              <ol className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-1.5 text-sm">
                {(order ?? []).map((n, i) => (
                  <li
                    key={n.id}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white border border-cream-400 shadow-card"
                  >
                    <span className="text-ink-300 w-8 shrink-0 font-mono text-xs">#{i + 1}</span>
                    <span className="font-medium text-ink-700 truncate">{n.name}</span>
                    <span className="ml-auto text-xs text-ink-400 shrink-0">{n.type}</span>
                  </li>
                ))}
                {!order && <Skeleton h={120} />}
              </ol>
            </div>
            {dag && dag.params && Object.keys(dag.params).length > 0 && (
              <div className="shrink-0">
                <h2 className="text-sm uppercase tracking-wider text-ink-400 font-medium mb-3">Parameters</h2>
                <dl className="text-xs space-y-1 bg-white border border-cream-400 rounded-lg p-3 max-h-32 overflow-y-auto shadow-card">
                  {Object.entries(dag.params).map(([k, v]) => (
                    <div key={k} className="flex gap-2 font-mono">
                      <dt className="text-coral-600 shrink-0">${'{'}{k}{'}'}</dt>
                      <dd className="text-ink-500 truncate">= {v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
          </div>
        </section>

        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm uppercase tracking-wider text-ink-400 font-medium">Generated code</h2>
            <div className="flex gap-1.5 p-1 rounded-lg bg-cream-200 border border-cream-400">
              <TabBtn active={tab === "py"}  onClick={() => setTab("py")}>pipeline.py</TabBtn>
              <TabBtn active={tab === "ksh"} onClick={() => setTab("ksh")}>pipeline.ksh</TabBtn>
            </div>
          </div>
          {tab === "py" ? (
            pyCode ? <CodePreview code={pyCode} language="python" /> : <Skeleton h={400} />
          ) : (
            kshCode ? <CodePreview code={kshCode} language="bash" /> : <Skeleton h={400} />
          )}
        </section>

        {report && (
          <section>
            <h2 className="text-sm uppercase tracking-wider text-ink-400 font-medium mb-3">Optimizer report</h2>
            <ReportPanel report={report} />
          </section>
        )}
      </div>
    </main>
  );
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={[
        "px-3 py-1 rounded-md text-sm transition",
        active
          ? "bg-white text-ink-700 font-medium shadow-card"
          : "text-ink-400 hover:text-ink-700",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function Skeleton({ h }: { h: number }) {
  return <div className="rounded-xl bg-cream-300 animate-pulse" style={{ height: h }} />;
}

// What each rule actually does — surfaced on hover.
const RULE_DOCS: Record<string, string> = {
  EarlyFilterPushdown:
    "Moves Filter nodes upstream past projection-only Reformats so less data flows into joins/aggregations. Bails when the filter touches a redefined column, or when the upstream is a Join/Aggregate.",
  ProjectionPruning:
    "Walks the DAG backward from sinks, computes per-Read required column sets, then emits .select(only-the-cols-we-need) right after each read. Reduces shuffle volume and memory.",
  CollapseConsecutiveTransforms:
    "Merges adjacent Reformat nodes (when the upstream has fan_out=1) into a single transform — fewer plan nodes for Catalyst to optimise on long pipelines.",
  JoinStrategyAnnotation:
    "Picks a join strategy and tags the Join node: dimension-sized inputs trigger F.broadcast(...); fact↔fact joins fall through to sort-merge; explicit skew_keys triggers SKEW hint.",
  FanOutCacheAnnotation:
    "Tags any node with out-degree > 1 for caching so Spark doesn't recompute the lineage once per consumer. Storage level chosen by W3 (StorageLevelSelection).",
  EliminatePassthroughNodes:
    "After identity stripping, if a Reformat has zero remaining assignments it's tagged passthrough — codegen emits a single df_X = df_Y alias instead of any transformation code.",
  StripIdentityAssignments:
    "Removes out.col = in.col and out.col = `col` no-ops. Each one would have produced a redundant withColumn that adds a Catalyst plan node without changing data.",
  FixDateTimeExpressions:
    "Replaces broken-by-locale patterns on date/timestamp columns: SUBSTRING(d,1,7) → DATE_FORMAT(d,'yyyy-MM'), SUBSTRING(d,1,4) → YEAR(d), strips meaningless UPPER/TRIM on date cols.",
  TypeNullLiterals:
    "Replaces F.expr(\"NULL\") with F.lit(None).cast(<schema_type>). Untyped NullType columns can't be written to Parquet/Delta — would fail at runtime.",
  RewriteUDFsToNativeFunctions:
    "Maps Ab-Initio-style helpers (string_length, to_upper, is_null, …) to native Spark functions (LENGTH, UPPER, IS NULL). Native fns let Catalyst optimise and Tungsten generate code; UDFs are black boxes.",
  NullSafeComparisonRewrite:
    "Inside Filter conditions on nullable columns, rewrites `col = literal` to `(col IS NOT NULL AND col = literal)` so rows with NULL aren't silently dropped (Spark `=` returns NULL, not FALSE).",
  DeduplicateCommonSubexpressions:
    "When the same non-trivial subexpression appears 2+ times in one Reformat, extracts it into a __cse_<hash> column and rewrites references — single computation per row instead of repeated work.",
  RewriteExprToNativeAPI:
    "Translates F.expr(\"<SQL>\") strings to idiomatic native PySpark API: F.col, F.upper, F.when().otherwise(), bitwise & |, .cast(...). Avoids runtime SQL parsing per task and is far more readable.",
  CoalesceBeforeWrite:
    "Bounds the output partition count via .coalesce(N) (or .repartition for large outputs). Append-mode writes always coalesce — prevents tiny-files explosion on incremental pipelines.",
  PartitionByAnnotation:
    "Detects time-bucket columns (order_month, year, date, …) on writes and emits .partitionBy(...) for Hive-style directory layout. Skipped for high-cardinality columns.",
  StorageLevelSelection:
    "Picks a StorageLevel for each .cache()-tagged node: MEMORY_ONLY for narrow primitive schemas, MEMORY_AND_DISK_SER for wide / nested, DISK_ONLY when only writes consume the cached DF.",
  RepartitionBeforeShuffleJoin:
    "For sort-merge joins on a single key, tags both inputs with .repartition(F.col(key)) so Spark co-partitions on the join key first — collapses two independent shuffles into one.",
};


function ReportPanel({ report }: { report: OptimizationReport }) {
  const sections = [
    {
      title: "Rules applied",
      count: report.rules_applied.length,
      entries: report.rules_applied,
      accent: "emerald",
    },
    {
      title: "Warnings",
      count: report.warnings.length,
      entries: report.warnings,
      accent: "amber",
    },
    {
      title: "Unresolved",
      count: report.unresolved.length,
      entries: report.unresolved,
      accent: "red",
    },
  ] as const;

  const ACCENT_BG = {
    emerald: "bg-emerald-500",
    amber:   "bg-amber-500",
    red:     "bg-red-500",
  };
  const ACCENT_TEXT = {
    emerald: "text-emerald-700",
    amber:   "text-amber-700",
    red:     "text-red-700",
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {sections.map((s) => (
        <div
          key={s.title}
          className="rounded-xl bg-white border border-cream-400 shadow-card overflow-visible"
        >
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-cream-300">
            <div className="flex items-center gap-2">
              <span className={`w-1.5 h-1.5 rounded-full ${ACCENT_BG[s.accent]}`} />
              <h3 className="text-sm font-medium text-ink-700">{s.title}</h3>
            </div>
            <span className={`text-xs font-mono ${ACCENT_TEXT[s.accent]}`}>{s.count}</span>
          </div>
          <div className="px-5 py-2 h-[420px] overflow-y-auto">
            {s.entries.length === 0 ? (
              <p className="text-sm text-ink-300 py-3">— none —</p>
            ) : (
              <ul className="divide-y divide-cream-300">
                {s.entries.map((e, i) => (
                  <li key={i} className="py-4 first:pt-3 last:pb-3">
                    <RuleEntry entry={e} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}


function RuleEntry({ entry }: { entry: { rule: string; description?: string; nodes_affected?: string[] } }) {
  const docs = RULE_DOCS[entry.rule];
  const ref = useRef<HTMLSpanElement | null>(null);
  const [pos, setPos] = useState<{ x: number; y: number; flip: boolean } | null>(null);

  function show() {
    if (!ref.current || !docs) return;
    const r = ref.current.getBoundingClientRect();
    const TOOLTIP_W = 288;
    const TOOLTIP_H = 140;
    // Default: below the rule name. Flip above if it would clip the viewport.
    const wantBelow = r.bottom + 8 + TOOLTIP_H < window.innerHeight - 12;
    const left = Math.min(r.left, window.innerWidth - TOOLTIP_W - 12);
    const top = wantBelow ? r.bottom + 8 : r.top - TOOLTIP_H - 8;
    setPos({ x: Math.max(12, left), y: top, flip: !wantBelow });
  }

  function hide() { setPos(null); }

  // Hide tooltip when the page scrolls (avoids stale position)
  useEffect(() => {
    if (!pos) return;
    const onScroll = () => hide();
    window.addEventListener("scroll", onScroll, true);
    return () => window.removeEventListener("scroll", onScroll, true);
  }, [pos]);

  return (
    <div className="text-xs">
      <span
        ref={ref}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        tabIndex={docs ? 0 : -1}
        className={[
          "font-mono font-medium text-ink-700",
          docs ? "border-b border-dotted border-ink-300 cursor-help outline-none focus:border-coral-500" : "",
        ].join(" ")}
      >
        {entry.rule}
      </span>
      {entry.description && (
        <p className="text-ink-500 mt-2 leading-relaxed">{entry.description}</p>
      )}
      {entry.nodes_affected && entry.nodes_affected.length > 0 && (
        <p className="text-ink-300 mt-2.5 font-mono text-[11px]">
          on: {entry.nodes_affected.join(", ")}
        </p>
      )}
      {pos && docs && typeof window !== "undefined" &&
        createPortal(
          <div
            role="tooltip"
            style={{ left: pos.x, top: pos.y }}
            className="
              fixed z-50 w-72 rounded-lg bg-ink-700 text-cream-100
              text-[11px] leading-relaxed p-3 shadow-xl pointer-events-none
              animate-in fade-in slide-in-from-top-1 duration-150
            "
          >
            {docs}
            <span
              className={[
                "absolute left-4 w-2 h-2 rotate-45 bg-ink-700",
                pos.flip ? "-bottom-1" : "-top-1",
              ].join(" ")}
            />
          </div>,
          document.body,
        )}
    </div>
  );
}
