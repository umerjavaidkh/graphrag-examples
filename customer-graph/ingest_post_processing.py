import os

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI

load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Connect to the Neo4j database
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

# create text properties for product
print("Formatting Product Text")
driver.execute_query('''
MATCH(p:Product)
OPTIONAL MATCH(p)-[:PART_OF]->(c:ProductCategory)
OPTIONAL MATCH(p)-[:PART_OF]->(t:ProductType)
SET p.text = '##Product\n' +
    'Name: ' + coalesce(p.name,'') + '\n' +
    'Type: ' + coalesce(t.name, '') + '\n' +
    'Category: ' + coalesce(c.name, '') + '\n' +
    'Description: ' + coalesce(p.description, ''),
    p.url = 'https://representative-domain/product/' + p.productCode
RETURN count(p) AS propertySetCount
''')

# create text embeddings for products — batched for speed
print("Creating Product Text Embeddings")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

with driver.session(database="neo4j") as session:
    products = session.run(
        "MATCH (n:Product) WHERE size(n.description) <> 0 RETURN elementId(n) AS id, n.text AS text"
    ).data()

    print(f"  Found {len(products)} products to embed")

    BATCH_SIZE = 500
    for i in range(0, len(products), BATCH_SIZE):
        batch = products[i:i + BATCH_SIZE]
        texts = [p["text"] for p in batch]

        response = client.embeddings.create(
            input=texts,
            model="text-embedding-ada-002"
        )

        for j, item in enumerate(response.data):
            session.run(
                "MATCH (n) WHERE elementId(n) = $id CALL db.create.setNodeVectorProperty(n, 'textEmbedding', $vector)",
                id=batch[j]["id"], vector=item.embedding
            )

        print(f"  Embedded {min(i + BATCH_SIZE, len(products))}/{len(products)} products")

# create vector index on text embeddings
print("Creating Product Vector Index")
driver.execute_query('''
CREATE VECTOR INDEX product_text_embeddings IF NOT EXISTS FOR (n:Product) ON (n.textEmbedding)
OPTIONS {indexConfig: {
 `vector.dimensions`: toInteger($dimension),
 `vector.similarity_function`: 'cosine'
}}
''', dimension=1536)

# wait for index to come online
print("Waiting for vector index to come online...")
driver.execute_query('CALL db.awaitIndex("product_text_embeddings", 300)')

print("Done.")
driver.close()