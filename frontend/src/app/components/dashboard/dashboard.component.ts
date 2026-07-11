import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';

import {
  AnalysisResult,
  DependencyEdge,
  Finding,
  HistoryFileStat,
  ScoreDriver,
} from '../../services/analysis.service';

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

const SEVERITY_RANK: Record<string, number> = { Critical: 0, High: 1, Medium: 2, Low: 3 };

interface ActionItem {
  text: string;
  /** Estimated points recoverable (honest: derived from the dimension's current deficit). */
  impact: number;
  tag: string;
  kind: 'test' | 'fix';
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
    // Defensive: never let a missing field in an old/partial payload
    // crash the render — degrade to zeros and dashes instead.
    const breakdown = this.result?.confidence_report?.breakdown;
    const complexity = this.result?.change_analysis?.complexity ?? '—';
    const impact = this.result?.blast_radius?.impact_level ?? '—';
    const severity = this.result?.engineering_review?.overall_severity ?? '—';
    const coverage = this.result?.testing_strategy?.test_coverage_assessment ?? '—';
    return [
      {
        key: 'change',
        title: 'Change Understanding',
        badge: `${complexity} complexity`,
        tone: this.toneFromValue(complexity),
        score: breakdown?.complexity_score ?? 0,
        max: breakdown?.complexity_max ?? 10,
      },
      {
        key: 'blast',
        title: 'Blast Radius Analysis',
        badge: `${impact} impact`,
        tone: this.toneFromValue(impact),
        score: breakdown?.blast_radius_score ?? 0,
        max: breakdown?.blast_radius_max ?? 40,
      },
      {
        key: 'engineering',
        title: 'Engineering Review',
        badge: `${severity} severity`,
        tone: this.toneFromValue(severity),
        score: breakdown?.engineering_score ?? 0,
        max: breakdown?.engineering_max ?? 30,
      },
      {
        key: 'testing',
        title: 'Testing Strategy',
        badge: coverage,
        tone: this.toneFromValue(coverage),
        score: breakdown?.testing_score ?? 0,
        max: breakdown?.testing_max ?? 20,
      },
      {
        key: 'confidence',
        title: 'Merge Confidence',
        badge: this.result?.confidence_report?.recommendation ?? '—',
        tone: this.result?.confidence_report?.recommendation_color ?? 'amber',
        score: this.result?.confidence_report?.score ?? 0,
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

  /** The three signals that moved the score most — shown before anything else. */
  get topDrivers(): ScoreDriver[] {
    const drivers = this.result?.confidence_report?.score_drivers;
    if (!drivers) return [];
    return [
      ...(drivers.blast_radius ?? []),
      ...(drivers.engineering ?? []),
      ...(drivers.testing ?? []),
      ...(drivers.complexity ?? []),
    ]
      .slice()
      .sort((a, b) => Math.abs(b.points) - Math.abs(a.points))
      .slice(0, 3);
  }

  /**
   * "Do these first" — ranked, concrete actions with estimated score impact.
   * Impact estimates split the related dimension's current point deficit
   * across its actions, so they are grounded in the real breakdown.
   */
  get actionPlan(): ActionItem[] {
    const breakdown = this.result?.confidence_report?.breakdown;
    if (!breakdown) return [];
    const actions: ActionItem[] = [];

    const testDeficit = Math.max(0, (breakdown.testing_max ?? 20) - (breakdown.testing_score ?? 0));
    // Old payloads had priority_tests as plain strings — accept both shapes.
    const rawTests = (this.result?.testing_strategy?.priority_tests ?? []).slice(0, 3);
    const tests = rawTests
      .map((t) => (typeof t === 'string' ? { text: t, effort: 'Medium' } : t))
      .filter((t) => !!t?.text);
    const testShare = tests.length && testDeficit ? Math.max(1, Math.round(testDeficit / tests.length)) : 0;
    for (const test of tests) {
      actions.push({ text: test.text, impact: testShare, tag: test.effort, kind: 'test' });
    }

    const engDeficit = Math.max(0, (breakdown.engineering_max ?? 30) - (breakdown.engineering_score ?? 0));
    const er = this.result?.engineering_review ?? ({} as AnalysisResult['engineering_review']);
    const findings = [
      ...(er.security ?? []),
      ...(er.code_quality ?? []),
      ...(er.maintainability ?? []),
      ...(er.performance ?? []),
    ]
      .filter((f) => !!f && typeof f === 'object' && !!f.text)
      .filter((f) => f.severity === 'Critical' || f.severity === 'High' || f.effort === 'Quick fix')
      .sort((a, b) => (SEVERITY_RANK[a.severity] ?? 4) - (SEVERITY_RANK[b.severity] ?? 4))
      .slice(0, 3);
    const fixShare = findings.length && engDeficit ? Math.max(1, Math.round(engDeficit / findings.length)) : 0;
    for (const finding of findings) {
      actions.push({ text: finding.text, impact: fixShare, tag: finding.severity, kind: 'fix' });
    }

    return actions.sort((a, b) => b.impact - a.impact).slice(0, 5);
  }

  /** Measured import edges, grouped by the changed file they point at. */
  get measuredDependents(): { changedFile: string; edges: DependencyEdge[] }[] {
    const evidence = this.result?.dependency_evidence;
    if (!evidence?.available || !evidence.edges.length) return [];
    const groups = new Map<string, DependencyEdge[]>();
    for (const edge of evidence.edges) {
      const list = groups.get(edge.to_file) ?? [];
      list.push(edge);
      groups.set(edge.to_file, list);
    }
    return [...groups.entries()].map(([changedFile, edges]) => ({ changedFile, edges }));
  }

  get graphScanned(): boolean {
    return !!this.result?.dependency_evidence?.available;
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
    const breakdown = this.result?.confidence_report?.breakdown;
    if (!breakdown) return [];
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
  const levels = this.result?.confidence_report?.input_levels;
  if (!levels) return '';
  switch (label) {
    case 'Blast Radius': return levels.blast_radius_level ?? '';
    case 'Engineering':  return levels.engineering_severity ?? '';
    case 'Testing':      return levels.testing_assessment ?? '';
    case 'Complexity':   return levels.complexity ?? '';
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
