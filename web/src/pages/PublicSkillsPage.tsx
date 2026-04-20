import { useState, useEffect } from "react";
import { Globe, Search, Loader2, User, Trash2, Package } from "lucide-react";
import { eSkills } from "@/lib/enterpriseApi";
import type { PublicSkillInfo } from "@/lib/enterpriseApi";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

export default function PublicSkillsPage() {
  const { user } = useAuth();
  const isAdmin = user?.is_admin ?? false;

  const [skills, setSkills] = useState<PublicSkillInfo[]>([]);
  const [filtered, setFiltered] = useState<PublicSkillInfo[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    eSkills.listAllPublic()
      .then((data) => { setSkills(data); setFiltered(data); })
      .catch(() => setError("加载公共技能失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    const q = query.toLowerCase();
    setFiltered(
      q
        ? skills.filter(
            (s) =>
              s.name.toLowerCase().includes(q) ||
              (s.description ?? "").toLowerCase().includes(q),
          )
        : skills,
    );
  }, [query, skills]);

  const handleRemove = async (skillId: string) => {
    if (!confirm("确认下架这个用户发布的公共技能？")) return;
    setRemovingId(skillId);
    try {
      await eSkills.adminRemove(skillId);
      load();
    } catch {
      setError("下架失败");
    } finally {
      setRemovingId(null);
    }
  };

  // Group skills by source
  const builtinSkills = filtered.filter(s => s.source === "builtin");
  const userSkills = filtered.filter(s => s.source === "user_published");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-lg sm:text-xl font-bold tracking-wider uppercase flex items-center gap-2">
          <Globe className="h-5 w-5" /> 公共技能市场
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          浏览所有可用的技能，包括系统内置技能和用户发布的公共技能。
        </p>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索技能名称或描述…"
          className="pl-9"
        />
      </div>

      {error && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>
      )}

      {/* Stats */}
      {!loading && (
        <p className="text-xs text-muted-foreground">
          共 {skills.length} 个技能（内置 {builtinSkills.length} + 用户发布 {userSkills.length}）
          {query && `，找到 ${filtered.length} 个匹配结果`}
        </p>
      )}

      {/* List */}
      {loading ? (
        <div className="flex items-center justify-center py-20 gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" /> 加载中…
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <p className="text-sm text-muted-foreground">
              {query ? "没有匹配的技能" : "暂无公共技能"}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {/* Builtin Skills Section */}
          {builtinSkills.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Package className="h-3.5 w-3.5" />
                <span>系统内置技能</span>
                <Badge variant="secondary" className="text-[0.6rem]">{builtinSkills.length}</Badge>
              </div>
              {builtinSkills.map((skill) => (
                <Card key={skill.name} className="overflow-hidden">
                  <div className="flex items-center gap-3 px-4 py-3">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm">{skill.name}</p>
                      {skill.description && (
                        <p className="text-xs text-muted-foreground mt-0.5 truncate">{skill.description}</p>
                      )}
                      {skill.category && (
                        <Badge variant="outline" className="text-[0.6rem] mt-1">{skill.category}</Badge>
                      )}
                    </div>
                    <Badge variant="secondary" className="text-[0.6rem] shrink-0">内置</Badge>
                  </div>
                </Card>
              ))}
            </div>
          )}

          {/* User Published Skills Section */}
          {userSkills.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <User className="h-3.5 w-3.5" />
                <span>用户发布技能</span>
                <Badge variant="secondary" className="text-[0.6rem]">{userSkills.length}</Badge>
              </div>
              {userSkills.map((skill) => (
                <Card key={skill.id || skill.name} className="overflow-hidden">
                  <div className="flex items-center gap-3 px-4 py-3">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm">{skill.name}</p>
                      {skill.description && (
                        <p className="text-xs text-muted-foreground mt-0.5 truncate">{skill.description}</p>
                      )}
                      {skill.owner_id && (
                        <div className="flex items-center gap-1 mt-1">
                          <User className="h-2.5 w-2.5 text-muted-foreground" />
                          <span className="text-[0.6rem] text-muted-foreground">
                            {skill.owner_id.slice(0, 8)}…
                          </span>
                        </div>
                      )}
                    </div>
                    <Badge variant="default" className="text-[0.6rem] shrink-0">用户发布</Badge>

                    {/* Admin: Remove button */}
                    {isAdmin && skill.can_remove && (
                      <Button
                        variant="outline"
                        size="sm"
                        title="下架技能"
                        className="shrink-0"
                        onClick={() => handleRemove(skill.id!)}
                        disabled={removingId === skill.id}
                      >
                        {removingId === skill.id
                          ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          : <Trash2 className="h-3.5 w-3.5" />}
                      </Button>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}