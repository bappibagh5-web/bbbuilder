import { UnsubscribePage } from "@/components/prospecting/unsubscribe-page";

export default async function Page({ params }: PageProps<"/unsubscribe/[token]">) {
  const { token } = await params;
  return <UnsubscribePage token={token} />;
}
