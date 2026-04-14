import { Inbox, Send, ShieldAlert, FileEdit, Trash2 } from "lucide-react";
import type { ComponentType } from "react";

export type NavItem = {
  icon: ComponentType<{ className?: string }>;
  label: string;
  path: string;
};

export const MAILBOX_NAV_ITEMS: NavItem[] = [
  { icon: Inbox, label: "Bandeja unificada", path: "inbox" },
  { icon: Send, label: "Enviados", path: "sent" },
  { icon: ShieldAlert, label: "Spam", path: "spam" },
  { icon: FileEdit, label: "Borradores", path: "drafts" },
  { icon: Trash2, label: "Papelera de reciclaje", path: "trash" },
];
