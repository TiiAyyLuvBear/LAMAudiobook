"""
Classifier Agent — Pure PhoBERT Implementation.
Uses ONLY PhoBERT MLM for all decisions (Genre, Mood, Type, Speaker, Emotion).
Optimized with Batched Inference and Threading to avoid blocking the event loop.
"""
import json
import re
import asyncio
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .base import BaseAgent, AgentResult
    from src.schema.pipeline import Sentence
except ImportError:
    import importlib.util
    repo_root = Path(__file__).resolve().parents[2]

    base_spec = importlib.util.spec_from_file_location(
        "agents.base", str(repo_root / "src" / "agents" / "base.py")
    )
    base_mod = importlib.util.module_from_spec(base_spec)
    base_spec.loader.exec_module(base_mod)

    types_spec = importlib.util.spec_from_file_location(
        "types.pipeline", str(repo_root / "src" / "types" / "pipeline.py")
    )
    types_mod = importlib.util.module_from_spec(types_spec)
    types_spec.loader.exec_module(types_mod)

    BaseAgent = base_mod.BaseAgent
    AgentResult = base_mod.AgentResult
    Sentence = types_mod.Sentence

# ==========================================
# CÁC DATA CLASSES
# ==========================================
class ClassifierInput:
    def __init__(
        self,
        chapters: Optional[List[Any]] = None,
        emotion_level: str = "basic",
        file_path: Optional[str] = None,
    ):
        self.chapters = chapters
        self.emotion_level = emotion_level
        self.file_path = file_path

class ClassifierOutput:
    def __init__(
        self,
        annotated_chapters: List[Dict[str, Any]],
        sentences: List[Sentence],
        speakers: List[str],
        speaker_count: int,
        dialogue_ratio: float,
        predictions: Optional[List[Dict[str, float]]] = None,
        genre: Optional[str] = None,
        mood: Optional[str] = None,
        source_text: Optional[str] = None,
    ):
        self.annotated_chapters = annotated_chapters
        self.sentences = sentences
        self.speakers = speakers
        self.speaker_count = speaker_count
        self.dialogue_ratio = dialogue_ratio
        self.predictions = predictions or []
        self.genre = genre
        self.mood = mood
        self.source_text = source_text

