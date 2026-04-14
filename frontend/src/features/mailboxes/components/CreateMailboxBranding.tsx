import { Inbox, Link, RefreshCw } from "lucide-react";

export default function CreateMailboxBranding() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-8 bg-gradient-to-b from-blue-500 to-blue-900 px-15 text-white">
      <div className="flex items-center gap-3">
        <div className="h-[52px] w-[52px] shrink-0 overflow-hidden rounded-[14px]">
          <img
            src="/logo.png"
            alt="MailManager logo"
            className="h-full w-full object-cover"
          />
        </div>
        <h1 className="text-[38px] font-extrabold tracking-tight">MailManager</h1>
      </div>

      <div className="flex max-w-[400px] flex-col items-center gap-5">
        <p className="text-center text-[22px] font-semibold text-white/[0.93]">
          Tu bandeja unificada te espera
        </p>
        <p className="text-center text-base leading-[1.6] text-white/[0.73]">
          Organiza todos tus correos de Gmail y Outlook en un solo lugar.
          Crea tu primera bandeja para empezar.
        </p>
      </div>

      <ul className="flex max-w-[400px] flex-col gap-4 rounded-2xl bg-white/[0.08] px-6 py-5">
        <li className="flex items-center gap-3">
          <Inbox className="h-5 w-5 shrink-0 text-white" />
          <span className="text-sm text-white/[0.87]">
            Un solo lugar para todos tus correos
          </span>
        </li>
        <li className="flex items-center gap-3">
          <Link className="h-5 w-5 shrink-0 text-white" />
          <span className="text-sm text-white/[0.87]">
            Gmail y Outlook conectados
          </span>
        </li>
        <li className="flex items-center gap-3">
          <RefreshCw className="h-5 w-5 shrink-0 text-white" />
          <span className="text-sm text-white/[0.87]">
            Sincronización automática
          </span>
        </li>
      </ul>
    </div>
  );
}
