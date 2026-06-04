"""Step 7 — Import structured CSV data via LOAD CSV.

Replaces the manual "paste into Neo4j Browser" workflow from the README.
The CSVs are read from Neo4j's import directory (file:///...). When running
via docker compose the `data/` folder is mounted into that directory, so no
`docker cp` is needed. For a manual run, copy the CSVs into the container's
import dir first (see README Step 7a) or rely on the compose mount.
"""

import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Each query mirrors a numbered block in README Step 7b and must run in order:
# suppliers and products first, then articles (which link to both), then
# customers, then orders/transactions (which link customers and articles).
QUERIES = [
    (
        "Suppliers",
        """
        LOAD CSV WITH HEADERS FROM 'file:///suppliers.csv' AS row
        MERGE (s:Supplier {supplierId: row.supplierId})
        SET s.name = row.supplierName,
            s.address = row.supplierAddress;
        """,
    ),
    (
        "Products",
        """
        LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS row
        MERGE (p:Product {productCode: row.productCode})
        SET p.name = row.prodName,
            p.productTypeNo = row.productTypeNo,
            p.productTypeName = row.productTypeName,
            p.productGroupName = row.productGroupName,
            p.garmentGroupNo = row.garmentGroupNo,
            p.garmentGroupName = row.garmentGroupName,
            p.description = row.detailDesc;
        """,
    ),
    (
        "Articles",
        """
        LOAD CSV WITH HEADERS FROM 'file:///articles.csv' AS row
        MERGE (a:Article {articleId: row.articleId})
        SET a.productCode = row.productCode,
            a.name = row.prodName,
            a.productTypeName = row.productTypeName,
            a.graphicalAppearanceNo = row.graphicalAppearanceNo,
            a.graphicalAppearanceName = row.graphicalAppearanceName,
            a.colourGroupCode = row.colourGroupCode,
            a.colourGroupName = row.colourGroupName
        WITH a, row
        MATCH (p:Product {productCode: row.productCode})
        MERGE (a)-[:VARIANT_OF]->(p)
        WITH a, row
        MATCH (s:Supplier {supplierId: row.supplierId})
        MERGE (a)-[:SUPPLIED_BY]->(s);
        """,
    ),
    (
        "Customers",
        """
        LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
        MERGE (c:Customer {customerId: row.customerId})
        SET c.firstName = row.fn,
            c.active = row.active,
            c.clubMemberStatus = row.clubMemberStatus,
            c.fashionNewsFrequency = row.fashionNewsFrequency,
            c.age = toInteger(row.age),
            c.postalCode = row.postalCode;
        """,
    ),
    (
        # toInteger(row.orderId) is critical so these Orders link with the
        # integer orderIds extracted from the PDFs in the cross-link step.
        "Orders, Transactions and Relationships",
        """
        LOAD CSV WITH HEADERS FROM 'file:///order-details.csv' AS row
        MERGE (o:Order {orderId: toInteger(row.orderId)})
        WITH o, row
        MERGE (t:Transaction {txId: row.txId})
        SET t.date = row.tDat,
            t.price = toFloat(row.price),
            t.salesChannelId = row.salesChannelId
        MERGE (o)-[:HAS_TRANSACTION]->(t)
        WITH o, t, row
        MATCH (c:Customer {customerId: row.customerId})
        MERGE (c)-[:PLACED]->(o)
        WITH o, t, row
        MATCH (a:Article {articleId: row.articleId})
        MERGE (t)-[:CONTAINS]->(a);
        """,
    ),
]


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    try:
        for name, query in QUERIES:
            print(f"Loading {name} ...")
            driver.execute_query(query)
        print("Structured CSV import complete.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
