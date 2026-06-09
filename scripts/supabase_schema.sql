-- ==============================================================================
-- Esquema de base de datos para Supabase - Agente Generador de Propuestas
-- Ejecuta este script en el SQL Editor de tu proyecto en Supabase
-- ==============================================================================

-- 1. Crear tabla de propuestas
CREATE TABLE IF NOT EXISTS public.proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prospect_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    sections_completed JSONB DEFAULT '[]'::jsonb,
    sections_content JSONB DEFAULT '{}'::jsonb,
    current_step TEXT,
    audio_url TEXT,
    brief_url TEXT,
    transcript TEXT,
    pdf_url TEXT,
    docx_url TEXT,
    amount TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Crear tabla de historial
CREATE TABLE IF NOT EXISTS public.proposal_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id UUID REFERENCES public.proposals(id) ON DELETE CASCADE,
    result TEXT,
    match_score INTEGER,
    duration TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Habilitar Row Level Security (RLS)
ALTER TABLE public.proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.proposal_history ENABLE ROW LEVEL SECURITY;

-- 4. Crear políticas para acceso desde el frontend (anon key)
-- Permitir select y leer a todo el mundo (útil para el hackathon)
CREATE POLICY "Permitir select anon en proposals" ON public.proposals FOR SELECT USING (true);
CREATE POLICY "Permitir select anon en history" ON public.proposal_history FOR SELECT USING (true);

-- (Opcional) Si quieres que el frontend también pueda insertar sin autenticación:
CREATE POLICY "Permitir insert anon en proposals" ON public.proposals FOR INSERT WITH CHECK (true);
CREATE POLICY "Permitir update anon en proposals" ON public.proposals FOR UPDATE USING (true);

-- ==============================================================================
-- INSTRUCCIONES PARA EL STORAGE (BUCKET)
-- ==============================================================================
-- Asegúrate de crear manualmente en el Dashboard de Supabase:
-- 1. Ve a "Storage"
-- 2. Crea un nuevo bucket llamado "proposal-files"
-- 3. Asegúrate de marcarlo como "Public"
