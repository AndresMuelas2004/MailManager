import { useState } from "react";
import { NavLink } from "react-router-dom";
import { Inbox, Send, Link, Settings, ChevronDown } from "lucide-react";
import type { ComponentType } from "react";

import MailboxDropdown from "./MailboxDropdown";
import SettingsDropdown from "./SettingsDropdown";

type MailboxItem = {
  mailbox_id: string;
  display_name: string | null;
};

type NavItem = {
  icon: ComponentType<{ className?: string }>;
  label: string;
  path: string;
};

type Props = {
  mailboxId: string;
  mailboxName: string;
  mailboxes: MailboxItem[];
  navItems: NavItem[];
  onMailboxSelect: (mailboxId: string) => void;
  onMailboxCreate: (displayName: string) => void;
  onCompose: () => void;
  onLogout: () => void;
  onDeleteAccount: () => void;
};

export default function Sidebar({
  mailboxId,
  mailboxName,
  mailboxes,
  navItems,
  onMailboxSelect,
  onMailboxCreate,
  onCompose,
  onLogout,
  onDeleteAccount,
}: Props) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const base = `/m/${mailboxId}`;

  return (
    <aside className="flex w-[260px] shrink-0 flex-col gap-1 border-r border-zinc-200 bg-white px-4 py-6">
      <div className="flex items-center gap-2.5 px-2 pb-5">
        <div className="h-8 w-8 shrink-0 overflow-hidden rounded-lg">
          <img src="/logo.png" alt="MailManager" className="h-full w-full object-cover" />
        </div>
        <span className="text-lg font-bold tracking-tight text-zinc-900">MailManager</span>
      </div>

      <div className="relative">
        <button
          type="button"
          onClick={() => setDropdownOpen((v) => !v)}
          className="flex h-11 w-full items-center justify-between rounded-[10px] bg-zinc-100 px-3"
        >
          <div className="flex items-center gap-2.5">
            <Inbox className="h-[18px] w-[18px] text-blue-600" />
            <span className="text-sm font-semibold text-zinc-900">
              {mailboxName || "Cargando..."}
            </span>
          </div>
          <ChevronDown className="h-4 w-4 text-zinc-500" />
        </button>

        {dropdownOpen && (
          <MailboxDropdown
            mailboxes={mailboxes}
            currentMailboxId={mailboxId}
            onSelect={(id) => { setDropdownOpen(false); onMailboxSelect(id); }}
            onCreate={(name) => { setDropdownOpen(false); onMailboxCreate(name); }}
          />
        )}
      </div>

      <nav className="mt-1 flex flex-col gap-0.5">
        {navItems.map(({ icon: Icon, label, path }) => (
          <NavLink
            key={path}
            to={`${base}/${path}`}
            className={({ isActive }) =>
              `flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium ${
                isActive
                  ? "bg-blue-50 text-blue-600"
                  : "text-zinc-500 hover:bg-zinc-50"
              }`
            }
          >
            <Icon className="h-5 w-5" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="my-2 h-px bg-zinc-200" />
      <p className="px-3 text-[11px] font-semibold tracking-wider text-zinc-400">
        CUENTAS CONECTADAS
      </p>
      <NavLink
        to={`${base}/accounts`}
        className={({ isActive }) =>
          `flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-semibold ${
            isActive
              ? "bg-blue-50 text-blue-600"
              : "text-zinc-500 hover:bg-zinc-50"
          }`
        }
      >
        <Link className="h-5 w-5" />
        Cuentas conectadas
      </NavLink>

      <div className="flex-1" />

      <div className="flex justify-center py-4">
        <button
          type="button"
          onClick={onCompose}
          className="flex h-[52px] w-[52px] items-center justify-center rounded-full bg-blue-600 text-white shadow-lg shadow-blue-600/25 transition-colors hover:bg-blue-700"
        >
          <Send className="h-6 w-6" />
        </button>
      </div>

      <div className="relative px-1 py-2">
        <button
          type="button"
          onClick={() => setSettingsOpen((v) => !v)}
          className="text-zinc-400 hover:text-zinc-600"
        >
          <Settings className="h-5 w-5" />
        </button>
        {settingsOpen && (
          <SettingsDropdown
            onLogout={() => { setSettingsOpen(false); onLogout(); }}
            onDeleteAccount={() => { setSettingsOpen(false); onDeleteAccount(); }}
          />
        )}
      </div>
    </aside>
  );
}
