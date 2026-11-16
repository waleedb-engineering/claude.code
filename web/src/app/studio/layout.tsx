import type { Metadata } from "next";
import { StudioNav } from "@/components/studio/ui";

export const metadata: Metadata = {
  title: "Creator Studio — ClipForge AI",
};

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <StudioNav />
      {children}
    </div>
  );
}
