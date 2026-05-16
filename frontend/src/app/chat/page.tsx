import { ChatPanel } from "@/components/ChatPanel";

export default async function ChatPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const raw = params.message;
  const initialQuery = typeof raw === "string" ? raw.trim() : Array.isArray(raw) ? raw[0]?.trim() ?? "" : "";

  return (
    <div className="bg-background text-on-background font-body-md h-screen flex flex-col overflow-hidden">
      <header className="bg-white/80 backdrop-blur-md border-b border-slate-200 h-14 px-4 flex items-center shrink-0">
        <span className="text-lg font-bold tracking-tighter text-slate-900 font-headline-md">
          ChemSynth AI
        </span>
      </header>
      <ChatPanel initialQuery={initialQuery || undefined} />
    </div>
  );
}

