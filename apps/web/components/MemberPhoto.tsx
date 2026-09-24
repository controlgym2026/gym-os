import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabaseClient";

const AVATAR_COLORS = [
  "bg-emerald-600",
  "bg-teal-600",
  "bg-blue-600",
  "bg-purple-600",
  "bg-rose-600",
  "bg-amber-600",
];

function colorFor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

/** member-media is a private bucket, so display needs a short-lived signed
 * URL rather than a public one. `path` is the storage path saved in
 * member.photo_url (e.g. "{tenant_id}/members/{member_id}/photo.jpg").
 * Falls back to an initial-letter avatar (colored by name) when there's no
 * photo, rather than a blank placeholder. */
export default function MemberPhoto({
  path,
  name = "",
  size = 40,
}: {
  path: string | null;
  name?: string;
  size?: number;
}) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!path) {
      setUrl(null);
      return;
    }
    supabase.storage
      .from("member-media")
      .createSignedUrl(path, 3600)
      .then(({ data }) => {
        if (!cancelled) setUrl(data?.signedUrl ?? null);
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  const style = { width: size, height: size, fontSize: Math.max(10, size * 0.4) };

  if (!url) {
    const initial = name.trim().charAt(0).toUpperCase() || "?";
    return (
      <div
        style={style}
        className={`rounded-full flex items-center justify-center font-semibold text-white shrink-0 ${colorFor(name || "?")}`}
      >
        {initial}
      </div>
    );
  }

  // Signed URLs are short-lived and per-viewer — next/image's remote-pattern
  // allowlist isn't a good fit here.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt="" style={style} className="rounded-full object-cover shrink-0" />;
}
