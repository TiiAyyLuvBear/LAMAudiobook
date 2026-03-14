import { NavLink } from "react-router-dom";
import { COLORS } from "./theme/colors";
import "./Navbar.css";

const LINKS = [
  { to: "/", label: "Trang chủ" },
  { to: "/gioi-thieu", label: "Giới thiệu" },
  { to: "/tin-tuc", label: "Tin tức" },
  { to: "/danh-muc", label: "Danh mục" },
];

export default function Navbar() {
  const style = {
    "--brand": COLORS.brand,
    "--brand-dark": COLORS.brandDark,
    "--accent": COLORS.accent,
    "--surface": COLORS.surface,
    "--stroke": COLORS.stroke,
    "--ink": COLORS.ink,
    "--muted": COLORS.muted,
  } as React.CSSProperties;

  return (
    <nav className="navbar" style={style}>
      <span className="navbar-logo">
        <span className="logo-dot" aria-hidden="true" />
        <span className="logo-main">Sách Nói</span>
        <span className="logo-ai">AI</span>
      </span>
      <div className="navbar-center">
        <div className="navbar-search-wrap">
          <span className="navbar-search-icon">🔎</span>
          <input
            type="text"
            className="navbar-search-input"
            placeholder="Tìm nội dung sách nói, tin tức..."
          />
        </div>
        <ul className="navbar-links">
          {LINKS.map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                end={link.to === "/"}
                className={({ isActive }) =>
                  isActive ? "nav-item active" : "nav-item"
                }
              >
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
