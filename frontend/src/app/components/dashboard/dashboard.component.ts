import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';

import { AnalysisResult, Finding, HistoryFileStat, ScoreDriver } from '../../services/analysis.service';

type DashboardSectionKey = 'change' | 'blast' | 'engineering' | 'testing' | 'confidence';

interface DashboardSection {
  key: DashboardSectionKey;
  title: string;
  badge: string;
  tone: 'neutral' | 'green' | 'amber' | 'red';
  /** Points this dimension contributed to the confidence score. */
  score: number;
  max: number;
}

interface CategorizedFinding extends Finding {
  category: string;
}

interface SeverityGroup {
  severity: 'Critical' | 'High' | 'Medium' | 'Low';
  findings: CategorizedFinding[];
}

interface FileRiskView {
  path: string;
  /**
   * 'hotspot'   — file has a history of fixes/reverts (empirical evidence)
   * 'epicenter' — file matches a blast-radius module (predicted risk)
   * 'standard'  — no elevated signal
   */
  risk: 'hotspot' | 'epicenter' | 'standard';
}

const SEVERITY_ORDER: SeverityGroup['severity'][] = ['Critical', 'High', 'Medium', 'Low'];

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
    const breakdown = this.result.confidence_report.breakdown;
    return [
      {
        key: 'change',
        title: 'Change Understanding',
        badge: `${this.result.change_analysis.complexity} complexity`,
        tone: this.toneFromValue(this.result.change_analysis.complexity),
        score: breakdown.complexity_score,
        max: breakdown.complexity_max,
      },
      {
        key: 'blast',
        title: 'Blast Radius Analysis',
        badge: `${this.result.blast_radius.impact_level} impact`,
        tone: this.toneFromValue(this.result.blast_radius.impact_level),
        score: breakdown.blast_radius_score,
        max: breakdown.blast_radius_max,
      },
      {
        key: 'engineering',
        title: 'Engineering Review',
        badge: `${this.result.engineering_review.overall_severity} severity`,
        tone: this.toneFromValue(this.result.engineering_review.overall_severity),
        score: breakdown.engineering_score,
        max: breakdown.engineering_max,
      },
      {
        key: 'testing',
        title: 'Testing Strategy',
        badge: this.result.testing_strategy.test_coverage_assessment,
        tone: this.toneFromValue(this.result.testing_strategy.test_coverage_assessment),
        score: breakdown.testing_score,
        max: breakdown.testing_max,
      },
      {
        key: 'confidence',
        title: 'Merge Confidence',
        badge: this.result.confidence_report.recommendation,
        tone: this.result.confidence_report.recommendation_color,
        score: this.result.confidence_report.score,
        max: 100,
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

    const hotspots = new Set(this.result?.history_risk?.hotspots ?? []);

    return files.map((path) => {
      if (hotspots.has(path)) {
        return { path, risk: 'hotspot' as const };
      }
      const flattened = path.toLowerCase().replace(/[^a-z0-9]/g, '');
      const isEpicenter = moduleTokens.some((token) => flattened.includes(token));
      return { path, risk: isEpicenter ? ('epicenter' as const) : ('standard' as const) };
    });
  }

  /** Dependency chains parsed into node lists for the visual chain renderer. */
  get dependencyChains(): string[][] {
    return (this.result?.blast_radius?.dependency_chain ?? [])
      .map((chain) =>
        chain
          .split('->')
          .map((node) => node.trim())
          .filter(Boolean),
      )
      .filter((nodes) => nodes.length > 0);
  }

  /** Per-file git evidence rows, worst first (already sorted by the backend). */
  get historyFiles(): HistoryFileStat[] {
    return this.result?.history_risk?.files ?? [];
  }

  get historyAvailable(): boolean {
    return !!this.result?.history_risk?.available && this.historyFiles.length > 0;
  }

  isHotspot(path: string): boolean {
    return (this.result?.history_risk?.hotspots ?? []).includes(path);
  }

  /** affected_module may be a comma-separated string from the LLM; guard against missing values. */
  get affectedModules(): string[] {
    const raw = this.result?.change_analysis?.affected_module ?? '';
    return raw
      .split(',')
      .map((module) => module.trim())
      .filter(Boolean);
  }

  /** All findings flattened with a category tag, grouped by severity (worst first). */
  get severityGroups(): SeverityGroup[] {
    const er = this.result.engineering_review;
    const all: CategorizedFinding[] = [
      ...(er.security ?? []).map((f) => ({ ...f, category: 'Security' })),
      ...(er.code_quality ?? []).map((f) => ({ ...f, category: 'Code Quality' })),
      ...(er.maintainability ?? []).map((f) => ({ ...f, category: 'Maintainability' })),
      ...(er.performance ?? []).map((f) => ({ ...f, category: 'Performance' })),
    ];

    return SEVERITY_ORDER.map((severity) => ({
      severity,
      findings: all.filter((f) => f.severity === severity),
    })).filter((group) => group.findings.length > 0);
  }

  /** Category names with zero findings — rendered as "clear" chips. */
  get clearCategories(): string[] {
    const er = this.result.engineering_review;
    const categories: [string, Finding[]][] = [
      ['Security', er.security ?? []],
      ['Code Quality', er.code_quality ?? []],
      ['Maintainability', er.maintainability ?? []],
      ['Performance', er.performance ?? []],
    ];
    return categories.filter(([, findings]) => !findings.length).map(([label]) => label);
  }

  severityTone(severity: string): 'red' | 'amber' | 'neutral' {
    if (severity === 'Critical' || severity === 'High') return 'red';
    if (severity === 'Medium') return 'amber';
    return 'neutral';
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

/** Score drivers for a breakdown dimension — the exact provenance of its points. */
driversFor(label: string): ScoreDriver[] {
  const drivers = this.result.confidence_report.score_drivers;
  if (!drivers) return [];
  switch (label) {
    case 'Blast Radius': return drivers.blast_radius ?? [];
    case 'Engineering':  return drivers.engineering ?? [];
    case 'Testing':      return drivers.testing ?? [];
    case 'Complexity':   return drivers.complexity ?? [];
    default:             return [];
  }
}
}
