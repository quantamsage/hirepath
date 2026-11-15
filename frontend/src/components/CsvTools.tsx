"use client";

import { ChangeEvent, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Props = {
  onImported: () => Promise<void>;
  onError: (err: unknown) => void;
};

const MAX_FILE_BYTES = 1_000_000;

/** Import a CSV of applications, or download everything as CSV. */
export default function CsvTools({ onImported, onError }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [problems, setProblems] = useState<{ field: string; message: string }[]>([]);

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // so picking the same file again still triggers a change
    if (!file) return;
    setMessage("");
    setProblems([]);
    if (file.size > MAX_FILE_BYTES) {
      setMessage("That file is over 1 MB. Split it into smaller files.");
      return;
    }
    setBusy(true);
    try {
      const { imported } = await api.importCsv(await file.text());
      setMessage(`Imported ${imported} application${imported === 1 ? "" : "s"}.`);
      await onImported();
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setMessage(err.details.length > 1 ? "Nothing was imported. Fix these rows and try again:" : err.message);
        if (err.details.length > 1) setProblems(err.details);
      } else {
        onError(err);
      }
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    setBusy(true);
    try {
      const blob = await api.exportCsv();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `applications-${new Date().toLocaleDateString("en-CA")}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      onError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="csv-tools">
      <div className="csv-buttons">
        <button type="button" className="btn btn-quiet" disabled={busy} onClick={() => fileRef.current?.click()}>
          Import CSV
        </button>
        <button type="button" className="btn btn-quiet" disabled={busy} onClick={download}>
          Export CSV
        </button>
        <input ref={fileRef} type="file" accept=".csv,text/csv" className="visually-hidden"
          aria-label="CSV file to import" onChange={handleFile} tabIndex={-1} />
      </div>
      {message && (
        <div className="csv-message" role="status">
          <p>{message}</p>
          {problems.length > 0 && (
            <ul>
              {problems.map((p, i) => <li key={i}><strong>{p.field}:</strong> {p.message}</li>)}
            </ul>
          )}
          <p className="csv-hint">
            Columns: <code>company, role, status, applied_on, follow_up_date, url, notes</code>.
            Only company and role are required. Dates look like 2026-10-31.
          </p>
        </div>
      )}
    </div>
  );
}
