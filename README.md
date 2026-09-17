# bdapps Revenue Agent (Python)

প্রতিদিন প্রতিটা bdapps developer account-এ লগইন করে **চলতি মাসের ১ তারিখ থেকে
গতকাল পর্যন্ত** app-ভিত্তিক revenue বের করে, revenue > 0 এমন app গুলো ফিল্টার
করে, আর সব account একসাথে একটা Telegram রিপোর্টে পাঠায়।

## এটা কেন আছে, PHP bot থাকতেও

এই একই রিপোর্টিং, বাংলায় বললে, আগে থেকেই **`../bdapps-revenue-bot`**
(PHP, cPanel-এর জন্য বানানো) প্রজেক্টে আছে — এবং সেটা মাস-ভিত্তিক subscriber/
renewal/unsubscribe সহ আরও রিচ রিপোর্ট দেয়। এই Python প্রজেক্টটা তার বদলি না,
পাশাপাশি একটা সহজ বিকল্প: শুধু app-ভিত্তিক revenue (filter → transform →
Telegram) — যেভাবে মূলত চাওয়া হয়েছিল সেভাবেই।

লগইন আর report-parsing অংশটা **PHP bot-এর প্রমাণিত (battle-tested) লজিক থেকে
পোর্ট করা** (`BdappsPortal.php` → `nodes/bdapps.py`), কারণ:

- bdapps-এর revenue-এর কোনো public API নেই।
- আসল login portal হলো `https://user.bdapps.com` (CAS/Spring Security দিয়ে),
  **`developer.bdapps.com` না** — সেই ডোমেইনে শুধু একটা placeholder "It works!"
  পেজ পাওয়া গেছে, আসল পোর্টাল না।
- তাই এখানে **Playwright/headless browser ব্যবহার করা হয়নি** — PHP bot-এর
  মতোই plain HTTP request (Python-এ `requests` লাইব্রেরি) দিয়ে লগইন ও
  report scrape করা হয়, যা cPanel/PythonAnywhere-এর মতো shared hosting-এও
  (যেখানে root access না থাকায় আসল Chromium ইনস্টল করা যায় না) কাজ করার
  সম্ভাবনা অনেক বেশি।

## প্রজেক্ট স্ট্রাকচার

```
bdapps-agent/
├── workflow.py           সব নোড জোড়া দেওয়া entry point (CLI)
├── config.py             .env থেকে multi-account অটো-ডিটেক্ট
├── nodes/
│   ├── bdapps.py         CAS login + daily revenue report scrape (plain HTTP)
│   ├── filter.py         revenue > 0 ফিল্টার
│   ├── transform.py      revenue_bdt, date_range ফিল্ড যোগ
│   ├── telegram.py       রিপোর্ট ফরম্যাট + পাঠানো
│   └── schedule.py       date range হিসাব + (ঐচ্ছিক) নিজস্ব scheduler loop
├── tests/                pytest ইউনিট টেস্ট
├── .github/workflows/    GitHub Actions দিয়ে দৈনিক রান (নিচে দেখুন)
├── .env.example
└── requirements.txt
```

## ১. ইনস্টলেশন (লোকাল, টেস্ট করার জন্য)

```bash
cd bdapps-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`.env.example` কপি করে `.env` বানান, তারপর মান বসান:

```bash
copy .env.example .env
```

## ২. Telegram bot বানানো

1. Telegram-এ **@BotFather** খুলে `/newbot` দিন। যে token দেবে সেটাই `.env`-এর
   `TELEGRAM_TOKEN`।
2. নতুন বটটাকে একটা মেসেজ পাঠান।
3. ব্রাউজারে খুলুন: `https://api.telegram.org/bot<TOKEN>/getUpdates` —
   `"chat":{"id":123456789` — এই সংখ্যাটাই `TELEGRAM_CHAT_ID`।

## ৩. Account যোগ করা

`.env`-এ প্রতিটা account-এর জন্য ৩টা লাইন (NAME ঐচ্ছিক):

```
ACCOUNT_1_USERNAME=user1@example.com
ACCOUNT_1_PASSWORD=pass1
```

নতুন account যোগ করতে `ACCOUNT_4_`, `ACCOUNT_5_` ... দিয়ে একই ২টা লাইন যোগ
করলেই হবে — `config.py` স্বয়ংক্রিয়ভাবে ডিটেক্ট করবে, **কোডে হাত দেওয়া লাগবে
না**। রিপোর্টে account দেখাবে "Acc- username" হিসেবে।

