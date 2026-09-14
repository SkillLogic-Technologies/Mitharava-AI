import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Mic, MicOff, Pause, Play, X, Keyboard as KeyboardIcon, Camera as CameraIcon, Sparkles, Users, BarChart3, ArrowDown } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Sheet, SheetContent } from "@/components/ui/sheet";


// TEMPLATES ONLY - {name} is filled in at render time from THIS session's randomly-assigned
// panel_roster (the "lead" member), never a fixed persona. Previously these were fully
// hardcoded strings baked with one specific name per exam_type (e.g. "I am Rajesh Menon" for
// every campus_it interview), which desynced from whichever lead the roster actually picked
// for that session - the root cause of the name-in-question-text mismatch bug.
const OPENINGS = {
  upsc: "Good morning. I am {name}, Chairman of this panel. We have reviewed your application. Tell us about yourself and what brought you to civil services.",
  ssc: "Good morning. I am {name}, Chairman of this SSC interview board. We have your documents before us. Please introduce yourself and tell us why you chose a career in government service.",
  banking: "Good morning. I am {name}, General Manager and head of this panel. Please introduce yourself and tell us why you want to build a career in banking.",
  railway: "Good morning. Welcome to the Railway Recruitment interview. Please introduce yourself and tell us why you wish to serve in the Indian Railways.",
  campus_it: "Good morning, welcome to the interview. I am {name}, {role}. Let's start with a quick introduction — tell me about yourself and your technical background.",
  campus_mba: "Good morning. I am {name}. Let's begin — walk me through your profile and why you chose this path.",
  hr: "Good morning, welcome. Let's begin with an introduction — tell me about yourself.",
  quick: "Welcome to your quick practice drill. Let's begin — tell me about yourself.",
};

const OPENINGS_HINDI = {
  upsc: "नमस्ते। मैं {name} हूँ, इस पैनल का अध्यक्ष। हमने आपका आवेदन देख लिया है। अपने बारे में बताइए और यह भी बताइए कि आप सिविल सेवा में क्यों आना चाहते हैं।",
  ssc: "नमस्ते। मैं {name} हूँ, इस SSC इंटरव्यू बोर्ड का अध्यक्ष। आपके दस्तावेज़ हमारे सामने हैं। कृपया अपना परिचय दीजिए और बताइए कि आपने सरकारी सेवा को करियर के रूप में क्यों चुना।",
  banking: "नमस्ते। मैं {name} हूँ, जनरल मैनेजर और इस पैनल का प्रमुख। कृपया अपना परिचय दीजिए और बताइए कि आप बैंकिंग में करियर क्यों बनाना चाहते हैं।",
  railway: "नमस्ते। रेलवे भर्ती इंटरव्यू में आपका स्वागत है। कृपया अपना परिचय दीजिए और बताइए कि आप भारतीय रेलवे में सेवा क्यों करना चाहते हैं।",
  campus_it: "नमस्ते, इंटरव्यू में आपका स्वागत है। मैं {name} हूँ, {role}। चलिए शुरू करते हैं — अपने बारे में और अपनी तकनीकी पृष्ठभूमि के बारे में बताइए।",
  campus_mba: "नमस्ते। मैं {name} हूँ। चलिए शुरू करते हैं — अपने बारे में बताइए और यह भी कि आपने यह रास्ता क्यों चुना।",
  hr: "नमस्ते, आपका स्वागत है। चलिए परिचय से शुरुआत करते हैं — अपने बारे में बताइए।",
  quick: "आपके क्विक प्रैक्टिस ड्रिल में स्वागत है। चलिए शुरू करते हैं — अपने बारे में बताइए।",
};

// Fills {name}/{role} placeholders in an OPENINGS template with the actual speaking member
// resolved from THIS session's roster - never a hardcoded value.
function fillOpeningTemplate(template, member) {
  if (!template) return template;
  return template
    .replace(/\{name\}/g, member?.name || "your interviewer")
    .replace(/\{role\}/g, member?.role || "panel member");
}

// Cosmetic-only UI metadata (avatar color/initials) for a panel_role - purely client-side
// presentation, NOT authoritative identity/voice data (that comes from the backend's
// session.panel_roster, picked randomly per session - see build_random_panel_roster in
// server.py). Cycles through a small palette by role so each panelist still looks distinct.
const PANEL_ROLE_STYLE = {
  lead: { color: "from-amber-400 to-yellow-700" },
  technical: { color: "from-indigo-400 to-indigo-700" },
  domain: { color: "from-indigo-400 to-indigo-700" },
  hr: { color: "from-emerald-400 to-emerald-700" },
};

