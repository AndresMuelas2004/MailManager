import { useEffect, useRef } from "react";

import Modal from "../../../components/common/Modal";
import Spinner from "../../../components/common/Spinner";
import useEmailContent from "../hooks/useEmailContent";
import { buildAccountMap, formatDate, resolveAccount } from "../../../lib/formatters";
import type { EmailMetadataOut, AccountOut } from "../../../api/types/dto";

type Props = {
  mailboxId: string;
  email: EmailMetadataOut;
  accounts: AccountOut[];
  onClose: () => void;
  onRead: (email: EmailMetadataOut) => Promise<void>;
};

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function wrapPlainText(text: string): string {
  const escaped = escapeHtml(text);
  return `<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;padding:16px;font-family:system-ui,-apple-system,Segoe UI,sans-serif;font-size:14px;color:#18181b"><pre style="white-space:pre-wrap;margin:0;font-family:inherit;font-size:inherit">${escaped}</pre></body></html>`;
}

function wrapHtmlEmail(html: string): string {
  return `<!doctype html><html><head><meta charset="utf-8"><base target="_blank"><style>html,body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#18181b;background:#fff;overflow:auto}body{padding:16px}img{max-width:100%;height:auto}</style></head><body>${html}</body></html>`;
}

export default function EmailViewer({
  mailboxId,
  email,
  accounts,
  onClose,
  onRead,
}: Props) {
  const { content, loading, error } = useEmailContent(mailboxId, {
    account_id: email.account_id,
    provider_message_id: email.provider_message_id,
  });

  const readTriggered = useRef(false);
  useEffect(() => {
    if (readTriggered.current) return;
    if (email.is_read) return;
    readTriggered.current = true;
    onRead(email).catch(() => {});
  }, [email, onRead]);

  const { providerName, accountEmail } = resolveAccount(email.account_id, buildAccountMap(accounts));
  const fromLabel = email.from_name
    ? `${email.from_name} <${email.from_email}>`
    : email.from_email;

  const subject = email.subject ?? "(Sin asunto)";

  let body: React.ReactNode;
  if (loading) {
    body = (
      <div className="flex h-[70vh] items-center justify-center">
        <Spinner />
      </div>
    );
  } else if (error) {
    body = (
      <div className="flex h-[70vh] items-center justify-center px-6 text-center text-sm text-red-600">
        {error.message}
      </div>
    );
  } else if (content?.html_body) {
    body = (
      <iframe
        title="Contenido del correo"
        srcDoc={wrapHtmlEmail(content.html_body)}
        sandbox="allow-popups allow-popups-to-escape-sandbox"
        referrerPolicy="strict-origin-when-cross-origin"
        className="h-[70vh] w-full border-0"
      />
    );
  } else if (content?.text_body) {
    body = (
      <iframe
        title="Contenido del correo"
        srcDoc={wrapPlainText(content.text_body)}
        sandbox="allow-popups allow-popups-to-escape-sandbox"
        referrerPolicy="strict-origin-when-cross-origin"
        className="h-[70vh] w-full border-0"
      />
    );
  } else {
    body = (
      <div className="flex h-[70vh] items-center justify-center text-sm text-zinc-400">
        Este correo no tiene contenido.
      </div>
    );
  }

  return (
    <Modal open onClose={onClose} ariaLabel={`Correo: ${subject}`}>
      <div className="flex flex-col gap-1.5 border-b border-zinc-200 px-6 pt-6 pb-4 pr-14">
        <h2 className="text-[20px] font-semibold leading-tight tracking-tight text-zinc-900">
          {subject}
        </h2>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[13px] text-zinc-600">
          <span className="font-medium text-zinc-900">De:</span>
          <span className="truncate">{fromLabel}</span>
          <span className="text-zinc-300">·</span>
          <span>{formatDate(email.received_at)}</span>
        </div>
        {accountEmail && (
          <div className="flex items-center gap-2 text-[12px] text-zinc-500">
            <span className="font-medium">Cuenta:</span>
            <span>{providerName}</span>
            <span className="text-zinc-300">·</span>
            <span className="truncate">{accountEmail}</span>
          </div>
        )}
      </div>
      <div className="flex flex-1 flex-col overflow-auto bg-white">{body}</div>
    </Modal>
  );
}
