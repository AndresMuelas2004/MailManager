const MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

export function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
  }
  return `${d.getDate()} ${MONTHS_ES[d.getMonth()]}`;
}

export function formatShortDate(dateStr: string): string {
  const d = new Date(dateStr);
  return `${d.getDate()} ${MONTHS_ES[d.getMonth()]}`;
}

export function resolveAccount(
  accountId: string,
  accounts: { account_id: string; provider: string; email_address: string | null; display_label: string }[],
): { providerName: string; accountEmail: string } {
  const acc = accounts.find((a) => a.account_id === accountId);
  return {
    providerName: acc ? (acc.provider === "gmail" ? "Google" : "Microsoft") : "",
    accountEmail: acc?.email_address ?? acc?.display_label ?? "",
  };
}
