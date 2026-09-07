import os, sys, re
from dotenv import load_dotenv
load_dotenv("/Users/eha/Desktop/financial-news-platform/.env", override=True)
import psycopg2
u=os.environ["DATABASE_URL"]
print("host:", re.sub(r"^.*@", "", u).split("/")[0])
conn=psycopg2.connect(u); conn.autocommit=True
cur=conn.cursor()
sql=sys.stdin.read()
for stmt in [s for s in sql.split(";\n") if s.strip()]:
    cur.execute(stmt)
    if cur.description:
        cols=[d[0] for d in cur.description]
        print("--", stmt.strip()[:100].replace("\n"," "))
        print(" | ".join(cols))
        for r in cur.fetchall(): print(" | ".join(str(x) for x in r))
    else:
        print("--", stmt.strip()[:100].replace("\n"," "), "-> rowcount", cur.rowcount)
