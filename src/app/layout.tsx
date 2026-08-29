import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/components/auth/auth-provider";

const title = "BB Builders | Preconstruction & Bid Management Demo";
const description =
  "Interactive demonstration of BB Builders' proposed preconstruction, subcontractor procurement, bid comparison, and proposal workflow.";

export const metadata: Metadata = {
  applicationName: "BB Builders Bid Management Demo",
  title: { default: title, template: "%s | BB Builders" },
  description,
  openGraph: {
    title,
    description,
    siteName: "BB Builders",
    type: "website",
  },
  twitter: {
    card: "summary",
    title,
    description,
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}
