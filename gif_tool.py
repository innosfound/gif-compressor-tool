import streamlit as st
import requests
from io import BytesIO
from PIL import Image

def process_and_compress_image(url, target_size_mb):
    """
    流暢度優先：精準計算每幀時間，優先使用色彩壓縮，最後才使用抽幀。
    結合「超級色板」與「開啟像素抖動 (Dithering)」，完美消除色塊與斷層！
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
        
        # 2. 提取所有影格
        frames = []
        durations = [] 
        try:
            while True:
                frames.append(img.copy().convert('RGBA'))
                durations.append(img.info.get('duration', 100)) 
                img.seek(len(frames))
        except EOFError:
            pass
        
        if original_size_mb <= target_size_mb and img.format == 'GIF':
            return response.content, original_size_mb

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
            
            # === 【終極色彩修復：拼接超級色板 + 開啟像素抖動】 ===
            processed_frames = []
            
            def safe_convert_to_rgb(img_frame):
                if img_frame.mode == 'RGBA':
                    bg = Image.new("RGB", img_frame.size, (255, 255, 255))
                    bg.paste(img_frame, mask=img_frame.split()[3])
                    return bg
                return img_frame.convert("RGB")

            # 抓取三個最具代表性的時間點
            frame_count = len(current_frames)
            img_start = safe_convert_to_rgb(current_frames[0])
            img_mid = safe_convert_to_rgb(current_frames[frame_count // 2])
            img_end = safe_convert_to_rgb(current_frames[-1])
            
            # 建立三倍大圖
            w, h = img_start.size
            collage = Image.new("RGB", (w * 3, h))
            collage.paste(img_start, (0, 0))
            collage.paste(img_mid, (w, 0))
            collage.paste(img_end, (w * 2, 0))
            
            # 產生超級色板
            super_palette_img = collage.convert("P", palette=Image.ADAPTIVE, colors=colors)
            
            # 強制所有影格對齊超級色板，【並重新開啟抖動 (dither=1)】來拯救漸層！
            for f in current_frames:
                f_rgb = safe_convert_to_rgb(f)
                # 修改這裡：把 dither=0 改成 dither=1
                processed_frames.append(f_rgb.quantize(palette=super_palette_img, dither=1))
            # ==============================================

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
                st.write(f"⏳ 嘗試策略 `{step_name}`... 大小 {current_size_mb:.2f} MB (仍過大)")
                
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
st.markdown("""
這個工具會使用 **Drop Frames (移除偶數幀)** 與 **Color Reduction (減少色彩)** 的技術來壓縮檔案。
**優點：** 絕對不會改變圖片的長寬比例，完美保護你的電子報排版！
""")

url_input = st.text_input("請貼上 GIF 或 WebP 的網址：")

target_size_option = st.radio(
    "📏 請選擇目標壓縮大小：",
    options=[10, 5],
    format_func=lambda x: f"小於 {x} MB",
    horizontal=True 
)

if st.button("開始處理"):
    if url_input:
        with st.spinner(f"正在執行抽幀與色彩壓縮 (目標：{target_size_option}MB)，請稍候..."):
            final_gif_bytes, final_size_or_error = process_and_compress_image(url_input, target_size_option)
            
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