const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type ParsedAst = {
  job_id: string;
  mp: { pipeline: { name: string }; nodes: any[]; edges: any[] };
  schema: any;
  transform: any;
};

export type DAG = {
  nodes: {
    id: string;
    name: string;
    type: string;
    properties: any;
    schema: any;
    schema_name?: string;
    input_ports?: Record<string, { node: string; port: string }>;
    output_ports?: string[];
  }[];
  edges: { from: string; to: string; from_port?: string; to_port?: string }[];
  params?: Record<string, string>;
  pipeline_name?: string;
};

export type ReportEntry = {
  rule: string;
  nodes_affected?: string[];
  description?: string;
  severity?: "info" | "warn" | "error";
};

export type OptimizationReport = {
  pipeline_id: string;
  rules_applied: ReportEntry[];
  warnings: ReportEntry[];
  unresolved: ReportEntry[];
};

export type GenResult = {
  pipeline_id: string;
  pyspark: string;
  ksh: string;
  report?: OptimizationReport;
};

export async function uploadFiles(files: File[]): Promise<{ job_id: string; files: string[] }> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const r = await fetch(`${API}/upload`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function parse(job_id: string): Promise<ParsedAst> {
  const r = await fetch(`${API}/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function store(job_id: string): Promise<{ pipeline_id: string }> {
  const r = await fetch(`${API}/store`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getGraph(pipeline_id: string): Promise<DAG> {
  const r = await fetch(`${API}/graph/${pipeline_id}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getOrder(pipeline_id: string): Promise<{ order: any[] }> {
  const r = await fetch(`${API}/graph/${pipeline_id}/order`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function generateCode(pipeline_id: string): Promise<GenResult> {
  const r = await fetch(`${API}/generate-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pipeline_id }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function downloadUrl(pipeline_id: string): string {
  return `${API}/download/${pipeline_id}`;
}

export async function getReport(pipeline_id: string): Promise<OptimizationReport> {
  const r = await fetch(`${API}/optimize-report/${pipeline_id}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function seedTestData(pipeline_id: string): Promise<{ created: string[] }> {
  const r = await fetch(`${API}/seed-test-data/${pipeline_id}`, { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export type DmlSchemaResult = {
  name: string;
  fields: any[];
  struct_code: string;
  recommended_format: { name: string; reason: string };
  alternatives: { name: string; reason: string }[];
  feature_flags: Record<string, boolean>;
  pyspark_code: string;
};

export type VisualizeStageNote = { label: string; detail: string };
export type VisualizeToken = { kind: string; value: string };
export type VisualizeSchemaView = {
  name: string;
  fields: any[];
  layout: string | null;
  record_length: number | null;
  struct_code: string;
};
export type VisualizeResponse = {
  source_raw: string;
  after_comments: string;
  after_macros: string;
  after_interpolate: string;
  stage1_notes: VisualizeStageNote[];
  tokens: VisualizeToken[];
  schemas: VisualizeSchemaView[];
};

export async function visualizeDml(
  dml: string,
  params?: Record<string, string>,
): Promise<VisualizeResponse> {
  const r = await fetch(`${API}/dml/visualize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dml, params: params ?? null }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function convertDml(dml: string): Promise<{ schemas: DmlSchemaResult[] }> {
  const r = await fetch(`${API}/dml/convert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dml }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function executeStream(
  pipeline_id: string,
  onLine: (line: string) => void,
  onDone: (exitCode: number) => void
): () => void {
  // SSE from POST is non-trivial; use the EventSource endpoint exposed.
  // (The backend accepts POST; for SSE we wrap it via fetch + reader.)
  const ctrl = new AbortController();
  fetch(`${API}/execute/${pipeline_id}`, { method: "POST", signal: ctrl.signal })
    .then(async (r) => {
      if (!r.body) return;
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const block of parts) {
          const data = block.split("\n").find((l) => l.startsWith("data:"));
          if (!data) continue;
          const line = data.slice(5).trim();
          const m = line.match(/^__exit__:(\d+)$/);
          if (m) onDone(parseInt(m[1], 10));
          else onLine(line);
        }
      }
    })
    .catch(() => {});
  return () => ctrl.abort();
}
