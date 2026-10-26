import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Nav from "./nav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Mini-Rayyan",
  description: "Search PubMed, deduplicate, screen and tag PICO for systematic reviews",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <Nav />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
        <footer className="border-t border-neutral-200 px-4 py-4 text-center text-xs text-neutral-500 dark:border-neutral-800">
          Records are retrieved from PubMed via the NCBI E-utilities. This product is not endorsed or certified by
          NCBI, NLM or NIH. Abstracts may be subject to publisher copyright; see the{" "}
          <a className="underline" href="https://www.ncbi.nlm.nih.gov/home/about/policies/" target="_blank">
            NCBI policies and disclaimers
          </a>
          .
        </footer>
      </body>
    </html>
  );
}
