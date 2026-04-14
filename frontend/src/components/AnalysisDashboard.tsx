import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip
} from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";
import { AnalysisResult, ExplainabilityFactor, KernelRisk } from "../App";

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement);

interface WarningItem {
  message: string;
  severity?: string;
}

interface Props {
  result: AnalysisResult;
  warnings: WarningItem[];
}

export default function AnalysisDashboard({ result, warnings }: Props) {
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

  return (
    <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl p-4">
        <h2 className="text-xl font-semibold mb-2">Compatibility Gauge</h2>
        <div className="max-w-xs mx-auto">
          <Doughnut data={gaugeData} />
        </div>
        <p className="text-center mt-3 text-2xl font-bold">{result.compatibility_score}/100</p>
      </div>

      <div className="bg-slate-900 border border-slate-700 rounded-xl p-4">
        <h2 className="text-xl font-semibold mb-2">Performance Prediction</h2>
        <Bar data={perfData} options={{ responsive: true, scales: { y: { beginAtZero: true } } }} />
        <p className="mt-3 text-slate-300">Estimated porting effort: {result.effort_hours} hours</p>
      </div>

      <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 lg:col-span-2">
        <h2 className="text-xl font-semibold mb-2">Risk Heatmap (MVP)</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {warnings.map((warning, index) => (
            <div
              key={`${warning.message}-${index}`}
              className={`rounded-lg p-3 ${warning.severity === "high" ? "bg-red-950 border border-red-700" : "bg-yellow-950 border border-yellow-700"}`}
            >
              <p className="font-medium">{warning.severity?.toUpperCase() ?? "MEDIUM"}</p>
              <p className="text-sm text-slate-200 mt-1">{warning.message}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 lg:col-span-2">
        <h2 className="text-xl font-semibold mb-3">Explainability Factors</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {(result.explainability ?? []).map((factor: ExplainabilityFactor, index) => (
            <div key={`${factor.name}-${index}`} className="rounded-lg border border-slate-700 bg-slate-800 p-3">
              <div className="flex items-center justify-between">
                <p className="font-medium">{factor.name}</p>
                <span
                  className={`text-xs px-2 py-1 rounded ${
                    factor.impact === "positive"
                      ? "bg-emerald-900 text-emerald-300"
                      : factor.impact === "negative"
                        ? "bg-rose-900 text-rose-300"
                        : "bg-slate-700 text-slate-200"
                  }`}
                >
                  {factor.impact}
                </span>
              </div>
              <p className="text-sm text-slate-300 mt-1">Value: {factor.value}</p>
              <p className="text-sm text-slate-400 mt-1">{factor.reason}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 lg:col-span-2">
        <h2 className="text-xl font-semibold mb-3">Kernel-Level Risk</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-300 border-b border-slate-700">
                <th className="py-2">Kernel</th>
                <th className="py-2">Complexity</th>
                <th className="py-2">Risk Score</th>
                <th className="py-2">Severity</th>
                <th className="py-2">Issue Count</th>
              </tr>
            </thead>
            <tbody>
              {(result.kernel_risks ?? []).map((kernel: KernelRisk, index) => (
                <tr key={`${kernel.name}-${index}`} className="border-b border-slate-800 text-slate-200">
                  <td className="py-2">{kernel.name}</td>
                  <td className="py-2">{kernel.complexity_score}</td>
                  <td className="py-2">{kernel.risk_score}</td>
                  <td className="py-2 uppercase">{kernel.severity}</td>
                  <td className="py-2">{kernel.issues.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
