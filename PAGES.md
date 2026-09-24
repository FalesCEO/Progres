# Деплой на GitHub Pages

Сайт готовий до статичного хостингу. Є два способи публікації.

## Найпростіше: завантажити готові файли

1. Завантажте **лише `index.html`** із кореня цього проєкту в корінь GitHub-репозиторію. CSS, JavaScript, іконка й каталог уже всередині; папка `assets` не потрібна. Такий самий файл містить `fales-pages.zip`.
2. У репозиторії відкрийте **Settings → Pages → Build and deployment → Source → Deploy from a branch**.
3. Виберіть **main**, папку **/ (root)**, натисніть **Save**. GitHub покаже адресу після завершення публікації.

Сайт працює як на `https://USERNAME.github.io/`, так і на `https://USERNAME.github.io/REPOSITORY/`. Усі ресурси інтерфейсу вбудовані в один HTML-файл.

## Автоматичні оновлення через GitHub Actions

Якщо завантажуєте весь вихідний проєкт, включно з прихованою папкою `.github`:

1. Відправте проєкт у гілку `main` GitHub-репозиторію. Не додавайте `.venv`, `.demo-work` чи `dist`.
2. У **Settings → Pages → Source** виберіть **GitHub Actions**.
3. Відкрийте **Actions → Deploy to GitHub Pages → Run workflow**. Наступні зміни в `main` публікуватимуться автоматично.

Workflow збирає лише статичні файли. Для деплою інтерфейсу не потрібні npm, Docker, ngspice, API-ключі чи Python-залежності.

## Як увімкнути реальні симуляції

**GitHub Pages розміщує інтерфейс, але не може запустити на сервері Python/ngspice.** Для генерації нових завдань і Run SPICE потрібен окремий запущений Fales API. Без нього сайт відкривається, показує каталог і форму підключення, а симуляції недоступні. Вигаданих результатів немає.

1. Запустіть бекенд із цього проєкту на сервері, який підтримує Docker, командою `docker compose up --build -d`. Налаштуйте HTTPS для нього.
2. На сервері в `.env` додайте:
   ```dotenv
   FALES_ALLOWED_ORIGINS=https://USERNAME.github.io
   ```
   Тут **немає** `/REPOSITORY/`: CORS використовує origin, а не шлях. Для власного домену вкажіть його origin. Кілька дозволених origin можна перелічити через кому. Перезапустіть контейнер після зміни.
3. Задайте адресу API для всіх відвідувачів:
   - **GitHub Actions:** у **Settings → Secrets and variables → Actions → Variables** створіть змінну `FALES_API_URL` зі значенням `https://YOUR-API-HOST` і повторно запустіть workflow.
   - **Один HTML:** у `index.html` знайдіть `const config =` і змініть значення `"apiOrigin": ""` на `"apiOrigin": "https://YOUR-API-HOST"`, потім завантажте файл у репозиторій.

Адреса має бути HTTPS, без `/api`, логіна, пароля чи ключів. Вона публічна, це не secret. Після налаштування сайт підключається автоматично.

Форма **Simulator connection** дозволяє перевірити інший API лише у вашому браузері; вона не змінює налаштування для інших відвідувачів. Кнопка **Use site default** повертає адресу зі збірки.

## Зібрати самостійно

```sh
python3 -B scripts/build_pages.py
```

Результат — самодостатній `index.html` у корені проєкту та його копія `dist/index.html`. Створити ZIP:

```sh
python3 -B scripts/package_pages.py
```

З адресою вже запущеного API:

```sh
FALES_API_URL=https://YOUR-API-HOST python3 -B scripts/package_pages.py
```

Перегляд статичного сайту локально:

```sh
python3 -m http.server 8001 --directory dist
```

Відкрийте `http://127.0.0.1:8001`. Для підключення локального API додайте `http://127.0.0.1:8001` у `FALES_ALLOWED_ORIGINS` його процесу. На опублікованій HTTPS-сторінці потрібен HTTPS API; локальний HTTP-сервер не підходить для публічних відвідувачів.

Офіційні інструкції GitHub: [джерело публікації](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), [GitHub Actions для Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
