import { useState, useRef, useCallback, useEffect, CSSProperties } from "react";
import { createPortal } from "react-dom";
import { useDisasterDemo } from "../state/DisasterDemoContext";

// ── Constants ─────────────────────────────────────────────────────────────────
const WS_URL = "ws://localhost:8000/api/v1/realtime/ws";
const USER_ID = "demo-user-001";
const SAMPLE_RATE = 24_000;

// ── Types ─────────────────────────────────────────────────────────────────────
type Phase = "idle" | "connecting" | "ready" | "listening" | "speaking" | "error";

interface VoiceWidgetProps {
  wsUrl?: string;
  userId?: string;
}

interface ServerMessage {
  type: string;
  transcript?: string;
  delta?: string;
}

interface IconProps {
  size?: number;
  color?: string;
}

interface WaveSVGProps {
  active: boolean;
  level?: number;
}

// ── Audio helpers ─────────────────────────────────────────────────────────────
function encodeAudioToPCM16(float32Array: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

function base64ToFloat32(b64: string): Float32Array<ArrayBuffer> {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const int16 = new Int16Array(bytes.buffer);
  const out = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) out[i] = int16[i] / 32_768;
  return out;
}

function resampleTo24k(input: Float32Array<ArrayBufferLike>, srcRate: number): Float32Array<ArrayBuffer> {
  if (srcRate === SAMPLE_RATE) return input as Float32Array<ArrayBuffer>;
  const ratio = srcRate / SAMPLE_RATE;
  const out = new Float32Array(Math.round(input.length / ratio));
  for (let i = 0; i < out.length; i++) out[i] = input[Math.round(i * ratio)] ?? 0;
  return out;
}

// ── Icons ─────────────────────────────────────────────────────────────────────
function MicSVG({ size = 16, color = "currentColor" }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none">
      <rect x="5" y="1" width="6" height="9" rx="3" fill={color} />
      <path
        d="M2 8c0 3.314 2.686 6 6 6s6-2.686 6-6"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        fill="none"
      />
      <line x1="8" y1="14" x2="8" y2="15.5" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function StopSVG({ size = 14, color = "currentColor" }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <rect x="2" y="2" width="10" height="10" rx="2" fill={color} />
    </svg>
  );
}

function WaveSVG({ active, level = 0 }: WaveSVGProps) {
  const bars: number[] = [0.4, 0.7, 1, 0.7, 0.4];
  return (
    <svg width="32" height="16" viewBox="0 0 32 16" style={{ display: "block" }}>
      {bars.map((base, i) => {
        const h = active ? Math.max(3, base * (6 + level * 10)) : base * 4;
        const y = (16 - h) / 2;
        return (
          <rect
            key={i}
            x={i * 7 + 1}
            y={y}
            width="4"
            height={h}
            rx="2"
            fill="var(--color-text-secondary)"
            opacity={active ? 0.9 : 0.35}
          />
        );
      })}
    </svg>
  );
}

