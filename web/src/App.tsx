import { useMemo, useState } from "react";
import { Routes, Route, NavLink, Navigate, useLocation } from "react-router-dom";
import {
  Activity, BarChart3, Clock, FileText, KeyRound,
  MessageSquare, Package, Settings, Puzzle,
  Sparkles, Terminal, Globe, Database, Shield,
  Wrench, Zap, Heart, Star, Code, Eye,
  MessageCircle, FolderOpen, BookMarked, LogIn, LogOut, User,
} from "lucide-react";
import StatusPage from "@/pages/StatusPage";
import ConfigPage from "@/pages/ConfigPage";
import EnvPage from "@/pages/EnvPage";
import SessionsPage from "@/pages/SessionsPage";
import LogsPage from "@/pages/LogsPage";
import AnalyticsPage from "@/pages/AnalyticsPage";
import CronPage from "@/pages/CronPage";
import SkillsPage from "@/pages/SkillsPage";
import LoginPage from "@/pages/LoginPage";
import ChatPage from "@/pages/ChatPage";
import SpacePage from "@/pages/SpacePage";
import MySkillsPage from "@/pages/MySkillsPage";
import PublicSkillsPage from "@/pages/PublicSkillsPage";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { AppSidebar, AdminSidebar } from "@/components/AppSidebar";
import { useI18n } from "@/i18n";
import { usePlugins } from "@/plugins";
import type { RegisteredPlugin } from "@/plugins";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";

// ---------------------------------------------------------------------------
// Nav items
// ---------------------------------------------------------------------------

interface NavItem {
  path: string;
  label: string;
  labelKey?: string;
  icon: React.ComponentType<{ className?: string }>;
  requireAuth?: boolean;   // enterprise pages — hide when not logged in
  authOnly?: boolean;      // only show when authenticated (hides login link)
  adminOnly?: boolean;     // only show to admin users
  userOnly?: boolean;      // only show to non-admin users
}

const BUILTIN_NAV: NavItem[] = [
  // ── User Features (shown to non-admin users) ──
  { path: "/chat", label: "Chat", labelKey: "chat", icon: MessageCircle, requireAuth: true, userOnly: true },
  { path: "/space", label: "Files", labelKey: "space", icon: FolderOpen, requireAuth: true, userOnly: true },
  { path: "/my-skills", label: "My Skills", labelKey: "mySkills", icon: BookMarked, requireAuth: true, userOnly: true },
  // ── Shared (both admin and user) ──
  { path: "/public-skills", label: "Public Skills", labelKey: "publicSkills", icon: Globe },
  // ── Admin / System ──
  { path: "/", labelKey: "status", label: "Status", icon: Activity, adminOnly: true },
  { path: "/sessions", labelKey: "sessions", label: "Sessions", icon: MessageSquare, adminOnly: true },
  { path: "/analytics", labelKey: "analytics", label: "Analytics", icon: BarChart3, adminOnly: true },
  { path: "/logs", labelKey: "logs", label: "Logs", icon: FileText, adminOnly: true },
  { path: "/cron", labelKey: "cron", label: "Cron", icon: Clock, requireAuth: true },
  { path: "/skills", labelKey: "skills", label: "Skills", icon: Package, adminOnly: true },
  { path: "/config", labelKey: "config", label: "Config", icon: Settings, adminOnly: true },
  { path: "/env", labelKey: "keys", label: "Keys", icon: KeyRound, adminOnly: true },
];

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  Activity, BarChart3, Clock, FileText, KeyRound,
  MessageSquare, Package, Settings, Puzzle,
  Sparkles, Terminal, Globe, Database, Shield,
  Wrench, Zap, Heart, Star, Code, Eye,
};

function resolveIcon(name: string): React.ComponentType<{ className?: string }> {
  return ICON_MAP[name] ?? Puzzle;
}

function buildNavItems(builtIn: NavItem[], plugins: RegisteredPlugin[]): NavItem[] {
  const items = [...builtIn];
  for (const { manifest } of plugins) {
    const pluginItem: NavItem = {
      path: manifest.tab.path,
      label: manifest.label,
      icon: resolveIcon(manifest.icon),
    };
    const pos = manifest.tab.position ?? "end";
    if (pos === "end") {
      items.push(pluginItem);
    } else if (pos.startsWith("after:")) {
      const target = "/" + pos.slice(6);
      const idx = items.findIndex((i) => i.path === target);
      items.splice(idx >= 0 ? idx + 1 : items.length, 0, pluginItem);
    } else if (pos.startsWith("before:")) {
      const target = "/" + pos.slice(7);
      const idx = items.findIndex((i) => i.path === target);
      items.splice(idx >= 0 ? idx : items.length, 0, pluginItem);
    } else {
      items.push(pluginItem);
    }
  }
  return items;
}

// ---------------------------------------------------------------------------
// Auth-aware route guard
// ---------------------------------------------------------------------------

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();
  if (isLoading) return null;
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />;
  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// Admin header (顶部导航栏 - 管理员专用)
// ---------------------------------------------------------------------------

