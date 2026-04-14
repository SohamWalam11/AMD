import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { ArcElement, BarElement, CategoryScale, Chart as ChartJS, Legend, LinearScale, Tooltip } from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";
ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement);
const AnalysisDashboard = ({ result, warnings }) => {
    const gaugeData = {
        labels: ["Compatibility", "Remaining"],
        datasets: [
            {
                data: [result.compatibility_score, 100 - result.compatibility_score],
                backgroundColor: ["#22d3ee", "#1e293b"],
                borderWidth: 0
            }
        ]
    };
    const perfValue = Number(result.performance_prediction.replace("%", ""));
    const perfData = {
        labels: ["Prediction vs NVIDIA"],
        datasets: [
            {
                label: "Performance Delta %",
                data: [perfValue],
                backgroundColor: perfValue >= 0 ? "#34d399" : "#fb7185"
            }
        ]
    };
    return (_jsxs("section", { className: "grid grid-cols-1 lg:grid-cols-2 gap-4", children: [_jsxs("div", { className: "bg-slate-900 border border-slate-700 rounded-xl p-4", children: [_jsx("h2", { className: "text-xl font-semibold mb-2", children: "Compatibility Gauge" }), _jsx("div", { className: "max-w-xs mx-auto", children: _jsx(Doughnut, { data: gaugeData }) }), _jsxs("p", { className: "text-center mt-3 text-2xl font-bold", children: [result.compatibility_score, "/100"] })] }), _jsxs("div", { className: "bg-slate-900 border border-slate-700 rounded-xl p-4", children: [_jsx("h2", { className: "text-xl font-semibold mb-2", children: "Performance Prediction" }), _jsx(Bar, { data: perfData, options: { responsive: true, scales: { y: { beginAtZero: true } } } }), _jsxs("p", { className: "mt-3 text-slate-300", children: ["Estimated porting effort: ", result.effort_hours, " hours"] })] }), _jsxs("div", { className: "bg-slate-900 border border-slate-700 rounded-xl p-4 lg:col-span-2", children: [_jsx("h2", { className: "text-xl font-semibold mb-2", children: "Risk Heatmap (MVP)" }), _jsx("div", { className: "grid grid-cols-1 md:grid-cols-3 gap-3", children: warnings.map((warning, index) => (_jsxs("div", { className: `rounded-lg p-3 ${warning.severity === "high" ? "bg-red-950 border border-red-700" : "bg-yellow-950 border border-yellow-700"}`, children: [_jsx("p", { className: "font-medium", children: warning.severity?.toUpperCase() ?? "MEDIUM" }), _jsx("p", { className: "text-sm text-slate-200 mt-1", children: warning.message })] }, `${warning.message}-${index}`))) })] })] }));
};
export default AnalysisDashboard;