# ==========================================
# AGENT CLASSIFIER PURE PHO-BERT
# ==========================================
class ClassifierAgent(BaseAgent):
    name = "classifier"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name=self.name, config=config)
        self._phobert_tokenizer = None
        self._phobert_mlm = None
        self._fill_mask_pipeline = None
        self._phobert_backend = "uninitialized"
        self.genre_map = self._load_json_reference("genres_ref.json")
        self.mood_map = self._load_json_reference("moods_ref.json")

    def _load_json_reference(self, filepath: str) -> dict:
        try:
            path = Path(filepath)
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Warning] Failed to load {filepath}: {e}")
        return {}

    def _load_phobert(self) -> None:
        """Khởi tạo PhoBERT và Pipeline Batched Inference"""
        if self._phobert_mlm is not None and self._fill_mask_pipeline is not None:
            return
        try:
            import torch
            from transformers import AutoModelForMaskedLM, AutoTokenizer, pipeline

            model_name = "vinai/phobert-base-v2"
            self._phobert_tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._phobert_mlm = AutoModelForMaskedLM.from_pretrained(model_name)
            self._phobert_mlm.eval()
            
            device = 0 if torch.cuda.is_available() else -1
            self._fill_mask_pipeline = pipeline(
                "fill-mask", 
                model=self._phobert_mlm, 
                tokenizer=self._phobert_tokenizer, 
                device=device,
                top_k=1 # Chỉ lấy token có xác suất cao nhất để tối ưu tốc độ
            )
            self._phobert_backend = model_name
        except Exception as e:
            self._phobert_backend = "model-load-failed"
            raise RuntimeError(f"PhoBERT load failed: {e}")

    def _clean_mask_token(self, token: str) -> str:
        token = str(token).strip()
        token = token.replace(" ", "_").replace("/", "_").replace("-", "_")
        token = re.sub(r"_+", "_", token).strip("_")
        return token or "unknown"

    def _split_sentences(self, text: str) -> List[str]:
        """Tách đoạn văn thành các chuỗi đầu vào (vẫn cần thiết để model đọc từng câu)"""
        if not text: return []
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p.strip() for p in parts if p.strip()]

    def _phobert_rank_document_sync(self, text: str) -> Tuple[List[Dict[str, float]], str, str]:
        self._load_phobert()
        mask_token = self._phobert_tokenizer.mask_token
        text_short = re.sub(r"\s+", " ", text).strip()[:800]

        g_prompt = f"Văn bản: {text_short}. Thể loại chính là {mask_token}."
        m_prompt = f"Văn bản: {text_short}. Không khí đoạn văn rất {mask_token}."
        genre_targets = list(self.genre_map.keys()) if self.genre_map else None
        mood_targets = list(self.mood_map.keys()) if self.mood_map else None

        try:
            g_res = self._fill_mask_pipeline(g_prompt, targets=genre_targets)
            m_res = self._fill_mask_pipeline(m_prompt, targets=mood_targets)

            raw_genre = self._clean_mask_token(g_res[0]["token_str"])
            raw_mood = self._clean_mask_token(m_res[0]["token_str"])
            top_genre = self.genre_map.get(raw_genre, raw_genre)
            top_mood = self.mood_map.get(raw_mood, raw_mood)
            
            predictions = [
                {"label": f"Genre_{top_genre}", "score": round(g_res[0]["score"], 4)},
                {"label": f"Mood_{top_mood}", "score": round(m_res[0]["score"], 4)}
            ]
            return predictions, top_genre, top_mood
        except Exception:
            return [], "unknown", "neutral"

    def _phobert_classify_batch_sync(self, sentences: List[str]) -> List[Dict[str, str]]:
        """
        Dự đoán Type, Emotion, Speaker cho một LÔ (Batch) các câu văn.
        Việc đưa list vào pipeline giúp tốc độ tăng gấp nhiều lần so với chạy for loop.
        """
        if not sentences: return []
        self._load_phobert()
        mask = self._phobert_tokenizer.mask_token

        # Chuẩn bị 3 list prompts cho 3 thuộc tính
        type_prompts = [f"Câu văn: '{s[:150]}'. Đây là lời {mask}." for s in sentences]
        emo_prompts = [f"Câu văn: '{s[:150]}'. Cảm xúc câu này là {mask}." for s in sentences]
        spk_prompts = [f"Câu văn: '{s[:150]}'. Người nói là {mask}." for s in sentences]
        emo_targets = list(self.mood_map.keys()) if self.mood_map else None

        try:
            # Chạy pipeline theo batch (tận dụng phần cứng I/O)
            t_preds = self._fill_mask_pipeline(type_prompts, batch_size=16)
            e_preds = self._fill_mask_pipeline(emo_prompts, batch_size=16, targets=emo_targets)
            s_preds = self._fill_mask_pipeline(spk_prompts, batch_size=16)

            results = []
            for i in range(len(sentences)):
                # Lấy kết quả từ pipeline (pipeline trả về dict nếu input là string, trả list dict nếu input là list)
                t_res = t_preds[i] if isinstance(t_preds, list) else t_preds
                e_res = e_preds[i] if isinstance(e_preds, list) else e_preds
                s_res = s_preds[i] if isinstance(s_preds, list) else s_preds

                # Trích xuất token
                t_tok = t_res[0]['token_str'] if isinstance(t_res, list) else t_res['token_str']
                raw_emo = e_res[0]['token_str'] if isinstance(e_res, list) else e_res['token_str']
                s_tok = s_res[0]['token_str'] if isinstance(s_res, list) else s_res['token_str']
                mapped_emo = self.mood_map.get(self._clean_mask_token(raw_emo), self._clean_mask_token(raw_emo))

                results.append({
                    "type": self._clean_mask_token(t_tok),
                    "emotion": mapped_emo,
                    "speaker": self._clean_mask_token(s_tok)
                })
            return results
        except Exception as e:
            print(f"[Warning] PhoBERT batch inference failed: {e}")
            return [{"type": "unknown", "emotion": "neutral", "speaker": "unknown"} for _ in sentences]

    async def _process_chapter_async(self, chapter_idx: int, chapter_title: str, paragraphs: List[Any]) -> Dict[str, Any]:
        """Xử lý từng chương bất đồng bộ bằng cách đẩy batch inference vào ThreadPool"""
        all_sentences_text = []
        para_mapping = [] # Lưu vết câu nào thuộc đoạn nào

        # 1. Thu thập và tách toàn bộ câu trong chương
        for p_idx, para in enumerate(paragraphs):
            para_text = getattr(para, "text", "") if not isinstance(para, dict) else para.get("text", "")
            if not para_text: continue
            
            sents = self._split_sentences(para_text)
            for s in sents:
                all_sentences_text.append(s)
                para_mapping.append({"p_idx": p_idx + 1, "text": para_text})

        # 2. Giao việc cho PhoBERT suy luận toàn bộ lô câu văn (trong background thread)
        batch_results = await asyncio.to_thread(self._phobert_classify_batch_sync, all_sentences_text)

        # 3. Đóng gói kết quả trả về
        chapter_dict = {
            "chapter_index": chapter_idx,
            "chapter_title": chapter_title,
            "paragraphs": [],
            "extracted_sentences": []
        }
        
        # Nhóm câu trả lại theo Paragraph
        current_p_idx = -1
        current_para_sents = []
        current_para_text = ""

        for s_text, mapping, res in zip(all_sentences_text, para_mapping, batch_results):
            sent_obj = Sentence(
                text=s_text,
                type=res["type"],
                speaker=res["speaker"],
                emotion=res["emotion"],
                intensity=0.5,
                chapter_index=chapter_idx,
                paragraph_index=mapping["p_idx"]
            )
            chapter_dict["extracted_sentences"].append(sent_obj)

            if mapping["p_idx"] != current_p_idx:
                if current_p_idx != -1:
                    chapter_dict["paragraphs"].append({"text": current_para_text, "sentences": current_para_sents})
                current_p_idx = mapping["p_idx"]
                current_para_text = mapping["text"]
                current_para_sents = []
            
            current_para_sents.append({"text": s_text, "type": res["type"], "speaker": res["speaker"], "emotion": res["emotion"]})

        if current_p_idx != -1:
             chapter_dict["paragraphs"].append({"text": current_para_text, "sentences": current_para_sents})

        return chapter_dict

    def _load_text_from_file(self, file_path: str) -> str:
        # Giữ nguyên logic đọc file của bạn...
        path = Path(file_path)
        if not path.exists(): raise FileNotFoundError(f"File not found: {file_path}")
        suffix = path.suffix.lower()
        if suffix == ".txt": return path.read_text(encoding="utf-8", errors="ignore").strip()
        if suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            plain = payload.get("plain_text")
            if isinstance(plain, str) and plain.strip(): return plain.strip()
            blocks = payload.get("blocks", [])
            if isinstance(blocks, list): return "\n".join([b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("text")]).strip()
        raise ValueError("Unsupported input format")

    async def run(self, input_data: ClassifierInput) -> AgentResult:
        try:
            if isinstance(input_data, dict):
                input_data = ClassifierInput(**input_data)

            # MODE 1: Xử lý file thẳng
            if input_data.file_path:
                source_text = self._load_text_from_file(input_data.file_path)
                predictions, genre, mood = await asyncio.to_thread(self._phobert_rank_document_sync, source_text)

                return AgentResult(
                    success=True,
                    data=ClassifierOutput(
                        annotated_chapters=[], sentences=[], speakers=[], speaker_count=0,
                        dialogue_ratio=0.0, predictions=predictions, genre=genre, mood=mood, source_text=source_text,
                    ),
                    metadata={"backend": self._phobert_backend, "mode": "phobert-auto-only"},
                )

            # MODE 2: Xử lý Chapter
            chapters = input_data.chapters or []
            annotated_chapters = []
            all_sentences = []
            speakers_set = set()
            dialogue_count = 0

            # Tung toàn bộ Chapter vào ThreadPool chạy song song
            tasks = []
            for chapter in chapters:
                c_idx = getattr(chapter, "chapter_index", 1)
                c_title = getattr(chapter, "chapter_title", "")
                paras = getattr(chapter, "paragraphs", [])
                tasks.append(self._process_chapter_async(c_idx, c_title, paras))

            chapter_results = await asyncio.gather(*tasks)

            # Tổng hợp kết quả
            for ch_res in chapter_results:
                annotated_chapters.append({
                    "chapter_index": ch_res["chapter_index"],
                    "chapter_title": ch_res["chapter_title"],
                    "paragraphs": ch_res["paragraphs"]
                })
                
                for sent_obj in ch_res["extracted_sentences"]:
                    all_sentences.append(sent_obj)
                    speakers_set.add(sent_obj.speaker)
                    # Tính ratio dựa trên những token model thường gán cho hội thoại
                    if any(kw in str(sent_obj.type).lower() for kw in ["nói", "thoại", "đáp", "hỏi"]):
                        dialogue_count += 1

            total_sentences = len(all_sentences)
            dialogue_ratio = dialogue_count / total_sentences if total_sentences > 0 else 0.0
            joined_text = " ".join([s.text for s in all_sentences]).strip()

            predictions, genre, mood = [], "unknown", "neutral"
            if joined_text:
                predictions, genre, mood = await asyncio.to_thread(self._phobert_rank_document_sync, joined_text)

            return AgentResult(
                success=True,
                data=ClassifierOutput(
                    annotated_chapters=annotated_chapters,
                    sentences=all_sentences,
                    speakers=list(speakers_set),
                    speaker_count=len(speakers_set),
                    dialogue_ratio=dialogue_ratio,
                    predictions=predictions,
                    genre=genre,
                    mood=mood,
                    source_text=joined_text,
                ),
                metadata={"backend": self._phobert_backend},
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))


