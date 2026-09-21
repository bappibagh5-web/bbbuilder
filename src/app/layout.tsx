import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/components/auth/auth-provider";

const title = "BB Builders | Preconstruction & Bid Management";
const description =
  "Organization-scoped preconstruction, subcontractor procurement, bid comparison, and proposal management.";

export const metadata: Metadata = {
  applicationName: "BB Builders Bid Management",
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
