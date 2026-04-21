import { NavLink, useLocation } from "react-router-dom";
import {
  MessageCircle, FolderOpen, BookMarked, Globe, Clock,
  LogOut, User, ChevronLeft, ChevronRight,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useState } from "react";

interface SidebarProps {
  collapsed?: boolean;
  onToggle?: () => void;
}

const USER_NAV_ITEMS = [
  { path: "/chat", label: "聊天", icon: MessageCircle },
  { path: "/space", label: "个人空间", icon: FolderOpen },
  { path: "/my-skills", label: "我的技能", icon: BookMarked },
  { path: "/public-skills", label: "公共技能", icon: Globe },
  { path: "/cron", label: "定时任务", icon: Clock },
];

export function AppSidebar({ collapsed = false, onToggle }: SidebarProps) {
  const { user, logout, isAuthenticated } = useAuth();
  const location = useLocation();
  const [hovering, setHovering] = useState(false);

  const isExpanded = !collapsed || hovering;

  return (
    <aside
      className={`fixed left-0 top-0 h-screen z-50 flex flex-col transition-all duration-300 ease-in-out ${
        isExpanded ? "w-56" : "w-16"
      }`}
      style={{ backgroundColor: "#0D1117" }}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      {/* Logo 区域 */}
      <div className="flex items-center gap-2 px-3 h-14 border-b border-[#1E293B]">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center shrink-0">
          <span className="text-white font-bold text-sm">运</span>
        </div>
        <span
          className={`font-bold text-base tracking-wide whitespace-nowrap transition-opacity duration-200 ${
            isExpanded ? "opacity-100" : "opacity-0 w-0"
          }`}
          style={{ color: "#F97316" }}
        >
          运维Max
        </span>
      </div>

      {/* 导航菜单 */}
      <nav className="flex-1 py-3 overflow-y-auto">
        <ul className="space-y-1 px-2">
          {USER_NAV_ITEMS.map(({ path, label, icon: Icon }) => {
            const isActive = location.pathname === path ||
              (path === "/chat" && location.pathname.startsWith("/chat"));
            return (
              <li key={path}>
                <NavLink
                  to={path}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150 group ${
                    isActive
                      ? "bg-[#1E293B] text-orange-500"
                      : "text-gray-400 hover:bg-[#1E293B]/50 hover:text-gray-200"
                  }`}
                >
                  <Icon className={`h-5 w-5 shrink-0 ${isActive ? "text-orange-500" : "text-gray-500 group-hover:text-gray-300"}`} />
                  <span
                    className={`text-sm font-medium whitespace-nowrap transition-opacity duration-200 ${
                      isExpanded ? "opacity-100" : "opacity-0 w-0"
                    }`}
                  >
                    {label}
                  </span>
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* 用户信息区域 */}
      <div className="border-t border-[#1E293B] px-3 py-3">
        {isAuthenticated ? (
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-[#1E293B] flex items-center justify-center shrink-0">
              <User className="h-4 w-4 text-gray-400" />
            </div>
            <div
              className={`flex-1 min-w-0 transition-opacity duration-200 ${
                isExpanded ? "opacity-100" : "opacity-0 w-0"
              }`}
            >
              <p className="text-sm text-gray-200 truncate">{user?.username || user?.email}</p>
              <p className="text-xs text-gray-500">普通用户</p>
            </div>
            <button
              onClick={logout}
              title="退出登录"
              className={`p-1.5 rounded-lg hover:bg-[#1E293B] text-gray-400 hover:text-gray-200 transition-colors ${
                isExpanded ? "" : "shrink-0"
              }`}
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <NavLink
            to="/login"
            className="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-[#1E293B] text-gray-400 hover:text-gray-200"
          >
            <User className="h-5 w-5" />
            <span className={`text-sm ${isExpanded ? "" : "hidden"}`}>登录</span>
          </NavLink>
        )}
      </div>

      {/* 折叠按钮 */}
      {onToggle && (
        <button
          onClick={onToggle}
          className="absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-[#1E293B] border border-[#334155] flex items-center justify-center text-gray-400 hover:text-gray-200 hover:bg-[#334155] transition-colors"
        >
          {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronLeft className="h-3 w-3" />}
        </button>
      )}
    </aside>
  );
}

// 管理员侧边栏（包含更多功能）
export function AdminSidebar({ collapsed = false, onToggle }: SidebarProps) {
  const { user, logout, isAuthenticated } = useAuth();
  const location = useLocation();
  const [hovering, setHovering] = useState(false);

  const isExpanded = !collapsed || hovering;

  const ADMIN_NAV_ITEMS = [
    { path: "/", label: "系统状态", icon: MessageCircle },
    { path: "/sessions", label: "会话管理", icon: FolderOpen },
    { path: "/analytics", label: "数据分析", icon: BookMarked },
    { path: "/public-skills", label: "公共技能", icon: Globe },
    { path: "/logs", label: "日志查看", icon: Clock },
    { path: "/cron", label: "定时任务", icon: Clock },
    { path: "/config", label: "系统配置", icon: FolderOpen },
    { path: "/env", label: "密钥管理", icon: BookMarked },
  ];

  return (
    <aside
      className={`fixed left-0 top-0 h-screen z-50 flex flex-col transition-all duration-300 ease-in-out ${
        isExpanded ? "w-56" : "w-16"
      }`}
      style={{ backgroundColor: "#0D1117" }}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      {/* Logo 区域 */}
      <div className="flex items-center gap-2 px-3 h-14 border-b border-[#1E293B]">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center shrink-0">
          <span className="text-white font-bold text-sm">运</span>
        </div>
        <span
          className={`font-bold text-base tracking-wide whitespace-nowrap transition-opacity duration-200 ${
            isExpanded ? "opacity-100" : "opacity-0 w-0"
          }`}
          style={{ color: "#F97316" }}
        >
          运维Max
        </span>
        {isExpanded && user?.is_admin && (
          <span className="text-xs bg-orange-500/20 text-orange-400 px-1.5 py-0.5 rounded">管理员</span>
        )}
      </div>

      {/* 导航菜单 */}
      <nav className="flex-1 py-3 overflow-y-auto">
        <ul className="space-y-1 px-2">
          {ADMIN_NAV_ITEMS.map(({ path, label, icon: Icon }) => {
            const isActive = location.pathname === path;
            return (
              <li key={path}>
                <NavLink
                  to={path}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150 group ${
                    isActive
                      ? "bg-[#1E293B] text-orange-500"
                      : "text-gray-400 hover:bg-[#1E293B]/50 hover:text-gray-200"
                  }`}
                >
                  <Icon className={`h-5 w-5 shrink-0 ${isActive ? "text-orange-500" : "text-gray-500 group-hover:text-gray-300"}`} />
                  <span
                    className={`text-sm font-medium whitespace-nowrap transition-opacity duration-200 ${
                      isExpanded ? "opacity-100" : "opacity-0 w-0"
                    }`}
                  >
                    {label}
                  </span>
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* 用户信息区域 */}
      <div className="border-t border-[#1E293B] px-3 py-3">
        {isAuthenticated ? (
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-[#1E293B] flex items-center justify-center shrink-0">
              <User className="h-4 w-4 text-gray-400" />
            </div>
            <div
              className={`flex-1 min-w-0 transition-opacity duration-200 ${
                isExpanded ? "opacity-100" : "opacity-0 w-0"
              }`}
            >
              <p className="text-sm text-gray-200 truncate">{user?.username || user?.email}</p>
              <p className="text-xs text-orange-400">管理员</p>
            </div>
            <button
              onClick={logout}
              title="退出登录"
              className={`p-1.5 rounded-lg hover:bg-[#1E293B] text-gray-400 hover:text-gray-200 transition-colors ${
                isExpanded ? "" : "shrink-0"
              }`}
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <NavLink
            to="/login"
            className="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-[#1E293B] text-gray-400 hover:text-gray-200"
          >
            <User className="h-5 w-5" />
            <span className={`text-sm ${isExpanded ? "" : "hidden"}`}>登录</span>
          </NavLink>
        )}
      </div>

      {/* 折叠按钮 */}
      {onToggle && (
        <button
          onClick={onToggle}
          className="absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-[#1E293B] border border-[#334155] flex items-center justify-center text-gray-400 hover:text-gray-200 hover:bg-[#334155] transition-colors"
        >
          {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronLeft className="h-3 w-3" />}
        </button>
      )}
    </aside>
  );
}