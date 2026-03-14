import { CSSProperties, useState } from "react";
import { COLORS } from "./theme/colors";
import "./CategoryPage.css";

interface Category {
  id: number;
  icon: string;
  name: string;
  count: number;
  desc: string;
  color: string;
}

const CATEGORIES: Category[] = [
  { id: 1, icon: "💻", name: "Công nghệ", count: 124, desc: "AI, lập trình, phần mềm, phần cứng", color: "#0F766E" },
  { id: 2, icon: "🏢", name: "Kinh doanh", count: 89, desc: "Khởi nghiệp, quản trị, marketing, tài chính", color: "#0369A1" },
  { id: 3, icon: "🎓", name: "Giáo dục", count: 76, desc: "Kỹ năng, học thuật, phát triển bản thân", color: "#7C3AED" },
  { id: 4, icon: "📖", name: "Văn học", count: 203, desc: "Tiểu thuyết, truyện ngắn, thơ ca", color: "#B45309" },
  { id: 5, icon: "🔬", name: "Khoa học", count: 57, desc: "Vật lý, hóa học, sinh học, thiên văn", color: "#0891B2" },
  { id: 6, icon: "🌍", name: "Xã hội", count: 98, desc: "Chính trị, lịch sử, văn hóa, địa lý", color: "#059669" },
  { id: 7, icon: "💪", name: "Sức khỏe", count: 65, desc: "Y tế, thể thao, dinh dưỡng, tâm lý", color: "#DC2626" },
  { id: 8, icon: "🎨", name: "Nghệ thuật", count: 41, desc: "Âm nhạc, hội họa, thiết kế, điện ảnh", color: "#C026D3" },
];

export default function CategoryPage() {
  const [search, setSearch] = useState("");

  const filtered = CATEGORIES.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.desc.toLowerCase().includes(search.toLowerCase())
  );

  const cssVars = {
    "--brand": COLORS.brand,
    "--brand-dark": COLORS.brandDark,
    "--accent": COLORS.accent,
    "--ink": COLORS.ink,
    "--muted": COLORS.muted,
    "--surface": COLORS.surface,
    "--surface-soft": COLORS.surfaceSoft,
    "--stroke": COLORS.stroke,
  } as CSSProperties;

  const total = CATEGORIES.reduce((s, c) => s + c.count, 0);

  return (
    <main className="cat-page" style={cssVars}>
      <header className="cat-header">
        <div className="cat-header-inner">
          <h1 className="cat-title">Danh mục nội dung</h1>
          <p className="cat-sub">
            {CATEGORIES.length} danh mục &nbsp;·&nbsp; {total.toLocaleString()} bài viết
          </p>
          <div className="cat-search-wrap">
            <span className="cat-search-icon">🔍</span>
            <input
              type="text"
              placeholder="Tìm danh mục…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="cat-search"
            />
          </div>
        </div>
      </header>

      {filtered.length === 0 ? (
        <p className="cat-empty">Không tìm thấy danh mục phù hợp.</p>
      ) : (
        <div className="cat-grid">
          {filtered.map((cat) => (
            <div key={cat.id} className="cat-card">
              <div
                className="cat-card-top"
                style={{ background: `${cat.color}18` }}
              >
                <span className="cat-icon">{cat.icon}</span>
                <span
                  className="cat-count-badge"
                  style={{ background: cat.color }}
                >
                  {cat.count} bài
                </span>
              </div>
              <div className="cat-card-body">
                <h2 className="cat-name" style={{ color: cat.color }}>
                  {cat.name}
                </h2>
                <p className="cat-desc">{cat.desc}</p>
                <button
                  className="cat-btn"
                  style={
                    { "--cat-color": cat.color } as CSSProperties
                  }
                >
                  Khám phá →
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
