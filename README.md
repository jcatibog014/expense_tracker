# Ang Gastos!

**Ang Gastos!** is a money notebook. You write down your income and your spending. The app adds them up for every month, and shows you charts.

"Gastos" means "spending" in Filipino.

## Screenshots

| Screen | Picture |
|---|---|
| **Log in.** Log in with your name and password. Or press "Try the demo". | ![The login page](docs/screenshots/login.png) |
| **Dashboard.** One month at a glance: money in, money out, what is left, and the money in your wallets. Small arrows show the change since last month. A bar for each category shows where your money goes. A line shows your spending day by day, next to last month. Columns show the last 12 months. | ![The dashboard](docs/screenshots/dashboard.png) |
| **Dark mode.** Press the moon button. The page turns dark. | ![The dashboard in dark mode](docs/screenshots/dashboard-dark.png) |
| **Phone.** The app works on small screens too. | ![The dashboard on a phone](docs/screenshots/phone.png) |
| **Transactions.** All your income and spending for one month. Use the arrows for other months. Search and filter by type, category or wallet. | ![The transactions list](docs/screenshots/transactions.png) |
| **Add a transaction.** Choose Spending, Income or Transfer. Type the amount, the date, the wallet and the category. | ![The form for a new transaction](docs/screenshots/add-transaction.png) |
| **Budgets.** Set a limit for a category, like ₱3,500 for Food. The bar turns yellow at 80% and red when you go over. "Copy September's budgets" fills a new month for you. | ![The budgets page](docs/screenshots/budgets.png) |
| **Reports.** One year at a time. A table for every month, and a table for every category and month: darker boxes mean more money. You also see your biggest spending. | ![The reports page](docs/screenshots/reports.png) |
| **Repeating.** Salary, rent, internet... Write them once. The app adds them every month on their day. | ![The repeating transactions page](docs/screenshots/repeating.png) |
| **Wallets.** Where is your money? Cash, GCash, the bank. You see how much is in each one. | ![The wallets page](docs/screenshots/wallets.png) |
| **Ikapu.** 10% of every income is set aside for the Lord, in your Ikapu wallet. You see what you set aside, what you gave, and what is waiting. "Give ikapu" writes it down for you. | ![The ikapu page](docs/screenshots/ikapu.png) |
| **Settings.** Things you set up once: Ikapu, Categories, Repeating, CSV files, and your password. | ![The settings page](docs/screenshots/settings.png) |
| **Categories.** Food, Rent, Salary... Each one has a colour. You can add your own. | ![The categories page](docs/screenshots/categories.png) |
| **CSV files.** Upload a table from Excel or Google Sheets. First you see a check: good rows, rows with problems, new names, and rows you already have. Then you press "Add the transactions". | ![The CSV check page](docs/screenshots/import.png) |
| **Transactions on a phone, dark mode.** | ![The transactions list on a phone in dark mode](docs/screenshots/transactions-phone.png) |

## What can it do?

- **Log in.** Only you can see your money. After 5 wrong passwords, the login waits 15 minutes.
- **Try the demo.** The demo has 6 months of made-up money. Anyone can use it. It starts fresh every hour.
- **Write down transactions.** Spending, income, or a **transfer** (money from one wallet to another, like an ATM withdrawal). Change or delete them later.
- **Find transactions.** Go month by month. Search a word. Show only one type, category or wallet.
- **Dashboard.** Pick a month. See income (green), spending (red), money left over, and how much of your income you kept. Is it more or less than last month? (For this month, it compares the same days: October 1–28 with September 1–28.)
- **Charts.** Spending by category, spending day by day, and the last 12 months. Press **Show as table** to see the same numbers in a table.
- **Ikapu (tithe).** When you add income, 10% of it moves by itself into your **Ikapu** wallet (it is set aside, like an envelope). When you give at church, press **Give ikapu**: it writes down the giving as spending from the Ikapu wallet. If you change or delete an income, its ikapu changes too. This works for typed income, repeating income and CSV files.
- **Budgets.** A limit for each category, each month. The dashboard shows which budgets are almost used up or over.
- **Reports.** A whole year: totals, the average spending a month, a category-by-month table, and your 5 biggest spendings.
- **Repeating transactions.** For money that comes or goes every month. Choose the day (1 to 31). Day 31 means the last day in short months. If you don't open the app for a while, the missed months are added when you come back. If you delete one of these transactions (you skipped a month), it doesn't come back.
- **Wallets.** Cash, GCash, Bank, or your own. The app adds up the money in each one.
- **Categories.** Use ours or make your own, with a colour.
- **Archive.** A wallet or category with transactions can't be deleted. You can archive it: the old transactions stay, but you can't pick it for new ones.
- **CSV files.** Download your transactions (all, one month, or just what the Transactions page shows) and open them in Excel. Or add many transactions from a CSV file. The columns are: `date, type, amount, wallet, to_wallet, category, note`.
- **Six tabs.** Dashboard, Transactions, Budgets, Reports, Wallets and Settings. Ikapu, Categories, Repeating and CSV files are inside Settings.
- **Light or dark.** Press the moon or sun button.
- **On your phone.** Open the website and choose "Add to Home Screen". It gets its own icon.