## ৩ক. "NetPay" — কমিশন বাদ দিয়ে হাতে আসা টাকা

bdapps-এর রিপোর্টে যে revenue দেখায় তার পুরোটা হাতে আসে না। `.env`-এ
`REVENUE_SHARE_PERCENT` দিয়ে বলে দিন হাতে কত percent আসে — রিপোর্টের একদম
**শেষে** একটা **NetPay** লাইনে সব account মিলিয়ে ততটুকু দেখাবে:

```
REVENUE_SHARE_PERCENT=40      # ৬০% বাদ, NetPay লাইনে ৪০% দেখাবে
```

রিপোর্টে যেভাবে আসবে:

```
🔹Acc- nafiz01
💰Total: BDT 11,650 (70%)
▫️Quiz Master: BDT 8,450
▫️Islamic Tips: BDT 3,200

🔹Acc- nafiz02
💰Total: BDT 5,100 (30%)
▫️Daily News: BDT 5,100
━━━━━━━━━━━━
🧮All accounts (2/2):
💰Total: BDT 16,750
💵NetPay: BDT 6,700
```

- **বাকি সব লাইনে portal-এর আসল সংখ্যাই থাকে**, যাতে portal-এর সাথে মিলিয়ে
  দেখা যায়; শুধু শেষের NetPay লাইনটা কমিশন বাদ দেওয়া।
- Total-এর পাশের `(৭০%)` মানে ঐ account-টা সব account মিলিয়ে কত অংশ — এটা আসল
  সংখ্যা থেকে হিসাব হয়, `REVENUE_SHARE_PERCENT`-এর সাথে এর সম্পর্ক নেই।
- মান না দিলে (বা `100` দিলে) কোনো NetPay লাইনই আসবে না, আগের মতোই থাকবে।
- একটা account থাকলে "All accounts" ব্লকটা আসে না, তখন NetPay লাইনটা ঐ
  account-এর শেষেই যোগ হয়।
- GitHub Actions-এ চালালে এটাকেও একটা **secret** হিসেবে যোগ করতে হবে (নিচের
  ৫ক দেখুন), নইলে NetPay লাইন আসবে না।

## ৪. লোকালি রান/টেস্ট করা

```bash
# ইউনিট টেস্ট
pytest

# রিপোর্ট বানিয়ে শুধু screen-এ দেখাবে, Telegram-এ পাঠাবে না
python workflow.py --preview

# আসল রিপোর্ট Telegram-এ পাঠাবে (এখনই, একবার)
python workflow.py
```

Login বা scraping ব্যর্থ হলে সেই account-এর জন্য রিপোর্টে ⚠️ দিয়ে error
দেখাবে, বাকি account গুলো ঠিকমতো চলবে, আর রিপোর্ট শেষে অবশ্যই পাঠানো হবে।
`workflow.log` ফাইলে বিস্তারিত লগ থাকবে।

**bdapps পোর্টাল যদি বদলে যায়** (form field/HTML গঠন পরিবর্তন), scraping
ব্যর্থ হলে `debug/` ফোল্ডারে সেই মুহূর্তের page source সেভ হয়ে যাবে
(`debug/<username>_<কারণ>_<timestamp>.html`) — সেটা দেখে `nodes/bdapps.py`-এর
সংশ্লিষ্ট selector/regex ঠিক করা যাবে।

## ৫. Deploy — প্রতিদিন সকাল ৬টায় স্বয়ংক্রিয় চালানো

তিনটা পথ নিচে দেওয়া হলো। **GitHub Actions সুপারিশ করছি** (নিচে কারণসহ),
বাকি দুটোও কাজ করবে।

### ৫ক. GitHub Actions (সুপারিশকৃত)

- সম্পূর্ণ ফ্রি (public বা private দুই repo-তেই দৈনিক এই সাইজের job-এর জন্য)।
- আপনার PC বন্ধ থাকলেও ঠিক সময়ে চলবে (নিজের PC/cPanel/PythonAnywhere-এর
  উল্টো, এখানে internet access-এর কোনো whitelist সমস্যা নেই)।
- Chromium লাগে না যেহেতু plain HTTP — তাই সেটআপ আরও সহজ।

