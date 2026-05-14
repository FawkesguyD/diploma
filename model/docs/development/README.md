# Разработка

Этот раздел отвечает на практические вопросы разработки.

## Страницы

- [Локальный запуск](local-setup.md) — как запустить API, UI, БД и тесты.
- [Пайплайн обучения](training-pipeline.md) — как устроено обучение legacy и Russia 2021.
- [Добавление новых признаков](adding-new-features.md) — как добавлять признаки без поломки inference.

## Правило перед изменениями ML

Перед изменением признаков проверьте:

- [model-inputs.md](../reference/model-inputs.md)
- [artifacts.md](../reference/artifacts.md)
- [known-issues.md](../reference/known-issues.md)

Новый признак должен быть добавлен централизованно в schema/preprocessing и пройти одинаковый путь train и inference.
