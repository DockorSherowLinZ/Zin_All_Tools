# Zin All Tools

Zin All Tools 是一套為 NVIDIA Omniverse 打造的強大擴充套件 (Extensions) 集合，專注於智慧製造、數位孿生、CAD 轉換、物理模擬及自動化組裝等工業應用場景。

## 擴充套件清單 (Extensions)

本專案包含以下多個專業模組，可根據需求在 Omniverse 中啟用：

### 🔧 核心與輔助工具 (Core & Utilities)
* **Zin Core** (`tw.zin.core`): 共用基礎模組，提供統一的 UI 樣式、元件、選單生命週期與非同步任務管理。其他模組均依賴此套件。
* **Tools Box** (`tools_box`): 整合型工具箱，包含 Smart Assets Library, Measure 和 Reference 等綜合工具。
* **Smart Assets Library** (`tw.zin.smart_assets_library`): 專屬資產庫 (Asset Library)，支援本機端 (Local) 與 Nucleus 路徑管理。
* **Zin Web Dashboard** (`tw.zin.web_dashboard`): 提供使用者的 Web 控制面板，支援 WebRTC 影像串流與 REST API 整合。
* **Smart Information** (`tw.zin.smart_information`): 顯示並管理 USD 中特定的自定義資料 (如 `Inventec_Tester` 屬性)，並支援 JSON 導出功能。

* **Smart HUD** (`tw.zin.smart_hud`): 數位孫生工廠的 3D HUD 顯示與動畫週期自動綁定。
* **SmartInfoPanel** (`tw.zin.smart_info_panel`): 顯示選取設備 AIF metadata 的 3D 懸浮資訊面板。

### ⚙️ 組裝與物理模擬 (Assembly & Physics)
* **Smart Assembly** (`tw.zin.smart_assembly`): 組裝順序管理器，具備基於物理的對齊與碰撞偵測功能。
* **Zin Smart Exploded View** (`tw.zin.smart_exploded`): 專業的 USD 物件爆炸圖與合併工具，支援自定義方向與平滑動畫。
* **Smart Physics Setup** (`tw.zin.smart_physics_setup`): 快速設置物理屬性的便捷工具。
* **Smart Conveyor 控制面板** (`tw.zin.smart_conveyor`): 提供自定義節點與速度，用以控制 PCB 在智慧產線輸送帶上的移動邏輯。

### 📐 測量、轉換與定位 (Measure, Align & CAD)
* **Smart CAD Convert** (`tw.zin.smart_cad_convert`): CAD 轉 USD 流程 (FBX -> flattened USDA -> Recenter -> Instance -> Material) 的可視化介面。
* **SmartAlign** (`tw.zin.smart_align`): 輔助對齊工具。
* **SmartMeasure** (`tw.zin.smart_measure`): 測量輔助工具。
* **SmartReference** (`tw.zin.smart_reference`): 從 BOM 表實現自動化組裝的輔助套件。
* **SmartAssetsBuilder** (`tw.zin.smart_assets_builder`): SimReady 資產建構工具。

## 系統需求
* NVIDIA Omniverse (如 USD Composer, Code 等)
* Omniverse Kit 架構相容版本

## 安裝方式
1. 在 Omniverse 應用程式中開啟 **Window > Extensions**。
2. 點擊齒輪圖示 (Settings) 並將本專案的 `exts` 目錄加入 **Extension Search Paths**，例如 Windows 的 `D:/Inventec/Zin_All_Tools/exts`。
3. 在上方搜尋列搜尋 "Zin" 或特定的套件名稱，並點擊啟用。

> 各模組已在 `extension.toml` 宣告對 `tw.zin.core` 的依賴，Kit 會自動一併載入。

## 開發與測試

執行完整驗證套件（結構、manifest、依賴、程式碼品質與單元測試）：

```bash
pip install -r requirements-dev.txt
pytest
```

若所處環境無法安裝 `pytest`（例如受限的企業 proxy），可使用內建的本機執行器：

```bash
python tools/run_tests.py
```
