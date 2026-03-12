# 📦 BACKEND STRUCTURE SUMMARY

## ✅ Đã hoàn thành

Backend được tổ chức trong folder `src/backend/` với cấu trúc hoàn chỉnh, tập trung vào các API cần thiết cho frontend (bỏ qua Chatbot/AI).

---

## 📁 Cấu trúc thư mục

```
src/
├── backend/
│   ├── __init__.py
│   ├── config.py                  # Cấu hình hệ thống
│   ├── database.py                # Database setup với SQLAlchemy
│   │
│   ├── models/                    # Database models
│   │   ├── __init__.py
│   │   ├── category.py            # Model Danh mục
│   │   └── news.py                # Model Tin tức
│   │
│   ├── schemas/                   # Pydantic schemas (validation)
│   │   ├── __init__.py
│   │   ├── category_schema.py    # Category request/response schemas
│   │   └── news_schema.py        # News request/response schemas
│   │
│   ├── services/                  # Business logic layer
│   │   ├── __init__.py
│   │   ├── category_service.py   # Category business logic
│   │   ├── news_service.py       # News business logic
│   │   └── homepage_service.py   # Homepage data aggregation
│   │
│   ├── routes/                    # API endpoints/controllers
│   │   ├── __init__.py
│   │   ├── category_routes.py    # Category APIs
│   │   ├── news_routes.py        # News APIs
│   │   └── homepage_routes.py    # Homepage APIs
│   │
│   └── API_REQUIREMENTS.md        # Chi tiết phân tích API
│
├── app.py                         # Main FastAPI application
└── seed_database.py               # Script khởi tạo dữ liệu mẫu
```

---

## 🎯 API Endpoints (18 total)

### **Homepage APIs (2)**
✅ `GET /api/v1/homepage` - Tất cả dữ liệu trang chủ  
✅ `GET /api/v1/homepage/stats` - Thống kê hệ thống

### **News APIs (9)**
✅ `GET /api/v1/news` - Danh sách tin (pagination, filter, search)  
✅ `GET /api/v1/news/featured` - Tin nổi bật  
✅ `GET /api/v1/news/trending` - Tin trending  
✅ `GET /api/v1/news/latest` - Tin mới nhất  
✅ `GET /api/v1/news/{id}` - Chi tiết tin (by ID)  
✅ `GET /api/v1/news/slug/{slug}` - Chi tiết tin (by slug)  
✅ `POST /api/v1/news` - Tạo tin mới  
✅ `PUT /api/v1/news/{id}` - Cập nhật tin  
✅ `DELETE /api/v1/news/{id}` - Xóa tin  
✅ `POST /api/v1/news/{id}/like` - Like/unlike tin

### **Categories APIs (7)**
✅ `GET /api/v1/categories` - Danh sách danh mục  
✅ `GET /api/v1/categories/{id}` - Chi tiết danh mục (by ID)  
✅ `GET /api/v1/categories/slug/{slug}` - Chi tiết (by slug)  
✅ `GET /api/v1/categories/{id}/news` - Tin theo danh mục  
✅ `POST /api/v1/categories` - Tạo danh mục  
✅ `PUT /api/v1/categories/{id}` - Cập nhật danh mục  
✅ `DELETE /api/v1/categories/{id}` - Xóa danh mục

---

## 🗄️ Database Models

### **Category Model**
```python
- id: Integer (PK)
- name: String(100) - Tên danh mục
- slug: String(100) - URL-friendly slug
- description: Text - Mô tả
- icon: String(200) - Icon (emoji hoặc URL)
- color: String(50) - Màu sắc (#hex)
- order: Integer - Thứ tự hiển thị
- is_active: Boolean - Trạng thái active
- created_at, updated_at: DateTime
- news: Relationship -> News (one-to-many)
```

### **News Model**
```python
- id: Integer (PK)
- title: String(500) - Tiêu đề
- slug: String(500) - URL-friendly slug
- summary: Text - Tóm tắt
- content: Text - Nội dung đầy đủ
- thumbnail: String(500) - Ảnh đại diện
- images: Text - JSON array ảnh phụ
- author: String(200) - Tác giả
- source: String(200) - Nguồn tin
- source_url: String(500) - Link gốc
- tags: String(500) - Tags (comma-separated)
- status: String(20) - draft/published/archived
- is_featured: Boolean - Tin nổi bật
- is_trending: Boolean - Tin hot
- is_breaking: Boolean - Tin nóng
- view_count, like_count, share_count: Integer
- category_id: Integer (FK -> Category)
- published_at: DateTime
- created_at, updated_at: DateTime
- category: Relationship -> Category (many-to-one)
```

---

## 🔧 Features

### **Pagination**
- Tất cả list endpoints hỗ trợ pagination
- Query params: `page` (default: 1), `limit` (default: 10, max: 100)
- Response bao gồm: `page`, `limit`, `total`, `total_pages`

