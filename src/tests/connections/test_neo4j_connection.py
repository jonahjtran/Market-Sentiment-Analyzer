import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

uri = os.environ["NEO4J_URI"]
username = os.environ["NEO4J_USERNAME"]
password = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(uri, auth=(username, password))

with driver.session() as session:
    result = session.run("RETURN 'AuraDB connection OK' AS message")
    print(result.single()["message"])

driver.close()
