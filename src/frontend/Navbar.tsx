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
      <span className="navbar-logo">📚 Sách Nói AI</span>
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
    </nav>
  );
}
