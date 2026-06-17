import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

export interface ChangeAnalysis {
  summary: string;
  change_type: string;
  affected_module: string;
  business_area: string;
  complexity: 'Low' | 'Medium' | 'High';
  estimated_lines_changed: number;
  business_impact: string;
  key_changes: string[];
  files_analyzed: string[];
  why_changed: string;
}

export interface DependencyHotspot {
  component: string;
  used_by: string[];
}

export interface BlastRadius {
  affected_modules: string[];
  impact_level: 'Low' | 'Medium' | 'High' | 'Critical';
  risk_level: 'Low' | 'Medium' | 'High' | 'Critical';
  reasoning: string;
  dependency_chain: string[];
  user_flows_at_risk: string[];
  estimated_downstream_services: number;
  high_risk_reason: string;
  dependency_hotspots: DependencyHotspot[];
  reference_evidence: Record<string, string[]>;
}

export interface EngineeringReview {
  security: string[];
  performance: string[];
  maintainability: string[];
  code_quality: string[];
  overall_severity: 'Low' | 'Medium' | 'High' | 'Critical';
  overall_health: 'Low' | 'Medium' | 'High';
  positive_notes: string[];
  total_issues_found: number;
}

export interface RecommendedTest {
  name: string;
  purpose: string;
}

export interface TestingStrategy {
  missing_tests: string[];
  edge_cases: string[];
  regression_risks: string[];
  recommended_test_types: string[];
  priority_tests: string[];
  test_coverage_assessment: 'Likely Adequate' | 'Needs More Tests' | 'Critical Gaps';
  total_tests_recommended: number;
  recommended_tests: RecommendedTest[];
  regression_risk_level: 'Low' | 'Medium' | 'High';
  regression_reason: string;
}

export interface ScoreBreakdown {
  blast_radius_score: number;
  blast_radius_max: number;
  engineering_score: number;
  engineering_max: number;
  testing_score: number;
  testing_max: number;
  complexity_score: number;
  complexity_max: number;
}

export interface ConfidenceReport {
  score: number;
  recommendation: 'Safe to Merge' | 'Needs Validation' | 'Do Not Merge';
  recommendation_color: 'green' | 'amber' | 'red';
  breakdown: ScoreBreakdown;
  executive_summary: string;
  top_reasons: string[];
  merge_guidance: string[];
  errors_during_analysis: string[];
}

export interface AnalysisResult {
  success: boolean;
  pr_url: string;
  pr_title: string;
  repo_name: string;
  change_analysis: ChangeAnalysis;
  blast_radius: BlastRadius;
  engineering_review: EngineeringReview;
  testing_strategy: TestingStrategy;
  confidence_report: ConfidenceReport;
  errors: string[];
}

@Injectable({
  providedIn: 'root',
})
export class AnalysisService {
  private readonly apiUrl = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  analysePR(prUrl: string): Observable<AnalysisResult> {
    return this.http
      .post<AnalysisResult>(`${this.apiUrl}/api/analyse`, { pr_url: prUrl })
      .pipe(catchError((error) => this.handleError(error)));
  }

  private handleError(error: HttpErrorResponse): Observable<never> {
    let message = 'An unexpected error occurred';

    if (error.status === 0) {
      message = 'Cannot connect to server. Start the FastAPI backend on port 8000.';
    } else if (error.status === 400) {
      message = error.error?.detail || 'Invalid PR URL format.';
    } else if (error.status === 422) {
      message =
        error.error?.detail || 'GitHub API request failed. Check your token and repository access.';
    } else if (error.status === 500) {
      message = error.error?.detail || 'Server error during analysis.';
    }

    return throwError(() => new Error(message));
  }
}
