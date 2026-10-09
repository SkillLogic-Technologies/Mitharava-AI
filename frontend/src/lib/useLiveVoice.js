// frontend/src/lib/useLiveVoice.js
//
// React hook for InterviewRoom's "Live Voice" mode — real-time, continuous
// conversation with the interviewer instead of record → upload → wait.
//
// WHY THIS EXISTS
//   The default pipeline (MediaRecorder -> Whisper STT -> text turn ->
//   browser SpeechSynthesis) is tap-to-talk and round-trips through several
//   HTTP calls per answer. This hook instead keeps one WebSocket open to
//   backend/voice_live.py, which itself holds one Gemini Live session open
//   for the whole interview: mic audio streams out continuously, spoken
//   audio streams back continuously, and Gemini's own voice-activity
//   detection decides when the candidate has finished talking. No taps.
//
// PROTOCOL — see backend/voice_live.py's module docstring for the full spec.
// Binary WS frames = raw PCM16 audio (16kHz out to Gemini, 24kHz back).
// Text WS frames = JSON control messages (ready/state/transcript/evaluation/error).
//
// KNOWN LIMITATION: no client-side barge-in yet — if the candidate starts
// talking while the interviewer's audio is still playing, that audio is not
// cut short. Gemini Live does support server-side interruption; wiring the
// client audio queue to stop on it is a follow-up, not done here.

import { useCallback, useRef, useState } from "react";

function wsBaseUrl() {
  const http = process.env.REACT_APP_BACKEND_URL || "";
  return http.replace(/^http/, "ws");
}

/** Downsamples a Float32 mic buffer (any input rate) to 16kHz PCM16 (Int16Array),
 * via simple linear interpolation — good enough for speech, no external deps. */
function downsampleTo16kPCM16(float32, inputSampleRate) {
  const targetRate = 16000;
  if (inputSampleRate === targetRate) {
    const out = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }
  const ratio = inputSampleRate / targetRate;
  const outLength = Math.floor(float32.length / ratio);
  const out = new Int16Array(outLength);
  for (let i = 0; i < outLength; i++) {
    const srcIdx = i * ratio;
    const i0 = Math.floor(srcIdx);
    const i1 = Math.min(i0 + 1, float32.length - 1);
    const frac = srcIdx - i0;
    const sample = float32[i0] * (1 - frac) + float32[i1] * frac;
    const s = Math.max(-1, Math.min(1, sample));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

export function useLiveVoice({ onTranscript, onEvaluation, onState, onError, onReady } = {}) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const audioCtxInRef = useRef(null);
  const processorRef = useRef(null);
  const micSourceRef = useRef(null);

  // --- playback (24kHz PCM16 coming back from the interviewer) ---
  const playCtxRef = useRef(null);
  const nextPlayTimeRef = useRef(0);
  const activeSourcesRef = useRef([]);

  const _ensurePlayCtx = () => {
    if (!playCtxRef.current) {
      playCtxRef.current = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
      nextPlayTimeRef.current = 0;
    }
    return playCtxRef.current;
  };

  const _enqueuePlayback = (int16Bytes) => {
    const ctx = _ensurePlayCtx();
    const int16 = new Int16Array(int16Bytes);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / (int16[i] < 0 ? 0x8000 : 0x7fff);

    const buffer = ctx.createBuffer(1, float32.length, 24000);
    buffer.copyToChannel(float32, 0);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    const startAt = Math.max(nextPlayTimeRef.current, now);
    source.start(startAt);
    nextPlayTimeRef.current = startAt + buffer.duration;

    activeSourcesRef.current.push(source);
    source.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
    };
  };

  const connect = useCallback(async (sessionId, micStream) => {
    const token = localStorage.getItem("mitharva_token");
    if (!token || !sessionId || !micStream) return;

    const ws = new WebSocket(`${wsBaseUrl()}/api/voice/live`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "auth", token, session_id: sessionId }));
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        _enqueuePlayback(event.data);
        return;
      }
      try {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
          case "ready":
            setConnected(true);
            onReady?.(msg);
            break;
          case "state":
            onState?.(msg.state);
            break;
          case "transcript":
            onTranscript?.(msg);
            break;
          case "evaluation":
            onEvaluation?.(msg);
            break;
          case "error":
            onError?.(msg.message);
            break;
          default:
            break;
        }
      } catch {
        // ignore malformed control frame
      }
    };

    ws.onerror = () => onError?.("Live voice connection error.");
    ws.onclose = () => setConnected(false);

    // Start streaming mic audio once the socket is open.
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    audioCtxInRef.current = audioCtx;
    const source = audioCtx.createMediaStreamSource(micStream);
    micSourceRef.current = source;

    // ScriptProcessorNode is deprecated but universally supported and needs
    // no separate worklet file to load — good enough for speech-rate audio.
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);
    processorRef.current = processor;
    processor.onaudioprocess = (e) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      const input = e.inputBuffer.getChannelData(0);
      const pcm16 = downsampleTo16kPCM16(input, audioCtx.sampleRate);
      ws.send(pcm16.buffer);
    };
    source.connect(processor);
    // Must connect to a destination for onaudioprocess to fire in most
    // browsers; route through a silent gain node so nothing is heard twice.
    const silence = audioCtx.createGain();
    silence.gain.value = 0;
    processor.connect(silence);
    silence.connect(audioCtx.destination);
  }, [onTranscript, onEvaluation, onState, onError, onReady]);

  const disconnect = useCallback(() => {
    try { wsRef.current?.send(JSON.stringify({ type: "end" })); } catch { /* noop */ }
    try { wsRef.current?.close(); } catch { /* noop */ }
    wsRef.current = null;

    try { processorRef.current?.disconnect(); } catch { /* noop */ }
    try { micSourceRef.current?.disconnect(); } catch { /* noop */ }
    try { audioCtxInRef.current?.close(); } catch { /* noop */ }
    processorRef.current = null;
    micSourceRef.current = null;
    audioCtxInRef.current = null;

    activeSourcesRef.current.forEach((s) => { try { s.stop(); } catch { /* noop */ } });
    activeSourcesRef.current = [];
    try { playCtxRef.current?.close(); } catch { /* noop */ }
    playCtxRef.current = null;
    nextPlayTimeRef.current = 0;

    setConnected(false);
  }, []);

  return { connect, disconnect, connected };
}
