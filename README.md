# 攝影比賽線上評分系統

依照 [photo-contest-SDD.md](./photo-contest-SDD.md) 實作。FastAPI + SQLite + Jinja2,單一 Python 程序即可運行。

## 功能總覽

- **管理後台**:評分項目(名稱/權重)、評審帳號(含免密碼專屬連結)、照片上傳(含作品標題/圖說)、成績總表、CSV 匯出、資料庫備份下載
- **唯讀管理帳號**:可瀏覽所有後台頁面與成績,但無法新增/刪除/修改任何資料,且不會看到評審的專屬登入連結與資料庫備份(見 `scripts/create_admin.py` 的 `--readonly` 參數)
- **評審端**:專屬連結或帳密登入、依組別瀏覽照片(含已評分/未評分狀態與加權分數)、線上評分並即時試算加權總分
- **匿名性**:評審之間互不可見,投稿者資訊(`submitter_note`)不會出現在任何評審可存取的頁面或 API
- **加權計算與破同分**:加權總分 = Σ(項目分數 × 權重) / Σ權重,再對評審取平均;同分時依序比較「≥9 分評審人數」與「單一評審最高分」,大幅降低並列名次機率
- **安全性**:bcrypt 密碼雜湊、CSRF 防護、登入失敗次數限制、圖片上傳格式與大小驗證、admin/judge session 完全隔離

## 目前正式站台

- 網址:https://rate-photo.petertseng.me
- 部署於 Linode(Ubuntu 24.04),與主機上既有的其他網站(Apache 服務)共存,詳見下方「部署到 Linode」章節

## 本機開發

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 建立第一個管理員帳號
python -m scripts.create_admin admin <你的密碼>

# 如需建立唯讀管理帳號(僅能瀏覽,無法新增/刪除/修改):
python -m scripts.create_admin <帳號> <密碼> --readonly

# 啟動開發伺服器(本機 HTTP 測試用,正式環境請勿加這個環境變數)
PHOTO_CONTEST_SECURE_COOKIES=0 uvicorn app.main:app --reload
```

瀏覽 http://127.0.0.1:8000/admin/login 與 http://127.0.0.1:8000/judge/login。

## 執行測試

```bash
pytest tests/ -v
```

測試涵蓋:未登入導向登入頁、評審端不洩漏其他評審身分或投稿者備註、CSRF 防護、加權總分計算、登入失敗次數限制。

## 目錄結構

```
app/
  main.py           # FastAPI app 進入點
  config.py         # 環境變數與設定
  database.py       # SQLAlchemy engine/session
  models.py         # 資料表定義
  auth.py           # session cookie 與 CSRF
  security.py       # 密碼雜湊、rate limiter
  scoring.py        # 加權總分計算
  uploads.py        # 圖片上傳驗證
  routers/
    admin.py        # 管理後台
    judge.py        # 評審端
    media.py        # 需登入才能存取的圖片伺服端點
  templates/         # Jinja2 樣板
  static/style.css
scripts/create_admin.py
deploy/              # 部署用腳本與設定檔
tests/
```

## 部署到 Linode(Akamai Cloud Computing)

以下對應 SDD 第 9 節。

### 1. 前置準備(Linode Cloud Manager,手動操作)

1. 建立 Compute Instance:Ubuntu 24.04 LTS,Nanode 1GB 或 Linode 2GB 即可。
2. 建立 Cloud Firewall:僅開放 inbound TCP 22(SSH,建議限制來源 IP)、80、443,其餘拒絕,並掛載到此 Linode。
3. DNS:若有網域,新增一筆 A 記錄指向此 Linode 的公開 IPv4(例如 `contest.yourclub.org`)。若沒有網域,可先用裸 IP,但 HTTPS 憑證無法自動簽發。
4. (建議)在 Cloud Manager 為此 Linode 開啟官方 Backups 服務,作為系統層級的每日快照備份。

### 2. 上傳程式碼到主機

在本機執行(需已可 SSH 連入該主機):

```bash
ssh <user>@<host> "sudo mkdir -p /opt/photo-contest && sudo chown \$USER:\$USER /opt/photo-contest"
rsync -avz --exclude 'venv/' --exclude 'data.db' --exclude '.secret_key' \
  --exclude 'uploads/' --exclude '__pycache__/' --exclude '.git/' \
  ./ <user>@<host>:/opt/photo-contest/
