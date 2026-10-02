import { useCallback, useEffect, useRef, useState } from "react";

const MAX_DIMENSION = 640; // plenty for the ~140px identification photo at 2x, keeps uploads small
const JPEG_QUALITY = 0.85;

type Mode = "idle" | "camera" | "captured";

/** Center-square crop + downscale + JPEG re-encode, shared by the webcam and
 * file-pick paths. Square because every display of a member photo (big
 * identification photo or small list avatar) is an `object-cover` crop, and
 * a phone photo is 3–5MB of detail nobody is going to look at. */
function drawToJpeg(
  source: HTMLVideoElement | HTMLImageElement,
  sourceWidth: number,
  sourceHeight: number,
): Promise<Blob> {
  const side = Math.min(sourceWidth, sourceHeight);
  const sx = (sourceWidth - side) / 2;
  const sy = (sourceHeight - side) / 2;
  const out = Math.min(side, MAX_DIMENSION);

  const canvas = document.createElement("canvas");
  canvas.width = out;
  canvas.height = out;
  const ctx = canvas.getContext("2d");
  if (!ctx) return Promise.reject(new Error("Could not process the image"));
  ctx.drawImage(source, sx, sy, side, side, 0, 0, out, out);

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Could not process the image"))),
      "image/jpeg",
      JPEG_QUALITY,
    );
  });
}

function fileToSquareJpeg(file: File): Promise<File> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = async () => {
      try {
        const blob = await drawToJpeg(img, img.naturalWidth, img.naturalHeight);
        resolve(new File([blob], "photo.jpg", { type: "image/jpeg" }));
      } catch (err) {
        reject(err);
      } finally {
        URL.revokeObjectURL(url);
      }
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("That file isn't a readable image"));
    };
    img.src = url;
  });
}

function cameraErrorMessage(err: unknown): string {
  const name = err instanceof Error ? err.name : "";
  if (name === "NotAllowedError")
    return "Camera access was blocked. Allow it in your browser's address-bar permissions, or use “Choose file” instead.";
  if (name === "NotFoundError" || name === "DevicesNotFoundError")
    return "No camera found on this device. Use “Choose file” instead — on a phone that opens the camera.";
  if (name === "NotReadableError")
    return "The camera is already in use by another app. Close it and try again.";
  return "Could not start the camera. Use “Choose file” instead.";
}

/** Capture a member photo from the webcam, or pick/shoot one via the file
 * picker (which opens the camera directly on a phone). Hands the parent a
 * ready-to-upload square JPEG `File`; the parent owns the actual upload. */
export default function PhotoCapture({
  onPhotoChange,
  existingPreview,
  label = "Photo",
}: {
  onPhotoChange: (file: File | null) => void;
  existingPreview?: React.ReactNode;
  label?: string;
}) {
  const [mode, setMode] = useState<Mode>("idle");
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previewRef = useRef<string | null>(null);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  // Releasing the camera and the preview blob matters here — a live webcam
  // light left on after the form closes reads as the app spying on you.
  useEffect(() => {
    return () => {
      stopCamera();
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    };
  }, [stopCamera]);

  function setPreviewUrl(url: string | null) {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = url;
    setPreview(url);
  }

  async function startCamera() {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser can't use the camera here. Use “Choose file” instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 960 } },
      });
      streamRef.current = stream;
      setMode("camera");
      // The <video> only exists once mode is "camera", so attach after paint.
      requestAnimationFrame(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
      });
    } catch (err) {
      setError(cameraErrorMessage(err));
    }
  }

  async function capture() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    setBusy(true);
    try {
      const blob = await drawToJpeg(video, video.videoWidth, video.videoHeight);
      const file = new File([blob], "photo.jpg", { type: "image/jpeg" });
      stopCamera();
      setPreviewUrl(URL.createObjectURL(blob));
      setMode("captured");
      onPhotoChange(file);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not capture the photo");
    } finally {
      setBusy(false);
    }
  }

  function cancelCamera() {
    stopCamera();
    setMode("idle");
  }

  async function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0];
    e.target.value = ""; // allow re-picking the same file
    if (!picked) return;
    setError(null);
    setBusy(true);
    try {
      const file = await fileToSquareJpeg(picked);
      setPreviewUrl(URL.createObjectURL(file));
      setMode("captured");
      onPhotoChange(file);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read that image");
    } finally {
      setBusy(false);
    }
  }

  function clearPhoto() {
    setPreviewUrl(null);
    setMode("idle");
    onPhotoChange(null);
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm">{label}</span>

      <div className="flex items-center gap-3 flex-wrap">
        {mode === "captured" && preview ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="" className="w-36 h-36 rounded-xl object-cover border" />
        ) : mode === "idle" ? (
          existingPreview ?? <div className="w-36 h-36 rounded-xl border border-dashed" />
        ) : null}

        {mode === "camera" && (
          <div className="flex flex-col gap-2">
            <video
              ref={videoRef}
              playsInline
              muted
              className="w-64 h-64 rounded-lg object-cover bg-black"
              style={{ transform: "scaleX(-1)" }} /* mirror: a selfie view people expect */
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={capture}
                disabled={busy}
                className="rounded bg-yellow-400 text-black px-3 py-1.5 text-sm disabled:opacity-50"
              >
                {busy ? "…" : "Capture"}
              </button>
              <button type="button" onClick={cancelCamera} className="rounded border px-3 py-1.5 text-sm">
                Cancel
              </button>
            </div>
          </div>
        )}

        {mode !== "camera" && (
          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={startCamera}
              disabled={busy}
              className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
            >
              📷 {mode === "captured" ? "Retake" : "Use camera"}
            </button>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
              className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
            >
              {busy ? "…" : "Choose file"}
            </button>
            {mode === "captured" && (
              <button type="button" onClick={clearPhoto} className="rounded border px-3 py-1.5 text-sm">
                Remove
              </button>
            )}
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="user" /* on a phone this opens the camera straight away */
          hidden
          onChange={handleFilePick}
        />
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}
    </div>
  );
}
