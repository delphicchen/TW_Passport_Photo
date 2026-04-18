# 護照照片工具

一個用於將手機照片調整為**中華民國護照照片規格**的桌面工具，以 Python + PySide6 開發，完全在本機運作，不需上傳照片。

## 功能

| 功能 | 說明 |
|------|------|
| 照片調整 | 拖曳移動、滾輪縮放，即時預覽裁切結果 |
| 規格參考線 | 頭頂上下限（綠色區間）、下巴線、垂直中心線 |
| 輪廓參考線 | 臉部橢圓輪廓輔助定位 |
| 自動填補留白 | 上方留白不足時，自動填補含細微雜訊的白色背景 |
| AI 痕跡偵測 | 掃描 EXIF metadata，顯示是否有 AI 工具編輯痕跡 |
| Gemini 浮水印移除 | 移除 Gemini 可見 Logo 浮水印（僅限可見浮水印）|
| 4×6 排版列印 | 橫式相紙，4 欄 × 2 列共 8 張，支援儲存與列印 |

## 護照照片規格（中華民國）

| 項目 | 規格 |
|------|------|
| 尺寸 | 35 × 45 mm |
| 臉部高度（下巴至頭頂） | 32–36 mm |
| 背景 | 白色或接近白色 |
| 解析度 | 600 DPI |
| 輸出像素 | 827 × 1063 px |

## 安裝(也可以由下方release 直接下載打包好的執行檔)

```bash
# 建議使用虛擬環境
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## 執行

```bash
python main.py
```

## 操作方式

1. 點擊「📂 載入照片」選擇手機拍攝的照片
2. 用**滾輪**縮放、**拖曳**移動，讓臉部對齊參考線
   - 頭頂落入**綠色區間**內
   - 下巴對齊**下巴線**
3. 右側預覽確認裁切結果
4. 若照片上方留白不足（頭頂太靠近照片邊緣），繼續向下拖曳即可；工具會自動採樣照片頂端顏色，填補無縫的背景（含細微雜訊，避免突兀色塊）
5. 點擊「💾 儲存照片」輸出 827×1063 px、600 DPI 的成品

## 關於 Gemini 浮水印移除

本工具僅移除 Gemini 加在圖片上的**可見 Logo 浮水印**。

- SynthID 隱形浮水印**無法**透過本工具移除
- Gemini logo mask 資料於**第一次使用時**自動從 [GeminiWatermarkTool](https://github.com/allenk/GeminiWatermarkTool)（MIT 授權）下載，不隨本專案散布，以避免散布 Google 商標資產

## 免責聲明

本工具供**個人合法持有的照片**使用，不得用於：
- 移除他人作品上的浮水印
- 規避版權保護措施
- 偽造任何官方文件

使用者需自行確認所提交的護照照片符合當地主管機關的規定。

## 相依套件

- [PySide6](https://doc.qt.io/qtforpython/) — LGPL v3
- [Pillow](https://python-pillow.org/) — MIT/HPND
- [NumPy](https://numpy.org/) — BSD

## 授權

MIT License + 非商業附加條款 — 詳見 [LICENSE](LICENSE)

個人、學術、非營利用途免費使用；**商業用途需取得作者授權**。
