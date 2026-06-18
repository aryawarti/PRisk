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
    why_changed: string;
    change_type: string;
    business_area: string;
    complexity: string;
    files_analyzed: string[];
  };
  blast_radius: {
    risk_level: string;
    estimated_downstream_services: number;
    affected_modules: string[];
    dependency_hotspots: { component: string; used_by: string[] }[];
    dependency_chain: string[];
    high_risk_reason: string;
  };
  engineering_review: {
    security: string[];
    performance: string[];
    maintainability: string[];
    code_quality: string[];
    overall_health: string;
    overall_severity: string;
    total_issues_found: number;
  };
  testing_strategy: {
    recommended_tests: { name: string; purpose: string }[];
    regression_risk_level: string;
    test_coverage_assessment: string;
    regression_reason: string;
    recommended_test_types: string[];
  };
  confidence_report: {
    score: number;
    recommendation: string;
    recommendation_color: 'green' | 'amber' | 'red';
    executive_summary: string;
    top_reasons: string[];
    merge_guidance: string[];
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
