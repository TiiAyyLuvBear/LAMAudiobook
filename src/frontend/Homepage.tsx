import { CSSProperties } from "react";
import { COLORS } from "./theme/colors";
import "./Homepage.css";

const features = [
  {
    icon: "🎙️",
    title: "Chuyển văn bản thành giọng đọc",
    desc: "Công nghệ TTS tiên tiến tạo ra giọng đọc tự nhiên, truyền cảm từ mọi loại văn bản.",
  },
  {
    icon: "📰",
    title: "Tổng hợp tin tức tự động",
    desc: "Thu thập và phân loại tin tức từ các nguồn uy tín, cập nhật liên tục 24/7.",
  },
  {
    icon: "🗂️",
    title: "Phân loại đa danh mục",
    desc: "Hệ thống NLP phân loại nội dung thông minh theo chủ đề, giúp bạn dễ dàng tìm kiếm.",
  },
];

const stats = [
  { value: "10 000+", label: "Bài viết đã xử lý" },
  { value: "98%", label: "Độ chính xác NLP" },
  { value: "< 3s", label: "Thời gian tạo audio" },
];

export default function Homepage() {
  const cssVars = {
    "--brand": COLORS.brand,
    "--brand-dark": COLORS.brandDark,
    "--accent": COLORS.accent,
    "--accent-soft": COLORS.accentSoft,
    "--ink": COLORS.ink,
    "--muted": COLORS.muted,
    "--surface": COLORS.surface,
    "--surface-soft": COLORS.surfaceSoft,
    "--stroke": COLORS.stroke,
    "--hero-start": COLORS.heroStart,
    "--hero-end": COLORS.heroEnd,
  } as CSSProperties;

  return (
    <main className="homepage" style={cssVars}>
      {/* Hero */}
      <section className="hp-hero">
        <div className="hp-hero-inner">
          <span className="hp-badge">🤖 Ứng dụng NLP trong doanh nghiệp</span>
          <h1 className="hp-title">
            Hệ thống tạo <span className="hp-highlight">Audiobook</span>
            <br />
            thông minh từ văn bản
          </h1>
          <p className="hp-subtitle">
            Ứng dụng xử lý ngôn ngữ tự nhiên để thu thập tin tức, phân loại nội
            dung và chuyển đổi sang audio chất lượng cao — hoàn toàn tự động.
          </p>
          <div className="hp-cta">
            <a href="/tin-tuc" className="btn-primary">
              Xem tin tức mới nhất →
            </a>
            <a href="/gioi-thieu" className="btn-secondary">
              Tìm hiểu thêm
            </a>
          </div>
        </div>
        <div className="hp-hero-visual">
          <div className="hp-hero-card">
            <div className="hp-waveform">
              {Array.from({ length: 20 }).map((_, i) => (
                <div
                  key={i}
                  className="hp-bar"
                  style={{ "--i": i } as CSSProperties}
                />
              ))}
            </div>
            <p className="hp-card-label">🎧 Đang tạo audiobook…</p>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="hp-stats">
        {stats.map((s) => (
          <div key={s.label} className="hp-stat">
            <span className="hp-stat-value">{s.value}</span>
            <span className="hp-stat-label">{s.label}</span>
          </div>
        ))}
      </section>

      {/* Features */}
      <section className="hp-features">
        <h2 className="hp-section-title">Tính năng nổi bật</h2>
        <div className="hp-grid">
          {features.map((f) => (
            <div key={f.title} className="hp-card">
              <span className="hp-card-icon">{f.icon}</span>
              <h3 className="hp-card-title">{f.title}</h3>
              <p className="hp-card-desc">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
