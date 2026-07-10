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

interface FileRiskView {
  path: string;
  /** 'epicenter' when the file matches a blast-radius module — the change's origin of risk. */
  risk: 'epicenter' | 'standard';
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

  // Start with nothing expanded
  expandedSection: DashboardSectionKey | null = null;

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
        badge: this.result.blast_radius.impact_level,
        tone: this.toneFromValue(this.result.blast_radius.impact_level),
      },
      {
        key: 'engineering',
        title: 'Engineering Review',
        badge: `${this.result.engineering_review.overall_severity}`,
        tone: this.toneFromValue(this.result.engineering_review.overall_severity),
      },
      {
        key: 'testing',
        title: 'Testing Strategy',
        badge: this.result.testing_strategy.test_coverage_assessment,
        tone: this.toneFromValue(this.result.testing_strategy.test_coverage_assessment),
      },
      {
        key: 'confidence',
        title: 'Merge Confidence',
        badge: `${this.result.confidence_report.score}%`,
        tone: this.result.confidence_report.recommendation_color,
      },
    ];
  }

  /**
   * File-level risk pins: cross-references each changed file against the
   * blast-radius modules. Files that match are the "epicenter" of the risk.
   */
  get fileRisks(): FileRiskView[] {
    const files = this.result?.changed_files ?? [];
    const moduleTokens = [
      ...(this.result?.blast_radius?.affected_modules ?? []),
      ...this.affectedModules,
    ]
      .map((token) => token.toLowerCase().replace(/[^a-z0-9]/g, ''))
      .filter((token) => token.length >= 3);

    return files.map((path) => {
      const flattened = path.toLowerCase().replace(/[^a-z0-9]/g, '');
      const isEpicenter = moduleTokens.some((token) => flattened.includes(token));
      return { path, risk: isEpicenter ? 'epicenter' : 'standard' };
    });
  }

  /** affected_module may be a comma-separated string from the LLM; guard against missing values. */
  get affectedModules(): string[] {
    const raw = this.result?.change_analysis?.affected_module ?? '';
    return raw
      .split(',')
      .map((module) => module.trim())
      .filter(Boolean);
  }

  get engineeringCategories(): ReviewCategoryView[] {
    return [
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
       this.buildCategory(
        'Security',
        this.result.engineering_review.security,
        'No critical issues found',
      ),
      this.buildCategory(
        'Performance',
        this.result.engineering_review.performance,
        'No material performance concerns were detected',
      )
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

  // ✅ FIXED: Simple open/close toggle — clicking same section closes it
  toggleSection(section: DashboardSectionKey): void {
    this.expandedSection = this.expandedSection === section ? null : section;
  }

  // ✅ FIXED: Only the actively clicked section is expanded
  isExpanded(section: DashboardSectionKey): boolean {
    return this.expandedSection === section;
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

  getProgressTone(score: number, max: number): string {
  const pct = (score / max) * 100;
  if (pct >= 75) return 'green';
  if (pct >= 50) return 'amber';
  return 'red';
}

getInputLevel(label: string): string {
  const levels = this.result.confidence_report.input_levels;
  switch (label) {
    case 'Blast Radius': return levels.blast_radius_level;
    case 'Engineering':  return levels.engineering_severity;
    case 'Testing':      return levels.testing_assessment;
    case 'Complexity':   return levels.complexity;
    default:             return '';
  }
}

getInputLevelTone(label: string): string {
  return this.toneFromValue(this.getInputLevel(label));
}
}
