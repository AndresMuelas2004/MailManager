import { NavLink } from "react-router-dom";
import { Inbox, Send, ShieldAlert, FileEdit, Trash2 } from "lucide-react";
import type { ComponentType } from "react";

type TabDef = {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
};

type Props = {
  basePath: string;
  inboxLabel?: string;
};

export default function AccountTabs({ basePath, inboxLabel = "Bandeja" }: Props) {
  const tabs: TabDef[] = [
    { to: `${basePath}/inbox`, label: inboxLabel, icon: Inbox },
    { to: `${basePath}/sent`, label: "Enviados", icon: Send },
    { to: `${basePath}/spam`, label: "Spam", icon: ShieldAlert },
    { to: `${basePath}/drafts`, label: "Borradores", icon: FileEdit },
    { to: `${basePath}/trash`, label: "Papelera", icon: Trash2 },
  ];

  return (
    <div className="flex gap-1 border-b border-zinc-200 px-8">
      {tabs.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
              isActive
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-zinc-500 hover:text-zinc-700"
            }`
          }
        >
          <Icon className="h-4 w-4" />
          {label}
        </NavLink>
      ))}
    </div>
  );
}
