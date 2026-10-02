import Image from "next/image";

/** The real "Gym Control" artwork (apps/web/public/logo*.png), in two forms:
 *
 * - compact (default): just the icon mark (logo-mark.png) plus a plain-text
 *   "GYM CONTROL" wordmark + tagline styled for whatever's using it — this
 *   is what fits a thin horizontal nav bar, where the full lockup's tall
 *   stacked composition would shrink to illegible slivers.
 * - full: the designed lockup (logo-full.png — mark + wordmark + tagline +
 *   "Product of Livnexa Care Pvt Ltd", all baked into the artwork). Its
 *   wordmark is rendered in white/light-gray with no backing of its own, so
 *   it's only legible on a dark surface — this mode wraps it in a black
 *   card itself rather than relying on every caller to remember that.
 */
export default function Logo({
  full = false,
  size = "md",
}: {
  full?: boolean;
  size?: "sm" | "md" | "lg";
}) {
  if (full) {
    const px = size === "lg" ? 240 : size === "sm" ? 140 : 180;
    return (
      <div className="bg-black rounded-2xl p-6 inline-flex items-center justify-center">
        <Image
          src="/logo-full.png"
          alt="Gym Control — Product of Livnexa Care Pvt Ltd"
          width={640}
          height={640}
          style={{ width: px, height: "auto" }}
          priority
        />
      </div>
    );
  }

  const iconH = size === "lg" ? 48 : size === "sm" ? 28 : 36;
  const wordmarkClass = size === "lg" ? "text-2xl" : size === "sm" ? "text-sm" : "text-lg";
  const taglineClass = size === "lg" ? "text-xs" : "text-[10px]";

  return (
    <span className="inline-flex items-center gap-2">
      <Image
        src="/logo-mark.png"
        alt="Gym Control"
        width={400}
        height={265}
        style={{ height: iconH, width: "auto" }}
        priority
      />
      <span className="flex flex-col leading-tight">
        <span className={`font-extrabold tracking-wide text-yellow-400 ${wordmarkClass}`}>GYM CONTROL</span>
        <span className={`text-yellow-100/70 ${taglineClass}`}>Product of Livnexa Care Pvt Ltd</span>
      </span>
    </span>
  );
}
