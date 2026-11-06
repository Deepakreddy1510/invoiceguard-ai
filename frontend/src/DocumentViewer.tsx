import { useEffect, useRef, useState } from "react";
import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { apiFetch } from "./client";
import { Dialog } from "./Experience";
GlobalWorkerOptions.workerSrc = workerUrl;

type Props = {
  documentId?: string;
  file?: File | null;
  sourcePath?: string;
  expanded?: boolean;
};
/** Fetch through the existing authenticated client; never send a private URL to a third party. */
export default function DocumentViewer({
  documentId,
  file,
  sourcePath,
  expanded = false,
}: Props) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [rendering, setRendering] = useState(false);
  const [expand, setExpand] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null);
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(400);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(160, entry.contentRect.width - 24)),
    );
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let object = "";
    let task: ReturnType<typeof getDocument> | undefined;
    setPdf(null);
    setPage(1);
    setZoom(1);
    setError("");
    setUrl("");
    async function load() {
      try {
        const response = file
          ? null
          : await apiFetch(
              sourcePath ?? `/api/v1/documents/${documentId}/content`,
              { signal: controller.signal },
            );
        if (response && !response.ok)
          throw new Error(
            response.status === 403 || response.status === 401
              ? "You do not have access to this document."
              : "The original PDF could not be loaded.",
          );
        const blob = file ?? (await response!.blob());
        const bytes = await blob.arrayBuffer();
        if (controller.signal.aborted) return;
        object = URL.createObjectURL(blob);
        setUrl(object);
        task = getDocument({ data: bytes });
        const document = await task.promise;
        if (!controller.signal.aborted) setPdf(document);
      } catch (reason) {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Unable to read this PDF.",
          );
      }
    }
    if (file || documentId || sourcePath) void load();
    return () => {
      controller.abort();
      if (object) URL.revokeObjectURL(object);
      void task?.destroy();
    };
  }, [documentId, file, sourcePath, retry]);
  useEffect(() => {
    if (!pdf || !canvas.current) return;
    let cancelled = false;
    let render:
      | ReturnType<Awaited<ReturnType<PDFDocumentProxy["getPage"]>>["render"]>
      | undefined;
    setRendering(true);
    void pdf
      .getPage(page)
      .then(async (source) => {
        if (cancelled || !canvas.current) return;
        const natural = source.getViewport({ scale: 1 });
        const scale = (width / natural.width) * zoom;
        const viewport = source.getViewport({ scale });
        const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.current.width = viewport.width * pixelRatio;
        canvas.current.height = viewport.height * pixelRatio;
        canvas.current.style.width = `${viewport.width}px`;
        canvas.current.style.height = `${viewport.height}px`;
        render = source.render({
          canvas: canvas.current,
          viewport,
          transform:
            pixelRatio === 1 ? undefined : [pixelRatio, 0, 0, pixelRatio, 0, 0],
        });
        await render.promise;
        if (!cancelled) setRendering(false);
      })
      .catch((reason: Error) => {
        if (!cancelled) {
          setError(reason.message);
          setRendering(false);
        }
      });
    return () => {
      cancelled = true;
      render?.cancel();
    };
  }, [pdf, page, width, zoom]);
  if (!file && !documentId && !sourcePath) return null;
  return (
    <section
      className="pdf-preview document-viewer"
      aria-label="Original invoice PDF"
    >
      <div className="document-toolbar">
        <div>
          <button
            aria-label="Previous PDF page"
            disabled={!pdf || page <= 1}
            onClick={() => setPage(page - 1)}
          >
            ‹
          </button>
          <span aria-live="polite">
            {pdf ? `Page ${page} of ${pdf.numPages}` : "Original PDF"}
          </span>
          <button
            aria-label="Next PDF page"
            disabled={!pdf || page >= pdf.numPages}
            onClick={() => setPage(page + 1)}
          >
            ›
          </button>
        </div>
        <label>
          <span className="sr-only">PDF zoom</span>
          <select
            aria-label="PDF zoom"
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
          >
            <option value="1">Fit width</option>
            <option value="0.8">80%</option>
            <option value="1.25">125%</option>
            <option value="1.5">150%</option>
            <option value="2">200%</option>
          </select>
        </label>
        {!expanded && (
          <button onClick={() => setExpand(true)}>Expand PDF</button>
        )}
      </div>
      {error && (
        <div role="alert" className="notice">
          <p>{error}</p>
          <button onClick={() => setRetry(retry + 1)}>Retry PDF</button>
        </div>
      )}
      {!pdf && !error && <p role="status">Loading original PDF…</p>}
      <div
        ref={container}
        className="document-canvas"
        aria-busy={rendering}
        role="region"
        aria-label="Scrollable PDF page"
        tabIndex={0}
      >
        <canvas
          ref={canvas}
          role="img"
          aria-label={`Original invoice PDF, page ${page}${pdf ? ` of ${pdf.numPages}` : ""}`}
        />
      </div>
      {url && (
        <a
          className="document-open"
          href={url}
          target="_blank"
          rel="noreferrer"
        >
          Open source PDF in browser ↗
        </a>
      )}
      {expand && (
        <Dialog
          title="Original invoice PDF"
          wide
          onClose={() => setExpand(false)}
        >
          <DocumentViewer
            documentId={documentId}
            file={file}
            sourcePath={sourcePath}
            expanded
          />
        </Dialog>
      )}
    </section>
  );
}
