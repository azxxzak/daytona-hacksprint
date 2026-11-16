import { TalkPage } from "@/components/talk/talk-page";

export default async function Page({ params }: PageProps<"/tests/[id]/talks/[talkId]">) {
  const { id, talkId } = await params;
  return <TalkPage testId={id} talkId={talkId} />;
}
