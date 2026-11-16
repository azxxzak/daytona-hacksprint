import { Suspense } from "react";
import { NewTest } from "@/components/new-test";

export const metadata = { title: "New test" };

export default function Page() {
  return (
    <Suspense>
      <NewTest />
    </Suspense>
  );
}
