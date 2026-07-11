import { CommonModule } from '@angular/common';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { DashboardComponent } from './components/dashboard/dashboard.component';
import {
  AnalysisResult,
  AnalysisService,
  AnalysisStreamEvent,
  StreamTransportError,
} from './services/analysis.service';
import { HistoryEntry, HistoryService } from './services/history.service';
import { buildMarkdownReport } from './services/report-export';

type AppState = 'idle' | 'loading' | 'done' | 'error';

interface ProgressStep {
  stage: string;
  label: string;
  status: 'active' | 'done';
}

interface TriageItem {
  url: string;
  status: 'queued' | 'running' | 'done' | 'error';
  report: AnalysisResult | null;
  error: string;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, DashboardComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class AppComponent {
  prUrl = '';
  triageInput = '';

  static readonly TRIAGE_MAX = 5;

  // Signals: change detection works reliably in this zoneless app even when
  // updates arrive from fetch/stream callbacks outside Angular's event system.
  readonly state = signal<AppState>('idle');
  readonly result = signal<AnalysisResult | null>(null);
  readonly errorMessage = signal('');
  readonly progressSteps = signal<ProgressStep[]>([]);
  readonly copied = signal(false);
  /** When viewing a saved snapshot from history: its capture timestamp. */
  readonly snapshotTime = signal<number | null>(null);
  readonly errorKind = signal<'url' | 'notfound' | 'llm' | 'rate' | 'generic'>('generic');
  readonly mode = signal<'single' | 'triage'>('single');
  readonly triageResults = signal<TriageItem[]>([]);
  /** Theme is applied to <html> pre-boot by index.html; this mirrors it. */
  readonly theme = signal<'light' | 'dark'>(
    (document.documentElement.getAttribute('data-theme') as 'light' | 'dark') ?? 'light',
  );

  /** GitHub (/pull/N) or any Gitea host (/pulls/N). */
  private static readonly PR_URL_PATTERN = /^https?:\/\/[^\/\s]+\/[^\/\s]+\/[^\/\s]+\/(pull|pulls)\/\d+/i;

  private abortController: AbortController | null = null;
  private copiedTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly analysisService: AnalysisService,
    readonly history: HistoryService,
  ) {}

  async analyse(): Promise<void> {
    const url = this.prUrl.trim();
    if (!url || this.state() === 'loading') return;

    // Validate the link shape before spending anything on a request.
    if (!AppComponent.PR_URL_PATTERN.test(url)) {
      this.result.set(null);
      this.snapshotTime.set(null);
      this.errorKind.set('url');
      this.errorMessage.set(
        'That link doesn’t point to a pull request. It needs the host, owner, repository, and PR number.',
      );
      this.state.set('error');
      return;
    }

    this.state.set('loading');
    this.result.set(null);
    this.triageResults.set([]);
    this.errorMessage.set('');
    this.snapshotTime.set(null);
    this.progressSteps.set([{ stage: 'connect', label: 'Connecting to analysis engine…', status: 'active' }]);

    this.abortController = new AbortController();

    try {
      await this.analysisService.analysePRStream(
        url,
        (event) => this.handleStreamEvent(event),
        this.abortController.signal,
      );
      // Stream ended without a result or error event → treat as failure.
      if (this.state() === 'loading') {
        this.fail('The analysis stream ended unexpectedly. Please try again.');
      }
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') return; // user reset
      if (err instanceof StreamTransportError) {
        // Streaming unavailable (old backend / strict proxy) — fall back to
        // the classic invoke-and-wait endpoint so nothing regresses.
        this.pushStep('fallback', 'Live progress unavailable — running full analysis…');
        this.analyseWithoutStream(url);
        return;
      }
      this.fail((err as Error)?.message || 'Something went wrong while analysing this pull request.');
    }
  }

  setMode(mode: 'single' | 'triage'): void {
    if (this.state() === 'loading') return;
    this.mode.set(mode);
  }

  /** Valid, deduplicated PR URLs from the triage textarea (capped). */
  get triageUrls(): string[] {
    const urls = this.triageInput
      .split(/\s+/)
      .map((u) => u.trim())
      .filter((u) => AppComponent.PR_URL_PATTERN.test(u));
    return [...new Set(urls)].slice(0, AppComponent.TRIAGE_MAX);
  }

