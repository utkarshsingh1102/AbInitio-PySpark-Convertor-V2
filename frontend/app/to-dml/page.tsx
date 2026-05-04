"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { CodePreview } from "@/components/CodePreview";
import {
  cobolToDml,
  hiveToDml,
  xmlToDml,
  type ToDmlResponse,
} from "@/lib/api";

type Format = "hive" | "cobol" | "xml" | "xsd";

const FORMAT_META: Record<Format, { label: string; placeholder: string; example: string }> = {
  hive: {
    label: "Hive CREATE TABLE",
    placeholder: "CREATE TABLE my_table (...);",
    example: `CREATE TABLE sales_data (
    transaction_id  BIGINT,
    customer_name   STRING,
    amount          DECIMAL(10,2),
    items_list      ARRAY<STRING>,
    meta_info       MAP<STRING, STRING>
)
PARTITIONED BY (year INT, month INT)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\\001';
`,
  },
  cobol: {
    label: "COBOL Copybook",
    placeholder: "01 RECORD.\n   05 FIELD ...",
    example: `01  EMPLOYEE-RECORD.
    05  EMP-ID              PIC 9(05).
    05  EMP-NAME            PIC X(20).
    05  EMP-DETAILS.
        10  EMP-DEPT        PIC X(10).
        10  EMP-SALARY      PIC S9(7)V99 COMP-3.
    05  PROJECT-COUNT       PIC 9(02).
    05  PROJECTS            OCCURS 1 TO 5 TIMES
                            DEPENDING ON PROJECT-COUNT.
        10  PROJ-ID         PIC X(04).
`,
  },
  xml: {
    label: "Sample XML document",
    placeholder: "<root>...</root>",
    example: `<Order id="101">
  <Customer>John Doe</Customer>
  <Items>
    <Product>Laptop</Product>
    <Product>Mouse</Product>
  </Items>
</Order>
`,
  },
  xsd: {
    label: "XSD schema",
    placeholder: "<xs:schema>...</xs:schema>",
    example: `<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Order">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="Customer" type="xs:string"/>
        <xs:element name="Amount">
          <xs:simpleType>
            <xs:restriction base="xs:decimal">
              <xs:totalDigits value="10"/>
              <xs:fractionDigits value="2"/>
            </xs:restriction>
          </xs:simpleType>
        </xs:element>
      </xs:sequence>
      <xs:attribute name="id" type="xs:string" use="required"/>
    </xs:complexType>
  </xs:element>
</xs:schema>
`,
  },
};

