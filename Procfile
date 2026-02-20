web: gunicorn main:app --workers 2 --threads 2 --timeout 120 --bind 0.0.0.0:$PORT
worker: python main.py --mode worker
