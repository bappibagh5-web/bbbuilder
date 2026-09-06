import type { Metadata } from "next";
import { ProductionDashboard } from "@/components/dashboard/production-dashboard";
export const metadata: Metadata = { title: "Dashboard" };
export default function DashboardPage() {
  return <ProductionDashboard />;
}
