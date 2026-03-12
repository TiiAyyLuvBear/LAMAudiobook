# 🚀 QUICK START - News Portal Backend

## Setup & Run (Windows)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Setup environment
copy .env.example .env

# 3. Seed database with sample data
python src\seed_database.py

# 4. Run server
cd src
python app.py
```

Server runs at: **http://localhost:8000**
- API Docs: http://localhost:8000/api/docs

## 📡 Available APIs

### Homepage
- `GET /api/v1/homepage` - Tất cả dữ liệu trang chủ
- `GET /api/v1/homepage/stats` - Thống kê

### News  
- `GET /api/v1/news` - Danh sách tin (pagination, filter)
- `GET /api/v1/news/featured` - Tin nổi bật
- `GET /api/v1/news/trending` - Tin trending
- `GET /api/v1/news/{id}` - Chi tiết tin
- `POST /api/v1/news` - Tạo tin mới
- `PUT /api/v1/news/{id}` - Cập nhật
- `DELETE /api/v1/news/{id}` - Xóa

### Categories
- `GET /api/v1/categories` - Danh sách danh mục
- `GET /api/v1/categories/{id}` - Chi tiết
- `GET /api/v1/categories/{id}/news` - Tin theo danh mục
- `POST /api/v1/categories` - Tạo danh mục
- `PUT /api/v1/categories/{id}` - Cập nhật
- `DELETE /api/v1/categories/{id}` - Xóa

**Chi tiết**: Xem [src/backend/API_REQUIREMENTS.md](src/backend/API_REQUIREMENTS.md)

## ❌ Excluded

Chatbot/AI APIs không có trong backend này (theo yêu cầu)
