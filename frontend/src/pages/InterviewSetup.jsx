import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Mic, Camera, Keyboard, ChevronRight, ChevronLeft, FileText, Check, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function InterviewSetup() {
  const navigate = useNavigate();
  const { user, refresh } = useAuth();
  const fileRef = useRef(null);
  const [step, setStep] = useState(1);
  const [creating, setCreating] = useState(false);
  const [resume, setResume] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [config, setConfig] = useState({
    session_type: "upsc",
    sub_type: "full_mock",
    duration_minutes: 30,
    difficulty: "medium",
    language: "english",
    mode: "voice_camera",
    company: "",
  });

  // Auto-set to user's exam_focus on first load
  useEffect(() => {
    if (user?.exam_focus && user.exam_focus !== config.session_type) {
      const subDefault = {
        upsc: "full_mock", banking: "sbi_po", ssc: "cgl", railway: "ntpc",
        campus_it: "tcs_digital", campus_mba: "hr_round",
      }[user.exam_focus] || "general";
      setConfig((c) => ({ ...c, session_type: user.exam_focus, sub_type: subDefault }));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.exam_focus]);

  // Default the interview language to the user's saved preference
  useEffect(() => {
    if (user?.preferred_language) {
      setConfig((c) => ({ ...c, language: user.preferred_language }));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.preferred_language]);

  const categories = [
    { k: "upsc", icon: "🏛️", title: "UPSC Civil Services" },
    { k: "ssc", icon: "📋", title: "SSC Examinations" },
    { k: "banking", icon: "🏦", title: "Banking Interviews" },
    { k: "railway", icon: "🚂", title: "Railway RRB/NTPC" },
    { k: "campus_it", icon: "💻", title: "Campus IT (TCS/Amazon)" },
    { k: "campus_mba", icon: "🎓", title: "Campus MBA" },
    { k: "hr", icon: "🗣️", title: "HR Round Practice" },
    { k: "quick", icon: "⚡", title: "Quick 10-Min Drill" },
  ];

  const subTypes = {
    upsc: [["full_mock", "Full Mock"], ["daf_based", "DAF-Based"], ["current_affairs", "Current Affairs"], ["optional", "Optional Subject"], ["panel", "Panel Sim (3 AI)"]],
    campus_it: [["tcs_ninja", "TCS Ninja"], ["tcs_digital", "TCS Digital"], ["infosys", "Infosys"], ["wipro", "Wipro"], ["amazon", "Amazon SDE"], ["google", "Google"], ["microsoft", "Microsoft"], ["goldman", "Goldman Sachs"]],
    banking: [["sbi_po", "SBI PO"], ["ibps_po", "IBPS PO"], ["rbi_grade_b", "RBI Grade B"]],
    ssc: [["cgl", "CGL"], ["chsl", "CHSL"], ["gd", "GD"]],
    railway: [["ntpc", "NTPC"], ["group_d", "Group D"]],
    campus_mba: [["hr_round", "HR Round"], ["case", "Case Interview"], ["finance", "Finance"]],
    hr: [["general", "General HR"]],
    quick: [["mixed", "Mixed 10-min"]],
  };

  const next = () => setStep((s) => Math.min(5, s + 1));
  const back = () => setStep((s) => Math.max(1, s - 1));

  const handleResume = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { toast.error("Max 5MB"); return; }
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post("/resume/parse", fd, { headers: { "Content-Type": "multipart/form-data" }});
      setResume({ name: file.name, parsed: data.parsed });
      // The account's cached `user` (loaded once at app start) still holds the OLD resume.
      // Refresh it now so the interview room and video label use THIS newly uploaded resume.
      await refresh();
      toast.success("Resume parsed. Questions will be personalized.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Resume parse failed");
    } finally { setUploading(false); }
  };

  const begin = async () => {
    setCreating(true);
    try {
      const { data } = await api.post("/sessions", config);
      toast.success("Interview created. Loading room...");
      navigate(`/interview/room/${data.id}`);
    } catch (e) {
      toast.error("Failed to create session");
    } finally { setCreating(false); }
  };

  const steps = ["Category", "Sub-type", "Settings", "Resume", "Review"];

  return (
    <div className="p-6 lg:p-10 max-w-5xl mx-auto">
      <h1 className="font-display text-3xl font-semibold text-foreground">New Interview Setup</h1>

      <div className="mt-6 flex items-center gap-2 overflow-x-auto pb-2">
        {steps.map((label, i) => (
          <div key={label} className="flex items-center gap-2 shrink-0">
            <div data-testid={`stepper-${i+1}`} className={`h-9 w-9 rounded-full flex items-center justify-center text-xs font-bold ${step >= i+1 ? "gradient-gold-bg text-navy-deep" : "border border-gold-subtle text-foreground/50"}`}>{i+1}</div>
            <span className={`text-sm ${step >= i+1 ? "text-foreground" : "text-foreground/50"}`}>{label}</span>
            {i < steps.length - 1 && <div className={`h-px w-10 ${step > i+1 ? "bg-gold" : "bg-foreground/20"}`} />}
          </div>
        ))}
      </div>

      <div className="mt-8 card-surface p-8 min-h-[400px]">
        {step === 1 && (
          <div>
            <h2 className="font-display text-2xl text-foreground mb-6">Pick a category</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {categories.map((c) => (
                <button
                  key={c.k}
                  data-testid={`setup-cat-${c.k}`}
                  onClick={() => setConfig({ ...config, session_type: c.k, sub_type: (subTypes[c.k] || [])[0]?.[0] || "" })}
                  className={`p-5 rounded-2xl border text-left transition-all ${config.session_type === c.k ? "border-gold glow-gold-sm" : "border-gold-subtle hover:border-gold"}`}
                >
                  <div className="text-4xl">{c.icon}</div>
                  <div className="mt-3 font-semibold text-foreground text-sm">{c.title}</div>
                  {config.session_type === c.k && (
                    <div className="mt-2 inline-flex items-center gap-1 text-xs text-gold"><Check size={12} /> Selected</div>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <h2 className="font-display text-2xl text-foreground mb-6">Select sub-type</h2>
            <div className="flex flex-wrap gap-2">
              {(subTypes[config.session_type] || [["general", "General"]]).map(([k, label]) => (
                <button
                  key={k}
                  data-testid={`setup-subtype-${k}`}
                  onClick={() => setConfig({ ...config, sub_type: k, company: config.session_type === "campus_it" ? label : "" })}
                  className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${config.sub_type === k ? "gradient-gold-bg text-navy-deep" : "border border-gold-subtle text-foreground/80 hover:border-gold"}`}
                >{label}</button>
              ))}
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-8">
            <div>
              <div className="text-sm text-foreground/60 mb-2">Duration</div>
              <div className="flex flex-wrap gap-2">
                {[10, 20, 30, 45].map((m) => (
                  <button key={m} data-testid={`setup-duration-${m}`} onClick={() => setConfig({ ...config, duration_minutes: m })}
                    className={`px-4 py-2 rounded-full text-sm ${config.duration_minutes === m ? "gradient-gold-bg text-navy-deep font-semibold" : "border border-gold-subtle text-foreground/80"}`}>
                    {m} min
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="text-sm text-foreground/60 mb-2">Difficulty</div>
              <div className="flex flex-wrap gap-2">
                {["easy", "medium", "hard"].map((d) => (
                  <button key={d} data-testid={`setup-difficulty-${d}`} onClick={() => setConfig({ ...config, difficulty: d })}
                    className={`px-4 py-2 rounded-full text-sm capitalize ${config.difficulty === d ? "gradient-gold-bg text-navy-deep font-semibold" : "border border-gold-subtle text-foreground/80"}`}>
                    {d}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="text-sm text-foreground/60 mb-2">Interview Language</div>
              <div className="flex gap-3">
                {[
                  { k: "english", label: "English" },
                  { k: "hindi", label: "हिन्दी (Hindi)" },
                ].map((l) => (
                  <button key={l.k} data-testid={`setup-lang-${l.k}`} onClick={() => setConfig({ ...config, language: l.k })}
                    className={`flex-1 px-4 py-3 rounded-xl text-sm font-semibold border-2 transition-all ${config.language === l.k ? "border-gold gradient-gold-bg text-navy-deep" : "border-gold-subtle text-foreground/80"}`}>
                    {l.label}
                  </button>
                ))}
              </div>
              <div className="text-xs text-foreground/50 mt-2">
                Questions, follow-ups, and feedback will be entirely in {config.language === "hindi" ? "Hindi" : "English"}.
              </div>
              <details className="mt-3">
                <summary className="text-xs text-foreground/50 cursor-pointer hover:text-foreground/70">More languages (experimental)</summary>
                <div className="flex flex-wrap gap-2 mt-2">
                  {["hinglish", "tamil", "bengali", "marathi"].map((l) => (
                    <button key={l} data-testid={`setup-lang-${l}`} onClick={() => setConfig({ ...config, language: l })}
                      className={`px-4 py-2 rounded-full text-sm capitalize ${config.language === l ? "gradient-gold-bg text-navy-deep font-semibold" : "border border-gold-subtle text-foreground/80"}`}>
                      {l}
                    </button>
                  ))}
                </div>
              </details>
            </div>
            <div>
              <div className="text-sm text-foreground/60 mb-3">Interview Mode</div>
              <div className="space-y-3">
                {[
                  { k: "voice_camera", icon: Camera, title: "Voice + Camera (Recommended)", body: "Real interview experience. AI analyzes your body language. Requires microphone + camera." },
                  { k: "voice", icon: Mic, title: "Voice Only", body: "Voice conversation without camera. Just like a phone interview." },
                  { k: "text", icon: Keyboard, title: "Text Mode", body: "Type your answers. Good for slow connections." },
                ].map((m) => (
                  <button key={m.k} data-testid={`setup-mode-${m.k}`} onClick={() => setConfig({ ...config, mode: m.k })}
                    className={`w-full text-left p-4 rounded-xl border flex gap-4 items-start transition-all ${config.mode === m.k ? "border-gold glow-gold-sm" : "border-gold-subtle"}`}>
                    <div className="h-10 w-10 rounded-full bg-[rgba(184,150,46,0.1)] flex items-center justify-center text-gold shrink-0">
                      <m.icon size={18} />
                    </div>
                    <div>
                      <div className="font-semibold text-foreground">{m.title}</div>
                      <div className="text-xs text-foreground/70 mt-0.5">{m.body}</div>
                    </div>
                    <div className="ml-auto">
                      <div className={`h-5 w-5 rounded-full border-2 ${config.mode === m.k ? "border-gold bg-gold" : "border-foreground/30"}`} />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {step === 4 && (
          <div>
            <h2 className="font-display text-2xl text-foreground mb-4">Upload Resume (Optional)</h2>
            <p className="text-sm text-foreground/60 mb-4">Helps the AI personalize questions to YOUR background.</p>
            <label className="block rounded-2xl border-2 border-dashed border-gold-subtle p-12 text-center cursor-pointer hover:border-gold transition-colors" data-testid="setup-resume-zone">
              <FileText size={40} className="mx-auto text-gold" />
              <div className="mt-4 text-foreground/80">
                {uploading ? "Uploading & analyzing..." : resume ? `✅ ${resume.name}` : "Drop your Resume here"}
              </div>
              <div className="text-xs text-foreground/60 mt-1">PDF or DOCX, max 5MB</div>
              <input type="file" className="hidden" accept=".pdf,.docx" onChange={handleResume} disabled={uploading} />
              <div className="mt-5 inline-flex px-4 py-2 rounded-full border border-gold text-gold text-sm">
                {uploading ? <Loader2 size={14} className="animate-spin" /> : resume ? "Replace file" : "Browse Files"}
              </div>
            </label>
            <div className="text-center text-xs text-foreground/60 mt-4">
              <button onClick={next} data-testid="setup-resume-skip" className="text-gold hover:underline">Skip for now →</button>
            </div>
          </div>
        )}

        {step === 5 && (
          <div>
            <h2 className="font-display text-2xl text-foreground mb-6">Review & Launch</h2>
            <div className="rounded-2xl panel-surface p-6 space-y-3 text-sm">
              <Row label="Type" value={labelType(config.session_type)} />
              <Row label="Sub-type" value={config.sub_type?.replace("_", " ") || "—"} />
              <Row label="Duration" value={`${config.duration_minutes} minutes`} />
              <Row label="Difficulty" value={config.difficulty} cap />
              <Row label="Language" value={config.language} cap />
              <Row label="Interface" value={config.mode.replace("_", " + ")} cap />
              <Row label="Questions" value="~10–12 personalized" />
              <Row label="Resume" value={resume ? `✅ ${resume.name}` : "Not uploaded"} />
            </div>
          </div>
        )}
      </div>

      <div className="mt-6 flex items-center justify-between">
        <button data-testid="setup-back" onClick={back} disabled={step === 1} className="inline-flex items-center gap-1 px-5 py-2.5 rounded-full border border-gold-subtle text-foreground/80 hover:text-gold disabled:opacity-40">
          <ChevronLeft size={16} /> Back
        </button>
        {step < 5 ? (
          <button data-testid="setup-next" onClick={next} className="inline-flex items-center gap-1 px-6 py-2.5 rounded-full gradient-gold-bg text-navy-deep font-semibold hover:scale-[1.02]">
            Next <ChevronRight size={16} />
          </button>
        ) : (
          <button data-testid="setup-begin" onClick={begin} disabled={creating} className="inline-flex items-center gap-2 px-7 py-3 rounded-full gradient-gold-bg text-navy-deep font-semibold hover:scale-[1.02] glow-gold-sm disabled:opacity-60">
            <Mic size={16} /> {creating ? "Creating..." : "Begin Interview →"}
          </button>
        )}
      </div>
    </div>
  );
}

function labelType(t) {
  return ({ upsc: "UPSC Civil Services", ssc: "SSC", banking: "Banking", railway: "Railway", campus_it: "Campus IT", campus_mba: "Campus MBA", hr: "HR Round", quick: "Quick Drill" }[t] || t);
}

function Row({ label, value, cap }) {
  return (
    <div className="flex justify-between items-center text-foreground">
      <span className="text-foreground/60">{label}</span>
      <span className={`font-medium ${cap ? "capitalize" : ""}`}>{value}</span>
    </div>
  );
}
