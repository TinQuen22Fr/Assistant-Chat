import { useEffect, useRef, useState } from "react";
import { matchPath, useLocation, useNavigate } from "react-router-dom";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { EmptyState } from "@/components/EmptyState";
import { Message } from "@/components/Message";
import { Composer } from "@/components/Composer";
import { FilesPanel } from "@/components/FilesPanel";
import { SummaryPanel } from "@/components/SummaryPanel";
import { useConversation } from "@/hooks/useConversation";
import { useSummary } from "@/hooks/useSummary";
import { useAuth } from "@/context/AuthContext";
import { validateFile } from "@/lib/files";

const isDesktop = () => window.innerWidth >= 768;

export default function ChatPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const routeId = matchPath("/c/:id", location.pathname)?.params.id ?? null;
  const chat = useConversation(routeId, navigate);
  const [sidebarOpen, setSidebarOpen] = useState(() => isDesktop() && localStorage.getItem("gp-sidebar") !== "0");
  const [filesOpen, setFilesOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [files, setFiles] = useState([]);
  const bottomRef = useRef(null);
  const { summary, run: runSummary, setOpen: setSummaryOpen } = useSummary();
  const cid = chat.conv?.id;

  const summarizeFile = (f) => {
    setFilesOpen(false);
    runSummary({ kind: "file", id: f.id, title: f.name, conversationId: cid });
  };
  const summarizeConversation = () =>
    runSummary({ kind: "conversation", id: cid, title: chat.conv.title, conversationId: cid });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chat.messages]);

  const toggleSidebar = () =>
    setSidebarOpen((o) => {
      if (isDesktop()) localStorage.setItem("gp-sidebar", o ? "0" : "1");
      return !o;
    });

  const addFiles = (picked) => {
    const errors = picked.map(validateFile).filter(Boolean);
    chat.setError(errors.length ? errors.join(" ") : null);
    setFiles((prev) => [...prev, ...picked.filter((f) => !validateFile(f))]);
  };

  const handleSend = async () => {
    if (chat.streaming || (!prompt.trim() && files.length === 0)) return;
    const payload = { content: prompt.trim(), files };
    setPrompt("");
    setFiles([]);
    const ok = await chat.send(payload);
    if (!ok) {
      setPrompt(payload.content);
      setFiles(payload.files);
    }
  };

  const newChat = () => {
    navigate("/");
    if (!isDesktop()) setSidebarOpen(false);
  };

  const lastModelIdx = chat.messages.map((m) => m.role).lastIndexOf("model");

  return (
    <div className="flex h-screen overflow-hidden bg-white">
      <Sidebar open={sidebarOpen} onToggle={toggleSidebar} activeId={routeId} onNew={newChat} onNavigate={() => !isDesktop() && setSidebarOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          model={chat.model}
          onModelChange={chat.setModel}
          disabled={chat.streaming}
          title={chat.conv?.title}
          onToggleSidebar={toggleSidebar}
          onOpenFiles={() => setFilesOpen(true)}
          onSummarize={summarizeConversation}
          canSummarize={chat.messages.length > 0 && !chat.streaming}
          hasConversation={!!chat.conv}
        />
        <main data-testid="chat-messages-container" className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-8 px-4 py-8 sm:px-6">
            {chat.messages.length === 0 && !chat.loading ? (
              <EmptyState name={user?.name} onPick={setPrompt} />
            ) : (
              chat.messages.map((m, i) => (
                <Message
                  key={m.id}
                  msg={m}
                  canRegenerate={i === lastModelIdx && i === chat.messages.length - 1 && !chat.streaming}
                  onRegenerate={chat.regenerate}
                  onSummarizeFile={summarizeFile}
                />
              ))
            )}
            <div ref={bottomRef} />
          </div>
        </main>
        <Composer
          value={prompt}
          onChange={setPrompt}
          files={files}
          onAddFiles={addFiles}
          onRemoveFile={(i) => setFiles((prev) => prev.filter((_, j) => j !== i))}
          onSend={handleSend}
          onStop={chat.stop}
          streaming={chat.streaming}
          error={chat.error}
          errorAction={
            chat.errorCode === "quota" && chat.conv
              ? { label: "Réessayer avec Gemini 3 Flash", onClick: chat.retryWithFlash }
              : null
          }
          onDismissError={() => chat.setError(null)}
        />
      </div>
      <FilesPanel open={filesOpen} onOpenChange={setFilesOpen} conversationId={cid} version={chat.filesVersion} onSummarize={summarizeFile} />
      <SummaryPanel summary={summary} onOpenChange={setSummaryOpen} />
    </div>
  );
}
