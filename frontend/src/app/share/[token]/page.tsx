import type { Metadata } from "next";
import { SharePage } from "@/components/report/share-page";

export const metadata: Metadata = { title: "Shared report", robots: { index: false, follow: false } };

export default async function Page({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <SharePage token={token} />;
}
