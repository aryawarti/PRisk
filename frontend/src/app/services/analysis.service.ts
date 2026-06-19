// src/app/services/analysis.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

export interface AnalysisResult {
  success: boolean;
  pr_url: string;
  pr_title: string;
  pr_description: string;
  author: string;
  name: string;
  repo_name: string;
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
    security: string[];
    performance: string[];
    maintainability: string[];
    code_quality: string[];
    overall_severity: string;
    total_issues_found: number;
    positive_notes: string[];
  };
  testing_strategy: {
    missing_tests: string[];
    edge_cases: string[];
    regression_risks: string[];
    recommended_test_types: string[];
    priority_tests: string[];
    test_coverage_assessment: string;
    total_tests_recommended: number;
  };
  confidence_report: {
    score: number;
    recommendation: string;
    recommendation_color: 'green' | 'amber' | 'red';
    executive_summary: string;
    errors_during_analysis: string[]; // ✅ add
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

@Injectable({ providedIn: 'root' })
export class AnalysisService {
  // ← Make sure this matches your FastAPI port (8000)
  private readonly apiUrl = 'http://localhost:8000/api/analyse';

  constructor(private http: HttpClient) {}

  analysePR(prUrl: string): Observable<AnalysisResult> {
    return this.http.post<AnalysisResult>(this.apiUrl, { pr_url: prUrl }).pipe(
      catchError((err: HttpErrorResponse) => {
        let message = 'Unknown error occurred';
        if (err.status === 0) {
          message = 'Cannot reach the backend. Is FastAPI running on port 8000?';
        } else if (err.error?.detail) {
          message = err.error.detail;
        } else if (err.message) {
          message = err.message;
        }
        return throwError(() => new Error(message));
      }),
    );
  }
}