function AdminHeader() {
  const { t } = useI18n();
  const { plugins } = usePlugins();
  const { isAuthenticated, user, logout } = useAuth();

  const navItems = useMemo(
    () => buildNavItems(BUILTIN_NAV, plugins),
    [plugins],
  );

  const isAdmin = user?.is_admin ?? false;

  const visibleNav = navItems.filter((item) => {
    if (item.requireAuth && !isAuthenticated) return false;
    if (item.adminOnly && !isAdmin) return false;
    if (item.userOnly && isAdmin) return false;
    return true;
  });

  return (
    <header className="fixed top-0 left-0 right-0 z-40 border-b border-border bg-background/90 backdrop-blur-sm">
      <div className="mx-auto flex h-12 max-w-[1400px] items-stretch">
        <div className="flex items-center border-r border-border px-3 sm:px-5 shrink-0">
          <span className="font-collapse text-lg sm:text-xl font-bold tracking-wider uppercase blend-lighter">
            H<span className="hidden sm:inline">ermes </span>A<span className="hidden sm:inline">gent</span>
          </span>
        </div>

        <nav className="flex items-stretch overflow-x-auto scrollbar-none">
          {visibleNav.map(({ path, label, labelKey, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              className={({ isActive }) =>
                `group relative inline-flex items-center gap-1 sm:gap-1.5 border-r border-border px-2.5 sm:px-4 py-2 font-display text-[0.65rem] sm:text-[0.8rem] tracking-[0.12em] uppercase whitespace-nowrap transition-colors cursor-pointer shrink-0 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                  isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className="h-4 w-4 sm:h-3.5 sm:w-3.5 shrink-0" />
                  <span className="hidden sm:inline">
                    {labelKey ? (t.app.nav as Record<string, string>)[labelKey] ?? label : label}
                  </span>
                  <span className="absolute inset-0 bg-foreground pointer-events-none transition-opacity duration-150 group-hover:opacity-5 opacity-0" />
                  {isActive && (
                    <span className="absolute bottom-0 left-0 right-0 h-px bg-foreground" />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1 px-2 sm:px-4">
          <ThemeSwitcher />
          <LanguageSwitcher />
          {isAuthenticated ? (
            <div className="flex items-center gap-1.5 border-l border-border pl-2 ml-1">
              <span className="hidden sm:inline text-[0.65rem] text-muted-foreground flex items-center gap-1">
                <User className="h-3 w-3" />
                {user?.username || user?.email}
              </span>
              <button
                onClick={logout}
                title="退出登录"
                className="flex items-center gap-1 text-[0.65rem] text-muted-foreground hover:text-foreground transition-colors px-1.5 py-1 rounded"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">退出</span>
              </button>
            </div>
          ) : (
            <NavLink
              to="/login"
              className="flex items-center gap-1 text-[0.65rem] text-muted-foreground hover:text-foreground transition-colors border-l border-border pl-2 ml-1 px-1.5 py-1"
            >
              <LogIn className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">登录</span>
            </NavLink>
          )}
        </div>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// App shell (inside AuthProvider)
// ---------------------------------------------------------------------------

function AppShell() {
  const { plugins } = usePlugins();
  const { isAuthenticated, user } = useAuth();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const isAdmin = user?.is_admin ?? false;

  // 普通用户使用侧边栏布局
  if (!isAdmin && isAuthenticated) {
    return (
      <div className="min-h-screen sidebar-theme bg-[#0D1117]">
        <AppSidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        />
        <main
          className={`transition-all duration-300 ${
            sidebarCollapsed ? "ml-16" : "ml-56"
          } min-h-screen p-6 bg-[#0D1117]`}
        >
          <Routes>
            <Route path="/chat" element={<RequireAuth><ChatPage /></RequireAuth>} />
            <Route path="/space" element={<RequireAuth><SpacePage /></RequireAuth>} />
            <Route path="/my-skills" element={<RequireAuth><MySkillsPage /></RequireAuth>} />
            <Route path="/public-skills" element={<PublicSkillsPage />} />
            <Route path="/cron" element={<CronPage />} />
            {plugins.map(({ manifest, component: PluginComponent }) => (
              <Route key={manifest.name} path={manifest.tab.path} element={<PluginComponent />} />
            ))}
            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Routes>
        </main>
      </div>
    );
  }

  // 管理员使用侧边栏布局
  if (isAdmin && isAuthenticated) {
    return (
      <div className="min-h-screen sidebar-theme bg-[#0D1117]">
        <AdminSidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        />
        <main
          className={`transition-all duration-300 ${
            sidebarCollapsed ? "ml-16" : "ml-56"
          } min-h-screen p-6 bg-[#0D1117]`}
        >
          <Routes>
            <Route path="/" element={<StatusPage />} />
            <Route path="/sessions" element={<SessionsPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="/cron" element={<CronPage />} />
            <Route path="/skills" element={<SkillsPage />} />
            <Route path="/config" element={<ConfigPage />} />
            <Route path="/env" element={<EnvPage />} />
            <Route path="/public-skills" element={<PublicSkillsPage />} />
            {plugins.map(({ manifest, component: PluginComponent }) => (
              <Route key={manifest.name} path={manifest.tab.path} element={<PluginComponent />} />
            ))}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    );
  }

  // 未登录用户使用原有布局（显示登录页）
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground overflow-x-hidden">
      <div className="noise-overlay" />
      <div className="warm-glow" />
      <AdminHeader />
      <main className="relative z-2 mx-auto w-full max-w-[1400px] flex-1 px-3 sm:px-6 pt-16 sm:pt-20 pb-4 sm:pb-8">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/public-skills" element={<PublicSkillsPage />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root export — wraps everything in AuthProvider
// ---------------------------------------------------------------------------

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}