import { Inbox, Shield, FolderOpen } from 'lucide-react';

export default function LoginBranding() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-10 bg-gradient-to-b from-blue-500 to-blue-900 px-15 text-white">
      <div className="flex flex-col items-center gap-6">
        <div className="flex items-center gap-3">
          <div className="h-[52px] w-[52px] shrink-0 overflow-hidden rounded-[14px]">
            <img src="/logo.png" alt="MailManager logo" className="h-full w-full object-cover" />
          </div>
          <h1 className="text-[38px] font-extrabold tracking-tight">MailManager</h1>
        </div>

        <p className="max-w-[380px] text-center text-[17px] leading-[1.6] text-white/[0.87]">
          Gestiona todas tus cuentas de correo en un solo lugar
        </p>
      </div>

      <ul className="flex max-w-[380px] flex-col gap-4 rounded-2xl bg-white/[0.08] px-6 py-5">
        <li className="flex items-center gap-3">
          <Inbox className="h-[22px] w-[22px] shrink-0 text-white" />
          <span className="text-[15px] text-white/[0.87]">
            Bandeja unificada para Gmail y Outlook
          </span>
        </li>
        <li className="flex items-center gap-3">
          <Shield className="h-[22px] w-[22px] shrink-0 text-white" />
          <span className="text-[15px] text-white/[0.87]">Autenticación segura con Google</span>
        </li>
        <li className="flex items-center gap-3">
          <FolderOpen className="h-[22px] w-[22px] shrink-0 text-white" />
          <span className="text-[15px] text-white/[0.87]">
            Organiza tus cuentas en buzones personalizados
          </span>
        </li>
      </ul>
    </div>
  );
}
