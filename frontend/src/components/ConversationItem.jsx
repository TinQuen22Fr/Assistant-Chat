import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MoreVertical, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useConversations } from "@/context/ConversationsContext";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const RenameDialog = ({ open, onOpenChange, initial, onSave }) => {
  const [value, setValue] = useState(initial);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-3xl sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Renommer la discussion</DialogTitle>
        </DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); if (value.trim()) onSave(value.trim()); }}>
          <input
            data-testid="rename-input"
            autoFocus
            value={value}
            maxLength={120}
            onChange={(e) => setValue(e.target.value)}
            className="h-11 w-full rounded-xl border border-slate-300 px-4 outline-none focus:border-[#1a73e8] focus:ring-4 focus:ring-blue-100"
          />
          <DialogFooter className="mt-6 gap-2">
            <button type="button" onClick={() => onOpenChange(false)} className="rounded-full px-5 py-2 text-sm font-medium text-[#1a73e8] hover:bg-blue-50">
              Annuler
            </button>
            <button data-testid="rename-confirm-button" type="submit" disabled={!value.trim()} className="rounded-full bg-[#1a73e8] px-5 py-2 text-sm font-medium text-white hover:bg-[#1557b0] disabled:opacity-50">
              Renommer
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export const ConversationItem = ({ conv, active, onNavigate }) => {
  const { rename, remove } = useConversations();
  const navigate = useNavigate();
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const save = async (title) => {
    try {
      await rename(conv.id, title);
      setRenaming(false);
    } catch (e) {
      toast.error(e.message);
    }
  };

  const confirmDelete = async () => {
    try {
      await remove(conv.id);
      toast.success("Discussion supprimée");
      if (active) navigate("/");
    } catch (e) {
      toast.error(e.message);
    }
  };

  return (
    <div
      data-testid={`conversation-item-${conv.id}`}
      className={`group flex items-center rounded-full pr-1 transition-colors ${active ? "bg-[#d3e3fd]" : "hover:bg-slate-200/70"}`}
    >
      <Link
        to={`/c/${conv.id}`}
        onClick={onNavigate}
        data-testid="conversation-link"
        className={`min-w-0 flex-1 truncate py-2 pl-4 text-sm ${active ? "font-medium text-[#041e49]" : "text-slate-700"}`}
      >
        {conv.title}
      </Link>
      {conv.imported && (
        <span data-testid="conversation-imported-badge" className="mr-1 shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
          Importé
        </span>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger
          data-testid="conversation-menu-button"
          aria-label="Options de la discussion"
          className="flex h-8 w-8 items-center justify-center rounded-full text-slate-500 opacity-0 transition-opacity hover:bg-slate-300/60 focus:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100"
        >
          <MoreVertical className="h-4 w-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="rounded-xl">
          <DropdownMenuItem data-testid="conversation-rename-option" onSelect={() => setRenaming(true)}>
            <Pencil className="mr-2 h-4 w-4" /> Renommer
          </DropdownMenuItem>
          <DropdownMenuItem data-testid="conversation-delete-option" onSelect={() => setDeleting(true)} className="text-red-600 focus:text-red-600">
            <Trash2 className="mr-2 h-4 w-4" /> Supprimer
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {renaming && <RenameDialog open={renaming} onOpenChange={setRenaming} initial={conv.title} onSave={save} />}

      <AlertDialog open={deleting} onOpenChange={setDeleting}>
        <AlertDialogContent className="rounded-3xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer la discussion ?</AlertDialogTitle>
            <AlertDialogDescription>
              « {conv.title} » ainsi que ses messages et fichiers seront définitivement supprimés.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="delete-cancel-button" className="rounded-full">Annuler</AlertDialogCancel>
            <AlertDialogAction data-testid="delete-confirm-button" onClick={confirmDelete} className="rounded-full bg-red-600 hover:bg-red-700">
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
