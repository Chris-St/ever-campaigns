"use client";

import { useEffect, useMemo, useRef, useState } from "react";

interface VoiceNoteCaptureProps {
  onComplete: (file: File) => Promise<void> | void;
  disabled?: boolean;
}

function chooseMimeType() {
  if (typeof MediaRecorder === "undefined") {
    return "";
  }
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? "";
}

function extensionForMimeType(mimeType: string) {
  if (mimeType.includes("mp4")) {
    return "m4a";
  }
  if (mimeType.includes("ogg")) {
    return "ogg";
  }
  return "webm";
}

export function VoiceNoteCapture({ onComplete, disabled = false }: VoiceNoteCaptureProps) {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const [supported] = useState(
    () =>
      typeof window !== "undefined" &&
      typeof MediaRecorder !== "undefined" &&
      Boolean(navigator.mediaDevices?.getUserMedia),
  );
  const [recording, setRecording] = useState(false);
  const [saving, setSaving] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [mimeType, setMimeType] = useState("");
  const [error, setError] = useState<string | null>(null);

  const audioUrl = useMemo(() => {
    if (!audioBlob) {
      return null;
    }
    return URL.createObjectURL(audioBlob);
  }, [audioBlob]);

  useEffect(() => {
    return () => {
      mediaRecorderRef.current?.stop();
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [audioUrl]);

  async function handleStart() {
    if (!supported || disabled) {
      return;
    }
    try {
      setError(null);
      setAudioBlob(null);
      chunksRef.current = [];
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const nextMimeType = chooseMimeType();
      const recorder = nextMimeType ? new MediaRecorder(stream, { mimeType: nextMimeType }) : new MediaRecorder(stream);
      setMimeType(nextMimeType || recorder.mimeType || "audio/webm");
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onerror = () => {
        setError("Voice note capture failed. Try again once the microphone is available.");
        setRecording(false);
      };
      recorder.onstop = () => {
        setRecording(false);
        mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
        if (!chunksRef.current.length) {
          return;
        }
        const blob = new Blob(chunksRef.current, { type: nextMimeType || recorder.mimeType || "audio/webm" });
        setAudioBlob(blob);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      setError("Microphone access was blocked. Allow mic access and try again.");
    }
  }

  function handleStop() {
    mediaRecorderRef.current?.stop();
  }

  async function handleSave() {
    if (!audioBlob) {
      return;
    }
    setSaving(true);
    setError(null);
    const extension = extensionForMimeType(mimeType || audioBlob.type || "audio/webm");
    const filename = `voice-note-${new Date().toISOString().replace(/[:.]/g, "-")}.${extension}`;
    const file = new File([audioBlob], filename, {
      type: mimeType || audioBlob.type || "audio/webm",
    });
    try {
      await onComplete(file);
      setAudioBlob(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to save the voice note.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={recording ? handleStop : () => void handleStart()}
          disabled={!supported || disabled || saving}
          className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {recording ? "Stop recording" : "Record voice note"}
        </button>
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={!audioBlob || saving || disabled}
          className="rounded-full bg-emerald-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {saving ? "Transcribing..." : "Save voice note"}
        </button>
        {!supported ? (
          <p className="text-xs text-slate-500">
            Voice notes need microphone access and MediaRecorder support in this browser.
          </p>
        ) : null}
      </div>

      <div className="mt-4 rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-4 text-sm text-slate-300">
        <p className="leading-7">
          Record naturally. Ever uploads the audio and transcribes it on the server, which avoids the repeated
          browser speech-text bug and gives the agent a cleaner brief.
        </p>
        {audioUrl ? (
          <audio controls src={audioUrl} className="mt-4 w-full">
            <track kind="captions" />
          </audio>
        ) : (
          <p className="mt-3 text-slate-500">{recording ? "Recording..." : "No voice note captured yet."}</p>
        )}
      </div>

      {error ? <p className="mt-3 text-sm text-amber-200">{error}</p> : null}
    </div>
  );
}
