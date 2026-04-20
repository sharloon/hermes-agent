import { useState, useEffect, useRef } from "react";
import { Upload, File, Trash2, FileText, Image, FileCode, Loader2 } from "lucide-react";
import { eFiles } from "@/lib/enterpriseApi";
import type { FileInfo } from "@/lib/enterpriseApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

// ── helpers ───────────────────────────────────────────────────────────────────

function fmtSize(bytes: number | null) {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(ts: number) {
  return new Date(ts * 1000).toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function FileIcon({ contentType }: { contentType: string | null }) {
  const ct = contentType ?? "";
  if (ct.startsWith("image/")) return <Image className="h-5 w-5 text-blue-400" />;
  if (ct === "application/pdf") return <FileText className="h-5 w-5 text-red-400" />;
  if (ct === "application/json" || ct.startsWith("text/")) return <FileCode className="h-5 w-5 text-green-400" />;
  return <File className="h-5 w-5 text-muted-foreground" />;
}

const ACCEPT = ".pdf,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.gif,.webp,.docx,.xlsx";

export default function SpacePage() {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    eFiles.list().then(setFiles).catch(() => setError("加载文件列表失败"));
  }, []);

  const uploadFiles = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;
    setError(null);
    setUploading(true);
    const results: FileInfo[] = [];
    for (const f of Array.from(fileList)) {
      try {
        const info = await eFiles.upload(f);
        results.push(info);
      } catch (err) {
        setError(`上传 ${f.name} 失败：${err instanceof Error ? err.message : String(err)}`);
      }
    }
    setFiles((prev) => [...results, ...prev]);
    setUploading(false);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确认删除这个文件？")) return;
    setDeletingId(id);
    try {
      await eFiles.delete(id);
      setFiles((prev) => prev.filter((f) => f.id !== id));
    } catch {
      setError("删除失败");
    } finally {
      setDeletingId(null);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    uploadFiles(e.dataTransfer.files);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-lg sm:text-xl font-bold tracking-wider uppercase">
          私有文件空间
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          上传文档、PDF、图片等文件，在对话中随时引用。
        </p>
      </div>

      {/* 上传区 */}
      <div
        className={`border-2 border-dashed rounded-xl p-10 text-center transition-colors cursor-pointer ${
          dragging ? "border-foreground bg-foreground/5" : "border-border hover:border-foreground/40"
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => uploadFiles(e.target.files)}
        />
        {uploading ? (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <Loader2 className="h-8 w-8 animate-spin" />
            <p className="text-sm">上传中…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <Upload className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium">拖拽文件到此处，或点击选择</p>
            <p className="text-xs text-muted-foreground">
              支持 PDF、TXT、Markdown、CSV、JSON、图片（PNG/JPG）、Word、Excel，最大 50 MB
            </p>
          </div>
        )}
      </div>

      {error && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>
      )}

      {/* 文件列表 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <File className="h-4 w-4" />
            我的文件
            <span className="ml-auto text-muted-foreground font-normal">{files.length} 个</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {files.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-12">
              还没有上传任何文件
            </p>
          ) : (
            <div className="divide-y divide-border">
              {files.map((f) => (
                <div key={f.id} className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors">
                  <FileIcon contentType={f.content_type} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{f.filename}</p>
                    <p className="text-xs text-muted-foreground">
                      {f.content_type ?? "未知类型"} · {fmtSize(f.size_bytes)} · {fmtDate(f.uploaded_at)}
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0 text-muted-foreground hover:text-destructive"
                    onClick={() => handleDelete(f.id)}
                    disabled={deletingId === f.id}
                  >
                    {deletingId === f.id
                      ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      : <Trash2 className="h-3.5 w-3.5" />}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
