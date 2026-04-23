import json
from pathlib import Path

def build_and_save_taxonomy():
    genres_taxonomy = {
        "sử": "Lịch sử / Biên niên sử",
        "chiến": "Tài liệu Chiến tranh / Quân sự",
        "truyện": "Tiểu thuyết / Hư cấu (Fiction)",
        "thơ": "Thơ ca / Vần điệu",
        "báo": "Phóng sự / Báo chí",
        "khoa": "Khoa học Viễn tưởng / Khoa học kỹ thuật",
        "luật": "Văn bản Pháp lý / Hiến pháp",
        "đạo": "Tôn giáo / Triết học / Đạo lý",
        "ký": "Hồi ký / Tự truyện",
        "kinh": "Kinh tế / Kinh doanh / Đầu tư",
        "tâm": "Tâm lý học / Phát triển bản thân",
        "trinh": "Trinh thám / Phá án",
        "y": "Y học / Sức khỏe",
        "hài": "Hài hước / Châm biếm"
    }

    moods_taxonomy = {
        "buồn": "Bi thương, u buồn, xót xa",
        "vui": "Vui vẻ, tích cực, lạc quan",
        "căng": "Căng thẳng, hồi hộp, kịch tính",
        "sợ": "Đáng sợ, kinh dị, ám ảnh",
        "bi": "Bi tráng, oai hùng, xót thương",
        "hùng": "Hùng hồn, sử thi, mạnh mẽ",
        "tĩnh": "Bình yên, tĩnh lặng, nhẹ nhàng",
        "động": "Sôi động, dồn dập, náo nhiệt",
        "sâu": "Sâu lắng, triết lý, suy ngẫm",
        "lạnh": "Lạnh lẽo, vô cảm, tàn nhẫn",
        "nhạt": "Bình thản, trung lập",
        "cáu": "Tức giận, phẫn nộ, gay gắt"
    }

    Path("genres_ref.json").write_text(json.dumps(genres_taxonomy, ensure_ascii=False, indent=4), encoding="utf-8")
    Path("moods_ref.json").write_text(json.dumps(moods_taxonomy, ensure_ascii=False, indent=4), encoding="utf-8")
    print("Taxonomy files created successfully.")

if __name__ == "__main__":
    build_and_save_taxonomy()
