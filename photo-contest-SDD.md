# 攝影比賽線上評分系統 — SDD(需求驅動開發文件)

版本:v1.0
文件用途:提供給 Claude Code(或其他工程師/AI開發工具)作為實作依據
部署目標:自有 VPS,單次比賽使用,比賽結束後可保留或關閉

---

## 1. 專案背景與目標

主辦單位已收集攝影比賽投稿照片,分為兩組:

| 組別 | 代碼 | 參賽件數 |
|---|---|---|
| 同仁組 | `staff` | 29 |
| 社會組 | `public` | 23 |

需要建置一套**線上評分系統**,讓 5 位評審依主辦單位訂定的評分標準,分別對兩組照片評分,系統自動計算加權總分並產生排名。

**核心目標:**
1. 評分資料完全存放在主辦單位自有的伺服器/資料庫,不依賴第三方平台的暫存機制
2. 評審之間彼此匿名(看不到誰是誰),投稿者對評審也匿名(評審只看到編號)
3. 每位評審有獨立的登入方式,不會在介面上看到其他評審的姓名或帳號
4. 同仁組與社會組完全分開評分、分開計算排名
5. 系統操作對非技術背景的評審友善(手機、平板、電腦皆可使用)

---

## 2. 使用者角色與情境(User Roles & Stories)

### 2.1 角色定義

| 角色 | 說明 | 人數 |
|---|---|---|
| 主辦方管理員(Admin) | 設定比賽資料、管理評審與照片、查看與匯出成績 | 1(或少數) |
| 評審(Judge) | 依專屬帳號登入,對兩組照片分別評分 | 5 |

### 2.2 使用者情境(User Stories)

- 身為管理員,我要能上傳照片檔案(不是網址)並標記所屬組別與編號,系統自動隱藏投稿者資訊。
- 身為管理員,我要能設定評分項目與各項權重(例如構圖30%、主題40%、創意30%)。
- 身為管理員,我要能為每位評審建立獨立帳號密碼,並取得一組專屬登入連結,方便我私下傳送給對應評審。
- 身為評審,我要能用自己的帳密或專屬連結登入,登入後只看到「我自己」的登入狀態,看不到其他評審是誰。
- 身為評審,我要能切換「同仁組」「社會組」分別評分,並清楚看到自己在該組已評/未評的照片。
- 身為評審,我要能對每張照片依各評分項目給分,系統即時算出加權總分,並儲存我的評分紀錄。
- 身為評審,我要能修改自己已經送出的分數(在成績未封存前)。
- 身為管理員,我要能查看兩組個別的成績總表(每張照片的加權平均分與排名),並匯出 CSV。
- 身為管理員,我要能隨時將整份資料庫備份下載,不擔心資料遺失。

---

## 3. 功能需求(Functional Requirements)

### 3.1 認證與權限

| 需求編號 | 描述 |
|---|---|
| FR-01 | 管理員登入需帳號密碼,密碼以雜湊(如 bcrypt)儲存,不可明文存放 |
| FR-02 | 評審登入支援兩種方式:(a)帳號密碼登入 (b)專屬連結(內含一次性 token)免密碼登入 |
| FR-03 | 評審登入後的畫面**不得**出現其他評審的姓名、帳號、或任何可識別身分的清單 |
| FR-04 | 所有需要登入的頁面,未登入時一律導向對應登入畫面,不可繞過 |
| FR-05 | 登入使用伺服器端 session(簽章 cookie),session 需設定合理過期時間(建議 8 小時或比賽期間內免登出) |

### 3.2 後台管理(Admin)

| 需求編號 | 描述 |
|---|---|
| FR-10 | 管理員可新增/編輯/刪除評分項目(名稱、權重) |
| FR-11 | 管理員可新增/編輯/刪除評審(姓名、帳號、密碼),系統自動產生專屬連結 token |
| FR-12 | 管理員可上傳照片檔案(jpg/png/webp),指定組別(同仁組/社會組)與編號,編號同組別內不可重複 |
| FR-13 | 管理員可刪除照片(需二次確認,刪除後連帶清除相關分數紀錄或標記為已刪除) |
| FR-14 | 管理員可依組別查看成績總表(排名、加權平均分、各評審已評分狀態) |
| FR-15 | 管理員可將成績總表匯出為 CSV(依組別分別匯出) |
| FR-16 | 管理員可一鍵下載整份資料庫備份檔 |

### 3.3 評審評分

| 需求編號 | 描述 |
|---|---|
| FR-20 | 評審登入後預設看到組別選單(同仁組/社會組),各組顯示件數 |
| FR-21 | 每組以縮圖列表(contact sheet)呈現所有照片,已評分/未評分需有明顯視覺區別 |
| FR-22 | 點選照片進入評分頁,顯示大圖與各評分項目(含權重顯示),輸入分數(1-10,整數) |
| FR-23 | 系統即時計算並顯示該張照片的加權總分,供評審參考 |
| FR-24 | 評審送出後即儲存,可重新進入該照片修改分數並覆蓋儲存 |
| FR-25 | 評分頁面**不得**顯示投稿者任何識別資訊,只顯示組別+編號 |