```

之後要更新程式碼,可直接用 `./deploy/push.sh <user>@<host>`。

### 3. 主機端安裝與啟動

> 若主機上已經在跑其他網站(例如既有的 Apache/Nginx 佔用 80 port),部署腳本分成兩支,先跑核心應用程式,網域準備好後再另外設定反向代理與 HTTPS,避免影響既有站台。

SSH 進入主機後執行:

```bash
cd /opt/photo-contest
sudo ./deploy/setup_server.sh
```

這個腳本會:安裝 Python、建立虛擬環境並安裝套件、安裝並啟用 `photo-contest` systemd 服務(僅監聽 `127.0.0.1:8000`,不動任何既有服務)、設定每日備份 cron。

腳本跑完後,建立第一個管理員帳號:

```bash
cd /opt/photo-contest
sudo -u www-data venv/bin/python -m scripts.create_admin admin <你的密碼>
```

**尚未申請網域時的臨時存取方式**:在 Linode Cloud Firewall 開放 TCP 8000(僅限評審需要用到的期間),並在 `/opt/photo-contest/.env` 加入 `PHOTO_CONTEST_SECURE_COOKIES=0`(範例見 `deploy/env.example`),再 `sudo systemctl restart photo-contest`。之後即可用 `http://<主機IP>:8000/admin/login` 存取。**注意此模式下帳密與分數皆以明文 HTTP 傳輸,僅建議短期過渡使用**,並盡快完成下一步申請網域。

### 3b. 網域申請好之後:設定 HTTPS

DNS A 記錄指向此主機後執行:

```bash
cd /opt/photo-contest
sudo ./deploy/setup_https.sh contest.yourclub.org
```

此腳本會自動偵測環境:
- 若主機上已有 Apache 在跑(本專案目前這台主機的狀況),會新增一個以 `ServerName` 區分的獨立 VirtualHost,並用 `certbot --apache` 申請憑證,不會動到既有站台的設定。
- 若沒有 Apache/Nginx,則安裝 Caddy 並自動處理 HTTPS。

跑完後會自動把 `.env` 內的 `PHOTO_CONTEST_SECURE_COOKIES=0` 移除並重啟服務,之後請記得到 Linode Cloud Firewall 關閉先前臨時開放的 8000 port。

### 4. 常用維運指令

```bash
sudo systemctl status photo-contest      # 檢查應用程式狀態
sudo systemctl restart photo-contest     # 重啟應用程式
sudo journalctl -u photo-contest -f      # 看即時 log
sudo systemctl status caddy              # 檢查反向代理/HTTPS 狀態
```

備份檔案位於 `/opt/backups/contest-YYYY-MM-DD.tar.gz`,每日凌晨 2 點自動產生,保留最近 30 天。也可以直接在後台「成績總表」頁面點擊「下載資料庫備份」隨時下載。

### 5. 環境變數(可選)

| 變數 | 預設值 | 說明 |
|---|---|---|
| `PHOTO_CONTEST_HOME` | 專案根目錄 | 資料庫、上傳目錄、secret key 檔案的預設基準路徑 |
| `PHOTO_CONTEST_DATABASE_URL` | `sqlite:///<HOME>/data.db` | 資料庫連線字串 |
| `PHOTO_CONTEST_UPLOAD_DIR` | `<HOME>/uploads` | 圖片儲存目錄 |
| `PHOTO_CONTEST_SECRET_KEY` | 自動產生並存於 `.secret_key` | session/CSRF 簽章金鑰 |
| `PHOTO_CONTEST_SECURE_COOKIES` | `1` | 設為 `0` 只在本機 HTTP 開發測試使用,正式環境務必維持 `1`(需 HTTPS) |

## 待確認事項(承接 SDD 第 12 節)

- 是否需要記錄投稿者真實姓名並提供管理員核對得獎名單的介面?目前 `photos.submitter_note` 欄位已保留但未開放任何寫入/顯示介面,如需要可再擴充管理後台。
- 是否需要評分截止時間鎖定機制?目前評審在比賽期間可隨時修改分數。
- 是否需要評語(文字備註)欄位?目前僅支援數值評分。
