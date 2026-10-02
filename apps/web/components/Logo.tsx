/** "Gym Control" wordmark — a custom black/yellow barbell badge plus the
 * name and the "Product of Livnexa Care Pvt Ltd" tagline. `variant`
 * controls the wordmark/tagline text color for whichever background it
 * sits on: "dark" for the black nav bar, "light" for white page
 * backgrounds (login/signup) — the badge itself is self-contained and
 * doesn't need to change either way. */
export default function Logo({
  variant = "dark",
  size = "md",
}: {
  variant?: "dark" | "light";
  size?: "sm" | "md" | "lg";
}) {
  const iconPx = size === "lg" ? 44 : size === "sm" ? 28 : 36;
  const wordmarkClass = size === "lg" ? "text-2xl" : size === "sm" ? "text-sm" : "text-lg";
  const taglineClass = size === "lg" ? "text-xs" : "text-[10px]";
  const wordmarkColor = variant === "dark" ? "text-yellow-400" : "text-black";
  const taglineColor = variant === "dark" ? "text-yellow-100/70" : "text-gray-500";

  return (
    <span className="inline-flex items-center gap-2">
      <BarbellBadge size={iconPx} />
      <span className="flex flex-col leading-tight">
        <span className={`font-extrabold tracking-wide ${wordmarkClass} ${wordmarkColor}`}>GYM CONTROL</span>
        <span className={`${taglineClass} ${taglineColor}`}>Product of Livnexa Care Pvt Ltd</span>
      </span>
    </span>
  );
}

function BarbellBadge({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" className="shrink-0" aria-hidden="true">
      <rect x="2" y="2" width="44" height="44" rx="10" fill="#000000" />
      <rect x="2" y="2" width="44" height="44" rx="10" fill="none" stroke="#facc15" strokeWidth="2" />
      {/* barbell: bar + two graduated weight plates each side */}
      <rect x="7" y="21" width="4" height="10" rx="1" fill="#facc15" />
      <rect x="12" y="19" width="3" height="14" rx="1" fill="#facc15" />
      <rect x="15" y="23" width="18" height="2" fill="#facc15" />
      <rect x="33" y="19" width="3" height="14" rx="1" fill="#facc15" />
      <rect x="37" y="21" width="4" height="10" rx="1" fill="#facc15" />
    </svg>
  );
}