// ── Main widget ───────────────────────────────────────────────────────────────
export default function VoiceWidget({ wsUrl = WS_URL, userId = USER_ID }: VoiceWidgetProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [lastUserText, setLastUserText] = useState("");
  const [lastAIText, setLastAIText] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [level, setLevel] = useState(0);
  const [isRecording, setIsRecording] = useState(false);
  const { currentStepIndex } = useDisasterDemo();
  const [isMinimized, setIsMinimized] = useState(false);
  const [portalEl, setPortalEl] = useState<HTMLElement | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && window.innerWidth < 640) {
      setIsMinimized(true);
    }

    if (typeof document === "undefined") return;
    const el = document.createElement("div");
    el.style.position = "fixed";
    el.style.inset = "auto";
    el.style.zIndex = "9999";
    document.body.appendChild(el);
    setPortalEl(el);
    requestAnimationFrame(() => setIsVisible(true));
    return () => {
      document.body.removeChild(el);
      setPortalEl(null);
    };
  }, []);

  const handleMinimize = () => {
    setIsVisible(false);
    setIsMinimized(true);
  };

  const handleExpand = () => {
    setIsMinimized(false);
    requestAnimationFrame(() => setIsVisible(true));
  };

  useEffect(() => {
    if (!isMinimized) {
      requestAnimationFrame(() => setIsVisible(true));
    } else {
      setIsVisible(false);
    }
  }, [isMinimized]);

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animRef = useRef<number>(0);
  const nextPlayRef = useRef<number>(0);
  const isPlayingRef = useRef<boolean>(false);
  const audioQueueRef = useRef<AudioBuffer[]>([]);
  const aiTextRef = useRef<string>("");
  const recordingRef = useRef(false)

  const getCtx = (): AudioContext => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioContext({ sampleRate: SAMPLE_RATE });
    }
    return audioCtxRef.current;
  };

  const drainQueue = useCallback((): void => {
    const ctx = getCtx();
    if (!audioQueueRef.current.length) {
      isPlayingRef.current = false;
      return;
    }
    isPlayingRef.current = true;
    const buf = audioQueueRef.current.shift()!;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    const t = Math.max(ctx.currentTime, nextPlayRef.current);
    src.start(t);
    nextPlayRef.current = t + buf.duration;
    src.onended = drainQueue;
  }, []);

  const scheduleAudio = useCallback(
    (f32: Float32Array<ArrayBuffer>): void => {
      const ctx = getCtx();
      const buf = ctx.createBuffer(1, f32.length, SAMPLE_RATE);
      buf.copyToChannel(f32, 0);
      audioQueueRef.current.push(buf);
      if (!isPlayingRef.current) drainQueue();
    },
    [drainQueue],
  );

  const handleMsg = useCallback(
    (msg: ServerMessage): void => {
      switch (msg.type) {
        case "conversation.item.input_audio_transcription.completed": {
          const t = msg.transcript?.trim();
          if (t) setLastUserText(t);
          aiTextRef.current = "";
          setLastAIText("");
          break;
        }
        case "response.audio_transcript.delta": {
          aiTextRef.current += msg.delta ?? "";
          setLastAIText(aiTextRef.current);
          break;
        }
        case "response.audio.delta": {
          if (msg.delta) scheduleAudio(base64ToFloat32(msg.delta));
          setPhase("speaking");
          break;
        }
        case "response.audio.done":
        case "response.done":
          setPhase("ready");
          break;
        case "input_audio_buffer.speech_started":
          setPhase("listening");
          break;
        default:
          break;
      }
    },
    [scheduleAudio],
  );

  const stopMic = useCallback((): void => {
    cancelAnimationFrame(animRef.current);
    processorRef.current?.disconnect();
    processorRef.current = null;
    analyserRef.current?.disconnect();
    analyserRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setLevel(0);
  }, []);

  const startMic = useCallback(async (): Promise<void> => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const ctx = getCtx();
      await ctx.resume();
      const src = ctx.createMediaStreamSource(stream);

      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      src.connect(analyser);
      analyserRef.current = analyser;

      const processor = ctx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;
      src.connect(processor);
      processor.connect(ctx.destination);

      processor.onaudioprocess = (e: AudioProcessingEvent): void => {
  if (!recordingRef.current) return

  if (wsRef.current?.readyState !== WebSocket.OPEN) return

  const raw = e.inputBuffer.getChannelData(0)
  const resampled = resampleTo24k(raw, ctx.sampleRate)
  const pcm = encodeAudioToPCM16(resampled)
  const b64 = btoa(String.fromCharCode(...new Uint8Array(pcm)))

  wsRef.current.send(JSON.stringify({
    type: "input_audio_buffer.append",
    audio: b64
  }))
}

      const tick = (): void => {
        if (!analyserRef.current) return;
        const data = new Uint8Array(analyserRef.current.frequencyBinCount);
        analyserRef.current.getByteFrequencyData(data);
        setLevel(data.reduce((a, b) => a + b, 0) / data.length / 128);
        animRef.current = requestAnimationFrame(tick);
      };
      animRef.current = requestAnimationFrame(tick);
    } catch {
      setErrorMsg("Microphone access denied.");
      setPhase("error");
    }
  }, []);

  const connect = useCallback(async (): Promise<void> => {
    setPhase("connecting");
    setErrorMsg("");
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = (): void => {
      ws.send(JSON.stringify({ user_id: userId, step_index: currentStepIndex }));
      ws.send(
        JSON.stringify({
          type: "session.update",
          session: {
            turn_detection: { type: "server_vad", threshold: 0.5, silence_duration_ms: 600 },
            input_audio_transcription: { model: "whisper-1" },
          },
        }),
      );
      setPhase("ready");
      startMic();
    };

    ws.onclose = (): void => {
      stopMic();
      setPhase("idle");
    };

    ws.onerror = (): void => {
      setErrorMsg("Connection failed.");
      setPhase("error");
    };

    ws.onmessage = (e: MessageEvent<string>): void => {
      try {
        handleMsg(JSON.parse(e.data) as ServerMessage);
      } catch {
        // ignore malformed frames
      }
    };
  }, [wsUrl, userId, currentStepIndex, startMic, stopMic, handleMsg]);

  const disconnect = useCallback((): void => {
    stopMic();
    wsRef.current?.close();
    wsRef.current = null;
    setPhase("idle");
    setLastUserText("");
    setLastAIText("");
    aiTextRef.current = "";
  }, [stopMic]);

  const stopTalking = () => {
  recordingRef.current = false
  setIsRecording(false)
  setPhase("ready")

  wsRef.current?.send(JSON.stringify({
    type: "input_audio_buffer.commit"
  }))
}

  const startTalking = () => {
  recordingRef.current = true
  setIsRecording(true)
  setPhase("listening")

  wsRef.current?.send(JSON.stringify({
    type: "response.cancel"
  }))
}

  useEffect(() => () => disconnect(), [disconnect]);

  useEffect(() => {
    const connected = (["ready", "listening", "speaking"] as Phase[]).includes(phase);
    if (connected && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "meta.step", step_index: currentStepIndex }));
    }
  }, [currentStepIndex, phase]);

  // ── Derived ──────────────────────────────────────────────────────────────────
  const isConnected = (["ready", "listening", "speaking"] as Phase[]).includes(phase);

  const statusLabel: Record<Phase, string> = {
    idle: "Click to connect",
    connecting: "Connecting…",
    ready: "Hold to talk",
    listening: "Listening",
    speaking: "Speaking",
    error: errorMsg || "Error",
  };

  const dotColor: Record<Phase, string> = {
    idle: "var(--color-border-secondary)",
    connecting: "#EF9F27",
    ready: "#1D9E75",
    listening: "#1D9E75",
    speaking: "#378ADD",
    error: "#E24B4A",
  };

  const expanded = (
    <div style={{ ...s.card, ...(isVisible ? s.cardShow : {}) }}>
      <div style={s.topRow}>
        <div style={s.statusGroup}>
          <span
            style={{
              ...s.dot,
              background: dotColor[phase],
              boxShadow: isConnected ? `0 0 0 3px ${dotColor[phase]}22` : "none",
            }}
          />
          <span style={s.statusText}>{statusLabel[phase]}</span>
        </div>

        <div style={s.buttonRow}>
        <button
          onClick={!isConnected ? connect : undefined}
          onMouseDown={isConnected ? startTalking : undefined}
          onMouseUp={isConnected ? stopTalking : undefined}
          onMouseLeave={isConnected ? stopTalking : undefined}
          onTouchStart={isConnected ? startTalking : undefined}
          onTouchEnd={isConnected ? stopTalking : undefined}
          disabled={phase === "connecting"}
          style={{
            ...s.actionBtn,
            background: "#f7f8fb",
            color: "#1f1f1f",
            borderColor: "#1f1f1f",
            opacity: phase === "connecting" ? 0.55 : 1,
            position: "relative",
          }}
        >
          {!isRecording && <MicSVG size={14} color="currentColor" />}
          {isRecording && <WaveSVG active={isRecording} level={level} />}
        </button>

        <button
          onClick={disconnect}
          disabled={phase === "idle" || phase === "connecting"}
          aria-label="Disconnect"
          style={{
            ...s.iconBtn,
            opacity: phase === "idle" || phase === "connecting" ? 0.45 : 1,
          }}
        >
          <StopSVG size={12} color="currentColor" />
        </button>

        <button
          onClick={handleMinimize}
          aria-label="Minimize voice controls"
          style={{
            ...s.iconBtn,
            borderColor: "var(--color-border-secondary)",
            background: "var(--color-background-primary)",
            color: "var(--color-text-secondary)",
          }}
        >
          ▾
        </button>
        </div>
      </div>

      {(lastUserText || lastAIText) && (
        <div style={s.transcript}>
          {lastUserText && (
            <div style={s.turn}>
              <span style={s.turnLabel}>You</span>
              <span style={s.turnText}>{lastUserText}</span>
            </div>
          )}
          {lastAIText && (
            <div style={s.turn}>
              <span style={{ ...s.turnLabel, color: "var(--color-text-info)" }}>Assistant</span>
              <span style={s.turnText}>{lastAIText}</span>
            </div>
          )}
        </div>
      )}

      {phase === "error" && <p style={s.errorText}>{errorMsg}</p>}
    </div>
  );

  const minimized = (
    <button onClick={handleExpand} aria-label="Expand voice controls" style={s.minFab}>
      <svg width={0} height={0} style={{ position: "absolute", inset: 0 }}>
        <defs>
          <linearGradient id="mic-gradient" x1="0%" y1="100%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#0379d1" />
            <stop offset="100%" stopColor="#0cba75" />
          </linearGradient>
        </defs>
      </svg>
      <div style={s.minFabIcon}>
        <MicSVG size={24} color="url(#mic-gradient)" />
      </div>
    </button>
  );
  const widget = isMinimized ? minimized : expanded;

  if (portalEl) {
    return createPortal(widget, portalEl);
  }

  return widget;
}

