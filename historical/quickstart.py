import os
import time
import pandas as pd
import duckdb as ddb
from neo4j import GraphDatabase
import redis

MEMGRAPH_URI = os.getenv("MEMGRAPH_URI", "bolt://memgraph:7687")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


def make_data(n=10000):
    df = pd.DataFrame({
        "sender": [f"A{i%500}" for i in range(n)],
        "receiver": [f"B{i%700}" for i in range(n)],
        "amount": (pd.Series(range(n)) % 97 + 1) * 1.0,
        "ts": pd.Timestamp("2024-01-01") + pd.to_timedelta(pd.Series(range(n)), unit="m"),
    })
    return df


def run_duckdb(df):
    con = ddb.connect(database=":memory:")
    con.register("tx", df)
    q = """
    select sender, receiver, count(*) as cnt, avg(amount) as avg_amt
    from tx
    group by sender, receiver
    order by cnt desc
    limit 5
    """
    top = con.execute(q).fetchdf()
    print("DuckDB top pairs:\n", top)
    return top


def push_to_memgraph(pairs):
    driver = GraphDatabase.driver(MEMGRAPH_URI, auth=None)
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        # create nodes
        session.run("UNWIND $nodes as id MERGE (:Entity {id:id})", parameters={"nodes": list(set(pairs["sender"]).union(set(pairs["receiver"])))})
        # create edges with weight
        rels = [
            {"s": row.sender, "r": row.receiver, "w": int(row.cnt)}
            for row in pairs.itertuples(index=False)
        ]
        session.run(
            """
            UNWIND $rels as rel
            MATCH (a:Entity {id: rel.s}), (b:Entity {id: rel.r})
            MERGE (a)-[e:TX]->(b)
            SET e.weight = rel.w
            """,
            parameters={"rels": rels},
        )
        counts = session.run("""
            MATCH (n:Entity) WITH count(n) as nodes
            MATCH ()-[e:TX]->() WITH nodes, count(e) as edges
            RETURN nodes, edges
        """).single()
        print(f"Memgraph graph: nodes={counts['nodes']} edges={counts['edges']}")
    driver.close()


def redis_demo():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    pong = r.ping()
    print("Redis ping:", pong)
    key = "feature:user:A1:tx_count"
    r.set(key, 42, ex=60)
    val = r.get(key)
    print(f"Redis get {key} ->", val)


def main():
    df = make_data(20000)
    pairs = run_duckdb(df)
    push_to_memgraph(pairs)
    redis_demo()
    print("Quickstart completed.")


if __name__ == "__main__":
    main()
