-- ATS check: how well an applicant tracking system can read the resume, and the final
-- score (job fit and ATS combined). Computed in Python (scoring v6); null on older rows.
alter table public.analyses
  add column if not exists ats_score smallint check (ats_score between 0 and 100),
  add column if not exists final_score smallint check (final_score between 0 and 100),
  add column if not exists potential_final_score smallint
    check (potential_final_score between 0 and 100);

alter table public.analysis_results
  add column if not exists ats jsonb;
