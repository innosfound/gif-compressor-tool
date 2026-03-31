import streamlit as st
import requests
from io import BytesIO
from PIL import Image
from streamlit_cropper import st_cropper

def safe_convert_to_rgb(img_frame):
    """將任何格式的影格安全轉換為純 RGB，並將透明背景填滿白色"""
    if img_frame.mode in ('RGBA', 'LA') or (img_frame.mode == 'P' and 'transparency' in img_frame.info):
        # 先轉為 RGBA 確保能萃取透明通道
        rgba_frame = img_frame.convert("RGBA")
        bg = Image.new("RGB", rgba_frame.size, (255, 255, 255))
        bg.paste(rgba_frame, mask=rgba_frame.split()[3])
        return bg
    return img_frame.convert("RGB")

def process_and_compress_image(img_bytes, target_size_mb, crop_box, resize_ratio):
    """核心壓縮引擎：接收已下載的圖片位元組，進行裁切、縮放與壓縮"""
    try:
        img = Image.open(BytesIO(img_bytes))
        
        # 1. 提取所有影格，同時進行「裁切」與「縮放」
        frames = []
        durations = [] 
        
        # 解析裁切框座標 (left, top, right, bottom)
        left, top, right, bottom = crop_box
        
        try:
            while True:
                frame = img.copy()
                
                # --- 執行裁切 (Crop) ---
                if right > left and bottom > top:
                    frame = frame.crop((left, top, right, bottom))
                
                # --- 執行縮放 (Resize) ---
                if resize_ratio < 100:
                    new_w = max(int(frame.width * (resize_ratio / 100.0)), 1)
                    new_h = max(int(frame.height * (resize_ratio / 100.0)), 1)
                    # LANCZOS 能提供最平滑的縮放畫質
                    frame = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)

                frames.append(frame)
                
                # 防止卡死：強制設定最低時間為 20 毫秒
                raw_duration = img.info.get('duration', 100)
                durations.append(max(raw_duration, 20)) 
                
                img.seek(len(frames))
        except EOFError:
            pass
            
        st.write(f"⚙️ 啟動智慧壓縮引擎 (目標: {target_size_mb}MB 以下)...")

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
            
            # === 修復黑白與鋸齒問題 ===
            # 取消強制單一色板，改讓每一幀依據自身畫面計算專屬色板 (Adaptive)。
            # 同時不再強制 dither=0，恢復預設的平滑抖動，大幅消除鋸齒感！
            processed_frames = []
            for f in current_frames:
                f_rgb = safe_convert_to_rgb(f)
                processed_frames.append(f_rgb.convert("P", palette=Image.ADAPTIVE, colors=colors))
            # ==========================

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
                    st.warning(f"⚠️ 已達極限壓縮，檔案仍略大於 {target_size_mb}MB。")

        return output_io.getvalue(), final_size_mb
        
    except Exception as e:
        return None, str(e)

# === Streamlit 網頁介面 ===
st.set_page_config(page_title="GIF 專業壓縮神器", page_icon="🪄", layout="wide")
st.title("🪄 動圖專業壓縮神器 (WebP 轉 GIF)")
st.markdown("完美保護你的電子報排版！支援滑鼠直覺裁切、縮放與自動智能壓縮。")

url_input = st.text_input("請貼上 GIF 或 WebP 的網址：")

if url_input:
    try:
        # 當使用者輸入網址後，立刻下載圖片並顯示裁切工具
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url_input, headers=headers)
        response.raise_for_status()
        
        img_bytes = response.content
        preview_img = Image.open(BytesIO(img_bytes))
        original_size_mb = len(img_bytes) / (1024 * 1024)
        
        st.success(f"📥 成功讀取！原始大小: `{original_size_mb:.2f} MB`")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("### ✂️ 步驟一：滑鼠框選裁切範圍")
            st.write("請直接在下方圖片上拖曳，框出你想保留的區域：")
            
            # 取得第一幀作為裁切預覽底圖
            first_frame_for_crop = safe_convert_to_rgb(preview_img.copy())
            
            # 使用 st_cropper 讓使用者視覺化裁切
            cropped_rect = st_cropper(
                first_frame_for_crop, 
                realtime_update=True, 
                box_color='#007BFF',
                aspect_ratio=None,
                return_type='box'
            )
            
            # 轉換為 Pillow 需要的座標格式
            crop_box = (
                cropped_rect['left'],
                cropped_rect['top'],
                cropped_rect['left'] + cropped_rect['width'],
                cropped_rect['top'] + cropped_rect['height']
            )

        with col2:
            st.markdown("### 🗜️ 步驟二：壓縮設定")
            resize_ratio = st.slider("📏 畫面等比例縮放 (%)", min_value=10, max_value=100, value=100, help="縮小整體畫面能非常有效地減少檔案大小喔！")
            
            target_size_option = st.radio(
                "🎯 目標壓縮大小：",
                options=[10, 5],
                format_func=lambda x: f"小於 {x} MB",
                horizontal=True 
            )
            
            st.markdown("---")
            
            if st.button("🚀 開始處理並產生 GIF", use_container_width=True):
                with st.spinner(f"正在執行智能壓縮，請稍候..."):
                    final_gif_bytes, final_size_or_error = process_and_compress_image(
                        img_bytes, target_size_option, crop_box, resize_ratio
                    )
                    
                    if final_gif_bytes:
                        st.success(f"🎉 處理完成！最終大小: {final_size_or_error:.2f} MB")
                        st.image(final_gif_bytes, caption="裁切與壓縮後的 GIF 預覽")
                        
                        st.download_button(
                            label="⬇️ 下載最終優化版 GIF",
                            data=final_gif_bytes,
                            file_name="newsletter_optimized.gif",
                            mime="image/gif",
                            use_container_width=True
                        )
                    else:
                        st.error(f"處理失敗: {final_size_or_error}")
                        
    except Exception as e:
        st.error(f"無法載入圖片，請確認網址是否正確。錯誤訊息：{e}")