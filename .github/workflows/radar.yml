name: Job Radar

on:
  # запуск за розкладом (час у UTC; Мадрид = UTC+1 взимку)
  # 07:00, 12:00 і 17:00 UTC  ≈  08:00, 13:00 і 18:00 за Мадридом
  schedule:
    - cron: "0 7,12,17 * * *"
  # кнопка ручного запуску (щоб перевірити одразу)
  workflow_dispatch:

permissions:
  contents: write   # щоб бот міг зберігати список уже надісланих вакансій

jobs:
  radar:
    runs-on: ubuntu-latest
    steps:
      - name: Забрати код
        uses: actions/checkout@v4

      - name: Поставити Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Запустити радар
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python job_radar.py

      - name: Зберегти список надісланих вакансій
        run: |
          if [ -n "$(git status --porcelain seen.json)" ]; then
            git config user.name "job-radar"
            git config user.email "actions@users.noreply.github.com"
            git add seen.json
            git commit -m "update seen jobs"
            git push
          else
            echo "нічого нового зберігати"
          fi
