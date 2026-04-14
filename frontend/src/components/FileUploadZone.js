import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
const FileUploadZone = ({ onAnalyze, loading }) => {
    const onDrop = useCallback(async (acceptedFiles) => {
        const cuFiles = acceptedFiles.filter((file) => file.name.endsWith(".cu"));
        if (cuFiles.length === 0)
            return;
        await onAnalyze(cuFiles[0]);
    }, [onAnalyze]);
    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        multiple: true,
        accept: { "text/plain": [".cu"] }
    });
    return (_jsxs("section", { className: "bg-slate-900 border border-slate-700 rounded-xl p-6", children: [_jsxs("div", { ...getRootProps(), className: `border-2 border-dashed rounded-xl p-10 text-center cursor-pointer ${isDragActive ? "border-cyan-400 bg-slate-800" : "border-slate-600"}`, children: [_jsx("input", { ...getInputProps() }), _jsx("p", { className: "text-lg font-medium", children: "Drag & drop CUDA .cu files here" }), _jsx("p", { className: "text-slate-400 text-sm mt-1", children: "Batch upload enabled (first file used in MVP)" }), _jsx("p", { className: "text-slate-400 text-sm", children: "GitHub repo integration can be added in week-2" })] }), loading && _jsx("p", { className: "mt-3 text-cyan-300", children: "Analyzing CUDA codebase..." })] }));
};
export default FileUploadZone;
