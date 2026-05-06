#!/usr/bin/env python3
"""
Audio Post-Processing Agent (All-in-One)
Ghép WAV + Thêm pause + Normalize + Fade
"""
# python -m venv .venv
# .\.venv\Scripts\Activate
# pip install librosa soundfile numpy
# python audio_processor.py --verbose

import os
import sys
import csv
import argparse
import numpy as np

if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except:
        pass

try:
    import librosa
    import soundfile as sf
except ImportError:
    print("Cần cài: pip install librosa soundfile numpy")
    sys.exit(1)


class AudioProcessor:
    """Audio post-processing agent"""
    
    def __init__(self, sr=22050):
        """Khoi tao processor voi cac tham so co ban"""
        self.sr = sr  # rate: 22050 Hz
        
        self.pause_config = {
            '.': 500,      # Dấu chấm
            ',': 300,      # Dấu phẩy
            '!': 700,      # Dấu chấm than
            '?': 700,      # Dấu hỏi
            ';': 400,      # Dấu chấm phẩy
            ':': 400,      # Dấu hai chấm
            '...': 600,    # Ba chấm
            'default': 200,# Mặc định (không có dấu)
        }
        
        # FADE CONFIG - Loai bo click/pop o dau/cuoi file
        self.fade_ms = 50  # Fade in/out
        
        # LOUDNESS CONFIG - Chuẩn hóa âm lượng
        self.loudness_db = -20.0  # Target: -20dB
    
    def get_pause_time(self, text):
        """LAY PAUSE TIME - Xac dinh thoi gian ngan theo dau cau
        
        Args:
            text: Noi dung cau
        
        Returns:
            Thoi gian pause (giay)
        """
        text = text.strip()
        
        # Check ba cham truoc 
        if text.endswith('...'):
            return self.pause_config['...'] / 1000.0  # 600ms -> 0.6s
        
        # Check cac dau cau khac
        for mark in '.!?,;:':
            if text.endswith(mark):
                ms = self.pause_config.get(mark, self.pause_config['default'])
                return ms / 1000.0  # Convert milliseconds to seconds
        
        # Nếu không có dấu câu, dùng default (200ms)
        return self.pause_config['default'] / 1000.0
    
    def normalize(self, audio):
        """NORMALIZE - Chuan hoa am luong tat ca file ve same level
        Van de: Moi file WAV tu TTS co volume khac nhau
        Giai phap: Tinh RMS -> Scale ve target loudness (-20dB)
        """
        # Tinh RMS (Root Mean Square) - do lon cua chuyen dong
        rms = np.sqrt(np.mean(audio ** 2))
        
        if rms < 1e-10:  # Neu audio qua yeu (gan silence)
            return audio  # Return as is, tranh division by zero
        
        # Quy doi target loudness tu dB sang linear
        target = 10 ** (self.loudness_db / 20.0)  # -20dB -> 0.1 (linear)
        
        # Scale audio: (audio/rms)*target
        normalized = (audio / rms) * target
        
        # Clipping de tranh distortion (giu trong [-1, 1])
        return np.clip(normalized, -1.0, 1.0)
    
    def fade(self, audio):
        """FADE - Loai bo click/pop o dau/cuoi file
        Van de: Khi ghep WAV file co the bi 'click' (am tieng gap gap)
        Giai phap: Tao fade in (0->1) o dau, fade out (1->0) o cuoi"""
        
        # Tinh so samples can fade (dua tren fade_ms)
        fade_samp = int(self.fade_ms * self.sr / 1000)  # 50ms * 22050Hz = ~1102 samples
        
        # Gioi han fade_samp de khong qua dai (max 1/6 chieu dai file)
        fade_samp = min(fade_samp, len(audio) // 6)
        
        if fade_samp < 2:
            return audio  # File qua ngan, skip fade
        
        # Fade IN - tang am luong tu 0 -> 1
        fade_in = np.linspace(0, 1, fade_samp)  # Tao curve tu 0 den 1
        audio[:fade_samp] *= fade_in  # Nhan tung sample voi fade curve
        
        # Fade OUT - giam am luong tu 1 -> 0  
        fade_out = np.linspace(1, 0, fade_samp)  # Tao curve tu 1 xuong 0
        audio[-fade_samp:] *= fade_out  # Ap dung vao phan cuoi file
        
        return audio
    
    def process(self, wavs_folder, metadata_file, output_file, verbose=False):
        """MAIN PIPELINE - Xu ly tat ca segments"""
        
        # === BUOC 1: LOAD METADATA ===
        # Doc file CSV co dau "|" la delimiter
        # Duong dan: metadata.csv (format: wavs/test_5min_XXXX.wav|Text content here)
        segments = []
        with open(metadata_file, 'r', encoding='utf-8') as f:
            for idx, row in enumerate(csv.reader(f, delimiter='|'), 1):
                if len(row) >= 2:
                    segments.append({
                        'idx': idx,
                        'wav': row[0].strip(),  # Duong dan WAV file
                        'text': row[1].strip(), # Noi dung cau (de tinh dau cau -> pause)
                    })
        
        print(f"\n{'='*60}")
        print(f"AUDIO POST-PROCESSING AGENT")
        print(f"{'='*60}")
        print(f"Load {len(segments)} segments")
        print(f"\nXu ly segments...")
        print(f"{'='*60}")
        
        # === BUOC 2: XU LY TUNG SEGMENT ===
        # all_audio = danh sach chua tung segment da xu lý 
        all_audio = []
        for seg in segments:
            # === Step A: XAC DINH DUONG DAN FILE ===
            wav_file = seg['wav']
            wav_file_norm = wav_file.replace('\\', '/')
            if wav_file_norm.startswith('wavs/') or wav_file_norm.startswith('wav/'):
                filename = os.path.basename(wav_file_norm)  # Extract filename
            else:
                filename = wav_file
            
            full_path = os.path.join(wavs_folder, filename)  # Build full path
            
            # Kiem tra file co ton tai hay khong
            if not os.path.exists(full_path):
                print(f"[{seg['idx']:3d}] Khong tim: {wav_file}")
                continue
            
            try:
                # === Step B: LOAD WAV FILE ===
                # librosa.load() tu dong convert ve 22050Hz neu can
                audio, _ = librosa.load(full_path, sr=self.sr)
                
                # === Step C: XU LY AUDIO (3 buoc chinh) ===
                
                # C1. NORMALIZE - Chuan hoa am luong ve -20dB
                audio = self.normalize(audio)
                
                # C2. FADE - Tao fade in/out de loai bo click ở dau/cuoi
                audio = self.fade(audio)
                
                # === Step D: THEM PAUSE (SAM) ===
                # Based on dau cau -> pause duration
                pause_sec = self.get_pause_time(seg['text'])  # Get pause from punctuation
                silence = np.zeros(int(pause_sec * self.sr))  # Create silence array
                audio = np.concatenate([audio, silence])      # Append silence to audio
                
                # Add to all_audio list (se ghep sau)
                all_audio.append(audio)
                
                # === DISPLAY RESULT ===
                text_short = seg['text'][:40] + "..." if len(seg['text']) > 40 else seg['text']
                punct = '?'
                if text_short.rstrip().endswith('...'):
                    punct = '...'
                elif text_short.rstrip()[-1] in '.!?,;:':
                    punct = text_short.rstrip()[-1]
                
                pause_ms = self.get_pause_time(seg['text']) * 1000
                
                if verbose:
                    print(f"[{seg['idx']:3d}] {len(audio)/self.sr:6.2f}s | {punct} | {pause_ms:.0f}ms")
                else:
                    print(f"[{seg['idx']:3d}] Processed")
                    
            except Exception as e:
                print(f"[{seg['idx']:3d}] Error: {e}")
                continue
        
        print(f"{'='*60}")
        
        # === BUOC 3: KEM HOP TAT CA SEGMENTS ===
        if not all_audio:
            print("No audio to merge!")
            return False
        
        # MERGE (GHEP) - Noi tuan tu: seg1+pause1+seg2+pause2+...+seg30+pause30
        # all_audio = [seg1_with_pause, seg2_with_pause, ..., seg30_with_pause]
        # np.concatenate() se noi lenh danh sach thanh 1 array dai
        merged = np.concatenate(all_audio)  # Ghep tuan tu tat ca segment
        total_sec = len(merged) / self.sr    # Tinh tong thoi gian (samples / sr)
        
        print(f"\nMerged! Tong: {total_sec:.2f}s")
        
        # === BUOC 4: LUU FILE ===
        # sf.write(file, audio_array, sample_rate)
        # Ghi merged audio ra file WAV format
        sf.write(output_file, merged, self.sr)
        file_size = os.path.getsize(output_file) / (1024*1024)  # Size in MB
        
        print(f"Done!")
        print(f"   File: {output_file}")
        print(f"   Size: {file_size:.2f} MB")
        print(f"   Time: {total_sec:.2f}s\n")
        
        return True


def _find_wavs_folder(folder_path):
    """Tim thu muc chua cac file wav trong 1 job folder."""
    for folder_name in ('wav', 'wavs'):
        candidate = os.path.join(folder_path, folder_name)
        if os.path.isdir(candidate):
            return candidate
    return None


def _find_metadata_csv(folder_path):
    """Tim file CSV metadata trong 1 job folder."""
    csv_files = sorted(
        f for f in os.listdir(folder_path)
        if f.lower().endswith('.csv') and os.path.isfile(os.path.join(folder_path, f))
    )
    if not csv_files:
        return None

    # Uu tien metadata.csv, neu khong co thi lay file csv dau tien.
    for csv_name in csv_files:
        if csv_name.lower() == 'metadata.csv':
            return os.path.join(folder_path, csv_name)

    return os.path.join(folder_path, csv_files[0])


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_audio_root = os.path.normpath(os.path.join(script_dir, '..', 'backend', 'audio'))

    parser = argparse.ArgumentParser(description="🎵 Audio Post-Processing")
    parser.add_argument('--audio-root', default=default_audio_root, help='Audio root folder')
    parser.add_argument('--output-name', default='output_merged.wav', help='Output file name per subfolder')
    parser.add_argument('--sr', type=int, default=22050, help='Sample rate')
    parser.add_argument('--fade', type=float, default=50, help='Fade (ms)')
    parser.add_argument('--loudness', type=float, default=-20.0, help='Loudness (dB)')
    parser.add_argument('--verbose', action='store_true', help='Verbose mode')
    
    args = parser.parse_args()
    
    processor = AudioProcessor(sr=args.sr)
    processor.fade_ms = args.fade
    processor.loudness_db = args.loudness

    audio_root = os.path.abspath(args.audio_root)
    if not os.path.isdir(audio_root):
        print(f"Khong tim thay audio root: {audio_root}")
        return 1

    subfolders = sorted(
        os.path.join(audio_root, name)
        for name in os.listdir(audio_root)
        if os.path.isdir(os.path.join(audio_root, name))
    )

    if not subfolders:
        print(f"Khong co folder con nao trong: {audio_root}")
        return 1

    success_count = 0
    failed_count = 0

    print(f"Audio root: {audio_root}")
    print(f"Tim thay {len(subfolders)} folder con de xu ly")

    for job_folder in subfolders:
        job_name = os.path.basename(job_folder)
        wavs_folder = _find_wavs_folder(job_folder)
        metadata_file = _find_metadata_csv(job_folder)

        if not wavs_folder or not metadata_file:
            print(f"\n[{job_name}] Skip: thieu folder wav/wavs hoac file csv")
            failed_count += 1
            continue

        output_file = os.path.join(job_folder, args.output_name)

        print(f"\n{'#'*60}")
        print(f"JOB: {job_name}")
        print(f"WAV: {wavs_folder}")
        print(f"CSV: {metadata_file}")
        print(f"OUT: {output_file}")
        print(f"{'#'*60}")

        success = processor.process(wavs_folder, metadata_file, output_file, args.verbose)
        if success:
            success_count += 1
        else:
            failed_count += 1

    print(f"\n{'='*60}")
    print("TONG KET")
    print(f"Thanh cong: {success_count}")
    print(f"That bai:   {failed_count}")
    print(f"{'='*60}")

    return 0 if success_count > 0 and failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
