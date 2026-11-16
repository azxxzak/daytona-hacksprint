import { TestPage } from "@/components/report/test-page";

export default async function Page({ params }: PageProps<"/tests/[id]">) {
  const { id } = await params;
  return <TestPage id={id} />;
}
