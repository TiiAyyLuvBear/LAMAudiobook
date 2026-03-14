import { BrowserRouter, Routes, Route } from "react-router-dom";
import Navbar from "./Navbar";
import Homepage from "./Homepage";
import Introduce from "./Introduce";
import NewsPage from "./NewsPage";
import CategoryPage from "./CategoryPage";
import Chatbox from "./Chatbox";

export default function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/" element={<Homepage />} />
        <Route path="/gioi-thieu" element={<Introduce />} />
        <Route path="/tin-tuc" element={<NewsPage />} />
        <Route path="/danh-muc" element={<CategoryPage />} />
      </Routes>
      <Chatbox />
    </BrowserRouter>
  );
}