### **Filtering**
- News: Filter theo `status`, `category_id`, `is_featured`, `is_trending`
- Categories: Filter theo `is_active`

### **Search**
- News: Tìm kiếm trong `title`, `summary`, `content`, `tags`
- Query param: `search`

### **Auto-increment**
- View count tự động tăng khi xem chi tiết tin
- Like/unlike với validation

### **Soft Delete**
- Categories: Soft delete (set `is_active=False`) hoặc hard delete
- Query param: `hard_delete=true/false`

### **Data Validation**
- Pydantic schemas cho request/response
- Automatic validation trước khi lưu database
- Clear error messages

---

## 🚀 Getting Started

### 1. **Install Dependencies**
```bash
pip install -r requirements.txt
```

### 2. **Setup Environment**
```bash
copy .env.example .env
# Edit .env if needed
```

### 3. **Initialize Database**
```bash
python src\seed_database.py
```

### 4. **Run Server**
```bash
cd src
python app.py
```

### 5. **Access API**
- Server: http://localhost:8000
- Swagger Docs: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

---

## 📝 Example API Calls

### **Get Homepage Data**
```bash
curl http://localhost:8000/api/v1/homepage
```

**Response**:
```json
{
  "success": true,
  "data": {
    "featured_news": [...],
    "trending_news": [...],
    "latest_news": [...],
    "breaking_news": [...],
    "categories": [...],
    "news_by_category": {...},
    "stats": {
      "total_news": 250,
      "total_published": 200,
      "total_categories": 5,
      "total_views": 15000
    }
  }
}
```

### **Get News List with Filters**
```bash
curl "http://localhost:8000/api/v1/news?page=1&limit=10&status=published&category_id=1"
```

### **Search News**
```bash
curl "http://localhost:8000/api/v1/news?search=công nghệ"
```

### **Create News (POST)**
```bash
curl -X POST "http://localhost:8000/api/v1/news" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Tin tức mới",
    "slug": "tin-tuc-moi",
    "content": "Nội dung tin tức...",
    "status": "published",
    "category_id": 1
  }'
```

---

## 🎨 Frontend Integration

### **React/Vue Example**
```javascript
import axios from 'axios';

const API_BASE = 'http://localhost:8000/api/v1';

// Get homepage data
const getHomepage = async () => {
  const response = await axios.get(`${API_BASE}/homepage`);
  return response.data.data;
};

// Get news list with filters
const getNews = async (page = 1, categoryId = null) => {
  const params = { page, limit: 10 };
  if (categoryId) params.category_id = categoryId;
  
  const response = await axios.get(`${API_BASE}/news`, { params });
  return response.data;
};

// Get news detail
const getNewsDetail = async (slug) => {
  const response = await axios.get(`${API_BASE}/news/slug/${slug}`);
  return response.data.data;
};

// Search news
const searchNews = async (query) => {
  const response = await axios.get(`${API_BASE}/news`, {
    params: { search: query }
  });
  return response.data.data;
};
```

---

## ❌ Excluded Features

Theo yêu cầu, các API sau **KHÔNG** được implement:
- ❌ Chatbot APIs
- ❌ AI/ML model endpoints
- ❌ User authentication (có thể thêm sau)
- ❌ Comments system (có thể thêm sau)
- ❌ File upload endpoints (có thể thêm sau)

---

## 📊 Database Sample Data

Sau khi chạy `seed_database.py`, database sẽ có:
- **5 Categories**: Công nghệ, Kinh tế, Thể thao, Giải trí, Thời sự
- **3 News articles**: Mẫu tin tức với đầy đủ thông tin
- Tất cả có timestamps và relationships đúng

---

## 🔍 API Documentation

Chi tiết đầy đủ về từng API endpoint:
- **File**: [src/backend/API_REQUIREMENTS.md](src/backend/API_REQUIREMENTS.md)
- **Swagger UI**: http://localhost:8000/api/docs (interactive)
- **ReDoc**: http://localhost:8000/api/redoc (clean docs)

---

## 🛠️ Technology Stack

- **Framework**: FastAPI 0.109+
- **Database**: SQLAlchemy ORM (SQLite default, hỗ trợ PostgreSQL/MySQL)
- **Validation**: Pydantic 2.5+
- **Server**: Uvicorn (ASGI)
- **Environment**: python-dotenv

---

## ✅ Ready for Frontend!

Backend đã sẵn sàng cho team Frontend (Lê Tuấn Anh) tích hợp:
- ✅ **Trang chủ**: GET /homepage - đầy đủ dữ liệu
- ✅ **Tin tức**: CRUD + search + filter + pagination
- ✅ **Danh mục**: CRUD + tin theo danh mục

Base URL: `http://localhost:8000/api/v1`
