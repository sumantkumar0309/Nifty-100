import psycopg2
try:
    c = psycopg2.connect('dbname=nifty100 user=postgres password=postgres host=127.0.0.1 port=5432')
    c.close()
    print('SUCCESS')
except Exception as e:
    print(e)
