# Most free hosts (Render, Railway, Heroku) run one process per service.
# Deploy main.py and app.py as TWO separate services from the same repo,
# each using the matching line below as its start command.

web: uvicorn main:app --host 0.0.0.0 --port $PORT
