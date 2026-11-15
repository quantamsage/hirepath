import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HirePath",
  description: "Track every job application, when to follow up, and how your search is going.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
