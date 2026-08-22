import type { Metadata } from "next";
import "./globals.css";
export const metadata:Metadata={ title:{default:"BB Builders Bid Management",template:"%s | BB Builders"},description:"Preconstruction and bid management demonstration for BB Builders." };
export default function RootLayout({children}:LayoutProps<"/">){return <html lang="en"><body>{children}</body></html>}
