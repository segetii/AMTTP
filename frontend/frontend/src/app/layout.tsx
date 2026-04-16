import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AMTTP Security Operations",
  description: "Blockchain Fraud Detection & Response Dashboard",
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              // Polyfill Performance API methods that Next.js expects
              // Prevents "mgt.clearMarks is not a function" in embedded/iframe contexts
              (function(){
                var p = window.performance || {};
                if (!p.clearMarks) p.clearMarks = function(){};
                if (!p.clearMeasures) p.clearMeasures = function(){};
                if (!p.mark) p.mark = function(){};
                if (!p.measure) p.measure = function(){};
                if (!p.getEntriesByName) p.getEntriesByName = function(){ return []; };
                if (!p.getEntriesByType) p.getEntriesByType = function(){ return []; };
                window.performance = p;
              })();
            `,
          }}
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-gray-950`}
        suppressHydrationWarning
      >
        {/* Skip link for keyboard accessibility */}
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
