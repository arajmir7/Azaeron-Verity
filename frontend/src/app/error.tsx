"use client";
import { ErrorRecovery } from "@/components/error-recovery";
export default function ErrorPage({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return <ErrorRecovery retry={retry} />;
}
