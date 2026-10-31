import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { displayName, useAuth } from "../auth";
import type { Role } from "../types";
import HelpAssistant from "./HelpAssistant";

// Menus are a convenience only; the backend enforces every permission.
export const MENU: Record<Role, { to: string; label: string }[]> = {
  admin: [
    { to: "/admin", label: "Overview" },
    { to: "/admin/users", label: "Users" },
    { to: "/admin/handoffs", label: "Handoffs" },
    { to: "/admin/audit", label: "Audit log" },
    { to: "/library", label: "Library" },
  ],
  member: [
    { to: "/expert", label: "My handoffs" },
    { to: "/learn", label: "Learning" },
    { to: "/library", label: "Library" },
  ],
};

const ROLE_LABEL: Record<Role, string> = { admin: "Administrator", member: "Member" };

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  const signOut = async () => {
    await logout().catch(() => undefined);
    navigate("/login", { replace: true });
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>SiloBreaker</h1>
          <p className="tagline">Detect knowledge risk → Capture missing context → Verify transfer</p>
        </div>
        <div className="account">
          <span className="who">
            <strong>{displayName(user)}</strong>
            <span className="role-badge">{ROLE_LABEL[user.role]}</span>
          </span>
          <button className="ghost small" onClick={signOut}>
            Log out
          </button>
        </div>
      </header>
      <nav className="mainnav" aria-label="Main">
        {MENU[user.role].map((m) => (
          <NavLink key={m.to} to={m.to} end={m.to === "/admin"}>
            {m.label}
          </NavLink>
        ))}
      </nav>
      <main>
        <Outlet />
      </main>
      <HelpAssistant />
    </div>
  );
}
