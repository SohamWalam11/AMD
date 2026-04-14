import jsPDF from "jspdf";
import { AnalysisResult } from "../App";

interface Props {
  result: AnalysisResult;
  cudaCode: string;
}

export default function ReportExport({ result }: Props) {
  const downloadHip = () => {
    const blob = new Blob([result.hip_code], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "converted_kernel.hip";
    link.click();
    URL.revokeObjectURL(url);
  };

  const exportPdf = () => {
    const doc = new jsPDF();
    doc.setFontSize(16);
    doc.text("ROCm Porting Intelligence Report", 10, 12);
    doc.setFontSize(11);
    doc.text(`Compatibility Score: ${result.compatibility_score}/100`, 10, 24);
    doc.text(`Performance Prediction: ${result.performance_prediction}`, 10, 32);
    doc.text(`Estimated Effort: ${result.effort_hours} hours`, 10, 40);
    doc.text("Challenges:", 10, 50);
    result.warnings.slice(0, 8).forEach((warning, idx) => {
      doc.text(`- ${warning}`, 12, 58 + idx * 7);
    });
    doc.save("rocm-migration-report.pdf");
  };

  return (
    <section className="bg-slate-900 border border-slate-700 rounded-xl p-4 flex flex-wrap items-center gap-3">
      <button
        onClick={downloadHip}
        className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 font-medium"
      >
        Download HIP Code
      </button>
      <button
        onClick={exportPdf}
        className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 font-medium"
      >
        Export PDF Report
      </button>
      <a
        className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 font-medium"
        href="https://www.amd.com/en/solutions/artificial-intelligence"
        target="_blank"
        rel="noreferrer"
      >
        Schedule AMD Expert
      </a>
    </section>
  );
}
