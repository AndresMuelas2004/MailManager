import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { createMailbox } from "../api/endpoints/mailboxes";

export default function MailboxesPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const trimmedName = name.trim();
  const isDisabled = trimmedName.length === 0 || isSubmitting;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (isDisabled) {
      return;
    }

    setErrorMsg("");
    try {
      setIsSubmitting(true);
      const mailbox = await createMailbox({ display_name: trimmedName });
      const mailboxId = mailbox.mailbox_id;

      localStorage.setItem("lastMailboxId", String(mailboxId));
      navigate(`/m/${mailboxId}/inbox`);
    } catch (error) {
      console.error("Failed to create mailbox.", error);
      setErrorMsg("No pudimos crear la bandeja. Intenta nuevamente.");
      setName("");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="px-4 py-12 flex items-center justify-center">
      <div className="w-full max-w-xl rounded-2xl border border-slate-100 bg-white p-8 sm:p-10 shadow-[0_12px_30px_rgba(15,23,42,0.08)]">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="mailbox-name" className="text-lg font-semibold text-slate-800">
              Nombre de bandeja
            </label>
            <input
              id="mailbox-name"
              type="text"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                if (errorMsg) {
                  setErrorMsg("");
                }
              }}
              placeholder="Ingrese el nombre de la bandeja"
              className="mt-3 w-full rounded-lg border border-slate-200 px-4 py-3 text-base text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
            {errorMsg ? <p className="mt-2 text-sm text-red-600">{errorMsg}</p> : null}
          </div>
          <button
            type="submit"
            disabled={isDisabled}
            className={`w-full rounded-lg py-3 text-base font-semibold text-white transition-colors ${
              isDisabled ? "cursor-not-allowed bg-slate-300" : "bg-blue-600 hover:bg-blue-700"
            }`}
          >
            Crear bandeja
          </button>
        </form>
      </div>
    </div>
  );
}
