import type { Metadata } from "next";
import { Geist, Geist_Mono, Source_Serif_4 } from "next/font/google";
import Nav from "./nav";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: { default: "Mini-Rayyan", template: "%s | Mini-Rayyan" },
  description: "Search PubMed and Europe PMC, deduplicate, screen and tag PICO for systematic reviews",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${sourceSerif.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col font-sans">
        <Nav />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">{children}</main>
        <footer className="border-t border-rule">
          <p className="mx-auto max-w-6xl px-4 py-5 text-xs leading-relaxed text-faint sm:px-6">
            Records are retrieved from PubMed via the NCBI E-utilities and from Europe PMC. This product is not
            endorsed or certified by NCBI, NLM, NIH or EMBL-EBI. Abstracts may be subject to publisher copyright; see
            the{" "}
            <a className="underline hover:text-muted" href="https://www.ncbi.nlm.nih.gov/home/about/policies/" target="_blank">
              NCBI policies and disclaimers
            </a>{" "}
            and the{" "}
            <a className="underline hover:text-muted" href="https://www.ebi.ac.uk/about/terms-of-use/" target="_blank">
              EMBL-EBI terms of use
            </a>
            .
          </p>
        </footer>
      </body>
    </html>
  );
}
