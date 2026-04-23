import { useState, useEffect, useRef } from "react";
import {
  Plus, Pencil, Trash2, DownloadCloud, RotateCcw,
  ChevronDown, ChevronUp, Loader2, Upload, FolderOpen, File, Download,
} from "lucide-react";
import { eSkills } from "@/lib/enterpriseApi";
import type { SkillSummary, SkillDetail, SkillFileInfo } from "@/lib/enterpriseApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

// ── SkillEditor ───────────────────────────────────────────────────────────────

interface EditorProps {
  initial?: SkillDetail | null;
  onSave: (name: string, description: string, content: string) => Promise<void>;
  onCancel: () => void;
}

function SkillEditor({ initial, onSave, onCancel }: EditorProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [content, setContent] = useState(
    initial?.skill_content ??
    `---\nname: my-skill\ndescription: 描述这个技能\n---\n\n# 技能名称\n\n在此处描述技能的使用方法、适用场景和操作步骤。\n`,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!name.trim()) { setError("技能名称不能为空"); return; }
    if (!content.trim()) { setError("技能内容不能为空"); return; }
    setSaving(true);
    setError(null);
    try {
      await onSave(name.trim(), description.trim(), content.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="border-foreground/30">
      <CardHeader>
        <CardTitle className="text-sm">
          {initial ? "编辑技能" : "新建私有技能"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label>技能名称 *</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-skill" />
          </div>
          <div className="space-y-1">
            <Label>简短描述</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="一句话说明技能用途" />
          </div>
        </div>

        <div className="space-y-1">
          <Label>技能内容（SKILL.md 格式）</Label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={14}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs font-mono placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-y"
            placeholder="---&#10;name: my-skill&#10;description: ...&#10;---&#10;&#10;# 技能内容"
          />
          <p className="text-[0.65rem] text-muted-foreground">
            YAML frontmatter（---…---）中的 name/description 字段将覆盖上方表单值。
          </p>
        </div>

        {error && (
          <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>
        )}

        <div className="flex gap-2 justify-end">
          <Button variant="outline" size="sm" onClick={onCancel}>取消</Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
            保存
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function MySkillsPage() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [editingSkill, setEditingSkill] = useState<SkillDetail | null | "new">(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedDetail, setExpandedDetail] = useState<SkillDetail | null>(null);
  const [expandedFiles, setExpandedFiles] = useState<SkillFileInfo[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = () => eSkills.listMine().then(setSkills).catch(() => setError("加载失败"));

  useEffect(() => { load(); }, []);

  const handleCreate = async (name: string, description: string, skill_content: string) => {
    await eSkills.create(name, description, skill_content);
    await load();
    setEditingSkill(null);
  };

  const handleUpdate = async (name: string, description: string, skill_content: string) => {
    if (!editingSkill || editingSkill === "new") return;
    await eSkills.update(editingSkill.id, { name, description, skill_content });
    await load();
    setEditingSkill(null);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确认删除这个技能？")) return;
    setActionId(id);
    try { await eSkills.delete(id); await load(); } catch { setError("删除失败"); }
    finally { setActionId(null); }
  };

  const handlePublish = async (id: string) => {
    setActionId(id);
    try { await eSkills.publish(id); await load(); } catch { setError("发布失败"); }
    finally { setActionId(null); }
  };

  const handleUnpublish = async (id: string) => {
    setActionId(id);
    try { await eSkills.unpublish(id); await load(); } catch { setError("撤回失败"); }
    finally { setActionId(null); }
  };

  const handleUploadZip = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith(".zip")) {
      setError("请上传 .zip 格式的压缩包");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await eSkills.uploadZip(file);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const toggleExpand = async (id: string) => {
    if (expandedId === id) { setExpandedId(null); setExpandedDetail(null); setExpandedFiles([]); return; }
    setExpandedId(id);
    setLoadingDetail(true);
    try {
      setExpandedDetail(await eSkills.get(id));
      setExpandedFiles(await eSkills.listFiles(id));
    }
    catch { setError("加载详情失败"); }
    finally { setLoadingDetail(false); }
  };

  const startEdit = async (id: string) => {
    const detail = await eSkills.get(id);
    setEditingSkill(detail);
  };

  const handleDownloadZip = async (skill: SkillSummary) => {
    setActionId(skill.id);
    try { await eSkills.downloadZip(skill.id, skill.name); }
    catch { setError("下载失败"); }
    finally { setActionId(null); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-display text-lg sm:text-xl font-bold tracking-wider uppercase">
            我的私有技能
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            管理只有你自己可见的技能，可发布到公共空间供所有人使用。
          </p>
        </div>
        {editingSkill === null && (
          <div className="flex gap-2 shrink-0">
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              onChange={handleUploadZip}
              className="hidden"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="gap-1.5"
            >
              {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
              上传 Zip
            </Button>
            <Button size="sm" onClick={() => setEditingSkill("new")} className="gap-1.5">
              <Plus className="h-3.5 w-3.5" /> 新建技能
            </Button>
          </div>
        )}
      </div>

      {error && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>
      )}

      {/* Editor */}
      {editingSkill !== null && (
        <SkillEditor
          initial={editingSkill === "new" ? null : editingSkill}
          onSave={editingSkill === "new" ? handleCreate : handleUpdate}
          onCancel={() => setEditingSkill(null)}
        />
      )}

      {/* Skills list */}
      {skills.length === 0 && editingSkill === null ? (
        <Card>
          <CardContent className="py-16 text-center">
            <p className="text-sm text-muted-foreground">还没有私有技能，点击「新建技能」或「上传 Zip」开始</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {skills.map((skill) => (
            <Card key={skill.id} className="overflow-hidden">
              <div className="flex items-center gap-3 px-4 py-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm truncate">{skill.name}</span>
                    <Badge variant={skill.status === "published" ? "default" : "secondary"} className="text-[0.6rem]">
                      {skill.status === "published" ? "已发布" : "草稿"}
                    </Badge>
                  </div>
                  {skill.description && (
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{skill.description}</p>
                  )}
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  {/* Download Zip */}
                  <Button
                    variant="outline" size="sm" title="下载为 Zip"
                    onClick={() => handleDownloadZip(skill)}
                    disabled={actionId === skill.id}
                  >
                    {actionId === skill.id
                      ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      : <Download className="h-3.5 w-3.5" />}
                  </Button>

                  {/* Publish / Unpublish */}
                  {skill.status === "draft" ? (
                    <Button
                      variant="outline" size="sm" title="发布到公共空间"
                      onClick={() => handlePublish(skill.id)}
                      disabled={actionId === skill.id}
                    >
                      {actionId === skill.id
                        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        : <DownloadCloud className="h-3.5 w-3.5" />}
                    </Button>
                  ) : (
                    <Button
                      variant="outline" size="sm" title="撤回发布"
                      onClick={() => handleUnpublish(skill.id)}
                      disabled={actionId === skill.id}
                    >
                      {actionId === skill.id
                        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        : <RotateCcw className="h-3.5 w-3.5" />}
                    </Button>
                  )}

                  {skill.status === "draft" && (
                    <Button variant="outline" size="sm" title="编辑" onClick={() => startEdit(skill.id)}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                  )}

                  <Button
                    variant="outline" size="sm" title="删除"
                    className="text-muted-foreground hover:text-destructive"
                    onClick={() => handleDelete(skill.id)}
                    disabled={actionId === skill.id}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>

                  <Button variant="outline" size="sm" onClick={() => toggleExpand(skill.id)}>
                    {expandedId === skill.id
                      ? <ChevronUp className="h-3.5 w-3.5" />
                      : <ChevronDown className="h-3.5 w-3.5" />}
                  </Button>
                </div>
              </div>

              {expandedId === skill.id && (
                <div className="border-t border-border bg-muted/30 px-4 py-3">
                  {loadingDetail ? (
                    <div className="flex items-center gap-2 text-muted-foreground text-sm">
                      <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {/* File tree */}
                      {expandedFiles.length > 1 && (
                        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
                          <FolderOpen className="h-3.5 w-3.5" />
                          <span>文件列表 ({expandedFiles.filter(f => !f.is_dir).length} 个文件)</span>
                        </div>
                      )}
                      {expandedFiles.length > 1 && (
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 mb-3">
                          {expandedFiles.filter(f => !f.is_dir).map(f => (
                            <div key={f.path} className="flex items-center gap-1.5 text-xs px-2 py-1 bg-muted/50 rounded">
                              <File className="h-3 w-3 text-muted-foreground" />
                              <span className="truncate">{f.path}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {/* SKILL.md content */}
                      <div className="text-xs text-muted-foreground mb-1">SKILL.md 内容：</div>
                      <pre className="text-xs font-mono whitespace-pre-wrap break-words max-h-64 overflow-y-auto bg-muted/50 p-2 rounded">
                        {expandedDetail?.skill_content}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
