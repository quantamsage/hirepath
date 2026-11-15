"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import TopBar from "@/components/TopBar";
import { api, ApiError, clearToken, getToken } from "@/lib/api";
import { STATUSES, type Stats } from "@/lib/types";

const percent = (value: number) => `${Math.round(value * 100)}%`;
const weekLabel = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });

export default function StatsPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");

  const handleError = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 401) {
      clearToken();
      router.replace("/login?expired=1");
      return;
    }
    setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
  }, [router]);

  const load = useCallback(() => {
    setError("");
    api.getStats().then(setStats).catch(handleError);
  }, [handleError]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api.me().then((u) => setEmail(u.email)).catch(handleError);
    load();
  }, [router, load, handleError]);

  return (
    <div className="page">
      <TopBar email={email} />
      <main className="board-page">
        <div className="board-head">
          <div>
            <h1>Your job search in numbers</h1>
            <p className="board-summary">Rates count every application that ever reached a stage, even if it was later rejected.</p>
          </div>
        </div>

        {error && (
          <div className="banner" role="alert">
            <span>{error}</span>
            <button type="button" className="btn-text" onClick={load}>Try again</button>
          </div>
        )}
        {!stats && !error && <p className="loading">Loading your stats…</p>}
        {stats && stats.total === 0 && (
          <p className="column-empty">No applications yet. Add some on the board, or import a CSV, and your stats will show up here.</p>
        )}
        {stats && stats.total > 0 && <StatsView stats={stats} />}
      </main>
    </div>
  );
}

function StatsView({ stats }: { stats: Stats }) {
  const funnel = [
    { label: "Applied", count: stats.total, rate: 1, tone: "applied" },
    { label: "Heard back", count: stats.responded, rate: stats.response_rate, tone: "rejected" },
    { label: "Interviewed", count: stats.interviewed, rate: stats.interview_rate, tone: "interview" },
    { label: "Offers", count: stats.offers, rate: stats.offer_rate, tone: "offer" },
  ];
  const busiest = Math.max(1, ...stats.weekly.map((w) => w.count));
  const thisWeek = stats.weekly[stats.weekly.length - 1]?.count ?? 0;

  return (
    <div className="stats">
      <section className="stat-tiles" aria-label="Summary">
        <Tile value={String(stats.total)} label="applications tracked" />
        <Tile value={percent(stats.response_rate)} label="response rate" />
        <Tile value={percent(stats.interview_rate)} label="reached an interview" />
        <Tile value={String(thisWeek)} label="applied this week" />
      </section>

      <section className="stat-panel" aria-labelledby="funnel-title">
        <h2 id="funnel-title">Funnel</h2>
        <ol className="funnel">
          {funnel.map((step) => (
            <li key={step.label} className={`funnel-step tone-${step.tone}`}>
              <span className="funnel-label">{step.label}</span>
              <span className="funnel-track">
                <span className="funnel-bar" style={{ width: `${Math.max(step.rate * 100, step.count ? 2 : 0)}%` }} />
              </span>
              <span className="funnel-value">{step.count} <span className="muted">({percent(step.rate)})</span></span>
            </li>
          ))}
        </ol>
      </section>

      <section className="stat-panel" aria-labelledby="weekly-title">
        <h2 id="weekly-title">Applications per week</h2>
        <p className="muted">Last 12 weeks, by the date you applied.</p>
        <div className="weekly" role="img"
          aria-label={stats.weekly.map((w) => `Week of ${weekLabel(w.week_start)}: ${w.count}`).join(", ")}>
          {stats.weekly.map((w) => (
            <div key={w.week_start} className="weekly-col" title={`Week of ${weekLabel(w.week_start)}: ${w.count}`}>
              <span className="weekly-count">{w.count || ""}</span>
              <span className="weekly-bar" style={{ height: `${(w.count / busiest) * 100}%` }} />
              <span className="weekly-label">{weekLabel(w.week_start)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="stat-panel" aria-labelledby="now-title">
        <h2 id="now-title">Where things stand now</h2>
        <ul className="status-now">
          {STATUSES.map((s) => (
            <li key={s} className={`column-${s.toLowerCase()}`}>
              <span className="column-count">{stats.by_status[s] ?? 0}</span> {s}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Tile({ value, label }: { value: string; label: string }) {
  return (
    <div className="stat-tile">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}
