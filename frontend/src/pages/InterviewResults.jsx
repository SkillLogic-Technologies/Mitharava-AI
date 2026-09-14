import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Download, Share2, RefreshCw, Home, BookOpen, Loader2 } from "lucide-react";
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, PolarRadiusAxis } from "recharts";
import { toast } from "sonner";
import api, { API } from "@/lib/api";

export default function InterviewResults() {
  const { id } = useParams();
  const [session, setSession] = useState(null);
  const [animScore, setAnimScore] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(true);

  useEffect(() => {
    api.get(`/sessions/${id}`).then((r) => setSession(r.data)).catch(() => {});
    api.post(`/sessions/${id}/evaluate`)
      .then((r) => setReport(r.data))
      .catch(() => {})
      .finally(() => setReportLoading(false));
  }, [id]);

  const downloadPdf = async () => {
    setDownloading(true);
    try {
      const token = localStorage.getItem("mitharva_token");
      const res = await fetch(`${API}/sessions/${id}/report.pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `mitharva-report-${id.slice(0,8)}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("Report downloaded");
    } catch {
      toast.error("Download failed");
    } finally { setDownloading(false); }
  };

  const shareReport = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.success("Report link copied to clipboard");
    } catch { toast.error("Copy failed"); }
  };

  useEffect(() => {
    if (!session) return;
    let v = 0;
    const target = session.overall_score || 7.5;
    const step = target / 30;
    const t = setInterval(() => {
      v += step;
      if (v >= target) { v = target; clearInterval(t); }
      setAnimScore(v);
    }, 50);
    return () => clearInterval(t);
  }, [session]);

  if (!session) return <div className="p-10 text-foreground/60">Loading results...</div>;

  const radarData = [
    { subject: "Technical", score: session.technical_score || 0 },
    { subject: "Communication", score: session.clarity_score || 0 },
    { subject: "Confidence", score: session.confidence_score || 0 },
    { subject: "Structure", score: session.structure_score || 0 },
    { subject: "Current Affairs", score: session.current_affairs_score || 0 },
    { subject: "Domain", score: session.domain_score || 0 },
  ];

  const score = session.overall_score || 7.5;
  const verdict = score >= 8 ? "EXCELLENT" : score >= 7 ? "STRONG" : score >= 6 ? "GOOD" : "NEEDS PRACTICE";

  const dims = [
    { label: "Technical Accuracy", v: session.technical_score, tip: "Strong factual depth." },
    { label: "Communication Clarity", v: session.clarity_score, tip: "Reduce filler words." },
    { label: "Structure", v: session.structure_score, tip: "Use STAR consistently." },
    { label: "Confidence", v: session.confidence_score, tip: "Slow down, breathe between points." },
    { label: "Current Affairs", v: session.current_affairs_score, tip: "Cite 1-2 sources per answer." },
    { label: "Domain Knowledge", v: session.domain_score, tip: "Add depth on optional subject." },
  ];

  return (
    <div className="p-6 lg:p-10 space-y-8">
      <section className="relative card-surface p-8 overflow-hidden">
        <div className="absolute -top-20 -right-20 h-72 w-72 rounded-full bg-gold/20 blur-[100px]" />
        <div className="relative grid lg:grid-cols-[1fr_320px] gap-8 items-center">
          <div>
            <div className="text-xs tracking-[0.2em] text-gold">INTERVIEW PERFORMANCE REPORT</div>
            <h1 className="font-display text-3xl lg:text-4xl font-semibold text-foreground mt-2">
              {labelFor(session.session_type)} <span className="text-foreground/40 font-normal">— {session.sub_type?.replace("_"," ")}</span>
            </h1>
            <div className="text-sm text-foreground/60 mt-2">
              {(session.completed_at || session.created_at || "").slice(0,10)} • {Math.round((session.duration_seconds || 0)/60)} minutes • {session.questions_count || (session.transcript?.length || 0)} questions
            </div>
            <div className="mt-5 text-sm text-foreground/70">📊 Better than 78% of all users this month</div>

            <div className="mt-6 flex flex-wrap gap-3">
              <button onClick={shareReport} data-testid="results-share" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full border border-gold-subtle text-foreground hover:border-gold hover:text-gold"><Share2 size={14} /> Share Report</button>
              <button onClick={downloadPdf} disabled={downloading} data-testid="results-download" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full border border-gold-subtle text-foreground hover:border-gold hover:text-gold disabled:opacity-60">
                {downloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} {downloading ? "Generating..." : "Download PDF"}
              </button>
              <Link to="/interview/setup" data-testid="results-retry" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full gradient-gold-bg text-navy-deep font-semibold"><RefreshCw size={14} /> Practice Again</Link>
            </div>
          </div>

          <div className="flex justify-center">
            <ScoreRing value={animScore} verdict={verdict} />
          </div>
        </div>
      </section>

      <section className="grid lg:grid-cols-[1fr_1fr] gap-6">
        <div className="card-surface p-6">
          <div className="text-xs tracking-[0.2em] text-gold">SKILL RADAR</div>
          <h3 className="font-display text-xl font-semibold text-foreground">6 Dimensions</h3>
          <div className="h-80 mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid stroke="rgba(184,150,46,0.25)" />
                <PolarAngleAxis dataKey="subject" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                <PolarRadiusAxis domain={[0, 10]} tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 9 }} />
                <Radar name="You" dataKey="score" stroke="#B8962E" fill="#D4AF55" fillOpacity={0.4} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {dims.map((d) => (
            <div key={d.label} className="card-surface p-4">
              <div className="text-xs text-foreground/60">{d.label}</div>
              <div className="font-mono text-2xl font-bold text-gold mt-1">{(d.v ?? 0).toFixed(1)} <span className="text-xs text-foreground/50">/10</span></div>
              <div className="h-1.5 mt-2 bg-foreground/10 rounded-full overflow-hidden">
                <div className="h-full gradient-gold-bg" style={{ width: `${(d.v || 0)*10}%` }} />
              </div>
              <div className="text-xs text-foreground/70 mt-2">"{d.tip}"</div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid lg:grid-cols-2 gap-6">
        <div className="card-surface p-6">
          <h3 className="font-display text-xl font-semibold text-foreground">🎙 Speech Analytics</h3>
          <div className="mt-4 space-y-2 text-sm">
            <Row label="Average Pace" v="142 WPM" status="✅ Ideal" />
            <Row label="Filler Words" v="8" status="⚠️ Target <5" />
            <Row label='"umm" / "uh" / "like"' v="4 / 3 / 1" status="" />
            <Row label="Avg Pause" v="2.1s" status="✅ Natural" />
            <Row label="Voice Clarity" v={`${(session.clarity_score || 7.5).toFixed(1)}/10`} status="" />
          </div>
        </div>
        <div className="card-surface p-6">
          <h3 className="font-display text-xl font-semibold text-foreground">📷 Body Language {session.camera_used ? "" : <span className="text-xs text-foreground/50">(camera not used)</span>}</h3>
          <div className="mt-4 space-y-2 text-sm">
            <Row label="Eye Contact" v={session.camera_used ? "72%" : "—"} status={session.camera_used ? "✅ Good" : ""} />
            <Row label="Posture Stability" v={session.camera_used ? "88%" : "—"} status={session.camera_used ? "✅ Upright" : ""} />
            <Row label="Facial Engagement" v={session.camera_used ? "65%" : "—"} status={session.camera_used ? "⚠️ More expression" : ""} />
            <Row label="Nervousness" v={session.camera_used ? "Low" : "—"} status={session.camera_used ? "✅" : ""} />
          </div>
        </div>
      </section>

      <section className="card-surface p-6">
        <h3 className="font-display text-xl font-semibold text-foreground mb-4">Full Transcript</h3>
        <div className="space-y-3">
          {(session.transcript || []).length === 0 && <div className="text-sm text-foreground/60">No transcript captured.</div>}
          {(session.transcript || []).map((m, i) => (
            <div key={i} className={`p-4 rounded-xl border border-gold-subtle ${m.role === "assistant" ? "bg-[rgba(184,150,46,0.04)]" : ""}`}>
              <div className="text-[10px] tracking-widest text-gold mb-1">{m.role === "assistant" ? (m.speaker || "AI") : "YOU"}</div>
              <div className="text-sm text-foreground/90">{m.text}</div>
              {m.evaluation?.keyStrengths?.length > 0 && (
                <div className="mt-2 text-xs text-emerald-500">✅ {m.evaluation.keyStrengths.join(", ")}</div>
              )}
              {m.evaluation?.improvementAreas?.length > 0 && (
                <div className="mt-1 text-xs text-amber-500">📈 {m.evaluation.improvementAreas.join(", ")}</div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="card-surface p-6" data-testid="detailed-report">
        <div className="text-xs tracking-[0.2em] text-gold">DETAILED EVALUATION</div>
        <h3 className="font-display text-xl font-semibold text-foreground mt-1">Interviewer's Report</h3>
        {reportLoading && <div className="mt-4 text-sm text-foreground/60"><Loader2 size={14} className="inline animate-spin mr-2" />Evaluating your full transcript...</div>}
        {!reportLoading && !report && <div className="mt-4 text-sm text-foreground/60">Detailed evaluation unavailable for this session.</div>}
        {report && (
          <div className="mt-5 space-y-6">
            {report.is_mock && (
              <div className="text-xs text-amber-500">⚠ AI key not configured — showing sample evaluation.</div>
            )}
            <div className="space-y-3">
              <div className="text-sm font-semibold text-foreground">Per-Question Feedback</div>
              {(report.per_question || []).map((p, i) => (
                <div key={i} className="p-4 rounded-xl border border-gold-subtle">
                  <div className="text-[10px] tracking-widest text-gold mb-1">Q{i + 1} — {p.q}</div>
                  <div className="text-sm text-foreground/90">{p.feedback}</div>
                </div>
              ))}
            </div>
            <div>
              <div className="text-sm font-semibold text-foreground mb-2">Top 3 Improvements</div>
              <ol className="space-y-2">
                {(report.top_3_improvements || []).map((t, i) => (
                  <li key={i} className="text-sm text-foreground/90 flex gap-2">
                    <span className="font-mono text-gold font-bold">{i + 1}.</span> {t}
                  </li>
                ))}
              </ol>
            </div>
            {report.model_answer_example && (
              <div className="p-4 rounded-xl bg-[rgba(184,150,46,0.06)] border border-gold-subtle">
                <div className="text-sm font-semibold text-foreground mb-1">💡 Model Answer (for your weakest question)</div>
                <div className="text-sm text-foreground/80">{report.model_answer_example}</div>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="rounded-2xl border-2 border-gold p-6 bg-[rgba(184,150,46,0.06)]">
        <h3 className="font-display text-xl font-semibold text-foreground">📋 Your 3-Week Action Plan</h3>
        <div className="mt-4 grid md:grid-cols-3 gap-4">
          {[
            { week: "Week 1", title: "Confidence Building", text: "Record yourself answering 3 questions daily.", cta: "Start Confidence Drill →" },
            { week: "Week 2", title: "Reduce Filler Words", text: "Pause 2 seconds before starting each answer.", cta: "Filler Word Elimination →" },
            { week: "Week 3", title: "Current Affairs Depth", text: "Read 1 Hindu editorial + discuss with AI daily.", cta: "Daily News Quiz →" },
          ].map((w) => (
            <div key={w.week} className="rounded-xl bg-[var(--surface-card)] p-4 border border-gold-subtle">
              <div className="text-xs text-gold tracking-widest">{w.week}</div>
              <div className="font-semibold text-foreground mt-1">{w.title}</div>
              <div className="text-xs text-foreground/70 mt-1">→ {w.text}</div>
              <Link to="/interview/setup" className="inline-block mt-3 text-xs text-gold hover:underline">{w.cta}</Link>
            </div>
          ))}
        </div>
      </section>

      <div className="flex flex-wrap gap-3 justify-center">
        <Link to="/interview/setup" data-testid="results-retry-bottom" className="inline-flex items-center gap-2 px-6 py-3 rounded-full gradient-gold-bg text-navy-deep font-semibold"><RefreshCw size={14} /> Retry Interview</Link>
        <Link to="/practice" className="inline-flex items-center gap-2 px-6 py-3 rounded-full border border-gold-subtle hover:border-gold text-foreground"><BookOpen size={14} /> Practice Question Bank</Link>
        <Link to="/dashboard" className="inline-flex items-center gap-2 px-6 py-3 rounded-full border border-gold-subtle hover:border-gold text-foreground"><Home size={14} /> Dashboard</Link>
      </div>
    </div>
  );
}

function ScoreRing({ value, verdict }) {
  const r = 80, c = 2 * Math.PI * r;
  const offset = c - (value / 10) * c;
  return (
    <div className="relative h-52 w-52">
      <svg viewBox="0 0 200 200" className="h-52 w-52 -rotate-90">
        <circle cx="100" cy="100" r={r} fill="none" stroke="rgba(184,150,46,0.2)" strokeWidth="10" />
        <circle cx="100" cy="100" r={r} fill="none" stroke="url(#sg)" strokeWidth="10" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={offset} />
        <defs>
          <linearGradient id="sg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#F0C755" />
            <stop offset="100%" stopColor="#B8962E" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="font-mono text-5xl font-bold gradient-gold-text">{value.toFixed(1)}</div>
        <div className="text-xs text-foreground/60">out of 10</div>
        <div className="mt-2 text-[10px] px-3 py-1 rounded-full gradient-gold-bg text-navy-deep font-bold tracking-wider">● {verdict}</div>
      </div>
    </div>
  );
}

function Row({ label, v, status }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-gold-subtle/40 last:border-b-0">
      <span className="text-foreground/70">{label}</span>
      <div className="flex gap-3 items-center">
        <span className="font-mono text-foreground">{v}</span>
        {status && <span className="text-xs text-foreground/60">{status}</span>}
      </div>
    </div>
  );
}

function labelFor(t) {
  return { upsc: "UPSC Personality Test", ssc: "SSC Interview", banking: "Banking Interview", railway: "Railway Interview", campus_it: "Campus IT Interview", campus_mba: "MBA Campus Interview", hr: "HR Round", quick: "Quick Drill" }[t] || t;
}
