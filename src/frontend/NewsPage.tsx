import { CSSProperties, useState } from "react";
import { COLORS } from "./theme/colors";
import "./NewsPage.css";

interface NewsItem {
  id: number;
  category: string;
  title: string;
  summary: string;
  date: string;
  readTime: string;
}

const NEWS: NewsItem[] = [
  {
    id: 1,
    category: "Công nghệ",
    title: "AI tổng hợp giọng nói đạt độ tự nhiên vượt trội trong năm 2024",
    summary:
      "Các mô hình text-to-speech thế hệ mới như XTTS-v2 đạt điểm MOS gần với giọng người thật, mở ra kỷ nguyên audiobook hoàn toàn tự động.",
    date: "12 tháng 6, 2025",
    readTime: "3 phút đọc",
  },
  {
    id: 2,
    category: "NLP",
    title: "Mô hình xử lý ngôn ngữ tiếng Việt cải thiện 40% độ chính xác",
    summary:
      "Nhóm nghiên cứu tại HCMUS công bố bộ dataset tiếng Việt lớn nhất từ trước đến nay giúp các mô hình NLP hiểu ngữ cảnh địa phương tốt hơn.",
    date: "8 tháng 6, 2025",
    readTime: "5 phút đọc",
  },
  {
    id: 3,
    category: "Giáo dục",
    title: "Audiobook giúp học sinh tiếp cận kiến thức hiệu quả hơn 60%",
    summary:
      "Nghiên cứu mới cho thấy học sinh sử dụng audiobook song song với sách giáo khoa ghi nhớ nội dung tốt hơn đáng kể so với chỉ đọc văn bản.",
    date: "5 tháng 6, 2025",
    readTime: "4 phút đọc",
  },
  {
    id: 4,
    category: "Doanh nghiệp",
    title: "Các công ty xuất bản đang chuyển dịch mạnh sang định dạng audio",
    summary:
      "Doanh thu audiobook toàn cầu dự kiến đạt 35 tỷ USD vào năm 2030, thúc đẩy làn sóng đầu tư vào công nghệ TTS tự động.",
    date: "1 tháng 6, 2025",
    readTime: "6 phút đọc",
  },
  {
    id: 5,
    category: "Công nghệ",
    title: "Fine-tuning XTTS-v2 với dữ liệu tiếng Việt chỉ cần 5 phút âm thanh",
    summary:
      "Kỹ thuật few-shot voice cloning cho phép tạo giọng đọc cá nhân hóa với lượng dữ liệu huấn luyện tối thiểu, phù hợp cho các dự án nhỏ.",
    date: "28 tháng 5, 2025",
    readTime: "4 phút đọc",
  },
  {
    id: 6,
    category: "NLP",
    title: "RAG kết hợp với TTS: tương lai của trợ lý đọc sách thông minh",
    summary:
      "Retrieval-Augmented Generation kết hợp với text-to-speech mở ra khả năng tạo tóm tắt sách âm thanh theo yêu cầu của người dùng trong thời gian thực.",
    date: "22 tháng 5, 2025",
    readTime: "7 phút đọc",
  },
];

const CATEGORIES = ["Tất cả", "Công nghệ", "NLP", "Giáo dục", "Doanh nghiệp"];

const CATEGORY_COLORS: Record<string, string> = {
  "Công nghệ": "#0F766E",
  NLP: "#7C3AED",
  "Giáo dục": "#D97706",
  "Doanh nghiệp": "#0369A1",
};

export default function NewsPage() {
  const [active, setActive] = useState("Tất cả");

  const filtered =
    active === "Tất cả" ? NEWS : NEWS.filter((n) => n.category === active);

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

  return (
    <main className="news-page" style={cssVars}>
      <header className="news-header">
        <h1 className="news-title">Tin tức mới nhất</h1>
        <p className="news-sub">
          Cập nhật các xu hướng công nghệ AI, NLP và audiobook trong nước và
          quốc tế
        </p>
        {/* Filter chips */}
        <div className="news-filters">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              className={`filter-chip ${active === cat ? "filter-chip--active" : ""}`}
              onClick={() => setActive(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
      </header>

      <div className="news-grid">
        {filtered.map((item) => (
          <article key={item.id} className="news-card">
            <div
              className="news-cat-badge"
              style={{ background: CATEGORY_COLORS[item.category] ?? COLORS.brand }}
            >
              {item.category}
            </div>
            <h2 className="news-card-title">{item.title}</h2>
            <p className="news-card-summary">{item.summary}</p>
            <div className="news-card-meta">
              <span>📅 {item.date}</span>
              <span>⏱ {item.readTime}</span>
            </div>
            <button className="news-read-btn">Nghe audio →</button>
          </article>
        ))}
      </div>
    </main>
  );
}
