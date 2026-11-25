import { Suspense } from "react";
import { Compare } from "@/components/compare";

export default function Page() {
  return (
    <Suspense>
      <Compare />
    </Suspense>
  );
}