def _default_output_path(input_file: str) -> str:
    p = Path(input_file)
    return str(p.with_suffix(".classified.json"))

async def _run_cli() -> int:
    parser = argparse.ArgumentParser(description="Classifier CLI: Pure PhoBERT Approach")
    parser.add_argument("-i", "--input", required=True, help="Input file (.txt or .json)")
    parser.add_argument("-o", "--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    output_path = args.output or _default_output_path(args.input)

    agent = ClassifierAgent()
    print(f"Đang phân tích file: {args.input} bằng PhoBERT...")
    result = await agent.run(ClassifierInput(file_path=args.input))
    
    if not result.success:
        print(f"Lỗi khi chạy Classifier: {result.error}")
        return 1

    out: ClassifierOutput = result.data
    
    # Gom các kết quả quan trọng để lưu ra file JSON
    payload = {
        "genre": out.genre,
        "mood": out.mood,
        "dialogue_ratio": out.dialogue_ratio,
        "predictions": out.predictions,
        "metadata": result.metadata or {},
        "sentences_preview": [
            {"text": s.text, "type": s.type, "emotion": s.emotion, "speaker": s.speaker} 
            for s in out.sentences[:5] # Chỉ lưu 5 câu đầu để preview tránh phình to file
        ] if out.sentences else []
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")

    print("\n--- KẾT QUẢ PHÂN TÍCH ---")
    print(f"Thể loại: {out.genre}")
    print(f"Không khí: {out.mood}")
    print(f"Tỉ lệ đối thoại: {out.dialogue_ratio:.2f}")
    print(f"File kết quả đã được lưu tại: {output_path}")
    
    return 0

if __name__ == "__main__":
    # Khởi chạy Event Loop cho các hàm async
    raise SystemExit(asyncio.run(_run_cli()))
