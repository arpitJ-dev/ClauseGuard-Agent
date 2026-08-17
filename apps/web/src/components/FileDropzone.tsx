import { FileText, Upload, X } from "lucide-react";
import { useRef, useState } from "react";

import { formatBytes } from "../lib/format";

const allowedExtensions = new Set(["txt", "docx", "pdf"]);
const maxFileBytes = 25 * 1024 * 1024;

interface FileDropzoneProps {
  id: string;
  label: string;
  file: File | null;
  disabled?: boolean;
  onChange: (file: File | null) => void;
}

function validateFile(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!allowedExtensions.has(extension)) return "Choose a TXT, DOCX, or PDF file.";
  if (file.size === 0) return "The selected file is empty.";
  if (file.size > maxFileBytes) return "The selected file exceeds 25 MB.";
  return null;
}

export function FileDropzone({
  id,
  label,
  file,
  disabled = false,
  onChange,
}: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectFile = (candidate: File | undefined) => {
    if (!candidate) return;
    const validationError = validateFile(candidate);
    setError(validationError);
    if (!validationError) onChange(candidate);
  };

  const clear = () => {
    setError(null);
    onChange(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="file-field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <input
        ref={inputRef}
        id={id}
        className="visually-hidden"
        type="file"
        accept=".txt,.docx,.pdf"
        disabled={disabled}
        onChange={(event) => selectFile(event.target.files?.[0])}
      />
      {file ? (
        <div className="selected-file">
          <span className="file-icon" aria-hidden="true">
            <FileText size={18} />
          </span>
          <span className="file-meta">
            <strong title={file.name}>{file.name}</strong>
            <small>{formatBytes(file.size)}</small>
          </span>
          <button
            className="icon-button"
            type="button"
            aria-label={`Remove ${file.name}`}
            title="Remove file"
            disabled={disabled}
            onClick={clear}
          >
            <X size={17} />
          </button>
        </div>
      ) : (
        <button
          type="button"
          className={`dropzone${dragging ? " is-dragging" : ""}`}
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          onDragEnter={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            selectFile(event.dataTransfer.files[0]);
          }}
        >
          <Upload size={20} aria-hidden="true" />
          <span>Choose or drop a document</span>
          <small>TXT, DOCX, or PDF up to 25 MB</small>
        </button>
      )}
      {error ? <p className="field-error">{error}</p> : null}
    </div>
  );
}