  /**
   * Triage mode: analyse up to 5 PRs sequentially (kind to the backend and
   * to LLM quotas) and rank them riskiest-first as they complete.
   */
  async analyseTriage(): Promise<void> {
    const urls = this.triageUrls;
    if (this.state() === 'loading') return;
    if (!urls.length) {
      this.errorKind.set('url');
      this.errorMessage.set('No valid pull request links found. Paste one URL per line — GitHub or Gitea.');
      this.state.set('error');
      return;
    }

    this.result.set(null);
    this.errorMessage.set('');
    this.snapshotTime.set(null);
    this.triageResults.set(urls.map((url) => ({ url, status: 'queued' as const, report: null, error: '' })));
    this.state.set('loading');
    this.abortController = new AbortController();

    const total = urls.length;
    for (let i = 0; i < total; i++) {
      if (this.abortController.signal.aborted) return;
      this.patchTriage(i, { status: 'running' });
      this.progressSteps.set([
        { stage: 'triage', label: `PR ${i + 1} of ${total} — connecting…`, status: 'active' },
      ]);

      const outcome = await this.runOneForTriage(urls[i], i + 1, total);
      if (outcome.aborted) return;
      if (outcome.report) {
        this.patchTriage(i, { status: 'done', report: outcome.report });
        this.history.record(outcome.report);
      } else {
        this.patchTriage(i, { status: 'error', error: outcome.error ?? 'Analysis failed.' });
      }
    }

    this.progressSteps.set([]);
    this.state.set('done');
  }

