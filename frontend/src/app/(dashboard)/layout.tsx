"use client";

import { DashboardShell } from "@/components/design-system";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
