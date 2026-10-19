"""Optional local-only embeddings with bounded cosine/FAISS retrieval."""
import hashlib
import math
import os
from pathlib import Path
import threading


class SemanticIndex:
    def __init__(self,*,encoder=None,model_path=None):
        self.encoder=encoder
        self.model_path=model_path or os.environ.get('SPARK_EMBEDDING_MODEL_DIR')
        self.cache={}
        self.lock=threading.Lock()

    def _load(self):
        if self.encoder is not None:return
        if not self.model_path:
            raise ValueError('No local embedding model configured')
        path=Path(self.model_path)
        if not path.is_absolute() or not path.is_dir() or path.is_symlink():
            raise ValueError('Configured local embedding model directory is unavailable')
        from spark_host_vitals import collect_host_vitals
        available=collect_host_vitals().get('ram_available_gb')
        if available is not None and available<1.5:raise ValueError('Insufficient spare RAM for optional embeddings; using FTS5')
        from sentence_transformers import SentenceTransformer
        model=SentenceTransformer(str(path),device='cpu',local_files_only=True,trust_remote_code=False)
        self.encoder=lambda texts:model.encode(texts,batch_size=8,normalize_embeddings=True,show_progress_bar=False).tolist()

    def search(self,query,records):
        try:
            with self.lock:
                self._load()
                records=records[:1000]
                if not records:return {'available':True,'results':[],'backend':'cosine'}
                keys=[hashlib.sha256(record['body'].encode()).hexdigest() for record in records]
                missing={key:record['body'] for key,record in zip(keys,records) if key not in self.cache}
                if len(self.cache)+len(missing)>1000:self.cache.clear();missing=dict(zip(keys,[record['body'] for record in records]))
                if missing:
                    encoded=self.encoder(list(missing.values()))
                    if len(encoded)!=len(missing):raise ValueError('Invalid embedding count')
                    self.cache.update(zip(missing,encoded))
                vectors=[self.cache[key] for key in keys]
                query_vector=self.encoder([query])[0]
                dimension=len(query_vector)
                if not 1<=dimension<=4096 or any(len(vector)!=dimension for vector in vectors):raise ValueError('Invalid embedding dimensions')
                def normalize(vector):
                    if any(not isinstance(value,(int,float)) or not math.isfinite(value) for value in vector):raise ValueError('Invalid vector')
                    norm=math.sqrt(sum(value*value for value in vector))
                    if norm==0:raise ValueError('Empty vector')
                    return [value/norm for value in vector]
                query_vector=normalize(query_vector);vectors=[normalize(vector) for vector in vectors]
                backend='cosine'
                if os.environ.get('SPARK_FAISS_ENABLED')=='1':
                    import faiss
                    import numpy as np
                    index=faiss.IndexFlatIP(dimension)
                    index.add(np.asarray(vectors,dtype='float32'))
                    scores,indices=index.search(np.asarray([query_vector],dtype='float32'),min(20,len(records)))
                    ranked=[(float(score),int(position)) for score,position in zip(scores[0],indices[0])]
                    backend='faiss'
                else:
                    ranked=sorted(((sum(a*b for a,b in zip(query_vector,vector)),position) for position,vector in enumerate(vectors)),reverse=True)[:20]
                return {'available':True,'backend':backend,'results':[{**records[position],'semantic_score':score} for score,position in ranked if score>.1]}
        except Exception:
            return {'available':False,'results':[],'reason':'Local semantic model or compatible dependencies unavailable; using FTS5'}