  private patchTriage(index: number, patch: Partial<TriageItem>): void {
    this.triageResults.update((items) => items.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  }

  private async runOneForTriage(
    url: string,
    position: number,
    total: number,
  ): Promise<{ report?: AnalysisResult; error?: string; aborted?: boolean }> {
    let report: AnalysisResult | undefined;
    let error: string | undefined;

    try {
      await this.analysisService.analysePRStream(
        url,
        (event) => {
          if (event.type === 'status') {
            this.pushStep(event.stage, `PR ${position}/${total} — ${event.label}`);
          } else if (event.type === 'result') {
            report = event.payload;
          } else {
            error = event.message;
          }
        },
        this.abortController?.signal,
      );
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') return { aborted: true };
      if (err instanceof StreamTransportError) {
        try {
          report = await firstValueFrom(this.analysisService.analysePR(url));
        } catch (fallbackErr) {
          error = (fallbackErr as Error)?.message;
        }
      } else {
        error = (err as Error)?.message;
      }
    }

    if (report) return { report };
    return { error: error ?? 'The analysis stream ended unexpectedly.' };
  }

  /** Board order: completed (riskiest first), then running, queued, failed. */
  get sortedTriage(): TriageItem[] {
    const rank: Record<TriageItem['status'], number> = { done: 0, running: 1, queued: 2, error: 3 };
    return [...this.triageResults()].sort((a, b) => {
      if (a.status !== b.status) return rank[a.status] - rank[b.status];
      if (a.status === 'done' && b.status === 'done' && a.report && b.report) {
        return a.report.confidence_report.score - b.report.confidence_report.score;
      }
      return 0;
    });
  }

  openTriageItem(item: TriageItem): void {
    if (item.status !== 'done' || !item.report) return;
    this.snapshotTime.set(null);
    this.result.set(item.report);
  }

  backToTriage(): void {
    this.result.set(null);
  }

  /** The single most damaging signal for a triage card's one-line summary. */
  triageTopRisk(item: TriageItem): string {
    const drivers = item.report?.confidence_report?.score_drivers;
    if (!drivers) return '';
    const all = [
      ...(drivers.blast_radius ?? []),
      ...(drivers.engineering ?? []),
      ...(drivers.testing ?? []),
      ...(drivers.complexity ?? []),
    ].filter((d) => d.points < 0);
    if (!all.length) return 'No significant risk signals';
    return all.sort((a, b) => a.points - b.points)[0].label;
  }

  triageTitle(item: TriageItem): string {
    if (item.report) return item.report.name || item.report.pr_title || item.url;
    return item.url.replace(/^https?:\/\//, '');
  }

  triageSub(item: TriageItem): string {
    if (!item.report) return '';
    const num = this.prNumber(item.url);
    return `${item.report.repo_name}${num ? ' #' + num : ''}`;
  }

  /**
   * Open a history entry: show the saved snapshot instantly when we have it
   * (viewing is free); fall back to re-analysing for old entries without one.
   * A visible "Re-analyse" action refreshes deliberately.
   */
  openHistory(entry: HistoryEntry): void {
    if (this.state() === 'loading') return;
    this.prUrl = entry.pr_url;
    if (entry.report) {
      this.result.set(entry.report);
      this.errorMessage.set('');
      this.progressSteps.set([]);
      this.snapshotTime.set(entry.timestamp);
      this.state.set('done');
    } else {
      void this.analyse();
    }
  }

  async copyReport(): Promise<void> {
    const report = this.result();
    if (!report) return;
    try {
      await navigator.clipboard.writeText(buildMarkdownReport(report));
      this.copied.set(true);
      if (this.copiedTimer) clearTimeout(this.copiedTimer);
      this.copiedTimer = setTimeout(() => this.copied.set(false), 2200);
    } catch {
      // Clipboard unavailable — no-op rather than breaking the flow.
    }
  }

  private analyseWithoutStream(url: string): void {
    this.analysisService.analysePR(url).subscribe({
      next: (result) => this.succeed(result),
      error: (error: Error) => this.fail(error.message),
    });
  }

  private handleStreamEvent(event: AnalysisStreamEvent): void {
    switch (event.type) {
      case 'status':
        this.pushStep(event.stage, event.label);
        break;
      case 'result':
        this.succeed(event.payload);
        break;
      case 'error':
        this.fail(event.message);
        break;
    }
  }

  private pushStep(stage: string, label: string): void {
    this.progressSteps.update((steps) => [
      ...steps.map((step) => ({ ...step, status: 'done' as const })),
      { stage, label, status: 'active' },
    ]);
  }

  private succeed(result: AnalysisResult): void {
    this.progressSteps.update((steps) => steps.map((step) => ({ ...step, status: 'done' as const })));
    this.result.set(result);
    this.state.set('done');
    this.history.record(result);
  }

  private fail(message: string): void {
    this.errorMessage.set(message);
    this.errorKind.set(this.classifyError(message));
    this.state.set('error');
  }

  private classifyError(message: string): 'url' | 'notfound' | 'llm' | 'rate' | 'generic' {
    const lowered = message.toLowerCase();
    if (lowered.includes('invalid github pr url')) return 'url';
    if (lowered.includes('not found')) return 'notfound';
    if (lowered.includes('ai analysis unavailable')) return 'llm';
    if (lowered.includes('rate limit')) return 'rate';
    return 'generic';
  }

  get errorTitle(): string {
    switch (this.errorKind()) {
      case 'url':
        return 'That doesn’t look like a PR link';
      case 'notfound':
        return 'Pull request not found';
      case 'llm':
        return 'AI unavailable — no report generated';
      case 'rate':
        return 'Taking a short breather';
      default:
        return 'Analysis failed';
    }
  }

  toggleTheme(): void {
    const next = this.theme() === 'dark' ? 'light' : 'dark';
    this.theme.set(next);
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem('prisk.theme', next);
    } catch {
      // Storage unavailable — theme still applies for this session.
    }
  }

  reset(): void {
    this.abortController?.abort();
    this.abortController = null;
    this.state.set('idle');
    this.result.set(null);
    this.triageResults.set([]);
    this.errorMessage.set('');
    this.progressSteps.set([]);
    this.snapshotTime.set(null);
    this.prUrl = '';
    this.triageInput = '';
  }

  get stateLabel(): string {
    switch (this.state()) {
      case 'loading':
        return 'Running';
      case 'done':
        return 'Ready';
      case 'error':
        return 'Blocked';
      default:
        return 'Waiting';
    }
  }

  /** Extract the PR number from the URL for the meta chip (GitHub or Gitea). */
  prNumber(url: string): string {
    const match = url?.match(/\/pulls?\/(\d+)/);
    return match ? match[1] : '';
  }

  /** Circumference-based offset for the SVG confidence gauge (r = 34). */
  gaugeOffset(score: number): number {
    const circumference = 2 * Math.PI * 34;
    return circumference * (1 - Math.max(0, Math.min(100, score)) / 100);
  }

  timeAgo(timestamp: number): string {
    const seconds = Math.floor((Date.now() - timestamp) / 1000);
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  }
}

export { AppComponent as App };
