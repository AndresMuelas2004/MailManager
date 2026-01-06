export default function InboxPage() {
  return (
    <div className="px-4 py-12 flex items-start justify-center">
      <div className="w-full max-w-xl rounded-2xl border border-slate-100 bg-white p-8 sm:p-10 shadow-[0_12px_30px_rgba(15,23,42,0.08)]">
        <p className="text-lg text-slate-700">No hay correos todavía</p>
        <button
          type="button"
          className="mt-6 w-full rounded-lg bg-blue-600 px-4 py-3 text-base font-semibold text-white hover:bg-blue-700"
        >
          Añadir cuenta
        </button>
      </div>
    </div>
  );
}
