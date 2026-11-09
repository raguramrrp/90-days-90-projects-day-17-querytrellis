import type { Metadata } from "next";
import "./globals.css";
import { WorkspaceProvider } from "@/lib/context";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "QueryTrellis — SQL Development & Query Optimization Workbench",
  description:
    "Schema-grounded natural language to SQL studio, multi-dialect IDE, diagnostic assistant, query optimizer, and visual SQL learning environment.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased selection:bg-[#DCE9E1] selection:text-[#202321]">
        <WorkspaceProvider>
          <AppShell>{children}</AppShell>
        </WorkspaceProvider>
      </body>
    </html>
  );
}