### 3.4 成績計算

| 需求編號 | 描述 |
|---|---|
| FR-30 | 單張照片加權總分 = Σ(評審對該項目分數 × 該項目權重) / Σ權重,再對「已評分的評審」取平均 |
| FR-31 | 未被任何評審評分的照片,總表顯示「尚未評分」,不納入排名 |
| FR-32 | 排名依加權平均分數由高到低排序,同分時排名並列(名次不跳號可依需求調整) |

---

## 4. 非功能需求(Non-Functional Requirements)

| 類別 | 需求 |
|---|---|
| 安全性 | 密碼雜湊儲存;所有表單需 CSRF 防護;登入失敗需有基本防暴力破解機制(如短時間內失敗次數限制) |
| 安全性 | 圖片上傳需驗證副檔名與實際檔案類型,限制檔案大小(建議單檔 ≤ 10MB) |
| 隱私 | 資料庫中若記錄投稿者姓名等資訊(供主辦方內部比對用),**評審可存取的任何 API/頁面皆不得回傳該欄位** |
| 可用性 | 介面需支援手機、平板、桌機瀏覽器,不需安裝 App |
| 效能 | 系統預期同時在線人數 ≤ 10 人,無高併發需求,不需特別的效能優化 |
| 資料保存 | 資料庫使用檔案型或伺服器型皆可,但需定期(或提供一鍵)備份機制 |
| 部署 | 需可透過 HTTPS 存取(避免帳密與分數以明文傳輸) |
| 可維運性 | 出錯時記錄伺服器端 log,方便主辦方(或協助的技術人員)排查問題 |

---

## 5. 資料模型(Data Model)

建議使用關聯式資料庫,單次比賽場景下 **SQLite** 已足夠(檔案型資料庫,備份=複製檔案,不需額外安裝資料庫服務);若未來要多場比賽並行或需要更高可靠性,可改用 PostgreSQL,以下設計兩者皆適用。

```
groups
  id            INTEGER PK
  code          TEXT UNIQUE      -- 'staff' / 'public'
  name          TEXT             -- 同仁組 / 社會組

criteria
  id            INTEGER PK
  name          TEXT
  weight        INTEGER          -- 例如 30, 40, 30
  sort_order    INTEGER

photos
  id            INTEGER PK
  group_id      INTEGER FK -> groups.id
  code          TEXT             -- 組內編號,如 '001'
  image_path    TEXT             -- 伺服器內儲存路徑
  submitter_note TEXT NULL       -- 內部備註,不對評審開放的API回傳
  created_at    DATETIME
  UNIQUE(group_id, code)

judges
  id             INTEGER PK
  name           TEXT
  username       TEXT UNIQUE
  password_hash  TEXT
  token          TEXT UNIQUE     -- 專屬連結用的亂數字串
  created_at     DATETIME

scores
  id            INTEGER PK
  judge_id      INTEGER FK -> judges.id
  photo_id      INTEGER FK -> photos.id
  criteria_json TEXT             -- {"構圖": 8, "主題契合度": 7, "創意": 9}
  weighted_total REAL            -- 後端計算後存入,避免每次查詢重算
  updated_at    DATETIME
  UNIQUE(judge_id, photo_id)

admin_users
  id            INTEGER PK
  username      TEXT UNIQUE
  password_hash TEXT
```

> 備註:`criteria_json` 以 JSON 儲存單一評審對單張照片各項目的分數,避免評分項目調整時需要改資料表結構;若偏好嚴格正規化,也可拆成獨立的 `score_details` 表(judge_id, photo_id, criterion_id, score)。單次比賽規模小,JSON 欄位已足夠且開發較快。

---

## 6. 系統架構與技術選型建議

