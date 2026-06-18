import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, NgZone, OnDestroy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';

import { DashboardComponent } from './components/dashboard/dashboard.component';
import { AnalysisResult, AnalysisService } from './services/analysis.service';

type AppState = 'idle' | 'loading' | 'done' | 'error';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule, DashboardComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class AppComponent implements OnDestroy {
  prUrl = '';
  state: AppState = 'idle';
  result: AnalysisResult | null = null;
  errorMessage = '';
  loadingStep = 0;
  private loadingTimer: ReturnType<typeof setInterval> | null = null;

  // ← Inject NgZone
  constructor(
    private readonly analysisService: AnalysisService,
    private readonly ngZone: NgZone,
    private readonly cdr: ChangeDetectorRef
  ) {}

  ngOnDestroy(): void {
    this.clearLoadingTimer();
  }

  analyse(): void {
    if (!this.prUrl.trim()) return;

    console.log('Ashish1');

    this.state = 'loading';
    this.result = null;
    this.errorMessage = '';
    this.loadingStep = 0;
    this.startLoadingTimer();

    this.analysisService.analysePR(this.prUrl.trim()).subscribe({
      next: (result) => {
        // ← Force Angular change detection after long async response

        this.clearLoadingTimer();
        this.result = result;
        this.state = 'done';
        this.cdr.detectChanges();
        console.log('[PRisk] State set to done, result:', result);
      },
      error: (error: Error) => {
        this.ngZone.run(() => {
          this.clearLoadingTimer();
          this.errorMessage = error.message;
          this.state = 'error';
          console.error('[PRisk] Error:', error.message);
        });
      },
    });
  }

  reset(): void {
    this.clearLoadingTimer();
    this.state = 'idle';
    this.result = null;
    this.errorMessage = '';
    this.loadingStep = 0;
    this.prUrl = '';
  }

  get stateLabel(): string {
    switch (this.state) {
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

  private startLoadingTimer(): void {
    this.clearLoadingTimer();
    this.loadingTimer = setInterval(() => {
      this.ngZone.run(() => {
        if (this.loadingStep < 4) this.loadingStep += 1;
      });
    }, 3500);
  }

  private clearLoadingTimer(): void {
    if (this.loadingTimer) {
      clearInterval(this.loadingTimer);
      this.loadingTimer = null;
    }
  }
}

export { AppComponent as App };