function initialsOf(name) {
  return (name || "?").split(/\s+/).filter(Boolean).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

// Builds the on-screen panel list from the session's backend-assigned panel_roster
// ({panel_role: {name, role, gender, sarvam_speaker, rumik_speaker}}), NOT a hardcoded list -
// this is what makes the panel vary per interview instead of always being the same 3 names.
function panelFromRoster(session) {
  const roster = session?.panel_roster;
  if (!roster || Object.keys(roster).length === 0) return [];
  return Object.entries(roster).map(([role, member]) => ({
    id: role,
    name: member.name,
    role: member.role,
    gender: member.gender,
    sarvam_speaker: member.sarvam_speaker,
    rumik_speaker: member.rumik_speaker,
    initials: initialsOf(member.name),
    color: (PANEL_ROLE_STYLE[role] || PANEL_ROLE_STYLE.lead).color,
  }));
}

export default function InterviewRoom() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  // Identity comes ONLY from the parsed resume, never the logged-in account name.
  const hasRealResume = !!user?.resume_parsed_data && !user.resume_parsed_data.is_mock && user?.resume_filename;
  const resumeFirstName = hasRealResume ? (user.resume_parsed_data.name || "").split(" ")[0] : "";
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioPlayerRef = useRef(null);
  const speakRequestIdRef = useRef(0);
  const scrollContainerRef = useRef(null);
  const bottomSentinelRef = useRef(null);
  const isNearBottomRef = useRef(true); // mirrors state below, but readable synchronously inside the scroll handler
  const [session, setSession] = useState(null);
  // The panel shown on screen comes from THIS session's backend-assigned roster (random per
  // interview), not a hardcoded per-exam-type list - see panelFromRoster above.
  const INTERVIEWERS = panelFromRoster(session);
  const [transcript, setTranscript] = useState([]);
  const [orbState, setOrbState] = useState("idle"); // idle | listening | processing | speaking
  const [currentSpeaker, setCurrentSpeaker] = useState(0);
  const [timer, setTimer] = useState(0);
  const [latestEval, setLatestEval] = useState(null);
  const [livesnippet, setLiveSnippet] = useState("");
  const [showPerm, setShowPerm] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);
  const [paused, setPaused] = useState(false);
  const [muted, setMuted] = useState(false);
  const [textMode, setTextMode] = useState(false);
  const [textInput, setTextInput] = useState("");
  const [endConfirm, setEndConfirm] = useState(false);
  const [qIndex, setQIndex] = useState(0);
  const [whisperMode, setWhisperMode] = useState(true); // true = server STT (Sarvam Saarika, best for Hindi), false = Browser STT
  const [panelDrawerOpen, setPanelDrawerOpen] = useState(false);
  const [analyticsDrawerOpen, setAnalyticsDrawerOpen] = useState(false);
  const [showNewMessagesPill, setShowNewMessagesPill] = useState(false);

  // Load session
  useEffect(() => {
    api.get(`/sessions/${id}`).then((r) => {
      setSession(r.data);
      if (r.data.mode === "text") setTextMode(true);
    }).catch(() => navigate("/dashboard"));
  }, [id, navigate]);

  // Timer
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setTimer((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [paused]);

  // Initialize camera + opening
  useEffect(() => {
    if (!session) return;
    const wantCamera = session.mode === "voice_camera";
    const wantMic = session.mode !== "text";

    if (wantCamera || wantMic) {
      navigator.mediaDevices.getUserMedia({ video: wantCamera, audio: wantMic })
        .then((stream) => {
          streamRef.current = stream;
          if (wantCamera) setCameraOn(true);
        })
        .catch(() => setShowPerm(true));
    }

    // Speak opening line and add to transcript. The opening is always voiced by the "lead"
    // role from THIS session's backend-assigned roster (panelFromRoster) - falls back to
    // whichever member is first if "lead" isn't present for some reason.
    setTimeout(() => {
      const panel = panelFromRoster(session);
      const leadMember = panel.find((m) => m.id === "lead") || panel[0];
      const openings = session.language === "hindi" ? OPENINGS_HINDI : OPENINGS;
      const template = openings[session.session_type] || openings.hr;
      const opening = {
        role: "assistant",
        speaker: leadMember?.name || "The Interviewer",
        speakerMember: leadMember,
        text: fillOpeningTemplate(template, leadMember),
        ts: Date.now(),
      };
      setTranscript([opening]);
      speak(opening.text, opening.speakerMember);
    }, 1000);

    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
      window.speechSynthesis?.cancel();
      try { audioPlayerRef.current?.pause(); } catch {}
      try { recognitionRef.current?.stop(); } catch {}
      try { if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop(); } catch {}
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  // Attach the stream once the <video> element is actually rendered
  useEffect(() => {
    if (cameraOn && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [cameraOn]);

  // --- Smart sticky auto-scroll for the chat transcript ---
  const NEAR_BOTTOM_THRESHOLD_PX = 120;

  const checkIsNearBottom = () => {
    const el = scrollContainerRef.current;
    if (!el) return true;
    return el.scrollTop + el.clientHeight >= el.scrollHeight - NEAR_BOTTOM_THRESHOLD_PX;
  };

  const scrollToBottom = (behavior = "smooth") => {
    bottomSentinelRef.current?.scrollIntoView({ behavior, block: "end" });
  };

  const handleTranscriptScroll = () => {
    const nearBottom = checkIsNearBottom();
    isNearBottomRef.current = nearBottom;
    if (nearBottom) setShowNewMessagesPill(false); // manually scrolling back down hides the pill
  };

  const dismissNewMessagesPill = () => {
    scrollToBottom("smooth");
    setShowNewMessagesPill(false);
  };

  // New message arrived: auto-scroll if the user was already near the bottom, or if the
  // new message is the candidate's own answer (they just typed/spoke it - always show it).
  // Otherwise (user scrolled up reading old messages) leave scroll position alone and
  // surface the "New messages" pill instead of yanking them back down.
  useEffect(() => {
    if (transcript.length === 0) return;
    const lastMsg = transcript[transcript.length - 1];
    const isOwnAnswer = lastMsg?.role === "user";
    if (isNearBottomRef.current || isOwnAnswer) {
      scrollToBottom(transcript.length === 1 ? "auto" : "smooth");
      setShowNewMessagesPill(false);
    } else {
      setShowNewMessagesPill(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transcript.length]);

  const speakBrowserFallback = (text, requestId) => {
    console.log("[TTS DEBUG] PATH: browser speechSynthesis fallback (server TTS failed or blob playback errored)");
    if (requestId !== undefined && requestId !== speakRequestIdRef.current) return;
    if (!("speechSynthesis" in window)) { setOrbState("idle"); return; }
    setOrbState("speaking");
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.95; u.pitch = 0.9;
    const voices = window.speechSynthesis.getVoices();
    const preferLang = session?.language === "hindi" ? /hi-IN/i : /en-IN/i;
    const indian =
      voices.find(v => preferLang.test(v.lang)) ||
      voices.find(v => /(en-IN|hi-IN)/i.test(v.lang)) ||
      voices.find(v => /India|हिन्दी|Ravi|Heera|Swara|Madhur/i.test(v.name)) ||
      voices.find(v => /Google.*UK English Male|Daniel/i.test(v.name)) || voices[0];
    if (indian) u.voice = indian;
    if (indian && /hi-IN/i.test(indian.lang)) u.lang = "hi-IN";
    u.onend = () => setOrbState("idle");
    u.onerror = () => setOrbState("idle");
    window.speechSynthesis.speak(u);
  };

  // speakerMember: the AUTHORITATIVE panel member object for this line (name/gender/
  // sarvam_speaker/rumik_speaker), as attached by the backend (session_turn's
  // speakerMember, or a roster entry for the opening line) - NOT just a name string, so
  // /voice/tts can pick the correct gendered voice without re-deriving anything client-side.
  const speak = async (text, speakerMember) => {
    // Stop any voice currently playing (ElevenLabs audio or browser TTS) before starting a new one
    window.speechSynthesis?.cancel();
    if (audioPlayerRef.current) {
      try { audioPlayerRef.current.pause(); } catch {}
      audioPlayerRef.current = null;
    }
    const requestId = ++speakRequestIdRef.current;
    setOrbState("speaking");
    try {
      console.log("[TTS DEBUG] PATH: requesting /voice/tts from backend | text=", JSON.stringify(text), "| language=", session?.language || "english", "| speakerMember=", speakerMember);
      const { data } = await api.post(
        "/voice/tts",
        {
          text,
          language: session?.language || "english",
          speaker_name: speakerMember?.name,
          speaker_gender: speakerMember?.gender,
          speaker_sarvam: speakerMember?.sarvam_speaker,
          speaker_rumik: speakerMember?.rumik_speaker,
        },
        { responseType: "blob" }
      );
      if (requestId !== speakRequestIdRef.current) return; // a newer speak() call superseded this one
      console.log("[TTS DEBUG] PATH: backend TTS responded OK, blob size=", data?.size, "type=", data?.type);
      const url = URL.createObjectURL(data);
      const audio = new Audio(url);
      audioPlayerRef.current = audio;
      audio.onended = () => { setOrbState("idle"); URL.revokeObjectURL(url); };
      audio.onerror = () => { console.log("[TTS DEBUG] PATH: audio blob playback errored, falling back"); URL.revokeObjectURL(url); speakBrowserFallback(text, requestId); };
      await audio.play();
    } catch (err) {
      console.warn("ElevenLabs TTS failed, falling back to browser voice:", err?.response?.status, err?.message);
      if (requestId === speakRequestIdRef.current) speakBrowserFallback(text, requestId);
    }
  };

  const startListening = useCallback(async () => {
    if (orbState !== "idle") return;

    if (whisperMode) {
      // Whisper path needs the captured MediaStream; browser STT (below) does NOT.
      if (!streamRef.current || streamRef.current.getAudioTracks().length === 0) {
        console.warn("startListening(whisper): no microphone stream/track");
        toast.error("Microphone not available. Switch to Browser STT or text mode.");
        return;
      }
      // Use MediaRecorder → Whisper STT
      try {
        const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus"
          : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm"
          : "audio/mp4";
        const audioStream = new MediaStream(streamRef.current.getAudioTracks());
        const mr = new MediaRecorder(audioStream, { mimeType });
        audioChunksRef.current = [];
        mr.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
        mr.onstop = async () => {
          const blob = new Blob(audioChunksRef.current, { type: mimeType });
          if (blob.size < 1000) { setOrbState("idle"); return; }
          setOrbState("processing");
          try {
            const fd = new FormData();
            fd.append("file", blob, "audio.webm");
            fd.append("language", session?.language || "english");
            // Backend prefers the session's own stored language (more reliable than this
            // form field alone) when resolving which language to transcribe as - see
            // _resolve_stt_language_code() in server.py.
            fd.append("session_id", id);
            const token = localStorage.getItem("mitharva_token");
            const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/voice/stt`, {
              method: "POST",
              headers: { Authorization: `Bearer ${token}` },
              body: fd,
            });
            const data = await res.json();
            if (data.text?.trim()) submitAnswer(data.text.trim());
            else { setOrbState("idle"); toast.error("Couldn't hear you. Try again."); }
          } catch {
            setOrbState("idle"); toast.error("Transcription failed");
          }
        };
        mediaRecorderRef.current = mr;
        mr.start();
        setOrbState("listening");
      } catch (e) {
        toast.error("Recording failed");
        setOrbState("idle");
      }
      return;
    }

    // Browser STT: Web Speech API (does NOT need our captured MediaStream — it opens the mic itself)
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      toast.error("Browser speech recognition not supported. Use Chrome, or switch to text mode.");
      setTextMode(true);
      return;
    }
    // Some browsers require an explicit mic permission before SpeechRecognition works.
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      console.warn("browser STT: microphone permission denied");
      toast.error("Microphone blocked. Allow mic access in the address bar, or use text mode.");
      return;
    }

    const r = new SR();
    r.continuous = true;          // keep listening through natural pauses
    r.interimResults = true;
    r.lang = session?.language === "hindi" ? "hi-IN" : "en-IN";
    setLiveSnippet("");

    let finalText = "";
    let gotAnything = false;
    r.onstart = () => { setOrbState("listening"); };
    r.onresult = (ev) => {
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const t = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) finalText += t + " ";
        else interim += t;
      }
      if (finalText || interim) gotAnything = true;
      setLiveSnippet((finalText + interim).trim());
    };
    r.onerror = (e) => {
      console.warn("browser STT error:", e.error);
      setOrbState("idle");
      setLiveSnippet("");
      if (e.error === "not-allowed" || e.error === "service-not-allowed")
        toast.error("Microphone permission blocked. Allow it in the browser, or use text mode.");
      else if (e.error === "no-speech")
        toast.error("Didn't catch anything. Tap and speak a bit louder.");
      else if (e.error !== "aborted")
        toast.error(`Mic error: ${e.error}`);
    };
    r.onend = () => {
      const final = finalText.trim();
      setLiveSnippet("");
      if (final) submitAnswer(final);
      else {
        setOrbState("idle");
        if (!gotAnything) toast.error("Didn't hear you. Tap the orb and speak clearly.");
      }
    };
    recognitionRef.current = r;
    try {
      r.start();
    } catch (err) {
      console.warn("browser STT start failed:", err?.message);
      setOrbState("idle");
      toast.error("Could not start listening. Tap again or use text mode.");
    }
  }, [orbState, session, whisperMode]);

  const stopListening = () => {
    if (whisperMode && mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    } else {
      try { recognitionRef.current?.stop(); } catch {}
    }
  };

  const submitAnswer = async (answerText) => {
    setOrbState("processing");
    const userMsg = { role: "user", text: answerText, ts: Date.now() };
    setTranscript((t) => [...t, userMsg]);
    try {
      const history = transcript.map((t) => ({ role: t.role, text: t.text }));
      const { data } = await api.post("/sessions/turn", { session_id: id, user_message: answerText, question_index: qIndex, history });
      const p = data.parsed || {};
      // speakerMember is the AUTHORITATIVE speaking panel member for this turn, attached by
      // the backend (session_turn resolves it from the session's stored roster + current
      // phase - see resolve_speaking_member in server.py). It now always carries a stable
      // "id" (the panel_role key, e.g. "lead"/"technical"/"hr") that matches an INTERVIEWERS
      // entry's id one-to-one. Matching by id (never by name) is what guarantees the chat
      // author label, the panel card highlight, and /voice/tts all agree on the SAME member -
      // a name-string match was the old, fragile path that could silently disagree.
      const speakerMember = p.speakerMember || null;
      const speakerName = speakerMember?.name || p.speakerName || INTERVIEWERS[0]?.name || "The Interviewer";
      const idx = INTERVIEWERS.findIndex((m) => m.id === speakerMember?.id);
      if (idx !== -1) {
        setCurrentSpeaker(idx);
      } else if (speakerMember?.id) {
        // Backend sent an id that isn't in this session's rendered panel - a real desync, not
        // just a missing id. Surface it loudly rather than silently falling back to a guess.
        console.warn("[PANEL DEBUG] speakerMember.id not found in INTERVIEWERS:", speakerMember?.id, INTERVIEWERS.map((m) => m.id));
      }
      // isRepeat: the backend detected this was a "repeat/rephrase the question" request, not
      // an actual answer - it re-sent the same question without advancing its phase/index, so
      // the frontend must not advance qIndex or record a score for it either.
      if (!data.isRepeat) {
        setLatestEval(p.evaluation || null);
        setQIndex((q) => q + 1);
      }

      const aiMsg = {
        role: "assistant",
        speaker: speakerName,
        speakerMember,
        text: p.nextQuestion || "Thank you. Please tell me more.",
        ts: Date.now(),
        evaluation: p.evaluation,
      };
      setTranscript((t) => [...t, aiMsg]);
      speak(aiMsg.text, aiMsg.speakerMember);

      if (!data.isRepeat && (p.isInterviewComplete || qIndex >= 11)) {
        setTimeout(() => endInterview(), 5000);
      }
    } catch (err) {
      setOrbState("idle");
      toast.error("AI response failed. Try again.");
    }
  };

  const submitText = () => {
    if (!textInput.trim()) return;
    submitAnswer(textInput.trim());
    setTextInput("");
  };

  const endInterview = async () => {
    try {
      window.speechSynthesis?.cancel();
      stopListening();
      await api.post("/sessions/complete", {
        session_id: id,
        transcript: transcript.map(t => ({ role: t.role, text: t.text, speaker: t.speaker, evaluation: t.evaluation })),
        duration_seconds: timer,
        camera_used: cameraOn,
      });
      toast.success("Interview complete! Generating report...");
      navigate(`/interview/results/${id}`);
    } catch {
      toast.error("Failed to save session");
    }
  };

  if (!session) return <div className="h-dvh bg-navy-deep flex items-center justify-center text-white">Loading interview room...</div>;

  const mmss = `${String(Math.floor(timer/60)).padStart(2,"0")}:${String(timer%60).padStart(2,"0")}`;

  // Shared panel-list content, rendered both inline (desktop/tablet sidebar) and inside the
  // mobile/tablet drawer - kept as one block so the two never drift out of sync.
  const panelList = (
    <>
      <SectionLabel>Panel</SectionLabel>
      <div className="space-y-2">
        {INTERVIEWERS.map((it, idx) => {
          const speaking = orbState === "speaking" && idx === currentSpeaker;
          return (
            <div
              key={it.id}
              className={`rounded-2xl p-3 border transition-all ${
                speaking
                  ? "bg-navy-mid border-gold/50 shadow-[0_0_0_1px_rgba(184,150,46,0.15),0_0_20px_rgba(184,150,46,0.15)]"
                  : "bg-navy-mid/40 border-white/[0.06] opacity-60"
              }`}
            >
              <div className="flex items-center gap-3">
                <div className={`relative h-10 w-10 rounded-full bg-gradient-to-br ${it.color} flex items-center justify-center text-navy-deep text-sm font-bold shrink-0 ${speaking ? "ring-2 ring-gold/60 ring-offset-2 ring-offset-navy-mid" : ""}`}>
                  {it.initials}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate leading-tight">{it.name}</div>
                  <div className="text-[11px] text-white/45 truncate leading-tight mt-0.5">{it.role}</div>
                </div>
              </div>
              <div className="mt-2.5 flex items-center gap-1.5 text-[11px]">
                {speaking ? (
                  <>
                    <span className="h-1.5 w-1.5 rounded-full bg-gold animate-pulse" />
                    <span className="text-gold-light font-medium">Speaking</span>
                    <div className="wave-bars ml-1"><span/><span/><span/><span/></div>
                  </>
                ) : (
                  <>
                    <span className="h-1.5 w-1.5 rounded-full bg-white/25" />
                    <span className="text-white/40">{orbState === "listening" ? "Listening" : "Waiting"}</span>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );

  // Shared analytics content, same reasoning as panelList above. Gold is reserved for the
  // ONE headline number (Current Answer Score) — the four sub-metric bars and all other
  // progress indicators are neutral white/slate, so the accent still reads as "the number
  // that matters" instead of being diluted across five competing gold bars.
  const analyticsContent = (
    <>
      <SectionLabel>Live Analytics</SectionLabel>

      <div className="mb-5">
        <div className="flex justify-between text-xs text-white/50 mb-1.5">
          <span>Question {qIndex + 1} of ~12</span>
        </div>
        <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
          <div className="h-full bg-white/30 transition-all" style={{ width: `${Math.min(100, ((qIndex + 1)/12)*100)}%` }} />
        </div>
      </div>

      <div className="mb-5 rounded-2xl bg-navy-mid/60 border border-white/[0.06] p-4">
        <div className="text-xs text-white/50 mb-1">Current Answer Score</div>
        <div className="flex items-baseline gap-1">
          <span className="font-mono text-3xl font-bold text-gold">{(latestEval?.overallScore ?? 0).toFixed(1)}</span>
          <span className="text-xs text-white/40">/ 10</span>
        </div>
        <div className="mt-3 h-1 bg-white/[0.06] rounded-full overflow-hidden">
          <div className="h-full gradient-gold-bg" style={{ width: `${(latestEval?.overallScore ?? 0)*10}%` }} />
        </div>
      </div>

      <div className="space-y-3 mb-5">
        {[
          ["Technical", latestEval?.technicalScore],
          ["Clarity", latestEval?.clarityScore],
          ["Structure", latestEval?.structureScore],
          ["Confidence", latestEval?.confidenceEstimate],
        ].map(([label, val]) => (
          <div key={label}>
            <div className="flex justify-between text-xs text-white/60 mb-1"><span>{label}</span><span className="font-mono text-white/80">{(val ?? 0).toFixed(1)}</span></div>
            <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
              <div className="h-full bg-white/40" style={{ width: `${((val ?? 0))*10}%` }} />
            </div>
          </div>
        ))}
      </div>

      <div className="mb-5 p-3.5 rounded-2xl bg-gold/[0.06] border border-gold/[0.15]">
        <div className="text-xs font-medium text-gold-light mb-1">💡 Live Tip</div>
        <div className="text-xs text-white/70 leading-relaxed">{latestEval?.liveTip || "Speak clearly and structure your answer with a beginning, middle, and end."}</div>
      </div>

      <div className="mb-5">
        <SectionLabel small>Body Language</SectionLabel>
        <div className="space-y-0.5">
          <BLine label="Eye Contact" v={cameraOn ? "Good" : "—"} />
          <BLine label="Posture" v={cameraOn ? "Upright" : "—"} />
          <BLine label="Expressions" v={cameraOn ? "Neutral" : "—"} />
          <BLine label="Nervousness" v={cameraOn ? "Low" : "—"} />
        </div>
      </div>

      <div>
        <SectionLabel small>Session</SectionLabel>
        <div className="space-y-0.5">
          <BLine label="Time" v={`${mmss} / ${String(session.duration_minutes).padStart(2,'0')}:00`} />
          <BLine label="Done" v={`${qIndex} / ~12`} />
          <BLine label="Avg" v={`${((latestEval?.overallScore ?? 0)).toFixed(1)} / 10`} />
        </div>
      </div>
    </>
  );

  return (
    <div className="h-dvh w-full bg-navy-deep text-white flex flex-col overflow-hidden" data-testid="interview-room">
      {/* TOP BAR — fixed, never scrolls. Neutral surface; gold reserved for the brand mark
          only (identity, not a UI-state accent) — timer/REC/buttons are all neutral. */}
      <div className="shrink-0 h-14 px-3 sm:px-4 lg:px-6 flex items-center justify-between border-b border-white/[0.06] bg-navy-deep/80 backdrop-blur-md">
        <div className="flex items-center gap-3 text-sm min-w-0">
          {/* Mobile + tablet: opens the PANEL drawer (panel is only inline at md+/lg+) */}
          <button
            onClick={() => setPanelDrawerOpen(true)}
            data-testid="open-panel-drawer"
            aria-label="Show interview panel"
            className="md:hidden shrink-0 p-1.5 rounded-lg border border-white/[0.06] text-white/50 hover:bg-white/[0.06] hover:text-white/90 transition-colors"
          >
            <Users size={16} />
          </button>
          <span className="text-gold font-display font-bold shrink-0">◆ Mitharva AI</span>
          <span className="hidden md:inline text-white/20">•</span>
          <span className="hidden md:inline text-white/50 text-xs truncate">{labelFor(session.session_type)} — {session.sub_type?.replace("_"," ")}</span>
        </div>
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <span className="font-mono text-sm text-white/70" data-testid="room-timer">{mmss}</span>
          <span className="hidden sm:flex items-center gap-1.5 text-[11px] text-white/40">
            <span className="h-1.5 w-1.5 rounded-full bg-red-500/80 animate-pulse" /> REC
          </span>
          <button onClick={() => setEndConfirm(true)} data-testid="room-end-btn" className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-white/[0.06] text-xs text-white/60 hover:border-red-400/40 hover:text-red-400 transition-colors">
            <X size={12} /> End
          </button>
          {/* Tablet + mobile: opens the ANALYTICS drawer (analytics is only inline at lg+) */}
          <button
            onClick={() => setAnalyticsDrawerOpen(true)}
            data-testid="open-analytics-drawer"
            aria-label="Show live analytics"
            className="lg:hidden p-1.5 rounded-lg border border-white/[0.06] text-white/50 hover:bg-white/[0.06] hover:text-white/90 transition-colors"
          >
            <BarChart3 size={16} />
          </button>
        </div>
      </div>

      {/* MAIN AREA — fills remaining height, itself never scrolls; only the chat list inside does */}
      <div className="flex-1 min-h-0 grid grid-rows-[minmax(0,1fr)] lg:grid-cols-[280px_1fr_320px] md:grid-cols-[240px_1fr] grid-cols-1">
        {/* LEFT: Interviewers — inline from md+ (tablet and up); drawer below md */}
        <div className="hidden md:flex md:flex-col border-r border-white/[0.06] bg-navy-deep/40 p-4 overflow-y-auto min-h-0">
          {panelList}
        </div>

        {/* CENTER: Camera (fixed) + Transcript (the ONLY scrollable region) + Orb */}
        <div className="flex flex-col min-h-0">
          {/* Camera — fixed 16:9 tile, capped width, centered. object-cover (not contain) so
              there's no letterbox void, but the FIXED aspect-ratio box (not a vh-based height)
              is what removes the "zoomed crop" feeling: the box's proportions now always
              match the video stream's own proportions, so cover only trims a little off the
              edges instead of aggressively cropping to fill a mismatched box. */}
          <div className="shrink-0 bg-navy-deep px-4 pt-4 pb-2 sm:px-5 sm:pt-5">
            <div className="relative mx-auto w-full max-w-md aspect-video rounded-2xl overflow-hidden border border-white/10 shadow-lg shadow-black/30 bg-black">
              {cameraOn ? (
                <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center text-center">
                  <div>
                    <CameraIcon size={32} className="mx-auto text-white/25" />
                    <div className="mt-2 text-xs text-white/40">{session.mode === "text" ? "Text mode active" : "Camera off"}</div>
                  </div>
                </div>
              )}
              {/* "You" pill — bottom-left, subtle dark glass, not a harsh block */}
              <div className="absolute bottom-2 left-2 px-2.5 py-1 rounded-full bg-black/50 backdrop-blur-sm text-[11px] font-medium">
                You — {resumeFirstName || "Candidate"}
              </div>
              {/* Live Tip — top overlay, subtle amber-tinted pill, not full-width harsh yellow */}
              {cameraOn && latestEval && (
                <div className="absolute top-2 left-2 right-2 flex justify-center">
                  <div className="px-3 py-1 rounded-full bg-black/50 backdrop-blur-sm border border-gold/25 text-[11px] text-gold-light max-w-full truncate">
                    💡 {latestEval.liveTip || "Make eye contact with the camera"}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Transcript — the ONLY scrollable region in the whole page */}
          <div className="relative flex-1 min-h-0">
            <div
              ref={scrollContainerRef}
              onScroll={handleTranscriptScroll}
              className="h-full overflow-y-auto overflow-x-hidden px-3 sm:px-4 lg:px-6 py-4 space-y-4"
              data-testid="transcript-area"
            >
              {transcript.map((m, i) => (
                <Message key={i} m={m} />
              ))}
              {orbState === "listening" && livesnippet && (
                <Message m={{ role: "user", text: livesnippet + "…" }} live />
              )}
              {orbState === "processing" && (
                <div className="text-xs text-gold flex items-center gap-2"><span className="inline-block h-2 w-2 bg-gold rounded-full animate-bounce" />Thinking...</div>
              )}
              {/* Bottom sentinel — scrollIntoView target for auto-scroll / the pill's jump-to-bottom */}
              <div ref={bottomSentinelRef} />
            </div>

            {/* Floating "New messages" pill — only shown when the user has scrolled up and a
                new message arrived without auto-scrolling them down. */}
            {showNewMessagesPill && (
              <button
                onClick={dismissNewMessagesPill}
                data-testid="new-messages-pill"
                className="absolute bottom-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full gradient-gold-bg text-navy-deep text-xs font-semibold shadow-lg shadow-black/30 animate-fade-up"
              >
                <ArrowDown size={12} /> New messages
              </button>
            )}
          </div>

          {/* Bottom control dock — fixed, always visible, pinned by the flex column
              (shrink-0). A single elevated floating pill (not loose buttons in empty
              space): subtle surface, soft shadow, mic as the primary control, four
              uniform secondary pills in the same row. Deliberately compact (~110-130px
              total) so the chat transcript keeps most of the vertical space. */}
          <div className="shrink-0 px-3 py-3 sm:px-4 sm:py-4 flex justify-center">
            {textMode ? (
              <div className="w-full max-w-2xl rounded-2xl bg-navy-mid/80 border border-white/[0.06] shadow-lg shadow-black/30 p-3">
                <textarea
                  data-testid="text-input"
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 rounded-xl bg-navy-deep/60 border border-white/[0.06] text-white text-sm focus:outline-none focus:border-gold/40 resize-none"
                  placeholder="Type your answer here…"
                />
                <div className="flex justify-between items-center mt-2">
                  <button onClick={() => setTextMode(false)} className="text-xs text-white/50 hover:text-gold-light inline-flex items-center gap-1"><Mic size={12} /> Switch to voice</button>
                  <button data-testid="text-submit" disabled={!textInput.trim() || orbState !== "idle"} onClick={submitText} className="px-5 py-1.5 rounded-full gradient-gold-bg text-navy-deep font-semibold text-sm disabled:opacity-50">Send →</button>
                </div>
              </div>
            ) : (
              // Single floating dock: mic (primary) + status + 4 uniform secondary pills,
              // all in one row on a shared elevated surface.
              <div className="inline-flex items-center gap-3 sm:gap-4 max-w-full rounded-full bg-navy-mid/80 border border-white/[0.06] shadow-lg shadow-black/30 pl-2 pr-4 py-2 sm:pl-2.5 sm:pr-5 sm:py-2.5">
                <button
                  onClick={orbState === "listening" ? stopListening : startListening}
                  disabled={orbState === "speaking" || orbState === "processing" || paused}
                  data-testid="voice-orb"
                  className={`shrink-0 !w-[72px] !h-[72px] sm:!w-20 sm:!h-20 disabled:opacity-50 ${orbState === "listening" ? "orb-listening" : orbState === "processing" ? "orb-processing" : orbState === "speaking" ? "orb-speaking" : "orb-idle"}`}
                  aria-label="Voice control"
                />
                <div className="flex flex-col items-start gap-1.5 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-white/60 whitespace-nowrap">
                      {orbState === "idle" && "Tap to speak your answer"}
                      {orbState === "listening" && "Listening..."}
                      {orbState === "processing" && "Analyzing..."}
                      {orbState === "speaking" && "AI is responding..."}
                    </span>
                    {orbState === "listening" && (
                      <div className="wave-bars"><span/><span/><span/><span/></div>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 flex-wrap max-w-full">
                    <button onClick={() => setPaused(!paused)} data-testid="room-pause" className="px-2.5 py-1 rounded-full bg-white/[0.04] border border-white/[0.06] text-[11px] text-white/60 hover:bg-white/[0.08] hover:text-white/90 inline-flex items-center gap-1 whitespace-nowrap transition-colors">
                      {paused ? <Play size={11} /> : <Pause size={11} />} {paused ? "Resume" : "Pause"}
                    </button>
                    <button onClick={() => setMuted(!muted)} data-testid="room-mute" className="px-2.5 py-1 rounded-full bg-white/[0.04] border border-white/[0.06] text-[11px] text-white/60 hover:bg-white/[0.08] hover:text-white/90 inline-flex items-center gap-1 whitespace-nowrap transition-colors">
                      {muted ? <MicOff size={11} /> : <Mic size={11} />} {muted ? "Unmute" : "Mute"}
                    </button>
                    <button onClick={() => setTextMode(true)} data-testid="switch-text" className="px-2.5 py-1 rounded-full bg-white/[0.04] border border-white/[0.06] text-[11px] text-white/60 hover:bg-white/[0.08] hover:text-white/90 inline-flex items-center gap-1 whitespace-nowrap transition-colors">
                      <KeyboardIcon size={11} /> Text
                    </button>
                    <button onClick={() => setWhisperMode(!whisperMode)} data-testid="toggle-whisper" className={`px-2.5 py-1 rounded-full text-[11px] inline-flex items-center gap-1 whitespace-nowrap transition-colors ${whisperMode ? "bg-gold/10 border border-gold/30 text-gold-light" : "bg-white/[0.04] border border-white/[0.06] text-white/60 hover:bg-white/[0.08] hover:text-white/90"}`}>
                      <Sparkles size={11} /> {whisperMode ? "Sarvam" : "Browser"}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT: Live Analytics — inline only at lg+ (desktop); drawer below lg */}
        <div className="hidden lg:block border-l border-white/[0.06] bg-navy-deep/40 p-5 overflow-y-auto overflow-x-hidden text-sm min-h-0 min-w-0">
          {analyticsContent}
        </div>
      </div>

      {/* PANEL DRAWER — mobile + tablet (<md) */}
      <Sheet open={panelDrawerOpen} onOpenChange={setPanelDrawerOpen}>
        <SheetContent side="left" className="bg-navy-deep border-white/[0.06] text-white p-4 overflow-y-auto w-[85vw] sm:w-80" data-testid="panel-drawer">
          <div className="mt-6">{panelList}</div>
        </SheetContent>
      </Sheet>

      {/* ANALYTICS DRAWER — mobile + tablet (<lg) */}
      <Sheet open={analyticsDrawerOpen} onOpenChange={setAnalyticsDrawerOpen}>
        <SheetContent side="right" className="bg-navy-deep border-white/[0.06] text-white p-4 overflow-y-auto text-sm w-[85vw] sm:w-80" data-testid="analytics-drawer">
          <div className="mt-6">{analyticsContent}</div>
        </SheetContent>
      </Sheet>

      {/* PERMISSION MODAL */}
      {showPerm && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6">
          <div className="card-surface !bg-navy-mid !border-white/[0.08] max-w-md w-full p-6 text-white shadow-xl shadow-black/40">
            <div className="flex items-center gap-2 text-gold mb-3"><CameraIcon size={20} /> <span className="font-semibold">Camera Access for Better Experience</span></div>
            <p className="text-sm text-white/70">Mitharva AI uses your camera to:</p>
            <ul className="mt-2 text-sm text-white/60 space-y-1">
              <li>• Simulate a real interview environment</li>
              <li>• Analyze eye contact & body language</li>
              <li>• Give posture feedback</li>
            </ul>
            <div className="flex gap-2 mt-5">
              <button data-testid="perm-allow" onClick={() => { setShowPerm(false); navigator.mediaDevices.getUserMedia({ video: true, audio: true }).then((s) => { streamRef.current = s; setCameraOn(true); }).catch(() => {}); }} className="flex-1 px-4 py-2 rounded-full gradient-gold-bg text-navy-deep font-semibold text-sm">Allow Camera + Mic</button>
              <button data-testid="perm-deny" onClick={() => setShowPerm(false)} className="flex-1 px-4 py-2 rounded-full border border-white/[0.08] text-white/70 text-sm hover:bg-white/[0.04] transition-colors">Continue Voice Only</button>
            </div>
          </div>
        </div>
      )}

      {/* END CONFIRM */}
      {endConfirm && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6">
          <div className="card-surface !bg-navy-mid !border-white/[0.08] max-w-md w-full p-6 text-white shadow-xl shadow-black/40">
            <div className="font-display text-xl">End interview?</div>
            <p className="text-sm text-white/60 mt-2">Your session will be saved and analyzed. You can review it on the results page.</p>
            <div className="flex gap-2 mt-5">
              <button data-testid="end-cancel" onClick={() => setEndConfirm(false)} className="flex-1 px-4 py-2 rounded-full border border-white/[0.08] text-white/70 text-sm hover:bg-white/[0.04] transition-colors">Continue</button>
              <button data-testid="end-confirm" onClick={endInterview} className="flex-1 px-4 py-2 rounded-full bg-red-500 text-white font-semibold text-sm">End & Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Message({ m, live }) {
  // max-width ~80% on mobile, ~70% on desktop (lg+); overflow-wrap "anywhere" so long
  // unbroken tokens (URLs, or Devanagari text with no spaces) wrap inside the bubble
  // instead of forcing horizontal scroll on the page. leading-relaxed + slightly larger
  // line-height on Devanagari-heavy text reads more comfortably than default line-height.
  const bubbleWrap = "max-w-[80%] lg:max-w-[70%] min-w-0";
  const bubbleText = "text-sm leading-[1.6] [overflow-wrap:anywhere] break-words";
  if (m.role === "assistant") {
    return (
      <div className="flex gap-2.5 animate-fade-up">
        <div className="h-8 w-8 rounded-full bg-white/10 border border-white/10 flex items-center justify-center text-white/80 text-[11px] font-semibold shrink-0 mt-0.5">
          {(m.speaker || "AI").split(" ").map(s => s[0]).join("").slice(0,2)}
        </div>
        <div className={bubbleWrap}>
          <div className="text-[11px] font-medium text-white/40 mb-1">{m.speaker || "AI"}</div>
          <div className={`rounded-2xl bg-navy-mid/70 border border-white/[0.06] px-4 py-2.5 text-white/90 ${bubbleText}`}>{m.text}</div>
        </div>
      </div>
    );
  }
  return (
    <div className="flex gap-2.5 justify-end animate-fade-up">
      <div className={bubbleWrap}>
        <div className="text-[11px] font-medium text-white/40 text-right mb-1">You</div>
        <div className={`rounded-2xl bg-gold/[0.12] border ${live ? "border-gold/50" : "border-gold/20"} px-4 py-2.5 text-white ${bubbleText}`}>{m.text}</div>
      </div>
    </div>
  );
}

// Consistent uppercase, letter-spaced, muted eyebrow used for every section header
// (PANEL, LIVE ANALYTICS, BODY LANGUAGE, SESSION) — same size/weight/tracking everywhere
// so the hierarchy reads as one system, not four ad-hoc labels.
function SectionLabel({ children, small }) {
  return (
    <div className={`text-[10px] font-semibold tracking-[0.15em] text-white/40 uppercase ${small ? "mb-2" : "mb-3"}`}>
      {children}
    </div>
  );
}

// Label/value row on a consistent baseline grid: label left (muted, truncates first if the
// column is narrow), value right (mono, higher contrast, never wraps/clips) — same
// line-height and vertical rhythm on every row. min-w-0 on the label + shrink-0 on the value
// is what stops long values ("Upright", "12 / ~12") from being clipped by the column's
// overflow-y-auto (which only permits vertical scroll, so horizontal overflow was invisible).
function BLine({ label, v }) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-xs py-1 leading-none">
      <span className="text-white/50 truncate min-w-0">{label}</span>
      <span className="font-mono text-white/80 shrink-0 whitespace-nowrap">{v}</span>
    </div>
  );
}

function labelFor(t) {
  return { upsc: "UPSC Personality Test", ssc: "SSC Interview", banking: "Banking Interview", railway: "Railway Interview", campus_it: "Campus IT Interview", campus_mba: "MBA Campus Interview", hr: "HR Round", quick: "Quick Drill" }[t] || t;
}
