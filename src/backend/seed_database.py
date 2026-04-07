# Seed Database with Sample Data
from backend.database import SessionLocal, init_db
from backend.models.category import Category
from backend.models.news import News
from datetime import datetime, timedelta

def seed_categories():
    """Create sample categories"""
    print("📑 Seeding categories...")
    
    db = SessionLocal()
    
    categories_data = [
        {
            "name": "Công nghệ",
            "slug": "cong-nghe",
            "description": "Tin tức về công nghệ, AI, khoa học máy tính",
            "icon": "💻",
            "color": "#3B82F6",
            "order": 1
        },
        {
            "name": "Kinh tế",
            "slug": "kinh-te",
            "description": "Tin tức kinh tế, tài chính, chứng khoán",
            "icon": "💰",
            "color": "#10B981",
            "order": 2
        },
        {
            "name": "Thể thao",
            "slug": "the-thao",
            "description": "Tin tức thể thao trong nước và quốc tế",
            "icon": "⚽",
            "color": "#EF4444",
            "order": 3
        },
        {
            "name": "Giải trí",
            "slug": "giai-tri",
            "description": "Tin tức giải trí, âm nhạc, điện ảnh",
            "icon": "🎬",
            "color": "#F59E0B",
            "order": 4
        },
        {
            "name": "Thời sự",
            "slug": "thoi-su",
            "description": "Tin tức thời sự trong nước và thế giới",
            "icon": "📰",
            "color": "#6366F1",
            "order": 5
        },
    ]
    
    for cat_data in categories_data:
        existing = db.query(Category).filter(Category.slug == cat_data["slug"]).first()
        if not existing:
            category = Category(**cat_data)
            db.add(category)
    
    db.commit()
    db.close()
    print("✅ Categories seeded successfully")

def seed_news():
    """Create sample news articles"""
    print("📰 Seeding news...")
    
    db = SessionLocal()
    
    # Get categories
    tech_cat = db.query(Category).filter(Category.slug == "cong-nghe").first()
    sports_cat = db.query(Category).filter(Category.slug == "the-thao").first()
    eco_cat = db.query(Category).filter(Category.slug == "kinh-te").first()
    
    now = datetime.utcnow()
    
    news_data = [
        {
            "title": "AI và Machine Learning đang thay đổi thế giới",
            "slug": "ai-machine-learning-thay-doi-the-gioi",
            "summary": "Công nghệ AI và Machine Learning đang mang đến những đột phá trong nhiều lĩnh vực từ y tế, giáo dục đến kinh doanh.",
            "content": """Trí tuệ nhân tạo (AI) và Machine Learning đang trở thành xu hướng công nghệ hàng đầu, ảnh hưởng sâu rộng đến mọi khía cạnh của cuộc sống.
            
            Trong lĩnh vực y tế, AI giúp chẩn đoán bệnh chính xác hơn. Trong giáo dục, AI cá nhân hóa trải nghiệm học tập. Trong kinh doanh, AI tối ưu hóa quy trình và tăng hiệu quả.
            
            Các công ty công nghệ lớn như Google, Microsoft, OpenAI đang đầu tư mạnh mẽ vào nghiên cứu và phát triển AI. ChatGPT, Gemini, và các mô hình ngôn ngữ lớn khác đang làm thay đổi cách chúng ta tương tác với công nghệ.
            
            Tuy nhiên, AI cũng đặt ra nhiều thách thức về đạo đức, quyền riêng tư và tác động đến việc làm. Các chính phủ và tổ chức đang nỗ lực xây dựng khung pháp lý phù hợp.""",
            "thumbnail": "https://via.placeholder.com/800x450?text=AI+Machine+Learning",
            "author": "Nguyễn Văn A",
            "source": "Tech News VN",
            "tags": "AI,Machine Learning,Technology,Future",
            "status": "published",
            "is_featured": True,
            "is_trending": True,
            "view_count": 1250,
            "like_count": 89,
            "category_id": tech_cat.id if tech_cat else None,
            "published_at": now - timedelta(hours=2)
        },
        {
            "title": "Đội tuyển Việt Nam vào chung kết SEA Games",
            "slug": "doi-tuyen-viet-nam-vao-chung-ket-sea-games",
            "summary": "Đội tuyển bóng đá Việt Nam đã có chiến thắng ấn tượng 3-0 trước Thái Lan để giành vé vào trận chung kết.",
            "content": """Trong trận bán kết kịch tính diễn ra tối qua, đội tuyển bóng đá Việt Nam đã có màn trình diễn xuất sắc để đánh bại Thái Lan với tỷ số 3-0.
            
            Các bàn thắng được ghi bởi Nguyễn Tiến Linh (phút 23), Nguyễn Quang Hải (phút 56) và Phạm Tuấn Hải (phút 82). HLV Park Hang-seo đã có sự điều chỉnh chiến thuật khôn ngoan giúp đội tuyển kiểm soát trận đấu.
            
            Chung kết sẽ diễn ra vào thứ 7 tuần này giữa Việt Nam và Indonesia. Đây hứa hẹn sẽ là trận cầu đỉnh cao của bóng đá Đông Nam Á.""",
            "thumbnail": "https://via.placeholder.com/800x450?text=Vietnam+Football",
            "author": "Trần Thị B",
            "source": "VnExpress Thể thao",
            "tags": "Football,Vietnam,SEA Games,Sports",
            "status": "published",
            "is_featured": True,
            "view_count": 2340,
            "like_count": 156,
            "category_id": sports_cat.id if sports_cat else None,
            "published_at": now - timedelta(hours=5)
        },
        {
            "title": "Chứng khoán Việt Nam tăng điểm mạnh trong phiên đầu tuần",
            "slug": "chung-khoan-viet-nam-tang-diem-manh",
            "summary": "VN-Index tăng hơn 15 điểm nhờ dòng tiền mạnh đổ vào cổ phiếu ngân hàng và BĐS.",
            "content": """Thị trường chứng khoán Việt Nam có phiên giao dịch tích cực với VN-Index tăng 15,67 điểm (1,32%) lên 1.202,45 điểm.
            
            Thanh khoản cải thiện đáng kể với giá trị giao dịch đạt 18.500 tỷ đồng. Nhóm cổ phiếu ngân hàng dẫn dầu với VCB, TCB, MBB đều tăng trần.
            
            Các chuyên gia nhận định xu hướng tích cực sẽ được duy trì trong các phiên tới nhờ triển vọng kinh tế khả quan và dòng tiền ngoại quay trở lại.""",
            "thumbnail": "https://via.placeholder.com/800x450?text=Stock+Market",
            "author": "Lê Văn C",
            "source": "Đầu tư Chứng khoán",
            "tags": "Stock Market,Economy,Finance,Vietnam",
            "status": "published",
            "is_trending": True,
            "view_count": 890,
            "like_count": 45,
            "category_id": eco_cat.id if eco_cat else None,
            "published_at": now - timedelta(hours=3)
        },
    ]
    
    for news_item in news_data:
        existing = db.query(News).filter(News.slug == news_item["slug"]).first()
        if not existing:
            news = News(**news_item)
            db.add(news)
    
    db.commit()
    db.close()
    print("✅ News seeded successfully")

def main():
    """Run database seeding"""
    print("\n" + "="*50)
    print("🌱 Database Seeding Started")
    print("="*50 + "\n")
    
    # Initialize database
    print("🔧 Initializing database...")
    init_db()
    
    # Seed data
    seed_categories()
    seed_news()
    
    print("\n" + "="*50)
    print("✅ Database Seeding Completed Successfully!")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