// ── Styles ────────────────────────────────────────────────────────────────────
const s: Record<string, CSSProperties> = {
  card: {
    position: "fixed",
    left: "auto",
    right: 16,
    bottom: 64,
    zIndex: 9999,
    border: "0.5px solid var(--color-border-tertiary)",
    borderRadius: 18,
    background: "#ffffff",
    padding: "14px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 10,
    maxWidth: 360,
    width: "50vw",
    boxShadow: "0 12px 32px rgba(0,0,0,0.14)",
    fontFamily: "var(--font-sans)",
    opacity: 0,
    transform: "translateY(8px)",
    transition: "opacity 0.18s ease, transform 0.18s ease",
  },
  cardShow: {
    opacity: 1,
    transform: "translateY(0)",
  },
  cardMinimized: {
    padding: "8px 10px",
    width: 68,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  minFab: {
    position: "fixed",
    right: 16,
    bottom: 64,
    zIndex: 9999,
    width: 55,
    height: 45,
    borderRadius: 18,
    border: "1px solid var(--color-border-info)",
    background: "#ffffff",
    color: "#1f1f1f",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    boxShadow: "0 12px 30px rgba(0,0,0,0.18)",
    cursor: "pointer",
    gap: 0,
    transition: "opacity 0.15s ease, transform 0.18s ease",
  },
  minFabMic: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  minFabIcon: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: 32,
    height: 32,
  },
  topRow: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 12,
  },
  statusGroup: {
    display: "flex",
    alignItems: "center",
    gap: 7,
  },
  buttonRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    width: "100%",
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    flexShrink: 0,
    transition: "background 0.3s, box-shadow 0.3s",
    display: "inline-block",
  },
  statusText: {
    fontSize: 13,
    color: "var(--color-text-secondary)",
    fontWeight: 500,
  },
  actionBtn: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    padding: "8px 14px",
    borderRadius: 10,
    border: "1px solid #d7deea",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    flexShrink: 0,
    transition: "opacity 0.15s, box-shadow 0.2s, transform 0.15s",
    lineHeight: 1,
    minWidth: 46,
    minHeight: 34,
    position: "relative",
    background: "linear-gradient(135deg, #f7f9fc 0%, #ffffff 100%)",
  },
  iconBtn: {
    width: 32,
    height: 32,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 10,
    border: "1px solid #c44141",
    background: "linear-gradient(135deg, #fdeaea 0%, #fff5f5 100%)",
    color: "#c44141",
    cursor: "pointer",
    transition: "opacity 0.15s, background 0.2s, border-color 0.2s",
  },
  waveOverlay: {
    position: "absolute",
    inset: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    pointerEvents: "none",
  },
  transcript: {
    borderTop: "0.5px solid var(--color-border-tertiary)",
    paddingTop: 10,
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  turn: {
    display: "flex",
    flexDirection: "column",
    gap: 2,
  },
  turnLabel: {
    fontSize: 11,
    fontWeight: 500,
    color: "var(--color-text-tertiary)",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  turnText: {
    fontSize: 13,
    color: "var(--color-text-primary)",
    lineHeight: 1.5,
  },
  errorText: {
    margin: 0,
    fontSize: 12,
    color: "var(--color-text-danger)",
  },
};



