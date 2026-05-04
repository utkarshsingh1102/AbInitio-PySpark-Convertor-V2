import "./globals.css";
import type { Metadata } from "next";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "Ab Initio → PySpark",
  description: "Convert Ab Initio graphs to production PySpark via Neo4j",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-cream-100 text-ink-700 antialiased">
        <Nav />
        {children}
      </body>
    </html>
  );
}
