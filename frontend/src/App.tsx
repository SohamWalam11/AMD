import { useMemo, useState } from "react";
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

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export default function App() {
  const [loading, setLoading] = useState(false);
  const [cudaCode, setCudaCode] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

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

    try {
      const text = await file.text();
      setCudaCode(text);

      const formData = new FormData();
      formData.append("file", file);

      const response = await axios.post<AnalysisResult>(`${API_BASE}/api/analyze`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });

      setResult(response.data);
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
