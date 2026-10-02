import { supabase } from "./supabaseClient";
import { apiFetch } from "./api";

/** Uploads a member photo to the private `member-media` bucket and saves the
 * resulting storage path to member.photo_url. The bucket's RLS policies scope
 * access by the path's first segment (tenant_id), so that prefix is required,
 * not cosmetic — see supabase/migrations/20260910134957_storage_member_media.sql.
 *
 * PhotoCapture always hands us a re-encoded square JPEG, so the extension is
 * fixed; re-uploading to the same path replaces the old photo rather than
 * accumulating orphans. Returns the stored path. */
export async function uploadMemberPhoto({
  file,
  tenantId,
  memberId,
  token,
}: {
  file: File;
  tenantId: string;
  memberId: string;
  token: string;
}): Promise<string> {
  const path = `${tenantId}/members/${memberId}/photo.jpg`;
  const { error } = await supabase.storage
    .from("member-media")
    .upload(path, file, { upsert: true, contentType: "image/jpeg" });
  if (error) throw new Error(`Photo upload failed: ${error.message}`);

  await apiFetch(`/members/${memberId}`, {
    method: "PATCH",
    token,
    body: { photo_url: path },
  });
  return path;
}
