import streamlit as st
import requests
from io import BytesIO
from PIL import Image

def process_and_compress_image(url, target_size_mb):
    """
    流暢度優先：精準計算每幀時間，優先使用色彩壓縮，最後才使用抽幀。
    新增了 target_size_mb 參數來動態決定目標壓縮大小。
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
        
        # 2. 提取所有影格，並且「精準記錄每一格的播放時間」
        frames = []
        durations = [] # 新增：用來記錄每格的時間
        try:
            while True:
                frames.append(img.copy().convert('RGBA'))
                # 抓取這格的時間，如果沒有就預設 100 毫秒
                durations.append(img.info.get('duration', 100)) 
                img.seek(len(frames))
        except EOFError:
            pass
        
        # 檢查原始大小是否已經小於我們設定的「目標大小」
        if original_size_mb <= target_size_mb and img.format == 'GIF':
            return response.content, original_size_mb

        st.write(f"⚙️ 啟動「流暢度優先」智慧壓縮引擎 (目標: {target_size_mb}MB 以下)...")

        # 重新排列策略：優先降色彩保流暢，最後才抽幀 (保留原設定)
        strategies = [
            {"drop_frames": False, "colors": 128}, # 策略 1: 全幀 + 128色 
            {"drop_frames": False, "colors": 64},  # 策略 2: 全幀 + 64色
            {"drop_frames": True,  "colors": 256}, # 策略 3: 抽幀 + 256色
            {"drop_frames": True,  "colors": 128}, # 策略 4: 抽幀 + 128色
            {"drop_frames": True,  "colors": 64}   # 策略 5: 抽幀 + 64色
        ]
        
        output_io = BytesIO()
        final_size_mb = 0
        
        for step, strategy in enumerate(strategies):
            temp_io = BytesIO()
            
            if strategy["drop_frames"]:
                current_frames = []
                current_durations = []
                # 重新計算抽幀後的時間，確保播放速度不變
                for i in range(0, len(frames), 2):
                    current_frames.append(frames[i])
                    # 把這格的時間，加上被抽掉的下一格的時間
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
            
            processed_frames = [
                f.convert("P", palette=Image.ADAPTIVE, colors=colors) 
                for f in current_frames
            ]

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
            
            # 檢查當前大小是否達成「目標大小」
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

# --- 新增的選擇按鈕區塊 ---
target_size_option = st.radio(
    "📏 請選擇目標壓縮大小：",
    options=[10, 5],
    format_func=lambda x: f"小於 {x} MB",
    horizontal=True # 讓按鈕橫向排列，節省畫面空間
)
# ------------------------

if st.button("開始處理"):
    if url_input:
        with st.spinner(f"正在執行抽幀與色彩壓縮 (目標：{target_size_option}MB)，請稍候..."):
            # 將選擇的目標大小作為第二個參數傳遞進去
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