## How to run it on your computer

You need Python 3.13.

1. Make a virtual environment and install the parts:

   ```
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```

2. Make the database (only the first time):

   ```
   .venv\Scripts\flask --app gastos init-db
   ```

3. Make your login. The app asks for a password two times:

   ```
   .venv\Scripts\flask --app gastos create-user juan
   ```

4. Start the app:

   ```
   .venv\Scripts\flask --app gastos run --debug --port 5002
   ```

5. Open http://127.0.0.1:5002 in your browser.

Did you forget your password? Run `.venv\Scripts\flask --app gastos set-password juan`.

## How to put it on the internet

The website runs on **Render**. Your data lives in **Neon** (a free PostgreSQL database). We need Neon because Render's free plan forgets its files every time it restarts.

### 1. Make the database on Neon

1. Go to https://neon.tech and make a free account.
2. Make a **new project**. Name: `ang-gastos`. Region: **Singapore** (it is close to the Philippines).
3. Press **Connect**. Turn on **Connection pooling**. Copy the **connection string**. It looks like this:
   `postgresql://neondb_owner:...@ep-...-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
4. This string is a password. Don't put it in GitHub, and don't send it to anyone.

### 2. Make the tables and your login (one time)

Open PowerShell in the project folder. Paste your connection string between the quotes:

```
$env:DATABASE_URL = "postgresql://..."
.venv\Scripts\flask --app gastos init-db
.venv\Scripts\flask --app gastos create-user juan
Remove-Item Env:DATABASE_URL
```

The last line makes your computer use your local database again.

### 3. Make the website on Render

1. Go to https://render.com and log in with GitHub.
2. Choose **New → Blueprint**. Pick the `expense_tracker` repository.
3. Render reads `render.yaml`. It asks for **DATABASE_URL**: paste your Neon connection string.
4. Press **Apply**. Wait for the first deploy (a few minutes).
5. Open https://ang-gastos.onrender.com and log in.

After that, every merge into `main` updates the website by itself. Before it starts, the website runs `flask --app gastos upgrade-db`, which brings the tables up to date (it keeps all your data).

### When a new version changes the database

Sometimes a new version needs new columns in the database (for example, Ikapu). `upgrade-db` adds them and keeps all data. It is safe to run many times. Render runs it by itself, but you can also run it from your computer first:

```
$env:DATABASE_URL = "postgresql://..."
.venv\Scripts\flask --app gastos upgrade-db
Remove-Item Env:DATABASE_URL
```

**Never run `init-db` on the live database.** It deletes everything.

The free website sleeps after 15 quiet minutes. The next visit wakes it up in about 30–50 seconds.

## How to run the tests

```
.venv\Scripts\python -m pytest
```

The tests use a new, empty SQLite file every time. They don't need the internet.

To test with PostgreSQL too, make a **new branch** in Neon (for example `test`) and use its connection string. **Never use your real database here: the tests delete all the tables.**

```
$env:TEST_DATABASE_URL = "postgresql://...test branch..."
.venv\Scripts\python -m pytest
Remove-Item Env:TEST_DATABASE_URL
```

## Tools we use

| Tool | What it is | What it does here |
|---|---|---|
| Python | A programming language | All the app's code |
| Flask | A small web framework for Python | Makes the pages and the login |
| SQL | The language of databases | Saves your money data and adds it up |
| SQLite | A small database in one file | Keeps your data on your computer |
| PostgreSQL | A big database | Keeps your data on the live website |
| Neon | A website that runs PostgreSQL for free | Our database on the internet |
| psycopg | A Python library | Lets Python talk to PostgreSQL |
| Jinja | HTML templates | Puts your data into the pages |
| HTML and CSS | The language of web pages | The look: a notebook with lines |
| JavaScript | A language for web pages | The light/dark button and the charts |
| Chart.js | A JavaScript library for charts | Draws the line and column charts |
| pytest | A test tool for Python | Checks that the code works |
| Playwright | A tool that drives a web browser | Takes the screenshots and makes the app icons |
| gunicorn | A web server for Python | Runs the app on Render |
| Render | A website that runs web apps | Our website on the internet |
| GitHub | A website for code | Keeps the code and its history |
