import "./Introduce.css";
import type { CSSProperties } from "react";
import { COLORS } from "./theme/colors";

type Feature = {
  title: string;
  description: string;
};

const FEATURES: Feature[] = [
  {
    title: "Text to Speech",
    description:
      "Chuyen van ban thanh giong doc tu nhien voi XTTSv2, ho tro giong doc truyen cam va de nghe.",
  },
  {
    title: "News Pipeline",
    description:
      "Lay du lieu tu he thong tin tuc, phan loai theo chu de va tu dong tao audiobook theo luong xu ly.",
  },
  {
    title: "Scalable Backend",
    description:
      "Backend duoc tach lop ro rang, de mo rong API, bo loc noi dung va quan ly model trong production.",
  },
];

const TECH_STACK = ["Python", "FastAPI", "PyTorch", "XTTSv2", "React", "TypeScript"];

export default function Introduce() {
  const cssVars = {
    "--brand": COLORS.brand,
    "--brand-dark": COLORS.brandDark,
    "--accent": COLORS.accent,
    "--ink": COLORS.ink,
    "--muted": COLORS.muted,
    "--surface": COLORS.surface,
    "--surface-soft": COLORS.surfaceSoft,
    "--stroke": COLORS.stroke,
    "--hero-start": COLORS.heroStart,
    "--hero-end": COLORS.heroEnd,
  } as CSSProperties;

  return (
    <main className="intro-page" style={cssVars}>
      <section className="intro-hero">
        <div className="intro-badge">Audiobook Generation System</div>
        <h1>Gioi thieu du an NLP trong doanh nghiep</h1>
        <p>
          He thong bien noi dung van ban thanh audiobook co cau truc, toi uu cho truyen tai
          thong tin nhanh, ro rang va gan voi trai nghiem nghe thuc te.
        </p>
        <div className="intro-actions">
          <button type="button" className="btn-primary">
            Bat dau ngay
          </button>
          <button type="button" className="btn-ghost">
            Xem kien truc
          </button>
        </div>
      </section>

      <section className="intro-grid">
        {FEATURES.map((item) => (
          <article className="feature-card" key={item.title}>
            <h2>{item.title}</h2>
            <p>{item.description}</p>
          </article>
        ))}
      </section>

      <section className="intro-stack">
        <h3>Cong nghe su dung</h3>
        <div className="stack-list">
          {TECH_STACK.map((tech) => (
            <span key={tech}>{tech}</span>
          ))}
        </div>
      </section>
    </main>
  );
}
