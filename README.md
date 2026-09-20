# Texas driving practice log

This single-student Flask app allow to track 10 topics with different suggested hours. Enter session durations in whole minutes; the dashboard shows hours, the 30-hour goal, and the 10-hour nighttime goal. Sessions can be edited or deleted, and CSV export includes the student's details and all session fields.

The template's 120-minute daily cap is enforced across sessions, including concurrent writes. Topic targets are suggestions and do not block entry. Day/night classification is entered manually. This tracker does not generate a signed official PDF.

## Deployment

`docker compose up -d --build`

The app uses port 5656. .Database and login: `tx_driving_log`. Credentials and the session secret are in the mode-600 `.env` file, excluded from Git and the image. Existing application databases are unchanged. Tables initialize on startup. Data lives in the existing PostgreSQL volume and survives app rebuilds; keep the PostgreSQL container/volume backed up.

`docker compose ps` checks container health. `docker compose logs --tail=100 app` shows logs. The `/health` endpoint checks database connectivity.

Tests: `docker compose exec -T app python -m unittest discover -s /tmp/tests -v` after copying `tests/` into `/tmp/tests` in the app container. Tests use an isolated in-memory SQLite database; deployment checks should also exercise PostgreSQL.

This deployment has no user accounts and is intended for a trusted private network. Anyone who can reach port 5656 can view and modify the log, including permit and adult license numbers.

Database backup (contains private information):

```sh
docker exec crochetkrush-postgres-1 pg_dump -U crochetkrush -d tx_driving_log -Fc > driving-log.dump
```