export default function SchemaToDmlPage() {
  const router = useRouter();
  const [format, setFormat] = useState<Format>("hive");
  const [source, setSource] = useState<string>(FORMAT_META.hive.example);
  const [result, setResult] = useState<ToDmlResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onConvert() {
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      let r: ToDmlResponse;
      if (format === "hive")        r = await hiveToDml(source);
      else if (format === "cobol")  r = await cobolToDml(source);
      else if (format === "xml")    r = await xmlToDml(source, "sample");
      else                          r = await xmlToDml(source, "xsd");
      setResult(r);
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function loadExample() {
    setSource(FORMAT_META[format].example);
    setResult(null);
    setErr(null);
  }

  function onFormatChange(next: Format) {
    setFormat(next);
    setSource(FORMAT_META[next].example);
    setResult(null);
    setErr(null);
  }

  function openInPlayground() {
    if (!result) return;
    // Stash the DML in sessionStorage so the Playground page can pick it up.
    try {
      sessionStorage.setItem("playground_prefill", result.dml);
    } catch {}
    router.push("/playground");
  }

  function copyDml() {
    if (!result) return;
    navigator.clipboard.writeText(result.dml);
  }

  return (
    <main className="min-h-[calc(100vh-3.5rem)]">
      <div className="max-w-6xl mx-auto px-6 py-10">
        <div className="mb-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-coral-50 border border-coral-200 text-coral-700 text-xs font-medium mb-4">
            <span className="w-1.5 h-1.5 rounded-full bg-coral-500" />
            Schema → DML
          </div>
          <h1 className="text-3xl font-serif tracking-tight text-ink-800 leading-tight">
            Convert <span className="text-coral-600">XML, COBOL, or Hive</span> schemas to Ab Initio DML.
          </h1>
          <p className="text-ink-400 mt-3 text-sm leading-relaxed max-w-2xl">
            Pick a source format, paste the schema, and we emit DML that
            round-trips through the existing parser. Use the
            <code className="text-ink-600 bg-cream-300 px-1.5 py-0.5 rounded text-xs mx-1">DML Playground</code>
            tab afterwards to get the matching <code className="text-ink-600 bg-cream-300 px-1.5 py-0.5 rounded text-xs">StructType</code> and PySpark snippet.
          </p>
        </div>

        {/* Source editor */}
        <div className="rounded-2xl border border-cream-400 bg-white shadow-card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-cream-300 bg-cream-50">
            <div className="flex items-center gap-3">
              <label className="text-xs font-mono uppercase tracking-wider text-ink-400">
                source format
              </label>
              <select
                value={format}
                onChange={(e) => onFormatChange(e.target.value as Format)}
                className="text-sm font-medium text-ink-700 bg-white border border-cream-400 rounded-md px-2 py-1 outline-none hover:border-coral-300 focus:border-coral-400 focus:ring-2 focus:ring-coral-100 transition"
              >
                {(Object.keys(FORMAT_META) as Format[]).map((f) => (
                  <option key={f} value={f}>{FORMAT_META[f].label}</option>
                ))}
              </select>
            </div>
            <button
              onClick={loadExample}
              className="text-xs text-ink-400 hover:text-coral-600 transition"
            >
              load example
            </button>
          </div>
          <textarea
            value={source}
            onChange={(e) => setSource(e.target.value)}
            spellCheck={false}
            className="block w-full h-[300px] p-4 font-mono text-[13px] leading-[1.6] text-ink-700 bg-white outline-none resize-y"
            placeholder={FORMAT_META[format].placeholder}
          />
        </div>

        <div className="mt-5 flex items-center gap-4">
          <button
            disabled={busy || !source.trim()}
            onClick={onConvert}
            className="px-6 py-3 rounded-xl bg-coral-500 hover:bg-coral-600 disabled:bg-cream-400 disabled:text-ink-300 disabled:cursor-not-allowed text-white font-medium shadow-soft transition active:scale-[0.98]"
          >
            {busy ? "Converting…" : "Convert to DML"}
          </button>
          {result && (
            <span className="text-sm text-ink-400">
              schema name: <code className="text-ink-600 bg-cream-200 px-1.5 py-0.5 rounded text-xs">{result.record_name}</code>
            </span>
          )}
        </div>

        {err && (
          <div className="mt-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm whitespace-pre-wrap">
            {err}
          </div>
        )}

        {result && (
          <section className="mt-10 rounded-2xl border border-cream-400 bg-white shadow-card overflow-hidden">
            <div className="px-5 py-4 border-b border-cream-300 bg-cream-50 flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="text-[10px] uppercase tracking-[0.08em] font-medium text-ink-400 mb-1">
                  generated dml
                </div>
                <h2 className="text-xl font-serif text-ink-800">{result.record_name}.dml</h2>
                {result.extras && Object.keys(result.extras).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {Object.entries(result.extras)
                      .filter(([, v]) => v != null)
                      .map(([k, v]) => (
                        <span
                          key={k}
                          className="text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded bg-cream-200 text-ink-500"
                        >
                          {k}: {String(v)}
                        </span>
                      ))}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={copyDml}
                  className="text-xs px-3 py-1.5 rounded-lg border border-cream-400 hover:border-coral-300 text-ink-500 hover:text-coral-600 transition"
                >
                  copy dml
                </button>
                <button
                  onClick={openInPlayground}
                  className="text-xs px-3 py-1.5 rounded-lg bg-coral-500 hover:bg-coral-600 text-white transition"
                >
                  open in DML Playground →
                </button>
              </div>
            </div>
            <div className="p-5">
              <CodePreview code={result.dml} language="text" />
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
