"use client";
import { ErrorRecovery } from "@/components/error-recovery";
export default function GlobalError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return <html lang="en"><body><ErrorRecovery retry={retry} /></body></html>;
}
