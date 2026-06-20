-- 1. Habilitar la extensión pgvector
create extension if not exists vector;

-- 2. Crear tabla para almacenar los embeddings de las propuestas
create table if not exists public.proposal_embeddings (
    id uuid primary key default gen_random_uuid(),
    proposal_id text not null,
    document text not null,
    metadata jsonb,
    embedding vector(384) -- all-MiniLM-L6-v2 produce vectores de 384 dimensiones
);

-- 3. Crear función de similitud (RPC) para buscar por RAG
create or replace function match_proposals(
  query_embedding vector(384),
  match_count int default 2
)
returns table (
  id uuid,
  proposal_id text,
  document text,
  metadata jsonb,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    pe.id,
    pe.proposal_id,
    pe.document,
    pe.metadata,
    1 - (pe.embedding <=> query_embedding) as similarity
  from proposal_embeddings pe
  order by pe.embedding <=> query_embedding
  limit match_count;
end;
$$;
