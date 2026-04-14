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
import { AnalysisResult } from "../App";

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
    </section>
  );
}
