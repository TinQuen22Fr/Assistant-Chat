import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { apiJson } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AuthCallback() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const sessionId = new URLSearchParams(window.location.hash.slice(1)).get("session_id");
    apiJson("/auth/google/emergent", { method: "POST", body: { session_id: sessionId } })
      .then((user) => {
        setUser(user);
        window.history.replaceState(null, "", "/");
        navigate("/", { replace: true });
      })
      .catch(() => {
        setUser(false);
        navigate("/login?erreur=google", { replace: true });
      });
  }, [navigate, setUser]);

  return (
    <div data-testid="auth-callback" className="flex h-screen items-center justify-center bg-white">
      <Sparkles className="h-8 w-8 animate-pulse text-[#4285f4]" />
    </div>
  );
}
