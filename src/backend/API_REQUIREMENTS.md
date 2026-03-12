# 📋 API REQUIREMENTS ANALYSIS

Dựa trên yêu cầu frontend từ bảng phân công, dưới đây là phân tích chi tiết các API cần thiết.

---

## 🎯 Frontend Requirements

### **1. Trang chủ (Homepage)** - Lê Tuấn Anh
Frontend cần hiển thị:
- Tin tức nổi bật (Featured News)
- Tin tức trending/hot
- Tin tức mới nhất
- Danh sách danh mục
- Tin tức theo từng danh mục

### **2. Tin tức (News Page)** - Lê Tuấn Anh
Frontend cần:
- Xem danh sách tin tức (có phân trang)
- Xem chi tiết một tin tức
- Tìm kiếm tin tức
- Lọc theo danh mục
- Lọc theo trạng thái (published)
- Tăng lượt xem khi đọc tin

### **3. Danh mục (Categories Page)** - Lê Tuấn Anh
Frontend cần:
- Xem danh sách tất cả danh mục
- Xem chi tiết danh mục
- Xem tin tức thuộc danh mục

---

## 🛣️ API ENDPOINTS SPECIFICATION

### **Base URL**: `/api/v1`

---

## 📰 **1. NEWS APIs**

### **GET /news**
Lấy danh sách tin tức (có phân trang, filter)

**Query Parameters:**
- `page` (int, default: 1) - Số trang
- `limit` (int, default: 10, max: 100) - Số item mỗi trang
- `status` (string, optional) - Filter theo trạng thái: draft, published, archived
- `category_id` (int, optional) - Filter theo danh mục
- `is_featured` (bool, optional) - Chỉ lấy tin nổi bật
- `is_trending` (bool, optional) - Chỉ lấy tin trending
- `search` (string, optional) - Tìm kiếm theo tiêu đề, nội dung

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "title": "Tiêu đề tin tức",
      "slug": "tieu-de-tin-tuc",
      "summary": "Tóm tắt ngắn",
      "thumbnail": "https://...",
      "author": "Tác giả",
      "source": "Nguồn",
      "tags": ["tag1", "tag2"],
      "status": "published",
      "is_featured": true,
      "is_trending": false,
      "view_count": 1234,
      "like_count": 56,
      "category": {
        "id": 1,
        "name": "Công nghệ",
        "slug": "cong-nghe"
      },
      "published_at": "2026-02-20T10:00:00",
      "created_at": "2026-02-20T09:00:00"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 10,
    "total": 100,
    "total_pages": 10
  }
}
```

---

### **GET /news/{id}** hoặc **GET /news/slug/{slug}**
Lấy chi tiết một tin tức (tự động tăng view_count)

**Response:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "title": "Tiêu đề tin tức",
    "slug": "tieu-de-tin-tuc",
    "summary": "Tóm tắt",
    "content": "Nội dung đầy đủ...",
    "thumbnail": "https://...",
    "images": ["url1", "url2"],
    "author": "Tác giả",
    "source": "Nguồn",
    "source_url": "https://...",
    "tags": ["tag1", "tag2"],
    "status": "published",
    "is_featured": true,
    "view_count": 1235,
    "category": {...},
    "published_at": "2026-02-20T10:00:00",
    "created_at": "2026-02-20T09:00:00",
    "updated_at": "2026-02-20T11:00:00"
  }
}
```

---

### **GET /news/featured**
Lấy tin tức nổi bật (cho homepage)

**Query Parameters:**
- `limit` (int, default: 5) - Số lượng tin

**Response:** Tương tự GET /news nhưng chỉ trả về tin is_featured=true

---

### **GET /news/trending**
Lấy tin tức trending (cho homepage)

**Query Parameters:**
- `limit` (int, default: 5) - Số lượng tin

**Response:** Tương tự GET /news nhưng chỉ trả về tin is_trending=true

---

### **GET /news/latest**
Lấy tin tức mới nhất

**Query Parameters:**
- `limit` (int, default: 10) - Số lượng tin

**Response:** Tương tự GET /news, sắp xếp theo published_at DESC

---

### **POST /news**
Tạo tin tức mới (Admin/CMS)

**Request Body:**
```json
{
  "title": "Tiêu đề tin",
  "slug": "tieu-de-tin",
  "summary": "Tóm tắt",
  "content": "Nội dung đầy đủ",
  "thumbnail": "https://...",
  "author": "Tác giả",
  "source": "Nguồn",
  "tags": "tag1,tag2,tag3",
  "category_id": 1,
  "status": "published",
  "is_featured": false,
  "is_trending": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Tạo tin tức thành công",
  "data": {...}
}
```

---

### **PUT /news/{id}**
Cập nhật tin tức (Admin/CMS)

**Request Body:** Tương tự POST (các field optional)

---

### **DELETE /news/{id}**
Xóa tin tức (Admin/CMS)

**Response:**
```json
{
  "success": true,
  "message": "Xóa tin tức thành công"
}
```

---

### **POST /news/{id}/like**
Like/Unlike tin tức

**Request Body:**
```json
{
  "action": "like" // hoặc "unlike"
}
```

---

## 📑 **2. CATEGORIES APIs**

