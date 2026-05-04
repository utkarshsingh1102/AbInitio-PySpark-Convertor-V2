"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/",           label: "Pipeline Converter" },
  { href: "/playground", label: "DML Playground" },
  { href: "/visualizer", label: "Pipeline Visualizer" },
];

export function Nav() {
  const pathname = usePathname() || "/";
  return (
    <header className="border-b border-cream-400 bg-cream-50/80 backdrop-blur-sm sticky top-0 z-30">
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center gap-8">
        <Link href="/" className="flex items-center gap-2 group">
          <span className="w-2 h-2 rounded-full bg-coral-500 group-hover:scale-125 transition" />
          <span className="font-serif text-base text-ink-800">Ab Initio → PySpark</span>
        </Link>
        <nav className="flex items-center gap-1">
          {TABS.map((t) => {
            const active = t.href === "/" ? pathname === "/" : pathname.startsWith(t.href);
            return (
              <Link
                key={t.href}
                href={t.href}
                className={[
                  "px-3 py-1.5 rounded-lg text-sm font-medium transition",
                  active
                    ? "bg-coral-50 text-coral-700 border border-coral-200"
                    : "text-ink-500 hover:text-ink-800 hover:bg-cream-200 border border-transparent",
                ].join(" ")}
              >
                {t.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
