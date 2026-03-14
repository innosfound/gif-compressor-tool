import streamlit as st
import requests
from io import BytesIO
from PIL import Image

# 設定最大檔案大小為 10MB (10 * 1024 * 1024 bytes)
MAX_FILE_SIZE = 10 * 1024 * 1024

def process_and_compress_image(url):
    """
    流暢度優先 ＋ 解決閃爍 Bug：統一調色盤並去除透明背景干擾。
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
        
        # 2. 提取所有影格，並墊上「純白背景」以防止透明度導致的閃爍
        frames = []
        durations = []
        try:
            while True:
                # 將每一格轉為 RGBA 提取出來
                f_rgba = img.copy().convert('RGBA')
                
                # 建立一張純白色的底圖
                white_bg = Image.new("RGB", f_rgba.size, (255, 255, 255))
                # 將原圖貼在白底上 (利用自身的 alpha 色版當作遮罩)
                white_bg.paste(f_rgba, mask=f_rgba.split()[3])
                
                frames.append(white_bg)
                durations.append(img.info.get('duration', 100)) 
                img.seek(len(frames))
        except EOFError:
            pass
        
        if original_size_mb <= 10 and img.format == 'GIF':
            return response.content, original_size_mb

        st.write("⚙️ 啟動「防閃爍」智慧壓縮引擎...")

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
            
            # 💡 核心修復：統一調色盤
            # 先將第一格轉換為指定色彩數，並取得它的調色盤
            first_frame_quantized = current_frames[0].quantize(colors=colors, method=Image.Quantize.MAXCOVERAGE)
            
            processed_frames = [first_frame_quantized]
            # 強制後續所有的影格，都套用第一格的調色盤！(dither=NONE 避免產生顆粒狀噪點)
            for f in current_frames[1:]:
                processed_frames.append(f.quantize(palette=first_frame_quantized, dither=Image.Dither.NONE))

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
            
            if current_size_mb <= 10:
                output_io = temp_io
                final_size_mb = current_size_mb
                st.write(f"✅ 成功命中目標！使用策略：`{step_name}`")
                break
            else:
                st.write(f"⏳ 嘗試策略 `{step_name}`... 大小 {current_size_mb:.2f} MB")
                
                if step == len(strategies) - 1:
                    output_io = temp_io
                    final_size_mb = current_size_mb
                    st.warning("⚠️ 已經使用最高強度壓縮，但檔案可能仍略大於 10MB。")

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

if st.button("開始處理"):
    if url_input:
        with st.spinner("正在執行抽幀與色彩壓縮，請稍候..."):
            final_gif_bytes, final_size_or_error = process_and_compress_image(url_input)
            
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
