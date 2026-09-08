import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Corgi Policy Administration",
  description: "Commercial General Liability Policy Administration System",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
