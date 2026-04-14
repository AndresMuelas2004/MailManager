export type Provider = "gmail" | "outlook";

export type ProviderMeta = {
  id: Provider;
  label: string;
  friendlyName: string;
  dotClass: string;
  headerBgClass: string;
  headerTextClass: string;
  accentTextClass: string;
};

export const PROVIDER_META: Record<Provider, ProviderMeta> = {
  gmail: {
    id: "gmail",
    label: "Gmail",
    friendlyName: "Google",
    dotClass: "bg-red-500",
    headerBgClass: "bg-red-50",
    headerTextClass: "text-red-600",
    accentTextClass: "text-red-600",
  },
  outlook: {
    id: "outlook",
    label: "Outlook",
    friendlyName: "Microsoft",
    dotClass: "bg-blue-600",
    headerBgClass: "bg-blue-50",
    headerTextClass: "text-blue-600",
    accentTextClass: "text-blue-600",
  },
};

const FALLBACK: ProviderMeta = {
  id: "gmail",
  label: "Unknown",
  friendlyName: "Unknown",
  dotClass: "bg-gray-400",
  headerBgClass: "bg-gray-50",
  headerTextClass: "text-gray-600",
  accentTextClass: "text-gray-600",
};

export function getProviderMeta(provider: string): ProviderMeta {
  return PROVIDER_META[provider as Provider] ?? FALLBACK;
}

export function isGenericLabel(label: string, provider: string): boolean {
  const meta = getProviderMeta(provider);
  return label === meta.label || label.toLowerCase() === provider.toLowerCase();
}

export const PROVIDER_OPTIONS: ProviderMeta[] = Object.values(PROVIDER_META);
