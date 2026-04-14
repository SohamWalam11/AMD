import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useMemo, useState } from "react";
import axios from "axios";
import FileUploadZone from "./components/FileUploadZone";
import AnalysisDashboard from "./components/AnalysisDashboard";
import CodeComparisonView from "./components/CodeComparisonView";
import ReportExport from "./components/ReportExport";
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
export default function App() {
    const [loading, setLoading] = useState(false);
    const [cudaCode, setCudaCode] = useState("");
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const warningItems = useMemo(() => {
        if (!result)
            return [];
        return result.warnings.map((message, index) => ({
            message,
            severity: index === 0 ? "high" : "medium"
        }));
    }, [result]);
    const handleAnalyze = async (file) => {
        setLoading(true);
        setError(null);
        setResult(null);
        try {
            const text = await file.text();
            setCudaCode(text);
            const formData = new FormData();
            formData.append("file", file);
            const response = await axios.post(`${API_BASE}/api/analyze`, formData, {
                headers: { "Content-Type": "multipart/form-data" }
            });
            setResult(response.data);
        }
        catch (err) {
            setError("Analysis failed. Verify backend is running and try again.");
        }
        finally {
            setLoading(false);
        }
    };
    return (_jsx("main", { className: "min-h-screen bg-slate-950 text-slate-100 p-6", children: _jsxs("div", { className: "max-w-7xl mx-auto space-y-6", children: [_jsxs("header", { children: [_jsx("h1", { className: "text-3xl font-bold", children: "ROCm Porting Intelligence Platform" }), _jsx("p", { className: "text-slate-300 mt-1", children: "AI-assisted CUDA to ROCm/HIP migration predictions" })] }), _jsx(FileUploadZone, { onAnalyze: handleAnalyze, loading: loading }), error && _jsx("p", { className: "text-red-400", children: error }), result && (_jsxs(_Fragment, { children: [_jsx(AnalysisDashboard, { result: result, warnings: warningItems }), _jsx(CodeComparisonView, { cudaCode: cudaCode, hipCode: result.hip_code, warnings: warningItems }), _jsx(ReportExport, { result: result, cudaCode: cudaCode })] }))] }) }));
}
