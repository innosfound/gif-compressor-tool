import streamlit as st
import requests
from io import BytesIO
from PIL import Image

def process_and_compress_image(url, target_size_mb, crop_params, resize_ratio):
    """
    流暢度優先：修復了黑白與卡死問題，並加入了畫面裁切與縮放功能。
    """
    try:
        # 1. 下載圖片
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        img_bytes = BytesIO(response.content)
        img = Image.open(img_bytes)
        
        original_size_mb = len(response.content) / (1024 * 1024)
        st.write(f"📥 成功讀取！格式: `{img.format}` | 原始大小: `{original_size_mb:.2f} MB`")
        
        # 2. 提取所有影格，同時進行「裁切」與「縮放」
        frames = []
        durations = [] 
        
        crop_top, crop_bottom, crop_left, crop_right = crop_params
        
        try:
            while True:
                frame = img.copy().convert('RGBA')
                
                # --- 新增功能：執行裁切 (Crop) ---
                if any([crop_top, crop_bottom, crop_left, crop_right]):
                    # 確保裁切範圍不會超出圖片本身，避免報錯
                    right_coord = max(img.width - crop_right, crop_left + 1)
                    bottom_coord = max(img.height - crop_bottom, crop_top + 1)
                    frame = frame.crop((crop_left, crop_top, right_coord, bottom_coord))
                
                # --- 新增功能：執行縮放 (Resize) ---
                if resize_ratio < 100:
                    new_w = max(int(frame.width * (resize_ratio / 100.0)), 1)
                    new_h = max(int(frame.height * (resize_ratio / 100.0)), 1)
                    # 使用 LANCZOS 確保縮放後的畫質最平滑
                    frame = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)

                frames.append(frame)
                
                # --- 修正 Bug 2：防止卡死，強制設定最低時間為 20 毫秒 ---
                raw_duration = img.info.get('duration', 100)
                durations.append(max(raw_duration, 20)) 
                
                img.seek(len(frames))
        except EOFError:
            pass
            
        st.write(f"⚙️ 啟動「流暢度優先」智慧壓縮引擎 (目標: {target_size_mb}MB 以下)...")

        strategies = [
            {"drop_frames": False, "colors": 128},
            {"drop_frames": False, "colors": 64}, 
            {"drop_frames": True,  "colors": 256},
            {"drop_frames": True,  "colors": 128},
            {"drop_frames": True,  "colors": 64}  
        ]
        
        output_io = BytesIO()
        final_size_mb = 0
        
        for step, strategy in enumerate(strategies):
            temp_io = BytesIO()
            
            if strategy["drop_frames"]:
                current_frames = []
                current_durations = []
                for i in range(0, len(frames), 2):
                    current_frames.append(frames[i])
                    dur = durations[i]
                    if i + 1 < len(durations):
                        dur += durations[i+1]
                    current_durations.append(dur)
                step_name = "抽幀(維持原速)"
            else:
                current_frames = frames
                current_durations = durations
                step_name = "保留全幀"

            colors = strategy["colors"]
            step_name += f" + 色彩數:{colors}"
            
            # === 安全轉檔邏輯 ===
            def safe_convert_to_rgb(img_frame):
                if img_frame.mode == 'RGBA':
                    bg = Image.new("RGB", img_frame.size, (255, 255, 255))
                    bg.paste(img_frame, mask=img_frame.split()[3])
                    return bg
                return img_frame.convert("RGB")

            # --- 修正 Bug 1：改用「中間那一幀」來產生全域色板，避免黑白破圖 ---
            middle_idx = len(current_frames) // 2
            palette_frame_rgb = safe_convert_to_rgb(current_frames[middle_idx])
            base_frame = palette_frame_rgb.convert("P", palette=Image.ADAPTIVE, colors=colors, dither=Image.NONE)
            
            processed_frames = []
            for f in current_frames:
                f_rgb = safe_convert_to_rgb(f)
                processed_frames.append(f_rgb.quantize(palette=base_frame, dither=0))
            # -------------------------------------------------------------

            # 儲存 GIF
            processed_frames[0].save(
                temp_io,
                format='GIF',
                save_all=True,
                append_images=processed_frames[1:],
                loop=0,
                duration=current_durations, 
                optimize=True
            )
            
            current_size_mb = temp_io.tell() / (1024 * 1024)
            
            if current_size_mb <= target_size_mb:
                output_io = temp_io
                final_size_mb = current_size_mb
                st.write(f"✅ 成功命中目標！使用策略：`{step_name}`")
                break
            else:
                st.write(f"⏳ 嘗試策略 `{step_name}`... 大小 {current_size_mb:.2f} MB")
                
                if step == len(strategies) - 1:
                    output_io = temp_io
                    final_size_mb = current_size_mb
                    st.warning(f"⚠️ 已經使用最高強度壓縮，但檔案可能仍略大於 {target_size_mb}MB。")

        return output_io.getvalue(), final_size_mb
        
    except Exception as e:
        return None, str(e)

# === Streamlit 網頁介面 ===
st.set_page_config(page_title="GIF 專業壓縮神器", page_icon="🪄")
st.title("🪄 動圖專業壓縮神器 (WebP 轉 GIF)")
st.markdown("完美保護你的電子報排版！支援裁切、縮放、與自動智能壓縮。")

url_input = st.text_input("請貼上 GIF 或 WebP 的網址：")

# --- 新增的裁切與縮放介面 ---
st.markdown("### ✂️ 畫面調整 (選填)")
resize_ratio = st.slider("📏 整體畫面縮放比例 (縮小能大幅減少檔案大小)", min_value=10, max_value=100, value=100, help="100% 代表不縮放")

st.markdown("📐 **裁切邊緣 (輸入要切掉的像素，0 代表不裁切)**")
col1, col2, col3, col4 = st.columns(4)
crop_top = col1.number_input("切除上邊緣", min_value=0, value=0)
crop_bottom = col2.number_input("切除下邊緣", min_value=0, value=0)
crop_left = col3.number_input("切除左邊緣", min_value=0, value=0)
crop_right = col4.number_input("切除右邊緣", min_value=0, value=0)
crop_params = (crop_top, crop_bottom, crop_left, crop_right)
# -----------------------------

st.markdown("### 🗜️ 壓縮設定")
target_size_option = st.radio(
    "📏 請選擇目標壓縮大小：",
    options=[10, 5],
    format_func=lambda x: f"小於 {x} MB",
    horizontal=True 
)

if st.button("開始處理"):
    if url_input:
        with st.spinner(f"正在執行智能壓縮 (目標：{target_size_option}MB)，請稍候..."):
            final_gif_bytes, final_size_or_error = process_and_compress_image(
                url_input, target_size_option, crop_params, resize_ratio
            )
            
            if final_gif_bytes:
                st.success(f"🎉 處理完成！最終大小: {final_size_or_error:.2f} MB")
                st.image(final_gif_bytes, caption="壓縮後的 GIF 預覽")
                
                st.download_button(
                    label="⬇️ 下載壓縮版 GIF",
                    data=final_gif_bytes,
                    file_name="newsletter_optimized.gif",
                    mime="image/gif"
                )
            else:
                st.error(f"處理失敗: {final_size_or_error}")
    else:
        st.warning("請先輸入連結喔！")