import { useCallback } from "react";
import { useDropzone } from "react-dropzone";

interface Props {
  onAnalyze: (file: File) => Promise<void>;
  loading: boolean;
}

export default function FileUploadZone({ onAnalyze, loading }: Props) {
  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const cuFiles = acceptedFiles.filter((file) => file.name.endsWith(".cu"));
      if (cuFiles.length === 0) return;
      await onAnalyze(cuFiles[0]);
    },
    [onAnalyze]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: true,
    accept: { "text/plain": [".cu"] }
  });

  return (
    <section className="bg-slate-900 border border-slate-700 rounded-xl p-6">
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer ${
          isDragActive ? "border-cyan-400 bg-slate-800" : "border-slate-600"
        }`}
      >
        <input {...getInputProps()} />
        <p className="text-lg font-medium">Drag & drop CUDA .cu files here</p>
        <p className="text-slate-400 text-sm mt-1">Batch upload enabled (first file used in MVP)</p>
        <p className="text-slate-400 text-sm">GitHub repo integration can be added in week-2</p>
      </div>
      {loading && <p className="mt-3 text-cyan-300">Analyzing CUDA codebase...</p>}
    </section>
  );
}
