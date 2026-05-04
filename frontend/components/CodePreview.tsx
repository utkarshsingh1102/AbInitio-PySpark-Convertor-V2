"use client";
import { Highlight, themes, type PrismTheme } from "prism-react-renderer";

// Custom Prism theme tuned to the cream / coral palette.
const claudeLight: PrismTheme = {
  plain: {
    color: "#1F1E1B",         // ink-700
    backgroundColor: "#FBFAF6", // cream-50
  },
  styles: [
    { types: ["comment", "prolog", "doctype", "cdata"], style: { color: "#A6A39A", fontStyle: "italic" } },
    { types: ["punctuation"],                            style: { color: "#6F6D65" } },
    { types: ["string", "char", "attr-value", "regex"],  style: { color: "#A04A2C" } },
    { types: ["number", "boolean"],                      style: { color: "#9333EA" } },
    { types: ["keyword", "selector", "builtin", "atrule"], style: { color: "#C15F3C", fontWeight: "500" } },
    { types: ["function", "class-name"],                 style: { color: "#0E7490" } },
    { types: ["operator", "entity", "url"],              style: { color: "#4A4945" } },
    { types: ["variable", "attr-name"],                  style: { color: "#1F1E1B" } },
    { types: ["tag"],                                    style: { color: "#C15F3C" } },
    { types: ["constant", "symbol", "deleted"],          style: { color: "#B91C1C" } },
    { types: ["property", "namespace"],                  style: { color: "#0284C7" } },
  ],
};

export function CodePreview({ code, language = "python" }: { code: string; language?: string }) {
  return (
    <Highlight code={code} language={language} theme={claudeLight}>
      {({ className, style, tokens, getLineProps, getTokenProps }) => (
        <pre
          className={`${className} rounded-xl p-4 overflow-auto text-[12px] leading-[1.65] border border-cream-400 shadow-card font-mono`}
          style={{ ...style, maxHeight: "560px" }}
        >
          {tokens.map((line, i) => (
            <div key={i} {...getLineProps({ line })} className="flex">
              <span className="inline-block w-10 text-ink-300 select-none text-right pr-4 shrink-0 font-mono">
                {i + 1}
              </span>
              <span className="flex-1 min-w-0">
                {line.map((token, key) => (
                  <span key={key} {...getTokenProps({ token })} />
                ))}
              </span>
            </div>
          ))}
        </pre>
      )}
    </Highlight>
  );
}
