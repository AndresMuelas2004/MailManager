type Props = {
  size?: "sm" | "md";
  color?: "blue" | "white";
};

export default function Spinner({ size = "md", color = "blue" }: Props) {
  const sizeClass = size === "sm" ? "h-4 w-4 border-2" : "h-8 w-8 border-4";
  const colorClass =
    color === "white"
      ? "border-white border-t-transparent"
      : "border-blue-600 border-t-transparent";

  return <div className={`animate-spin rounded-full ${sizeClass} ${colorClass}`} />;
}
