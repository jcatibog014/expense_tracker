# Ang Gastos!

**Ang Gastos!** is a money notebook. You write down your income and your spending. The app adds them up for every month.

"Gastos" means "spending" in Filipino.

> This app is still growing. It is built in 6 steps (see [docs/PLAN.md](docs/PLAN.md)). Step 1 is done: login, the demo, and the database.

## Screenshots

| Screen | Picture |
|---|---|
| **Log in.** Log in with your name and password. Or press "Try the demo". | ![The login page](docs/screenshots/login.png) |
| **Home.** You see this month: money in, money out, and what is left. You also see your latest entries. | ![The home page](docs/screenshots/dashboard.png) |
| **Dark mode.** Press the moon button. The page turns dark. | ![The home page in dark mode](docs/screenshots/dashboard-dark.png) |
| **Phone.** The app works on small screens too. | ![The home page on a phone](docs/screenshots/phone.png) |

## What can it do?

- **Log in.** Only you can see your money.
- **Try the demo.** The demo has 6 months of made-up money. Anyone can use it. It starts fresh every hour.
- **See this month.** Income (green), spending (red), and money left over.
- **Light or dark.** Press the moon or sun button.

Coming next: add and edit entries, wallets (Cash, GCash, Bank), charts, budgets, repeating bills, and CSV files.

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

## How to run the tests

```
.venv\Scripts\python -m pytest
```

## Tools we use

| Tool | What it is | What it does here |
|---|---|---|
| Python | A programming language | All the app's code |
| Flask | A small web framework for Python | Makes the pages and the login |
| SQL | The language of databases | Saves your money data and adds it up |
| SQLite | A small database in one file | Keeps your data on your computer |
| PostgreSQL (Neon) | A big database on the internet | Will keep your data on the live website |
| Jinja | HTML templates | Puts your data into the pages |
| HTML and CSS | The language of web pages | The look: a notebook with lines |
| JavaScript | A language for web pages | The light/dark button (and charts later) |
| pytest | A test tool for Python | Checks that the code works |
| GitHub | A website for code | Keeps the code and its history |