### **GET /categories**
Lấy danh sách tất cả danh mục

**Query Parameters:**
- `is_active` (bool, optional) - Filter theo trạng thái active

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "Công nghệ",
      "slug": "cong-nghe",
      "description": "Tin tức công nghệ",
      "icon": "💻",
      "color": "#3B82F6",
      "order": 1,
      "is_active": true,
      "news_count": 45,
      "created_at": "2026-01-01T00:00:00"
    }
  ]
}
```

---

### **GET /categories/{id}** hoặc **GET /categories/slug/{slug}**
Lấy chi tiết danh mục

**Response:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "Công nghệ",
    "slug": "cong-nghe",
    "description": "Tin tức công nghệ, AI, khoa học...",
    "icon": "💻",
    "color": "#3B82F6",
    "order": 1,
    "is_active": true,
    "news_count": 45,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-02-01T00:00:00"
  }
}
```

---

### **GET /categories/{id}/news**
Lấy tin tức thuộc danh mục

**Query Parameters:**
- `page`, `limit` - Phân trang
- `status` - Filter theo trạng thái

**Response:** Tương tự GET /news

---

### **POST /categories**
Tạo danh mục mới (Admin)

**Request Body:**
```json
{
  "name": "Công nghệ",
  "slug": "cong-nghe",
  "description": "Tin tức công nghệ",
  "icon": "💻",
  "color": "#3B82F6",
  "order": 1,
  "is_active": true
}
```

---

### **PUT /categories/{id}**
Cập nhật danh mục (Admin)

---

### **DELETE /categories/{id}**
Xóa danh mục (Admin)

---

## 🏠 **3. HOMEPAGE APIs**

### **GET /homepage**
Lấy toàn bộ dữ liệu cho trang chủ (tổng hợp)

**Response:**
```json
{
  "success": true,
  "data": {
    "featured_news": [...],  // Top 5 tin nổi bật
    "trending_news": [...],  // Top 5 tin trending
    "latest_news": [...],    // Top 10 tin mới nhất
    "breaking_news": [...],  // Tin breaking (nếu có)
    "categories": [...],     // Tất cả danh mục
    "news_by_category": {    // Tin theo từng danh mục
      "cong-nghe": {
        "category": {...},
        "news": [...]  // Top 3-5 tin
      },
      "kinh-te": {
        "category": {...},
        "news": [...]
      }
    },
    "stats": {
      "total_news": 250,
      "total_categories": 8,
      "total_views": 15000
    }
  }
}
```

---

### **GET /homepage/stats**
Lấy thống kê hệ thống

**Response:**
```json
{
  "success": true,
  "data": {
    "total_news": 250,
    "total_categories": 8,
    "total_views": 15000,
    "total_published": 200
  }
}
```

---

## 🔍 **4. SEARCH API**

### **GET /search**
Tìm kiếm toàn bộ hệ thống

**Query Parameters:**
- `q` (string, required) - Từ khóa tìm kiếm
- `type` (string, optional) - Loại: news, categories, all
- `page`, `limit` - Phân trang

**Response:**
```json
{
  "success": true,
  "data": {
    "news": [...],
    "categories": [...],
    "query": "công nghệ AI",
    "total_results": 25
  }
}
```

---

## 📊 Summary

### APIs cần implement:

**News APIs (9 endpoints):**
1. ✅ GET /news - Danh sách tin tức
2. ✅ GET /news/{id} - Chi tiết tin
3. ✅ GET /news/slug/{slug} - Chi tiết tin (by slug)
4. ✅ GET /news/featured - Tin nổi bật
5. ✅ GET /news/trending - Tin trending
6. ✅ GET /news/latest - Tin mới nhất
7. ✅ POST /news - Tạo tin
8. ✅ PUT /news/{id} - Cập nhật tin
9. ✅ DELETE /news/{id} - Xóa tin

**Categories APIs (6 endpoints):**
1. ✅ GET /categories - Danh sách danh mục
2. ✅ GET /categories/{id} - Chi tiết danh mục
3. ✅ GET /categories/slug/{slug} - Chi tiết (by slug)
4. ✅ GET /categories/{id}/news - Tin theo danh mục
5. ✅ POST /categories - Tạo danh mục
6. ✅ PUT /categories/{id} - Cập nhật danh mục

**Homepage APIs (2 endpoints):**
1. ✅ GET /homepage - Dữ liệu trang chủ
2. ✅ GET /homepage/stats - Thống kê

**Search API (1 endpoint):**
1. ✅ GET /search - Tìm kiếm

**Tổng: 18 API endpoints**

---

## 🚫 Excluded (Chatbot/AI)

Các API sau KHÔNG implement (do liên quan chatbot/AI):
- ❌ POST /chatbot/chat
- ❌ GET /chatbot/history
- ❌ Any ML/AI model endpoints

---

## 📝 Notes

1. **Authentication**: Tạm thời không implement (có thể thêm sau)
2. **File Upload**: POST /upload (có thể thêm sau cho upload ảnh)
3. **Comments**: Có thể là feature tương lai
4. **Admin Panel**: Các endpoint POST/PUT/DELETE tạm thời public (thêm auth sau)
