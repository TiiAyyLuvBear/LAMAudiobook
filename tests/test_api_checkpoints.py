from datetime import datetime
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app import app  # noqa: E402
from backend.database import Base, get_db  # noqa: E402
from backend.models.category import Category  # noqa: E402
from backend.models.news import News  # noqa: E402


TEST_DB_URL = "sqlite://"

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _seed_mock_data() -> None:
    db = TestingSessionLocal()
    try:
        tech = Category(
            name="Cong nghe",
            slug="cong-nghe",
            description="Tin tuc cong nghe",
            icon="laptop",
            color="#3B82F6",
            order=1,
            is_active=True,
        )
        sports = Category(
            name="The thao",
            slug="the-thao",
            description="Tin tuc the thao",
            icon="football",
            color="#EF4444",
            order=2,
            is_active=True,
        )
        db.add_all([tech, sports])
        db.flush()

        news_items = [
            News(
                title="AI dang tang toc",
                slug="ai-dang-tang-toc",
                summary="He sinh thai AI tiep tuc mo rong.",
                content="Noi dung chi tiet ve AI.",
                author="Mock Author",
                source="Mock Source",
                tags="AI,Technology",
                status="published",
                is_featured=True,
                is_trending=True,
                view_count=10,
                like_count=2,
                category_id=tech.id,
                published_at=datetime.utcnow(),
            ),
            News(
                title="Viet Nam thang lon",
                slug="viet-nam-thang-lon",
                summary="Doi tuyen co chien thang an tuong.",
                content="Noi dung the thao.",
                author="Mock Author",
                source="Mock Source",
                tags="Sports,Vietnam",
                status="published",
                is_featured=False,
                is_trending=True,
                view_count=5,
                like_count=1,
                category_id=sports.id,
                published_at=datetime.utcnow(),
            ),
        ]
        db.add_all(news_items)
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="function")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _seed_mock_data()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

    Base.metadata.drop_all(bind=engine)


def test_health_checkpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"


def test_categories_checkpoint_returns_mock_data(client: TestClient):
    response = client.get("/api/v1/categories/")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["count"] == 2
    slugs = [item["slug"] for item in payload["data"]]
    assert "cong-nghe" in slugs
    assert "the-thao" in slugs


def test_news_checkpoint_pagination_works(client: TestClient):
    response = client.get("/api/v1/news/?page=1&limit=10&status=published")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert len(payload["data"]) == 2
    assert payload["pagination"]["total"] == 2


def test_homepage_checkpoint_aggregates_data(client: TestClient):
    response = client.get("/api/v1/homepage/")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert "featured_news" in payload["data"]
    assert "categories" in payload["data"]
    assert len(payload["data"]["categories"]) == 2


def test_middleware_blocks_duplicate_category_slug(client: TestClient):
    response = client.post(
        "/api/v1/categories/",
        json={
            "name": "Cong nghe moi",
            "slug": "cong-nghe",
            "description": "Trung slug",
            "icon": "chip",
            "color": "#000000",
            "order": 3,
            "is_active": True,
        },
    )

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_news_detail_checkpoint_increments_view(client: TestClient):
    list_resp = client.get("/api/v1/news/?page=1&limit=10")
    news_id = list_resp.json()["data"][0]["id"]
    before_view = list_resp.json()["data"][0]["view_count"]

    detail_resp = client.get(f"/api/v1/news/{news_id}")
    assert detail_resp.status_code == 200

    after_resp = client.get(f"/api/v1/news/{news_id}")
    assert after_resp.status_code == 200
    assert after_resp.json()["data"]["view_count"] >= before_view + 1
