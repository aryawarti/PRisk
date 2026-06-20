import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, NgZone } from '@angular/core';
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
export class AppComponent {
  prUrl = '';
  state: AppState = 'idle';
  result: AnalysisResult | null = null;
  errorMessage = '';

  constructor(
    private readonly analysisService: AnalysisService,
    private readonly ngZone: NgZone,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  analyse(): void {
    if (!this.prUrl.trim()) return;

    this.state = 'loading';
    this.result = null;
    this.errorMessage = '';

    this.analysisService.analysePR(this.prUrl.trim()).subscribe({
      next: (result) => {
        this.result = result;
        this.state = 'done';
        this.cdr.detectChanges();
      },
      error: (error: Error) => {
        this.ngZone.run(() => {
          this.errorMessage = error.message;
          this.state = 'error';
        });
      },
    });
  }

  reset(): void {
    this.state = 'idle';
    this.result = null;
    this.errorMessage = '';
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
}

export { AppComponent as App };
