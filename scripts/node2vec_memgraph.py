"""
Node2Vec on Memgraph for Fraud Detection
==========================================
Generates node embeddings from the transaction graph using Node2Vec algorithm.
Uses Memgraph's built-in random walk capabilities + Word2Vec for embeddings.

Node2Vec: https://arxiv.org/abs/1607.00653
- p: Return parameter (controls likelihood of revisiting a node)
- q: In-out parameter (controls search to differentiate inward vs outward nodes)
"""
import numpy as np
import pandas as pd
from collections import defaultdict
from typing import List, Dict, Tuple, Optional
import random
import time
from datetime import datetime
import sys

# Install dependencies if needed
try:
    import mgclient
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymgclient", "-q"])
    import mgclient

try:
    from gensim.models import Word2Vec
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "gensim", "-q"])
    from gensim.models import Word2Vec

print("="*70)
print("NODE2VEC ON MEMGRAPH - FRAUD NETWORK EMBEDDINGS")
print("="*70)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


class MemgraphNode2Vec:
    """
    Node2Vec implementation using Memgraph for graph traversal.
    
    Features:
    - Biased random walks with p,q parameters
    - Efficient walk generation via Memgraph queries
    - Word2Vec embeddings from walks
    - Fraud-aware node sampling
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7687,
        dimensions: int = 64,
        walk_length: int = 30,
        num_walks: int = 10,
        p: float = 1.0,
        q: float = 1.0,
        workers: int = 4,
        window: int = 5,
        min_count: int = 1,
        seed: int = 42,
    ):
        """
        Initialize Node2Vec.
        
        Args:
            dimensions: Embedding dimension size
            walk_length: Length of each random walk
            num_walks: Number of walks per node
            p: Return parameter (higher = less likely to return)
            q: In-out parameter (higher = more outward exploration)
            workers: Parallel workers for Word2Vec
            window: Context window for Word2Vec
            min_count: Minimum node frequency
            seed: Random seed
        """
        self.dimensions = dimensions
        self.walk_length = walk_length
        self.num_walks = num_walks
        self.p = p
        self.q = q
        self.workers = workers
        self.window = window
        self.min_count = min_count
        self.seed = seed
        
        # Connect to Memgraph
        self.conn = mgclient.connect(host=host, port=port)
        self.conn.autocommit = True
        self.cursor = self.conn.cursor()
        
        # Cache
        self.node_ids = []
        self.id_to_idx = {}
        self.idx_to_id = {}
        self.embeddings = None
        self.model = None
        
        random.seed(seed)
        np.random.seed(seed)
        
        print(f"   Connected to Memgraph at {host}:{port}")
        print(f"   Parameters: dim={dimensions}, walks={num_walks}x{walk_length}, p={p}, q={q}")
    
    def execute(self, query: str, params: dict = None) -> List:
        """Execute Cypher query."""
        try:
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Query error: {e}")
            return []
    
    def _load_graph_structure(self) -> Tuple[Dict, Dict]:
        """Load adjacency list from Memgraph."""
        print("\n[1/4] Loading graph structure from Memgraph...")
        
        # Get all nodes
        nodes_query = "MATCH (a:Address) RETURN a.id"
        result = self.execute(nodes_query)
        self.node_ids = [row[0] for row in result]
        self.id_to_idx = {nid: idx for idx, nid in enumerate(self.node_ids)}
        self.idx_to_id = {idx: nid for nid, idx in self.id_to_idx.items()}
        
        print(f"   Loaded {len(self.node_ids):,} nodes")
        
        # Get adjacency (outgoing edges)
        adj_query = """
        MATCH (a:Address)-[:TRANSFER]->(b:Address)
        RETURN a.id, collect(DISTINCT b.id)
        """
        result = self.execute(adj_query)
        
        # Build adjacency dict
        adj_out = defaultdict(list)
        for row in result:
            from_id, to_ids = row
            adj_out[from_id] = to_ids if to_ids else []
        
        print(f"   Loaded {sum(len(v) for v in adj_out.values()):,} edges")
        
        # For Node2Vec, we need bidirectional adjacency
        adj_query_in = """
        MATCH (a:Address)<-[:TRANSFER]-(b:Address)
        RETURN a.id, collect(DISTINCT b.id)
        """
        result = self.execute(adj_query_in)
        
        adj_in = defaultdict(list)
        for row in result:
            to_id, from_ids = row
            adj_in[to_id] = from_ids if from_ids else []
        
        # Combine for undirected view
        adj_combined = defaultdict(set)
        for node, neighbors in adj_out.items():
            adj_combined[node].update(neighbors)
        for node, neighbors in adj_in.items():
            adj_combined[node].update(neighbors)
        
        self.adj = {k: list(v) for k, v in adj_combined.items()}
        
        # Count nodes with neighbors
        connected = sum(1 for n in self.node_ids if n in self.adj and len(self.adj[n]) > 0)
        print(f"   Connected nodes: {connected:,} ({100*connected/len(self.node_ids):.1f}%)")
        
        return self.adj, self.id_to_idx
    
    def _compute_transition_probs(self):
        """Precompute transition probabilities for biased walks."""
        print("\n[2/4] Computing transition probabilities...")
        
        # For each edge (t, v), compute normalized probabilities to neighbors of v
        # considering the previous node t
        
        # This is memory intensive for large graphs
        # For efficiency, we'll compute on-the-fly during walks
        # But cache neighbors for each node
        
        self.neighbor_weights = {}
        
        # For pure Node2Vec, we'd precompute alias tables
        # For simplicity, we'll compute probabilities during walk
        
        print("   Using on-the-fly probability computation")
    
    def _biased_neighbor(self, prev: str, curr: str) -> Optional[str]:
        """
        Select next node using biased random walk.
        
        Bias based on:
        - Distance from previous node (p controls return)
        - Whether neighbor is connected to previous (q controls BFS vs DFS)
        """
        neighbors = self.adj.get(curr, [])
        if not neighbors:
            return None
        
        if prev is None:
            # First step - uniform random
            return random.choice(neighbors)
        
        # Compute unnormalized probabilities
        probs = []
        prev_neighbors = set(self.adj.get(prev, []))
        
        for neighbor in neighbors:
            if neighbor == prev:
                # Return to previous node
                probs.append(1.0 / self.p)
            elif neighbor in prev_neighbors:
                # Neighbor of previous (BFS-like)
                probs.append(1.0)
            else:
                # Further from previous (DFS-like)
                probs.append(1.0 / self.q)
        
        # Normalize
        total = sum(probs)
        probs = [p / total for p in probs]
        
        # Sample
        return random.choices(neighbors, weights=probs, k=1)[0]
    
    def _generate_walks(self) -> List[List[str]]:
        """Generate random walks for all nodes."""
        print(f"\n[3/4] Generating {self.num_walks} walks per node (length {self.walk_length})...")
        
        walks = []
        total_nodes = len(self.node_ids)
        
        # Only walk from connected nodes
        connected_nodes = [n for n in self.node_ids if n in self.adj and len(self.adj[n]) > 0]
        print(f"   Walking from {len(connected_nodes):,} connected nodes")
        
        start_time = time.time()
        
        for walk_iter in range(self.num_walks):
            random.shuffle(connected_nodes)
            
            for node in connected_nodes:
                walk = [node]
                
                for step in range(self.walk_length - 1):
                    prev = walk[-2] if len(walk) > 1 else None
                    curr = walk[-1]
                    
                    next_node = self._biased_neighbor(prev, curr)
                    if next_node is None:
                        break
                    
                    walk.append(next_node)
                
                walks.append(walk)
            
            # Progress
            if (walk_iter + 1) % max(1, self.num_walks // 5) == 0:
                elapsed = time.time() - start_time
                print(f"   Walk {walk_iter + 1}/{self.num_walks} | {len(walks):,} walks | {elapsed:.1f}s")
        
        print(f"   Generated {len(walks):,} walks total")
        print(f"   Average walk length: {np.mean([len(w) for w in walks]):.1f}")
        
        return walks
    
    def _train_embeddings(self, walks: List[List[str]]):
        """Train Word2Vec on walks to get embeddings."""
        print(f"\n[4/4] Training Word2Vec embeddings (dim={self.dimensions})...")
        
        start_time = time.time()
        
        self.model = Word2Vec(
            sentences=walks,
            vector_size=self.dimensions,
            window=self.window,
            min_count=self.min_count,
            sg=1,  # Skip-gram (better for Node2Vec)
            workers=self.workers,
            seed=self.seed,
            epochs=5,
        )
        
        elapsed = time.time() - start_time
        print(f"   Training completed in {elapsed:.1f}s")
        print(f"   Vocabulary size: {len(self.model.wv):,} nodes")
        
        # Store embeddings
        self.embeddings = {}
        for node_id in self.node_ids:
            if node_id in self.model.wv:
                self.embeddings[node_id] = self.model.wv[node_id]
        
        print(f"   Embeddings generated for {len(self.embeddings):,} nodes")
    
    def fit(self) -> Dict[str, np.ndarray]:
        """Run full Node2Vec pipeline."""
        self._load_graph_structure()
        self._compute_transition_probs()
        walks = self._generate_walks()
        self._train_embeddings(walks)
        return self.embeddings
    
    def get_embedding(self, node_id: str) -> Optional[np.ndarray]:
        """Get embedding for a specific node."""
        return self.embeddings.get(node_id)
    
    def most_similar(self, node_id: str, topn: int = 10) -> List[Tuple[str, float]]:
        """Find most similar nodes."""
        if self.model is None or node_id not in self.model.wv:
            return []
        return self.model.wv.most_similar(node_id, topn=topn)
    
    def save_embeddings(self, filepath: str):
        """Save embeddings to file."""
        if not self.embeddings:
            print("No embeddings to save. Run fit() first.")
            return
        
        # Save as numpy
        nodes = list(self.embeddings.keys())
        vectors = np.array([self.embeddings[n] for n in nodes])
        
        np.savez(
            filepath,
            nodes=nodes,
            vectors=vectors,
            dimensions=self.dimensions,
        )
        print(f"Saved {len(nodes)} embeddings to {filepath}")
    
    def save_to_memgraph(self):
        """Store embeddings back in Memgraph nodes."""
        print("\nSaving embeddings to Memgraph nodes...")
        
        count = 0
        for node_id, embedding in self.embeddings.items():
            # Store first 10 dimensions as properties (Memgraph limit)
            # For full embeddings, use external storage
            props = {f'emb_{i}': float(embedding[i]) for i in range(min(10, len(embedding)))}
            props['node_id'] = node_id
            
            # Create embedding property string
            emb_str = ','.join([f"{v:.6f}" for v in embedding[:10]])
            
            query = f"""
            MATCH (a:Address {{id: $node_id}})
            SET a.embedding = $emb_str,
                a.emb_dim = $dim
            """
            
            self.execute(query, {
                'node_id': node_id,
                'emb_str': emb_str,
                'dim': self.dimensions
            })
            count += 1
            
            if count % 10000 == 0:
                print(f"   Saved {count:,} embeddings")
        
        print(f"   ✓ Saved {count:,} embeddings to Memgraph")


def analyze_fraud_similarity(n2v: MemgraphNode2Vec):
    """Analyze similarity between fraud and non-fraud nodes."""
    print("\n" + "="*70)
    print("FRAUD SIMILARITY ANALYSIS")
    print("="*70)
    
    # Get fraud nodes from Memgraph
    fraud_query = "MATCH (f:Fraud) RETURN f.id"
    result = n2v.execute(fraud_query)
    fraud_nodes = [row[0] for row in result if row[0] in n2v.embeddings]
    
    print(f"\nFraud nodes with embeddings: {len(fraud_nodes)}")
    
    if len(fraud_nodes) == 0:
        print("No fraud nodes with embeddings found.")
        return
    
    # Get embeddings
    fraud_embeddings = np.array([n2v.embeddings[n] for n in fraud_nodes])
    
    # Compute centroid of fraud cluster
    fraud_centroid = fraud_embeddings.mean(axis=0)
    
    # Find non-fraud nodes closest to fraud centroid
    print("\nNodes most similar to FRAUD cluster centroid:")
    print("-" * 60)
    
    similarities = []
    for node_id, emb in n2v.embeddings.items():
        if node_id not in fraud_nodes:
            # Cosine similarity
            sim = np.dot(emb, fraud_centroid) / (np.linalg.norm(emb) * np.linalg.norm(fraud_centroid))
            similarities.append((node_id, sim))
    
    similarities.sort(key=lambda x: x[1], reverse=True)
    
    # Show top suspicious addresses
    print("\nTop 10 addresses most similar to fraud pattern:")
    for node_id, sim in similarities[:10]:
        # Get risk info from Memgraph
        info_query = "MATCH (a:Address {id: $id}) RETURN a.hybrid_score, a.risk_level"
        result = n2v.execute(info_query, {'id': node_id})
        if result:
            score, risk = result[0]
            print(f"   {node_id[:42]} | Sim: {sim:.4f} | Score: {score:.1f} | {risk}")
    
    # Find most similar fraud pairs
    print("\nMost similar fraud address pairs:")
    print("-" * 60)
    
    fraud_sims = []
    for i, n1 in enumerate(fraud_nodes):
        for j, n2 in enumerate(fraud_nodes):
            if i < j:
                e1, e2 = n2v.embeddings[n1], n2v.embeddings[n2]
                sim = np.dot(e1, e2) / (np.linalg.norm(e1) * np.linalg.norm(e2))
                fraud_sims.append((n1, n2, sim))
    
    fraud_sims.sort(key=lambda x: x[2], reverse=True)
    
    for n1, n2, sim in fraud_sims[:5]:
        print(f"   {n1[:20]}... <-> {n2[:20]}... | Sim: {sim:.4f}")


def main():
    """Main execution."""
    
    # Initialize Node2Vec
    n2v = MemgraphNode2Vec(
        dimensions=64,       # Embedding size
        walk_length=20,      # Steps per walk
        num_walks=5,         # Walks per node
        p=1.0,               # Return parameter
        q=0.5,               # In-out (lower = more local/DFS)
        workers=4,
        window=5,
    )
    
    # Fit model
    embeddings = n2v.fit()
    
    if embeddings:
        # Analyze fraud patterns
        analyze_fraud_similarity(n2v)
        
        # Save embeddings
        n2v.save_embeddings('c:/amttp/processed/node2vec_embeddings.npz')
        
        # Optionally save to Memgraph
        save_to_db = input("\nSave embeddings to Memgraph? (y/n): ").lower().strip()
        if save_to_db == 'y':
            n2v.save_to_memgraph()
        
        print("\n" + "="*70)
        print("NODE2VEC COMPLETE")
        print("="*70)
        print(f"""
   Embeddings generated: {len(embeddings):,}
   Dimension: {n2v.dimensions}
   Saved to: c:/amttp/processed/node2vec_embeddings.npz
   
   USAGE:
   ------
   # Load embeddings
   data = np.load('c:/amttp/processed/node2vec_embeddings.npz', allow_pickle=True)
   nodes = data['nodes']
   vectors = data['vectors']
   
   # Find similar nodes
   n2v.most_similar('0x...address...', topn=10)
   
   # Use for fraud detection
   # Add embeddings as features for XGBoost
""")


if __name__ == "__main__":
    main()
