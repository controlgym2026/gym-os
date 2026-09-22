import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabaseClient";

/** member-media is a private bucket, so display needs a short-lived signed
 * URL rather than a public one. `path` is the storage path saved in
 * member.photo_url (e.g. "{tenant_id}/members/{member_id}/photo.jpg"). */
export default function MemberPhoto({
  path,
  size = 40,
}: {
  path: string | null;
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

  const style = { width: size, height: size };

  if (!url) {
    return (
      <div
        style={style}
        className="rounded-full bg-black/10 dark:bg-white/10 flex items-center justify-center text-xs opacity-60 shrink-0"
      >
        —
      </div>
    );
  }

  // Signed URLs are short-lived and per-viewer — next/image's remote-pattern
  // allowlist isn't a good fit here.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt="" style={style} className="rounded-full object-cover shrink-0" />;
}
