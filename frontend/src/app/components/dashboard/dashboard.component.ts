import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';

import { AnalysisResult } from '../../services/analysis.service';

type DashboardSectionKey = 'change' | 'blast' | 'engineering' | 'testing' | 'confidence';

interface DashboardSection {
  key: DashboardSectionKey;
  title: string;
  badge: string;
  tone: 'neutral' | 'green' | 'amber' | 'red';
}

interface ReviewCategoryView {
  label: string;
  tone: 'clear' | 'warning';
  findings: string[];
  summary: string;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css',
})
export class DashboardComponent {
  @Input({ required: true }) result!: AnalysisResult;

  showAllSections = true;
  expandedSection: DashboardSectionKey | null = null;

  ngOnInit() {
    console.log(this.result);
  }

  get sections(): DashboardSection[] {
    return [
      {
        key: 'change',
        title: 'Change Understanding',
        badge: this.result.change_analysis.complexity,
        tone: this.toneFromValue(this.result.change_analysis.complexity),
      },
      {
        key: 'blast',
        title: 'Blast Radius Analysis',
        badge: this.result.blast_radius.risk_level,
        tone: this.toneFromValue(this.result.blast_radius.risk_level),
      },
      {
        key: 'engineering',
        title: 'Engineering Review',
        badge: `${this.result.engineering_review.overall_health} Health`,
        tone: this.toneFromValue(this.result.engineering_review.overall_severity),
      },
      {
        key: 'testing',
        title: 'Testing Strategy',
        badge: this.result.testing_strategy.regression_risk_level,
        tone: this.toneFromValue(this.result.testing_strategy.regression_risk_level),
      },
      {
        key: 'confidence',
        title: 'Merge Confidence',
        badge: `${this.result.confidence_report.score}%`,
        tone: this.result.confidence_report.recommendation_color,
      },
    ];
  }

  get engineeringCategories(): ReviewCategoryView[] {
    return [
      this.buildCategory(
        'Security',
        this.result.engineering_review.security,
        'No critical issues found',
      ),
      this.buildCategory(
        'Performance',
        this.result.engineering_review.performance,
        'No material performance concerns were detected',
      ),
      this.buildCategory(
        'Maintainability',
        this.result.engineering_review.maintainability,
        'Maintainability remains within normal review expectations',
      ),
      this.buildCategory(
        'Code Quality',
        this.result.engineering_review.code_quality,
        'Code quality follows the current project standards',
      ),
    ];
  }

  get scoreBreakdownItems() {
    const breakdown = this.result.confidence_report.breakdown;
    return [
      {
        label: 'Blast Radius',
        score: breakdown.blast_radius_score,
        max: breakdown.blast_radius_max,
      },
      {
        label: 'Engineering',
        score: breakdown.engineering_score,
        max: breakdown.engineering_max,
      },
      {
        label: 'Testing',
        score: breakdown.testing_score,
        max: breakdown.testing_max,
      },
      {
        label: 'Complexity',
        score: breakdown.complexity_score,
        max: breakdown.complexity_max,
      },
    ];
  }

  get confidenceMarkerPosition(): number {
    return Math.max(0, Math.min(100, this.result.confidence_report.score));
  }

  toggleSection(section: DashboardSectionKey): void {
    if (this.showAllSections) {
      this.showAllSections = false;
      this.expandedSection = section;
      return;
    }

    if (this.expandedSection === section) {
      this.showAllSections = true;
      this.expandedSection = null;
      return;
    }

    this.expandedSection = section;
  }

  isExpanded(section: DashboardSectionKey): boolean {
    return this.showAllSections || this.expandedSection === section;
  }
  toneFromValue(value?: string): 'neutral' | 'green' | 'amber' | 'red' {
    if (!value) {
      return 'neutral';
    }

    const lowered = value.toLowerCase();

    if (lowered.includes('safe') || lowered.includes('high health') || lowered === 'low') {
      return 'green';
    }

    if (lowered.includes('do not merge') || lowered.includes('critical') || lowered === 'high') {
      return 'red';
    }

    if (lowered.includes('needs') || lowered.includes('medium')) {
      return 'amber';
    }

    return 'neutral';
  }

  private buildCategory(
    label: string,
    findings: string[],
    clearSummary: string,
  ): ReviewCategoryView {
    if (!findings.length) {
      return {
        label,
        tone: 'clear',
        findings,
        summary: clearSummary,
      };
    }

    return {
      label,
      tone: 'warning',
      findings,
      summary: findings[0],
    };
  }
}
