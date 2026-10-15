import { BookOpen, Brain, Download, LogOut, Upload } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const initials = (name = "") =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("") || "?";

export const ProfileMenu = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        data-testid="profile-menu-button"
        aria-label="Menu du profil"
        className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-full bg-[#1a73e8] text-sm font-semibold text-white ring-offset-2 transition-shadow hover:ring-2 hover:ring-slate-200"
      >
        {user.picture ? <img src={user.picture} alt="" className="h-full w-full object-cover" /> : initials(user.name)}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64 rounded-2xl p-2">
        <DropdownMenuLabel className="font-normal">
          <p data-testid="profile-name" className="truncate text-sm font-semibold text-slate-900">{user.name}</p>
          <p data-testid="profile-email" className="truncate text-xs text-slate-500">{user.email}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem data-testid="profile-memory-link" onSelect={() => navigate("/memoire")} className="rounded-lg">
          <Brain className="mr-2 h-4 w-4" /> Mémoire
        </DropdownMenuItem>
        <DropdownMenuItem data-testid="profile-import-link" onSelect={() => navigate("/importer")} className="rounded-lg">
          <Upload className="mr-2 h-4 w-4" /> Importer depuis Gemini
        </DropdownMenuItem>
        <DropdownMenuItem data-testid="profile-deploy-guide-link" onSelect={() => window.open(`${API}/deploy/guide`, "_blank")} className="rounded-lg">
          <BookOpen className="mr-2 h-4 w-4" /> Guide d'auto-hébergement
        </DropdownMenuItem>
        <DropdownMenuItem data-testid="profile-deploy-bundle-link" onSelect={() => { window.location.href = `${API}/deploy/bundle`; }} className="rounded-lg">
          <Download className="mr-2 h-4 w-4" /> Fichiers de déploiement (.zip)
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem data-testid="logout-button" onSelect={logout} className="rounded-lg">
          <LogOut className="mr-2 h-4 w-4" /> Se déconnecter
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
