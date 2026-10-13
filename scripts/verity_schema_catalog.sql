-- Schema metadata only: no table rows or customer content are read.
-- Run against an isolated migrated database with a schema-owning role.
SELECT jsonb_pretty(jsonb_build_object(
  'alembic_revision', (SELECT version_num FROM public.alembic_version LIMIT 1),
  'tables', COALESCE((
    SELECT jsonb_agg(jsonb_build_object(
      'name', c.relname,
      'rls_enabled', c.relrowsecurity,
      'rls_forced', c.relforcerowsecurity,
      'columns', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'name', a.attname,
          'type', format_type(a.atttypid, a.atttypmod),
          'nullable', NOT a.attnotnull,
          'default', pg_get_expr(d.adbin, d.adrelid)
        ) ORDER BY a.attnum)
        FROM pg_attribute a
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
      ), '[]'::jsonb),
      'constraints', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'name', k.conname,
          'kind', k.contype,
          'definition', pg_get_constraintdef(k.oid, true)
        ) ORDER BY k.conname)
        FROM pg_constraint k WHERE k.conrelid = c.oid
      ), '[]'::jsonb),
      'indexes', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'name', ic.relname,
          'definition', pg_get_indexdef(i.indexrelid)
        ) ORDER BY ic.relname)
        FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid
        WHERE i.indrelid = c.oid
      ), '[]'::jsonb),
      'policies', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'name', p.polname,
          'command', p.polcmd,
          'roles', COALESCE((
            SELECT jsonb_agg(r.rolname ORDER BY r.rolname)
            FROM pg_roles r WHERE r.oid = ANY(p.polroles)
          ), '[]'::jsonb),
          'using', pg_get_expr(p.polqual, p.polrelid),
          'with_check', pg_get_expr(p.polwithcheck, p.polrelid)
        ) ORDER BY p.polname)
        FROM pg_policy p WHERE p.polrelid = c.oid
      ), '[]'::jsonb)
    ) ORDER BY c.relname)
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
  ), '[]'::jsonb)
));
