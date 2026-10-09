import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "AgentScope · Agent observability",
  description:
    "Trace every run. Understand every incident. Agent observability and evidence-grounded incident response.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
