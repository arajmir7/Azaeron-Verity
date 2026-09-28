import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Azaeron Verity — Evidence-first document analysis",
  description: "Workspace-scoped document versions, traceable evidence, and responsible writing improvement.",
  openGraph: {
    title: "AZAERON VERITY",
    description: "Evidence-first document analysis and responsible writing improvement.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100">
        {children}
      </body>
    </html>
  );
}
