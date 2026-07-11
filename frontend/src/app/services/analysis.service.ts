// src/app/services/analysis.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { API_BASE_URL } from '../api-config';

export interface Finding {
  text: string;
  severity: 'Critical' | 'High' | 'Medium' | 'Low';
  effort: string;
}

export interface PriorityTest {
  text: string;
  effort: string;
}

export interface ScoreDriver {
  label: string;
  points: number;
}

export interface HistoryFileStat {
  path: string;
  commits: number;
  fix_commits: number;
  last_modified_days: number;
  authors: number;
}

export interface DependencyEdge {
  from_file: string;
  line: number;
  code: string;
  to_file: string;
  symbol: string;
}

export interface AnalysisResult {
  success: boolean;
  pr_url: string;
  pr_title: string;
  pr_description: string;
  author: string;
  name: string;
  repo_name: string;
  changed_files: string[];
  history_risk: {
    available: boolean;
    window_commits: number;
    overall_level: string;
    hotspots: string[];
    files: HistoryFileStat[];
  };
  dependency_evidence: {
    available: boolean;
    files_scanned: number;
    edges: DependencyEdge[];
    dependents_by_file: Record<string, string[]>;
    direct_dependents: number;
  };
  analysis_quality: {
    mode: 'full' | 'partial' | 'degraded';
    degraded_agents: string[];
    history_evidence: boolean;
    note: string;
  };
  change_analysis: {
    summary: string;
    change_type: string;
    affected_module: string;
    complexity: string;
    estimated_lines_changed: number;
    key_changes: string[];
    business_impact: string;
  };
  blast_radius: {
    affected_modules: string[];
    impact_level: string;
    reasoning: string;
    dependency_chain: string[];
    user_flows_at_risk: string[];
    estimated_downstream_services: number;
  };
  engineering_review: {
    security: Finding[];
    performance: Finding[];
    maintainability: Finding[];
    code_quality: Finding[];
    overall_severity: string;
    total_issues_found: number;
    positive_notes: string[];
  };
  testing_strategy: {
    missing_tests: string[];
    edge_cases: string[];
    regression_risks: string[];
    recommended_test_types: string[];
    priority_tests: PriorityTest[];
    test_coverage_assessment: string;
    total_tests_recommended: number;
  };
  confidence_report: {
    score: number;
    recommendation: string;
    recommendation_color: 'green' | 'amber' | 'red';
    executive_summary: string;
    errors_during_analysis: string[];
    guardrails: string[];
    score_drivers: {
      blast_radius: ScoreDriver[];
      engineering: ScoreDriver[];
      testing: ScoreDriver[];
      complexity: ScoreDriver[];
    }; // ✅ add
    input_levels: {
      // ✅ add
      blast_radius_level: string;
      engineering_severity: string;
      testing_assessment: string;
      complexity: string;
    };
    breakdown: {
      blast_radius_score: number;
      blast_radius_max: number;
      engineering_score: number;
      engineering_max: number;
      testing_score: number;
      testing_max: number;
      complexity_score: number;
      complexity_max: number;
    };
  };
  errors: string[];
}

/** Events emitted by the streaming endpoint. */
export type AnalysisStreamEvent =
  | { type: 'status'; stage: string; label: string }
  | { type: 'result'; payload: AnalysisResult }
  | { type: 'error'; status?: number; message: string };

/** Thrown when the SSE transport itself fails before any event arrives —
 *  the caller can fall back to the plain POST endpoint. */
export class StreamTransportError extends Error {}

@Injectable({ providedIn: 'root' })
export class AnalysisService {
  private readonly apiUrl = `${API_BASE_URL}/api/analyse`;
  private readonly streamUrl = `${API_BASE_URL}/api/analyse/stream`;

  constructor(private http: HttpClient) {}

  /** Classic invoke-and-wait call. Kept as the streaming fallback. */
  analysePR(prUrl: string): Observable<AnalysisResult> {
    return this.http.post<AnalysisResult>(this.apiUrl, { pr_url: prUrl }).pipe(
      catchError((err: HttpErrorResponse) => {
        let message = 'Something went wrong while analysing this pull request.';
        if (err.status === 0) {
          message =
            'Cannot reach the analysis service. It may be waking up — please try again in ~30 seconds.';
        } else if (err.error?.detail) {
          message = err.error.detail;
        } else if (err.message) {
          message = err.message;
        }
        return throwError(() => new Error(message));
      }),
    );
  }

  /**
   * Streaming analysis over Server-Sent Events.
   * EventSource only supports GET, so we POST with fetch() and parse the
   * SSE frames off the response body ourselves.
   *
   * Resolves once the stream ends. Every parsed event is handed to
   * `onEvent` as it arrives, including the final result/error event.
   */
  async analysePRStream(
    prUrl: string,
    onEvent: (event: AnalysisStreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    let response: Response;
    try {
      response = await fetch(this.streamUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pr_url: prUrl }),
        signal,
      });
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') throw err;
      throw new StreamTransportError('Streaming endpoint unreachable');
    }

    if (!response.ok || !response.body) {
      throw new StreamTransportError(`Streaming endpoint returned ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    const dispatchFrames = (chunk: string) => {
      buffer += chunk;
      // SSE frames are separated by a blank line.
      const frames = buffer.split('\n\n');
      buffer = frames.pop() ?? '';
      for (const frame of frames) {
        for (const line of frame.split('\n')) {
          if (!line.startsWith('data:')) continue; // ignore comments/heartbeats
          const raw = line.slice(5).trim();
          if (!raw) continue;
          try {
            onEvent(JSON.parse(raw) as AnalysisStreamEvent);
          } catch {
            // Malformed frame — skip rather than break the whole stream.
          }
        }
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      dispatchFrames(decoder.decode(value, { stream: true }));
    }
    dispatchFrames(decoder.decode());
  }
}
