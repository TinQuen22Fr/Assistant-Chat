import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ConversationsProvider } from "@/context/ConversationsContext";
import AuthPage from "@/pages/AuthPage";
import AuthCallback from "@/pages/AuthCallback";
import ChatPage from "@/pages/ChatPage";
import MemoryPage from "@/pages/MemoryPage";
import ImportPage from "@/pages/ImportPage";
import { Sparkles } from "lucide-react";

const Splash = () => (
  <div data-testid="app-loading" className="flex h-screen items-center justify-center bg-white">
    <Sparkles className="h-8 w-8 animate-pulse text-[#4285f4]" />
  </div>
);

const Protected = ({ children }) => {
  const { user } = useAuth();
  if (user === null) return <Splash />;
  if (user === false) return <Navigate to="/login" replace />;
  return children;
};

const PublicOnly = ({ children }) => {
  const { user } = useAuth();
  if (user === null) return <Splash />;
  if (user) return <Navigate to="/" replace />;
  return children;
};

function AppRouter() {
  const location = useLocation();
  // Détection synchrone du retour Google (avant toute vérification de session)
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><AuthPage /></PublicOnly>} />
      <Route path="/memoire" element={<Protected><MemoryPage /></Protected>} />
      <Route path="/importer" element={<Protected><ImportPage /></Protected>} />
      <Route
        path="*"
        element={
          <Protected>
            <ConversationsProvider>
              <ChatPage />
            </ConversationsProvider>
          </Protected>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRouter />
        <Toaster theme="light" position="bottom-center" />
      </AuthProvider>
    </BrowserRouter>
  );
}
