import Editor from "@monaco-editor/react";

interface WarningItem {
  message: string;
  severity?: string;
  doc_url?: string;
}

interface Props {
  cudaCode: string;
  hipCode: string;
  warnings: WarningItem[];
}

export default function CodeComparisonView({ cudaCode, hipCode, warnings }: Props) {
  return (
    <section className="bg-slate-900 border border-slate-700 rounded-xl p-4 space-y-3">
      <h2 className="text-xl font-semibold">CUDA vs HIP Comparison</h2>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div>
          <p className="mb-2 text-slate-300">CUDA</p>
          <Editor
            language="cpp"
            theme="vs-dark"
            value={cudaCode}
            options={{ readOnly: true, minimap: { enabled: false } }}
            height="340px"
          />
        </div>
        <div>
          <p className="mb-2 text-slate-300">HIP</p>
          <Editor
            language="cpp"
            theme="vs-dark"
            value={hipCode}
            options={{ readOnly: true, minimap: { enabled: false } }}
            height="340px"
          />
        </div>
      </div>

      <div className="space-y-2">
        <h3 className="font-semibold">Inline Warning Annotations</h3>
        {warnings.map((warning, idx) => (
          <div key={`${warning.message}-${idx}`} className="bg-slate-800 border border-slate-600 rounded-lg p-3">
            <p className="text-sm">⚠️ {warning.message}</p>
            <a
              href={warning.doc_url ?? "https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/hip_porting_guide.html"}
              target="_blank"
              rel="noreferrer"
              className="text-cyan-300 text-sm underline"
            >
              Open AMD docs
            </a>
          </div>
        ))}
      </div>
    </section>
  );
}
