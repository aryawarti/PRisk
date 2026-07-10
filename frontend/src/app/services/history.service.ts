import { Injectable, signal } from '@angular/core';

import { AnalysisResult } from './analysis.service';

export interface HistoryEntry {
  pr_url: string;
  repo_name: string;
  title: string;
  score: number;
  recommendation: string;
  color: 'green' | 'amber' | 'red';
  timestamp: number;
  /** Score change vs. the previous analysis of the same PR, if any. */
  delta: number | null;
  /** Full saved report so history opens instantly without re-running. */
  report?: AnalysisResult;
}

const STORAGE_KEY = 'prisk.history.v1';
const MAX_ENTRIES = 8;

/**
 * Recent-analyses history, persisted locally.
 * The headline feature is the score delta: re-analyse the same PR after
 * pushing fixes and the sidebar shows "67 → 84 (+17)" — the product's
 * value loop made visible.
 */
@Injectable({ providedIn: 'root' })
export class HistoryService {
  readonly entries = signal<HistoryEntry[]>(this.load());

  record(result: AnalysisResult): void {
    const previous = this.entries().find((entry) => entry.pr_url === result.pr_url);

    const entry: HistoryEntry = {
      pr_url: result.pr_url,
      repo_name: result.repo_name,
      title: result.name || result.pr_title || result.pr_url,
      score: result.confidence_report.score,
      recommendation: result.confidence_report.recommendation,
      color: result.confidence_report.recommendation_color,
      timestamp: Date.now(),
      delta: previous ? result.confidence_report.score - previous.score : null,
      report: result,
    };

    const next = [entry, ...this.entries().filter((e) => e.pr_url !== result.pr_url)].slice(
      0,
      MAX_ENTRIES,
    );
    this.entries.set(next);
    this.persist(next);
  }

  clear(): void {
    this.entries.set([]);
    this.persist([]);
  }

  private load(): HistoryEntry[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.slice(0, MAX_ENTRIES) : [];
    } catch {
      return [];
    }
  }

  private persist(entries: HistoryEntry[]): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    } catch {
      // Quota exceeded or storage unavailable — retry without the full
      // reports so at least the score history survives.
      try {
        const slim = entries.map(({ report, ...rest }) => rest);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(slim));
      } catch {
        // Storage fully unavailable (private mode etc.) — skip persistence.
      }
    }
  }
}
