# Diplom Ticket Automation

Инструментарий для автоматизации жизненного цикла заявок в отделе инфотелекоммуникаций ХИИК СибГУТИ.

## Запуск через Docker

1. Скопируйте пример переменных окружения:

```bash
cp .env.example .env
```

2. Запустите сервисы:

```bash
docker-compose up --build
```

3. Проверьте состояние API:

- Health check: [http://localhost:8000/health](http://localhost:8000/health)
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

## Переменные окружения

- `DATABASE_URL` - строка подключения к PostgreSQL
- `REDIS_URL` - URL подключения к Redis
- `SECRET_KEY` - ключ подписи JWT
- `ALGORITHM` - алгоритм подписи JWT (по умолчанию `HS256`)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - срок жизни access token в минутах