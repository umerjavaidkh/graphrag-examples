"""Step 8 — Cross-link structured (CSV) and unstructured (PDF) data.

Replaces the manual "paste into Neo4j Browser" workflow from the README.
The LLM extracts orderId/articleId as integers from the PDFs, while LOAD CSV
imports articleId as a string, so joins silently fail until the types are
aligned and the cross-link relationships are created.
"""

import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

FIX_ARTICLE_ID_TYPE = """
MATCH (a:Article) WHERE NOT '__KGBuilder__' IN labels(a)
SET a.articleId = toInteger(a.articleId)
"""

LINK_CREDIT_NOTES_TO_ARTICLES = """
MATCH (c:CreditNote)-[:REFUND_OF_ARTICLE]->(a1:Article)
WHERE '__KGBuilder__' IN labels(a1)
MATCH (a2:Article) WHERE NOT '__KGBuilder__' IN labels(a2)
AND a2.articleId = a1.articleId
MERGE (c)-[:REFUND_OF_ARTICLE_STRUCTURED]->(a2)
"""

LINK_CREDIT_NOTES_TO_SUPPLIERS = """
MATCH (c:CreditNote)-[:REFUND_FOR_ORDER]->(o1:Order)
MATCH (o2:Order)-[:HAS_TRANSACTION]->(t:Transaction)-[:CONTAINS]->(a:Article)-[:SUPPLIED_BY]->(s:Supplier)
WHERE o1.orderId = o2.orderId
MERGE (c)-[:RETURNED_TO_SUPPLIER]->(s)
"""

VERIFY_ARTICLE_LINKS = """
MATCH (c:CreditNote)-[:REFUND_OF_ARTICLE_STRUCTURED]->(a) RETURN count(*) AS articleLinks
"""

VERIFY_SUPPLIER_LINKS = """
MATCH (c:CreditNote)-[:RETURNED_TO_SUPPLIER]->(s) RETURN count(*) AS supplierLinks
"""


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    try:
        print("Fixing Article ID type (string -> integer) ...")
        driver.execute_query(FIX_ARTICLE_ID_TYPE)

        print("Linking CreditNotes to structured Articles ...")
        driver.execute_query(LINK_CREDIT_NOTES_TO_ARTICLES)

        print("Linking CreditNotes to Suppliers via the Order chain ...")
        driver.execute_query(LINK_CREDIT_NOTES_TO_SUPPLIERS)

        article_links = driver.execute_query(VERIFY_ARTICLE_LINKS).records[0]["articleLinks"]
        supplier_links = driver.execute_query(VERIFY_SUPPLIER_LINKS).records[0]["supplierLinks"]
        print(f"  articleLinks = {article_links}")
        print(f"  supplierLinks = {supplier_links}")

        if article_links == 0 or supplier_links == 0:
            print(
                "WARNING: one or more cross-link counts is 0. "
                "Check that Steps 6 and 7 completed successfully."
            )
        else:
            print("Cross-linking complete.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
