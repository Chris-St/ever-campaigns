"use client";

import { useEffect, useRef, useState } from "react";

declare global {
  interface Window {
    webkitSpeechRecognition?: new () => SpeechRecognition;
    SpeechRecognition?: new () => SpeechRecognition;
  }
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

interface SpeechRecognitionEvent {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      0: {
        transcript: string;
      };
    };
  };
}

interface SpeechRecognitionErrorEvent {
  error: string;
}

interface VoiceNoteCaptureProps {
  onComplete: (transcript: string) => void;
}

export function VoiceNoteCapture({ onComplete }: VoiceNoteCaptureProps) {
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const [supported] = useState(
    () => typeof window !== "undefined" && Boolean(window.SpeechRecognition ?? window.webkitSpeechRecognition),
  );
  const [listening, setListening] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) {
      return;
    }
    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      let nextDraft = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        nextDraft += event.results[index][0].transcript;
      }
      setDraft((current) => `${current} ${nextDraft}`.trim());
    };
    recognition.onerror = (event) => {
      setError(`Voice capture stopped: ${event.error}`);
      setListening(false);
    };
    recognition.onend = () => {
      setListening(false);
    };
    recognitionRef.current = recognition;
    return () => {
      recognition.stop();
    };
  }, []);

  function handleStart() {
    if (!recognitionRef.current) {
      return;
    }
    setError(null);
    setListening(true);
    setDraft("");
    recognitionRef.current.start();
  }

  function handleStop() {
    recognitionRef.current?.stop();
    setListening(false);
  }

  return (
    <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={listening ? handleStop : handleStart}
          disabled={!supported}
          className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {listening ? "Stop voice note" : "Start voice note"}
        </button>
        <button
          type="button"
          onClick={() => {
            const value = draft.trim();
            if (!value) {
              return;
            }
            onComplete(value);
            setDraft("");
            setError(null);
          }}
          disabled={!draft.trim()}
          className="rounded-full bg-emerald-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Save transcript
        </button>
        {!supported ? <p className="text-xs text-slate-500">Browser speech-to-text is not available here.</p> : null}
      </div>
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="Talk through brand context, claims, customer language, or constraints. You can edit the transcript before saving."
        className="mt-4 min-h-[140px] w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
      />
      {error ? <p className="mt-3 text-sm text-amber-200">{error}</p> : null}
    </div>
  );
}
