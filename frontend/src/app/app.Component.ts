// src/app/app.component.ts
// --------------------------
// Root component. Shows either:
//   - The URL input form (when no analysis is running/done)
//   - A loading spinner (while LangGraph runs)
//   - The full report dashboard (when analysis is complete)
//   - An error message (if something went wrong)

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';

import { AnalysisService, AnalysisResult } from './services/analysis.service';
import { DashboardComponent } from './components/dashboard/dashboard.component';

type AppState = 'idle' | 'loading' | 'done' | 'error';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule, DashboardComponent],
  template: `
    <div class="app">
      <!-- ── HEADER ── -->
      <header class="header">
        <div class="header-inner">
          <div class="logo">
            <span class="logo-icon">⬡</span>
            <span class="logo-text">DiffVision</span>
          </div>
          <span class="tagline">PR Risk Intelligence</span>
        </div>
      </header>

      <!-- ── MAIN ── -->
      <main class="main">
        <!-- URL Input Form (shown in idle state) -->
        <section class="hero" *ngIf="state === 'idle' || state === 'error'">
          <h1 class="hero-title">Should this PR be merged?</h1>
          <p class="hero-sub">
            Paste a GitHub Pull Request URL and DiffVision will estimate blast radius, identify
            engineering risks, recommend tests, and score merge confidence.
          </p>

          <div class="input-row">
            <input
              class="pr-input"
              type="text"
              [(ngModel)]="prUrl"
              placeholder="https://github.com/owner/repo/pull/42"
              (keydown.enter)="analyse()"
            />
            <button
              class="analyse-btn"
              (click)="analyse()"
              [disabled]="!prUrl.trim()"
            >
              Analyse PR
            </button>
          </div>

          <div class="error-box" *ngIf="state === 'error'">
            <strong>Error:</strong> {{ errorMessage }}
          </div>

          <!-- Example URLs to help beginners -->
          <div class="examples">
            <span class="examples-label">Try with a public PR:</span>
            <button
              class="example-link"
              (click)="useExample('https://github.com/pallets/flask/pull/5000')"
            >
              Flask #5000
            </button>
            <button
              class="example-link"
              (click)="useExample('https://github.com/django/django/pull/1')"
            >
              Django
            </button>
          </div>
        </section>

        <!-- Loading State -->
        <section class="loading-screen" *ngIf="state === 'loading'">
          <div class="spinner"></div>
          <h2 class="loading-title">Analysing Pull Request...</h2>
          <div class="loading-steps">
            <div class="step" [class.active]="loadingStep >= 0">📥 Fetching PR from GitHub</div>
            <div class="step" [class.active]="loadingStep >= 1">
              🔍 Reading repository structure
            </div>
            <div class="step" [class.active]="loadingStep >= 2">
              🤖 Running AI agents (this takes ~30 seconds)
            </div>
            <div class="step" [class.active]="loadingStep >= 3">
              📊 Computing merge confidence score
            </div>
          </div>
        </section>

        <!-- Results Dashboard -->
        <section *ngIf="state === 'done' && result">
          <div class="results-header">
            <button class="back-btn" (click)="reset()">← New Analysis</button>
            <span class="results-repo">{{ result.repo_name }}</span>
          </div>
          <app-dashboard [result]="result"></app-dashboard>
        </section>
      </main>
    </div>
  `,
  styles: [
    `
      .app {
        min-height: 100vh;
        background: #f8f9fa;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }

      /* Header */
      .header {
        background: #1a1a2e;
        padding: 0 2rem;
      }
      .header-inner {
        max-width: 1100px;
        margin: 0 auto;
        height: 60px;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .logo {
        display: flex;
        align-items: center;
        gap: 10px;
      }
      .logo-icon {
        font-size: 1.5rem;
        color: #7c3aed;
      }
      .logo-text {
        font-size: 1.25rem;
        font-weight: 700;
        color: #fff;
        letter-spacing: -0.02em;
      }
      .tagline {
        font-size: 0.75rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }

      /* Main layout */
      .main {
        max-width: 1100px;
        margin: 0 auto;
        padding: 2rem 1.5rem;
      }

      /* Hero */
      .hero {
        max-width: 680px;
        margin: 4rem auto;
        text-align: center;
      }
      .hero-title {
        font-size: 2.5rem;
        font-weight: 800;
        color: #111827;
        margin: 0 0 1rem;
        letter-spacing: -0.03em;
      }
      .hero-sub {
        font-size: 1.05rem;
        color: #6b7280;
        line-height: 1.7;
        margin: 0 0 2rem;
      }

      /* Input */
      .input-row {
        display: flex;
        gap: 10px;
        margin-bottom: 1rem;
      }
      .pr-input {
        flex: 1;
        padding: 0.75rem 1rem;
        border: 1.5px solid #d1d5db;
        border-radius: 8px;
        font-size: 0.95rem;
        outline: none;
        transition: border-color 0.15s;
      }
      .pr-input:focus {
        border-color: #7c3aed;
      }
      .analyse-btn {
        padding: 0.75rem 1.5rem;
        background: #7c3aed;
        color: #fff;
        border: none;
        border-radius: 8px;
        font-size: 0.95rem;
        font-weight: 600;
        cursor: pointer;
        transition:
          background 0.15s,
          transform 0.1s;
        white-space: nowrap;
      }
      .analyse-btn:hover:not(:disabled) {
        background: #6d28d9;
      }
      .analyse-btn:active:not(:disabled) {
        transform: scale(0.98);
      }
      .analyse-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      /* Error */
      .error-box {
        background: #fef2f2;
        border: 1px solid #fecaca;
        color: #991b1b;
        padding: 0.75rem 1rem;
        border-radius: 8px;
        font-size: 0.9rem;
        margin-bottom: 1rem;
        text-align: left;
      }

      /* Examples */
      .examples {
        display: flex;
        align-items: center;
        gap: 8px;
        justify-content: center;
        flex-wrap: wrap;
      }
      .examples-label {
        font-size: 0.8rem;
        color: #9ca3af;
      }
      .example-link {
        background: none;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        padding: 2px 10px;
        font-size: 0.8rem;
        color: #7c3aed;
        cursor: pointer;
      }
      .example-link:hover {
        background: #f5f3ff;
      }

      /* Loading */
      .loading-screen {
        text-align: center;
        padding: 4rem 2rem;
      }
      .spinner {
        width: 48px;
        height: 48px;
        border: 3px solid #e5e7eb;
        border-top-color: #7c3aed;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
        margin: 0 auto 1.5rem;
      }
      @keyframes spin {
        to {
          transform: rotate(360deg);
        }
      }
      .loading-title {
        font-size: 1.5rem;
        font-weight: 700;
        color: #111827;
        margin-bottom: 1.5rem;
      }
      .loading-steps {
        display: inline-flex;
        flex-direction: column;
        gap: 8px;
        text-align: left;
      }
      .step {
        font-size: 0.9rem;
        color: #9ca3af;
        padding: 6px 12px;
        border-radius: 6px;
        transition: all 0.3s;
      }
      .step.active {
        color: #111827;
        background: #f3f0ff;
      }

      /* Results header */
      .results-header {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-bottom: 1.5rem;
      }
      .back-btn {
        background: none;
        border: 1px solid #d1d5db;
        padding: 6px 14px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.875rem;
        color: #374151;
      }
      .back-btn:hover {
        background: #f9fafb;
      }
      .results-repo {
        font-size: 0.875rem;
        color: #6b7280;
        font-family: monospace;
      }
    `,
  ],
})
export class AppComponent {
  prUrl = '';
  state: AppState = 'idle';
  result: AnalysisResult | null = null;
  errorMessage = '';
  loadingStep = 0;
  private loadingTimer: any;

  constructor(private analysisService: AnalysisService) {}

  analyse(): void {
    if (!this.prUrl.trim()) return;

    this.state = 'loading';
    this.result = null;
    this.errorMessage = '';
    this.loadingStep = 0;

    // Simulate progress steps while waiting for API
    this.loadingTimer = setInterval(() => {
      if (this.loadingStep < 3) this.loadingStep++;
    }, 8000);

    this.analysisService.analysePR(this.prUrl).subscribe({
      next: (result) => {
        clearInterval(this.loadingTimer);
        this.result = result;
        this.state = 'done';
      },
      error: (err: Error) => {
        clearInterval(this.loadingTimer);
        this.errorMessage = err.message;
        this.state = 'error';
      },
    });
  }

  useExample(url: string): void {
    this.prUrl = url;
  }

  reset(): void {
    this.state = 'idle';
    this.result = null;
    this.prUrl = '';
  }
}