ধাপ:

1. এই `bdapps-agent` ফোল্ডারটা একটা GitHub repo-তে push করুন (আলাদা repo,
   `IELTSCapsule`-এর সাথে মেশাবেন না)।
2. Repo-র **Settings → Secrets and variables → Actions**-এ গিয়ে এগুলো যোগ
   করুন (Secret হিসেবে, প্রতিটা আলাদা):
   `ACCOUNT_1_USERNAME`, `ACCOUNT_1_PASSWORD`,
   `ACCOUNT_2_USERNAME`, `ACCOUNT_2_PASSWORD`,
   `ACCOUNT_3_USERNAME`, `ACCOUNT_3_PASSWORD`,
   `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`,
   `REVENUE_SHARE_PERCENT` (যেমন `40` — ৩ক দেখুন; না দিলে NetPay লাইন আসবে না)।
   নতুন account যোগ করলে `ACCOUNT_4_...` secrets যোগ করুন এবং
   `.github/workflows/daily-report.yml`-এ সেই env লাইনগুলোও যোগ করুন।
3. `.github/workflows/daily-report.yml` ইতিমধ্যে দেওয়া আছে, প্রতিদিন
   `00:00 UTC` (= সকাল ৬টা Asia/Dhaka) চালাবে। সময় বদলাতে চাইলে সেই ফাইলের
   `cron:` লাইন বদলান।
4. Repo-র **Actions** ট্যাবে গিয়ে "BDApps Daily Revenue Report" workflow-টা
   ম্যানুয়ালি একবার **Run workflow** দিয়ে টেস্ট করে নিন।

### ৫খ. নিজের Windows PC (Task Scheduler)

PC প্রতিদিন সকাল ৬টায় চালু/জাগ্রত থাকলে এটাও ভালো কাজ করবে:

1. Task Scheduler খুলুন → **Create Basic Task**।
2. Trigger: Daily, 06:00।
3. Action: Start a program →
   - Program: `N:\WebApp\bdapps-agent\.venv\Scripts\python.exe`
   - Arguments: `workflow.py`
   - Start in: `N:\WebApp\bdapps-agent`

### ৫গ. PythonAnywhere (মূল স্পেক অনুযায়ী)

যেভাবে চেয়েছিলেন সেভাবেও চালানো সম্ভব, কারণ Playwright/Chromium আর লাগছে
না — কিন্তু দুটো ব্যাপার মাথায় রাখবেন:

- **Free/Beginner প্ল্যানে internet access একটা whitelist-এ সীমিত** —
  `user.bdapps.com` সেই তালিকায় না থাকলে request block হয়ে যাবে। পেইড
  প্ল্যানে (Hacker আর তার উপরে) এই সীমাবদ্ধতা নেই।
- ধাপ: Files ট্যাবে প্রজেক্ট আপলোড → Consoles-এ virtualenv বানিয়ে
  `pip install -r requirements.txt` → **Tasks** ট্যাবে দৈনিক scheduled
  task বানিয়ে কমান্ড দিন: `python3.11 /home/<user>/bdapps-agent/workflow.py`
  (সময় UTC-তে দিতে হয়, তাই Asia/Dhaka সকাল ৬টা মানে UTC 00:00)।
- প্রথমবার চালিয়ে Task-এর "Latest log" চেক করুন network access কাজ করছে কি
  না দেখতে; ব্লক হলে GitHub Actions বা নিজের PC-তে সরিয়ে নিন।

## সীমাবদ্ধতা

- এই bot-এর রিপোর্ট শুধু per-app revenue দেখায় (PHP bot-এর মতো subscriber/
  renewal/unsubscribe ব্রেকডাউন এখানে নেই)।
- Telegram রিপোর্টের box-drawing ফরম্যাটটা এই প্রজেক্টে নতুন করে ডিজাইন করা —
  মূল অনুরোধে একটা "exact" template-এর কথা বলা হয়েছিল কিন্তু সেটা মেসেজে
  দেওয়া ছিল না, তাই `nodes/telegram.py`-এর `build_sections()`-এ নিজের মতো
  সাজিয়ে নিতে পারবেন।
- bdapps পোর্টাল ব্যবহারের শর্তাবলি (Terms of Service) নিজের account হলেও
  automated access নিয়ে কী বলে, একবার চেক করে নেওয়া ভালো।
