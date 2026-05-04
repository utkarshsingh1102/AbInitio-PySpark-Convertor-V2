"use client";
import { useCallback, useState } from "react";

type Props = {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
};

const ACCEPTED = [".mp", ".dml", ".xfr"];

export function FileUpload({ onFiles, disabled }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [picked, setPicked] = useState<File[]>([]);

  const handle = useCallback((files: FileList | null) => {
    if (!files) return;
    const arr = Array.from(files).filter((f) =>
      ACCEPTED.some((ext) => f.name.toLowerCase().endsWith(ext))
    );
    setPicked(arr);
    onFiles(arr);
  }, [onFiles]);

  return (
    <label
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (!disabled) handle(e.dataTransfer.files);
      }}
      className={[
        "relative block border-2 border-dashed rounded-2xl p-12 text-center transition-all",
        dragOver
          ? "border-coral-500 bg-coral-50"
          : "border-cream-500 bg-cream-50 hover:border-coral-300 hover:bg-cream-200",
        disabled ? "opacity-60 pointer-events-none" : "cursor-pointer",
      ].join(" ")}
    >
      <div className="flex flex-col items-center gap-3">
        <div className="w-12 h-12 rounded-xl bg-coral-100 text-coral-600 flex items-center justify-center">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <div>
          <p className="text-base font-medium text-ink-700">
            Drop <span className="text-coral-600">.mp / .dml / .xfr</span> files here
          </p>
          <p className="text-sm text-ink-400 mt-1">or click to browse</p>
        </div>
      </div>

      <input
        type="file"
        multiple
        accept={ACCEPTED.join(",")}
        className="absolute inset-0 opacity-0 cursor-pointer"
        onChange={(e) => handle(e.target.files)}
      />

      {picked.length > 0 && (
        <ul className="mt-6 inline-block text-left text-sm text-ink-500 space-y-1">
          {picked.map((f) => (
            <li key={f.name} className="flex items-center gap-2">
              <span className="w-1 h-1 rounded-full bg-coral-500" />
              <span className="font-mono text-xs text-ink-700">{f.name}</span>
              <span className="text-ink-300 text-xs">{f.size.toLocaleString()} B</span>
            </li>
          ))}
        </ul>
      )}
    </label>
  );
}
