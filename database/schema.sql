CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS porting_attempts (
    id SERIAL PRIMARY KEY,
    user_id INT,
    cuda_code_hash VARCHAR(64) UNIQUE,
    compatibility_score INT,
    predicted_performance VARCHAR(20),
    actual_performance VARCHAR(20),
    effort_hours INT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS code_patterns (
    id SERIAL PRIMARY KEY,
    pattern_hash VARCHAR(64),
    pattern_type VARCHAR(50),
    embedding VECTOR(1536),
    success_rate FLOAT
);

CREATE INDEX IF NOT EXISTS idx_code_patterns_embedding
ON code_patterns USING ivfflat (embedding vector_cosine_ops);