| 項目 | 建議 | 理由 |
|---|---|---|
| 後端框架 | **FastAPI**(或 Flask) | Python 生態成熟,Claude Code 熟悉度高,文件完整 |
| 資料庫 | **SQLite** | 單檔案、免額外安裝、備份=複製檔案,符合單次比賽規模 |
| ORM | SQLAlchemy(可選) | 加速開發,但小型專案也可用純 SQL |
| 前端 | 伺服器端渲染(Jinja2 templates)+ 少量原生 JS | 不需要複雜前端框架,降低部署與維護成本 |
| 圖片儲存 | 伺服器本機磁碟(如 `/var/www/contest/uploads/`) | 免第三方依賴;VPS 有磁碟空間即可 |
| Session | 簽章 cookie(如 `itsdangerous` 或框架內建 session) | 免額外資料庫查詢即可驗證登入 |
| 反向代理 / HTTPS | **Caddy**(自動申請 Let's Encrypt 憑證,設定最簡單)或 Nginx + Certbot | Caddy 設定檔僅需幾行,適合單次快速部署 |
| 執行方式 | Gunicorn/Uvicorn + systemd 常駐服務,或 Docker Compose | 依你 VPS 的既有習慣選擇 |

### 架構示意

```
[使用者瀏覽器] --HTTPS--> [Caddy 反向代理] --> [Uvicorn/Gunicorn 執行 FastAPI App] --> [SQLite 檔案 + uploads/ 圖片目錄]
```

---

## 7. API 端點設計(草案)

### 管理端(需 Admin session)
```
POST   /admin/login
POST   /admin/logout
GET    /admin/criteria
POST   /admin/criteria
DELETE /admin/criteria/{id}
GET    /admin/judges
POST   /admin/judges              # 回傳含專屬連結 token
DELETE /admin/judges/{id}
GET    /admin/photos?group=staff
POST   /admin/photos              # multipart/form-data 上傳圖片
DELETE /admin/photos/{id}
GET    /admin/results?group=staff
GET    /admin/results/export.csv?group=staff
GET    /admin/backup.db           # 下載資料庫備份
```

### 評審端(需 Judge session)
```
POST   /judge/login                       # 帳密登入
GET    /judge/link/{token}                # 專屬連結登入
POST   /judge/logout
GET    /judge/groups                      # 取得兩組件數
GET    /judge/photos?group=staff          # 該組照片列表(含自己是否已評分)
GET    /judge/photos/{id}                 # 單張照片詳情(供評分頁使用)
POST   /judge/photos/{id}/score           # 送出/更新分數
```

> 所有評審端 API 回傳的照片資料**僅包含**:編號、組別、圖片路徑。不得包含 `submitter_note` 或其他任何投稿者資訊欄位。

---

## 8. 安全性設計重點

1. **密碼儲存**:使用 `bcrypt` 或 `argon2` 雜湊,不存明文,不用可逆加密。
2. **CSRF 防護**:所有會修改資料的表單/請求需帶 CSRF token 驗證。
3. **Session 隔離**:Admin session 與 Judge session 使用不同的 cookie 名稱與權限範圍,避免越權存取。
4. **速率限制**:登入端點建議加上簡易的失敗次數限制(例如同一 IP 5 分鐘內失敗 5 次即鎖定 1 分鐘),防止暴力猜密碼。
5. **上傳檔案驗證**:檢查副檔名與 MIME type,重新命名儲存(避免用原始檔名,防止路徑注入),限制檔案大小。
6. **HTTPS 強制**:所有登入與評分頁面必須經由 HTTPS,Caddy 預設會自動處理憑證與轉址。
7. **匿名性保證**:資料庫層面即使儲存投稿者資訊,也要在程式層面明確排除在所有評審可存取的回傳資料之外(建議寫自動化測試驗證這點)。

---

## 9. 部署方案(Linode / Akamai Cloud Computing)

主辦方使用的 VPS 為 **Linode(現屬 Akamai Cloud Computing,控制台仍稱 Cloud Manager)**。以下步驟針對 Linode 的產品介面撰寫。

### 9.1 前置準備(Linode Cloud Manager)

1. **建立/確認 Compute Instance(Linode)**:若尚未有專用主機,可在 Cloud Manager 建立一台最小規格即可(Nanode 1GB 或 Linode 2GB 皆足夠應付 5 位評審 + 52 張照片的流量)。作業系統建議選 **Ubuntu 24.04 LTS**(套件與文件最完整,Claude Code 也最熟悉)。
2. **設定 Cloud Firewall**:在 Cloud Manager 建立一個 Cloud Firewall,規則只開放:
   - Inbound: TCP 22(SSH,建議限制來源 IP 為你自己的固定IP或辦公室IP)、TCP 80、TCP 443
   - 其餘 inbound 一律拒絕
   建立好後,將此 Firewall 指派給你的 Linode(可在建立時指定,或之後於 Linode 的 Network 頁籤掛上去)。
3. **DNS 設定**:若你有自己的網域(例如比賽單位官網的網域),用 Linode 內建的 **DNS Manager**(免費)或你網域商的 DNS 後台,新增一筆 A 記錄,將子網域(如 `contest.yourclub.org`)指向這台 Linode 的公開 IPv4。若沒有網域,也可以先直接用 Linode 配發的 IP 存取(僅比賽短期使用時可接受,但 HTTPS 憑證會較難自動簽發,建議還是申請一個免費/低價子網域)。
4. **開啟 Linode Backups 附加服務(選用但建議)**:Cloud Manager 中可為此 Linode 加開官方 Backups 服務(约 $2/月),對整台主機做每日快照,作為系統層級的額外備份保險,和應用層的 SQLite 備份互為雙重保障。

### 9.2 主機環境設定(SSH 進入後)

```bash
# 更新系統、安裝 Python 環境
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip git

# 建立應用程式目錄與虛擬環境
sudo mkdir -p /opt/photo-contest
cd /opt/photo-contest
python3.12 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn[standard] sqlalchemy bcrypt python-multipart jinja2
```

### 9.3 常駐執行(systemd)

建立 `/etc/systemd/system/photo-contest.service`,內容參考:

```ini
[Unit]
Description=Photo Contest Scoring App
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/photo-contest
ExecStart=/opt/photo-contest/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now photo-contest
```

### 9.4 反向代理與 HTTPS(Caddy)

```bash
# 安裝 Caddy(Ubuntu 官方套件庫)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

編輯 `/etc/caddy/Caddyfile`:

```
contest.yourclub.org {
    reverse_proxy 127.0.0.1:8000
}
```

```bash
sudo systemctl reload caddy
```

Caddy 會自動向 Let's Encrypt 申請憑證並處理 HTTPS,不需要額外跑 certbot。前提是第 9.1 步驟的 DNS 與 Cloud Firewall(80/443)已設定正確,否則憑證簽發會失敗。

### 9.5 備份(應用層 + Linode 系統層雙重保險)

```bash
# 每日備份 SQLite 與圖片目錄,加上時間戳記
sudo crontab -e
# 新增一行:
0 2 * * * tar -czf /opt/backups/contest-$(date +\%F).tar.gz /opt/photo-contest/data.db /opt/photo-contest/uploads
```

再搭配 9.1 提到的 Linode Backups 服務(整機每日快照),即使應用層備份出問題,系統層仍有一份可還原。

### 9.6 Docker 化(可選)

若你偏好用 Docker 管理,Linode 的 Ubuntu 映像可直接 `apt install docker.io docker-compose-plugin`,將上述 app 打包為容器,`docker-compose.yml` 內把 `data.db` 與 `uploads/` 目錄掛載為 volume,並用 `caddy-docker-proxy` 或另跑一個 Caddy 容器處理 HTTPS。適合你之後想把「同一台 Linode」拿來跑多個服務時做隔離。

---

## 10. 驗收標準(Acceptance Criteria)

- [ ] 管理員可完整走完:登入 → 設定評分項目 → 新增5位評審(取得專屬連結)→ 上傳同仁組29張、社會組23張照片
- [ ] 每位評審用專屬連結登入後,畫面上找不到任何其他評審的姓名或帳號痕跡(檢查 HTML 原始碼與 API 回傳內容)
- [ ] 評審可分別對兩組照片評分,分數即時試算加權總分並可成功儲存
- [ ] 評審重新登入後,先前已評分的照片正確顯示已評分狀態與原分數,可修改並覆蓋
- [ ] 管理員可查看兩組個別的成績總表與排名,並成功匯出 CSV,數字與手動試算相符
- [ ] 關閉/重啟伺服器後,資料庫與已上傳照片不遺失
- [ ] 未登入狀態下,直接嘗試存取評分或後台 API,皆被正確導向登入或回傳 401/403
- [ ] 管理員可下載完整資料庫備份檔案

---

## 11. 建議開發順序(給 Claude Code 的任務拆解)

1. 專案骨架:FastAPI + SQLite + SQLAlchemy 初始化,建立資料表
2. Admin 認證(登入/登出/session)
3. Admin CRUD:評分項目、評審(含 token 產生)、照片上傳
4. Judge 認證(帳密登入 + 專屬連結登入)
5. Judge 端:組別列表、照片列表(含已評分狀態)、評分頁與送出邏輯
6. 成績計算與成績總表頁面、CSV 匯出
7. 安全性補強:CSRF、速率限制、上傳檔案驗證、HTTPS 設定確認
8. 部署腳本/說明:systemd service 檔、Caddyfile、備份 cron job
9. 端對端測試:比照第10節驗收標準逐項驗證

---

## 12. 待確認事項(Open Questions)

- 資料庫是否需要記錄投稿者真實姓名以供主辦方核對得獎名單?若需要,建議獨立存放於管理員專用資料表,並在程式層面嚴格阻擋評審端 API 存取。
- 評分是否需要「截止時間」自動鎖定,截止後評審不能再修改分數?(目前規格未包含,如需要可加一個 `contest_settings.locked` 欄位控制)
- 是否需要「評語」欄位(文字備註),供評審留下質化意見?(目前規格僅涵蓋數值評分)
- VPS 的網域名稱與現有防火牆/既有服務配置,需要你提供實際資訊才能完成部署腳本細節

---
