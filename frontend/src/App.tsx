import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { AnalysisDashboard, CodeComparisonView, FileUploadZone, ReportExport } from "./components";

export interface WarningItem {
  code?: string;
  message: string;
  severity?: string;
  doc_url?: string;
}

export interface ExplainabilityFactor {
  name: string;
  value: number;
  impact: "positive" | "neutral" | "negative";
  reason: string;
}

export interface KernelRisk {
  name: string;
  complexity_score: number;
  risk_score: number;
  severity: "low" | "medium" | "high";
  issues: WarningItem[];
}

export interface AnalysisResult {
  compatibility_score: number;
  performance_prediction: string;
  effort_hours: number;
  warnings: string[];
  warning_details?: WarningItem[];
  recommendations: string[];
  explainability?: ExplainabilityFactor[];
  kernel_risks?: KernelRisk[];
  hip_code: string;
  analysis: {
    complexity: number;
    kernels: Array<{
      name: string;
      complexity_score: number;
      incompatible_patterns: WarningItem[];
    }>;
  };
  migration_guide: string;
}

interface AsyncJobEnqueue {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  stage: string;
}

interface AsyncJobStatus extends AsyncJobEnqueue {
  result?: AnalysisResult;
  error?: string;
}

interface HistoryItem {
  job_id?: string;
  code_hash: string;
  compatibility_score: number;
  performance_prediction: string;
  effort_hours: number;
  warnings_count: number;
  completed_at: string;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export default function App() {
  const [loading, setLoading] = useState(false);
  const [cudaCode, setCudaCode] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<AsyncJobStatus | null>(null);
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);

  const loadHistory = async () => {
    try {
      const response = await axios.get<{ items: HistoryItem[] }>(`${API_BASE}/api/history?limit=5`);
      setHistoryItems(response.data.items ?? []);
    } catch {
      setHistoryItems([]);
    }
  };

  useEffect(() => {
    void loadHistory();
  }, []);

  const warningItems = useMemo(() => {
    if (!result) return [];
    if (result.warning_details && result.warning_details.length > 0) {
      return result.warning_details;
    }
    return result.warnings.map((message, index) => ({
      message,
      severity: index === 0 ? "high" : "medium"
    }));
  }, [result]);

  const handleAnalyze = async (file: File) => {
    setLoading(true);
    setError(null);
    setResult(null);
    setJobStatus(null);

    try {
      const text = await file.text();
      setCudaCode(text);

      const formData = new FormData();
      formData.append("file", file);

      const enqueue = await axios.post<AsyncJobEnqueue>(`${API_BASE}/api/analyze/async`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      setJobStatus(enqueue.data);

      const maxAttempts = 180;
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        const statusResponse = await axios.get<AsyncJobStatus>(`${API_BASE}/api/jobs/${enqueue.data.job_id}`);
        setJobStatus(statusResponse.data);

        if (statusResponse.data.status === "completed") {
          if (statusResponse.data.result) {
            setResult(statusResponse.data.result);
          }
          await loadHistory();
          break;
        }

        if (statusResponse.data.status === "failed") {
          setError(statusResponse.data.error ?? "Analysis job failed");
          break;
        }
      }

    } catch (err) {
      setError("Analysis failed. Verify backend is running and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <header>
          <h1 className="text-3xl font-bold">ROCm Porting Intelligence Platform</h1>
          <p className="text-slate-300 mt-1">AI-assisted CUDA to ROCm/HIP migration predictions</p>
        </header>

        <FileUploadZone onAnalyze={handleAnalyze} loading={loading} />

        {jobStatus && (
          <section className="bg-slate-900 border border-slate-700 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <p className="font-medium">Job Status: {jobStatus.status.toUpperCase()}</p>
              <p className="text-slate-300 text-sm">{jobStatus.stage}</p>
            </div>
            <div className="mt-3 h-2 bg-slate-800 rounded">
              <div className="h-2 bg-cyan-500 rounded" style={{ width: `${jobStatus.progress}%` }} />
            </div>
            <p className="text-xs text-slate-400 mt-2">Progress: {jobStatus.progress}%</p>
          </section>
        )}

        {historyItems.length > 0 && (
          <section className="bg-slate-900 border border-slate-700 rounded-xl p-4">
            <h2 className="text-lg font-semibold mb-2">Recent Analyses</h2>
            <div className="space-y-2">
              {historyItems.map((item) => (
                <div key={`${item.code_hash}-${item.completed_at}`} className="bg-slate-800 rounded p-3 text-sm">
                  <p>Score: {item.compatibility_score}/100 | Perf: {item.performance_prediction} | Effort: {item.effort_hours}h</p>
                  <p className="text-slate-400">Warnings: {item.warnings_count} | Completed: {new Date(item.completed_at).toLocaleString()}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {error && <p className="text-red-400">{error}</p>}

        {result && (
          <>
            <AnalysisDashboard result={result} warnings={warningItems} />
            <CodeComparisonView cudaCode={cudaCode} hipCode={result.hip_code} warnings={warningItems} />
            <ReportExport result={result} cudaCode={cudaCode} />
          </>
        )}
      </div>
    </main>
  );
}
