import os
import sys

try:
    import torch
    from transformers import AutoTokenizer, AutoModel
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

DB_PATH = "data/qdrant_voice_db"
COLLECTION_NAME = "voices"
MODEL_NAME = "keepitreal/vietnamese-sbert"
VECTOR_SIZE = 768

VOICES = [
    {
        "voice_id": "female_hn_01",
        "gender": "female",
        "name": "Giọng nữ Hà Nội nhẹ nhàng",
        "description": "Giọng nữ Hà Nội nhẹ nhàng, dịu dàng, lãng mạn, ấm áp. Phù hợp ngôn tình, tình cảm, đời thường, sách có nhịp kể mềm mại."
    },
    {
        "voice_id": "female_hn_02",
        "gender": "female",
        "name": "Giọng nữ Hà Nội kể chuyện",
        "description": "Giọng nữ Hà Nội rõ ràng, trung tính, nhẹ nhàng, phù hợp sách phổ thông, tự sự, tản văn, tri thức nhẹ và kể chuyện dài."
    },
    {
        "voice_id": "female_hcm_01",
        "gender": "female",
        "name": "Giọng nữ Sài Gòn tự nhiên",
        "description": "Giọng nữ Sài Gòn tự nhiên, gần gũi, linh hoạt. Phù hợp sách hiện đại, hội thoại đời thường, nội dung trẻ trung."
    },
    {
        "voice_id": "female_hcm_02",
        "gender": "female",
        "name": "Giọng nữ Sài Gòn vui tươi",
        "description": "Giọng nữ Sài Gòn trẻ trung, vui vẻ, hào hứng, vui tươi. Thích hợp truyện thanh xuân, hài hước, tích cực."
    },
    {
        "voice_id": "male_hn_01",
        "gender": "male",
        "name": "Giọng nam Hà Nội trầm",
        "description": "Giọng nam Hà Nội trầm ấm, trang nghiêm, u buồn, chiêm nghiệm. Thích hợp sách chiến tranh, lịch sử, kiếm hiệp, suy ngẫm."
    },
    {
        "voice_id": "male_hn_02",
        "gender": "male",
        "name": "Giọng nam Hà Nội mạnh mẽ",
        "description": "Giọng nam Hà Nội mạnh mẽ, kịch tính, căng thẳng, huyền bí. Phù hợp truyện trinh thám, kinh dị, bí ẩn, hồi hộp, hành động."
    },
]

def main():
    print("Building Qdrant Voice Database...")
    os.makedirs("data", exist_ok=True)
    
    # 1. Initialize Qdrant Client (Local file-based)
    # To deploy, simply change this to: QdrantClient(url="YOUR_URL", api_key="YOUR_KEY")
    client = QdrantClient(path=DB_PATH)
    
    # 2. Recreate Collection
    if client.collection_exists(collection_name=COLLECTION_NAME):
        client.delete_collection(collection_name=COLLECTION_NAME)
        
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    print(f"Created collection '{COLLECTION_NAME}'")

    # 3. Load Model
    if HAS_TORCH:
        print(f"Loading model {MODEL_NAME} for generating embeddings...")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        model = AutoModel.from_pretrained(MODEL_NAME)
        model.eval()
    else:
        print("WARNING: torch/transformers not installed. Using mock random vectors.")
        import random

    # 4. Insert Data
    points = []
    for idx, voice in enumerate(VOICES):
        text = voice["description"]
        
        if HAS_TORCH:
            inputs = tokenizer(text, padding=True, truncation=True, max_length=128, return_tensors="pt")
            with torch.no_grad():
                outputs = model(**inputs)
            emb = outputs.last_hidden_state.mean(dim=1).squeeze().tolist()
        else:
            emb = [random.uniform(-0.1, 0.1) for _ in range(VECTOR_SIZE)]
            
        points.append(
            PointStruct(
                id=idx + 1,
                vector=emb,
                payload={
                    "voice_id": voice["voice_id"],
                    "gender": voice["gender"],
                    "name": voice["name"],
                    "description": voice["description"]
                }
            )
        )
        print(f"  -> Processed {voice['voice_id']}")

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )
    
    print(f"Saved {len(points)} voices to Qdrant Database at {DB_PATH}")

if __name__ == "__main__":
    main()
