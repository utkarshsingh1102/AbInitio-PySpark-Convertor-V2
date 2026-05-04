"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { FileUpload } from "@/components/FileUpload";
import { uploadFiles, parse, store } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConvert() {
    if (!files.length) return;
    setBusy(true);
    setError(null);
    try {
      setStatus("Uploading…");
      const { job_id } = await uploadFiles(files);
      setStatus("Parsing…");
      await parse(job_id);
      setStatus("Storing in Neo4j…");
      const { pipeline_id } = await store(job_id);
      setStatus("Done");
      router.push(`/results/${pipeline_id}`);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen">
      <div className="max-w-3xl mx-auto px-6 pt-20 pb-16">
        <div className="mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-coral-50 border border-coral-200 text-coral-700 text-xs font-medium mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-coral-500" />
            Ab Initio Conversion Platform
          </div>
          <h1 className="text-5xl font-serif tracking-tight text-ink-800 leading-[1.05]">
            Migrate Ab Initio graphs<br />
            to production <span className="text-coral-600">PySpark</span>.
          </h1>
          <p className="text-ink-400 mt-5 text-lg leading-relaxed max-w-xl">
            Upload your <code className="text-ink-600 bg-cream-300 px-1.5 py-0.5 rounded text-sm">.mp</code>,{" "}
            <code className="text-ink-600 bg-cream-300 px-1.5 py-0.5 rounded text-sm">.dml</code>, and{" "}
            <code className="text-ink-600 bg-cream-300 px-1.5 py-0.5 rounded text-sm">.xfr</code> files.
            We parse them into a Neo4j DAG, build an IR, run a 16-rule optimizer, and emit
            idiomatic PySpark + a KSH wrapper.
          </p>
        </div>

        <FileUpload onFiles={setFiles} disabled={busy} />

        <div className="mt-8 flex items-center gap-4">
          <button
            disabled={busy || files.length === 0}
            onClick={handleConvert}
            className="px-6 py-3 rounded-xl bg-coral-500 hover:bg-coral-600 disabled:bg-cream-400 disabled:text-ink-300 disabled:cursor-not-allowed text-white font-medium shadow-soft transition active:scale-[0.98]"
          >
            {busy ? "Converting…" : "Convert"}
          </button>
          {status && (
            <span className="text-sm text-ink-400 flex items-center gap-2">
              {busy && <span className="w-1.5 h-1.5 rounded-full bg-coral-500 animate-pulse" />}
              {status}
            </span>
          )}
        </div>

        {error && (
          <div className="mt-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm whitespace-pre-wrap">
            {error}
          </div>
        )}

        <footer className="mt-24 pt-8 border-t border-cream-400 text-xs text-ink-400 space-y-1">
          <p>Backend: FastAPI · Neo4j · PySpark 3.5</p>
          <p>Frontend: Next.js 14 · React Flow · Tailwind</p>
        </footer>
      </div>
    </main>
  );
}
