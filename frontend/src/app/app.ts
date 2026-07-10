import { CommonModule } from '@angular/common';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

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

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, DashboardComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class AppComponent {
  prUrl = '';

  // Signals: change detection works reliably in this zoneless app even when
  // updates arrive from fetch/stream callbacks outside Angular's event system.
  readonly state = signal<AppState>('idle');
  readonly result = signal<AnalysisResult | null>(null);
  readonly errorMessage = signal('');
  readonly progressSteps = signal<ProgressStep[]>([]);
  readonly copied = signal(false);
  /** When viewing a saved snapshot from history: its capture timestamp. */
  readonly snapshotTime = signal<number | null>(null);

  private abortController: AbortController | null = null;
  private copiedTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly analysisService: AnalysisService,
    readonly history: HistoryService,
  ) {}

  async analyse(): Promise<void> {
    const url = this.prUrl.trim();
    if (!url || this.state() === 'loading') return;

    this.state.set('loading');
    this.result.set(null);
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
    this.state.set('error');
  }

  reset(): void {
    this.abortController?.abort();
    this.abortController = null;
    this.state.set('idle');
    this.result.set(null);
    this.errorMessage.set('');
    this.progressSteps.set([]);
    this.snapshotTime.set(null);
    this.prUrl = '';
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
