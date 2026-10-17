# OS Insight

OS Insight is a container resource observatory. This initial scaffold includes a
PostgreSQL database and schema; the `web`, `api`, and `worker` directories are
reserved for the application services.

## Start the database

```sh
cp .env.example .env
docker compose up -d
```

PostgreSQL initializes its tables from
`db/init.sql` when its data volume is first created. To stop the database, run
`docker compose down`; its data remains in the named volume.

The `.env.example` password is for local development only. Change it before
using the database in a shared or deployed environment.
